"""Documented observations: the platforms and technological features a court record names.

    python -m state_machines.observations.observe <case_id> [--text-root DIR] [--bundle resolved.json] [--out FILE]

Three levels of evidence are kept apart (state_machines/README.md):

1. **Observation** (this module). A listed service is named, or a codebook feature phrase is
   stated, in a sentence of the record. Found by rule on every page except docket sheets (which
   record court business, such as a hearing held by video), independent of any model
   and of whether an act was coded there. Each observation cites its sentence (document, page,
   character span, hashes) and carries the document's legal standing. It says the record
   *mentions* the platform or feature. It does not say anyone used it.
2. **Act** (state_machines/coding). What both coders agree the record states someone did.
3. **Supported relationship** (``relate``). An observation is tied to an act only when the
   observation lies in the act's own cited sentence *and* that sentence states the act was done
   by means of it ("through the Kitebox application", "used the disappearing-message feature
   to ..."). Sharing a case, a page, a sentence or a date is never enough.

Dates stated in an observation's sentence are kept as ``dates_in_sentence``: what the sentence
mentions, with no claim about what the date refers to (the act, an account, the investigation,
the filing). They never enter a timeline.

Nothing here is free text: platform names come from ``enrich.PLATFORMS``, feature terms from
``FEATURES`` below, and everything else is a code, an offset, a date bound or a hash.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V
from state_machines.coding import enrich as N
from state_machines.coding.coder import _ABBREV, pages_of

RULE_VERSION = "observe-1.3.0"
SCHEMA_VERSION = "observations-1.1.0"

# Feature phrases per affordance class: the codebook's list, the same one the coders' level C uses (rule B0).
FEATURES: Dict[str, List[str]] = N.FEATURES


def _breakable(text: str) -> str:
    """``text`` as a pattern that also matches where the page breaks a word across a line ("Mes- senger")."""
    out = []
    for prev, ch in zip(" " + text, text):
        if ch == "-":
            out.append(r"-\s?")
        elif ch == " ":
            out.append(r"\s")
        else:
            out.append((r"(?:-\s)?" if prev.isalnum() and ch.isalnum() else "") + re.escape(ch))
    return "".join(out)


def _same(found: str, listed: str) -> bool:
    return re.sub(r"-\s", "", found).lower() == listed.lower() or found.lower() == listed.lower()


_FEATURE_PATTERNS = [(cls, ph, re.compile(r"(?<![A-Za-z0-9])" + _breakable(ph) + r"(?![A-Za-z0-9])", 0 if ph in ("Tor", "VPN") else re.I))
                     for cls, phrases in FEATURES.items() for ph in sorted(phrases, key=len, reverse=True)]

# Service names that are also ordinary words: counted only with a service word beside them.
AMBIGUOUS = {"Line", "Signal", "Session", "Element", "Matrix", "Monkey", "Mega", "Whisper", "Tagged", "Hoop", "Steam", "Vine", "Ares",
             "Tox", "Gab", "Amino", "Outlook", "Zoom", "Twitch", "Messenger", "Yahoo", "Discord", "Wizz", "Parler", "Tinder", "Bumble"}
_SERVICE_AFTER = re.compile(r"^[\s-]+(?:app|apps|application|applications|account|accounts|messenger|platform|chat|chats|group|groups|"
                            r"channel|channels|server|servers|profile|profiles|username|user|users|website|service|message|messages|"
                            r"messaging|link|links|folder|folders|call|calls|video|videos)\b", re.I)
_SERVICE_BEFORE = re.compile(r"\b(?:on|via|using|through|over|onto|into|from|with)\s+(?:(?:the|a|an|his|her|their|its)\s+)?$", re.I)
# Two listed spellings of one service are one platform.
ALIASES = {"Kik Messenger": "Kik", "Text Now": "TextNow", "CashApp": "Cash App", "Play Station": "PlayStation", "Xbox Live": "Xbox",
           "Yahoo Messenger": "Yahoo", "Google Hangouts": "Hangouts"}
# A bare "Messenger" is not observed: it follows other services' names ("Signal Messenger") as often as it names one.
_NAMES = sorted((N.PLATFORMS | N.FICTIONAL_PLATFORMS) - {"Messenger"}, key=len, reverse=True)
_NAME_PATTERNS = [(name, re.compile(r"(?<![A-Za-z0-9])(?:" + _breakable(name) + ("" if name in AMBIGUOUS else "|" + _breakable(name.upper()))
                                    + r")(?![A-Za-z0-9])")) for name in _NAMES]

# A service the record refers to by a placeholder instead of its name ("Website A"). The record says a
# service exists and withholds which one, so it is observed under the record's own label, inside the case
# only: "Website A" in two cases is two services. Nothing follows from the withholding itself: it is not
# evidence of anonymity, of any feature, or of use. Only "Website" followed by one capital letter or a
# number is taken (the one form the 30 real cases hold); the letter I is left out, because "the Website I
# described" is far more common than a ninth placeholder.
_WITHHELD = re.compile(r"(?<![A-Za-z0-9])(?:Web(?:-\s)?site|WEBSITE)\s(?P<k>[A-HJ-Z]|\d{1,2})(?![A-Za-z0-9-])")
WITHHELD_SUFFIX = " (name withheld)"
_LABEL_END = re.compile(_WITHHELD.pattern + r"[.;!?]$")


def withheld_in(sentence: str) -> List[Tuple[str, int, int]]:
    """Placeholder labels the sentence uses for a service: (label, start, end), first use of each."""
    out: Dict[str, Tuple[str, int, int]] = {}
    for m in _WITHHELD.finditer(sentence):
        out.setdefault("Website " + m.group("k"), ("Website " + m.group("k"), m.start(), m.end()))
    return sorted(out.values(), key=lambda t: t[1])


# A generic description of an online service with no name and no label ("a social media application").
# It is kept as what it is: a cited phrase from a closed grammar. It is not a platform, carries no
# affordance class, and is never tied to an act. Qualifiers that would themselves claim a capability
# ("encrypted", "anonymous", "dark web") are not in the grammar; a bare "website", "application" or
# "social media" names nothing and is not taken.
_PLACE = r"(?:online|internet-based|internet|web-based|mobile)"
_QUAL = (r"(?:social[-\s]media|social[-\s]networking|instant[-\s]messaging|messaging|video[-\s]chat|chat|"
         r"peer(?:-\s?|\s)to(?:-\s?|\s)peer(?:\sfile(?:-\s?|\s)sharing)?|(?:file|photo|image|video)(?:-\s?|\s)sharing|"
         r"(?:cloud|file)[-\s]storage|dating|gaming|live(?:-\s?|\s)?streaming)")
_HEAD = r"(?:applications?|apps?|websites?|sites?|platforms?|services?|programs?|networks?|software|forums?)"
SERVICE = re.compile(r"(?<![A-Za-z0-9-])(?:(?:" + _PLACE + r"\s)?(?:" + _QUAL + r"\s" + _HEAD + r"|chat\s?rooms?|social[-\s]networks?)|"
                     + _PLACE + r"\sforums?|(?:online|internet|electronic)\s(?:bulletin|message)\sboards?)(?![A-Za-z0-9-])", re.I)
_SPELLING = [(r"-\s", "-"), (r"\bpeer[-\s]to[-\s]peer\b", "peer-to-peer"), (r"\b(file|photo|image|video)[-\s]sharing\b", r"\1-sharing"),
             (r"\bsocial[-\s]media\b", "social media"), (r"\bsocial[-\s]network(ing)?\b", r"social network\1"),
             (r"\binstant[-\s]messaging\b", "instant messaging"), (r"\bvideo[-\s]chat\b", "video chat"),
             (r"\b(cloud|file)[-\s]storage\b", r"\1 storage"), (r"\blive[-\s]?streaming\b", "live-streaming"), (r"\bchatroom", "chat room"),
             (r"(application|app|website|site|platform|service|program|network|forum|room|board)s$", r"\1")]
_OWN_NAME_BEFORE = re.compile(r"(?:'s)?[\s,(\"]*(?:(?:a|an|the)\s)?$", re.I)          # "the Kik messaging application"
_OWN_NAME_AFTER = re.compile(r"^[\s,(\"]*(?:(?:called|named|known as)\s)?[\"(]?$", re.I)   # "a messaging app called Kik"


def service_term(found: str) -> str:
    """The canonical spelling of a matched description: lower case, one spelling per phrase, singular."""
    t = " ".join(found.lower().split())
    for pat, to in _SPELLING:
        t = re.sub(pat, to, t)
    return t


def descriptions_in(sentence: str, names: List[Tuple[int, int]]) -> List[Tuple[str, int, int]]:
    """Generic service descriptions the sentence holds: (canonical term, start, end), first use of each.
    One that overlaps or sits right beside a named or withheld service is that service's own descriptor
    ("the Kik messaging application") and is not taken."""
    out: Dict[str, Tuple[str, int, int]] = {}
    for m in SERVICE.finditer(sentence):
        if any(m.start() < e and s < m.end() for s, e in names):
            continue
        if any((e <= m.start() and _OWN_NAME_BEFORE.fullmatch(sentence[e:m.start()])) or
               (m.end() <= s and _OWN_NAME_AFTER.fullmatch(sentence[m.end():s])) for s, e in names):
            continue
        out.setdefault(service_term(m.group(0)), (service_term(m.group(0)), m.start(), m.end()))
    return sorted(out.values(), key=lambda t: t[1])


def listed_service_term(o: dict) -> bool:
    """A service description holds only a canonical phrase of the closed grammar."""
    v = o.get("service_term") or ""
    return bool(SERVICE.fullmatch(v)) and service_term(v) == v


def listed_platform(o: dict) -> bool:
    """A platform observation holds only a listed service name, or a placeholder label of the fixed form."""
    if "withheld" in o:
        return o["withheld"] is True and bool(re.fullmatch(r"Website (?:[A-HJ-Z]|\d{1,2})", o["named_as"])) and o["platform"] == o["named_as"] + WITHHELD_SUFFIX
    return N.known_platform(o["named_as"]) == o["named_as"] and ALIASES.get(o["named_as"], o["named_as"]) == o["platform"]


# Level 3: the sentence states the act was done by means of the platform or feature. The cue and
# the term must stand together in one clause; that clause must not be someone else's doing or a
# denial; and "on" or "to" count only after a verb of the offender's own conduct.
_DET = r"(?i:(?:the|a|an|his|her|their|its)\s+)?"
_CONDUCT = (r"(?i:contact|messag|wrote|write|writing|chat|communicat|talk|spoke|speak|sent|send|post|shar|upload|distribut|met|meet|"
            r"text|call|ask|request|told|tell|threaten|solicit|found|find|search|advertis|stream|record|receiv|stor|sav|kept|keep|"
            r"exchang|trad|creat|open|join|ran|operat|administ|convers|correspond|engag|befriend|approach|initiat|began|start|"
            r"direct|instruct|demand|offer|paid|pay|entic|persuad|coerc|groom|view|watch|download|access|publish|maintain)\w*")
_PLATFORM_CUES = [
    ("Moved_To", r"\b(?P<cue>(?i:continu|mov|switch|migrat|transition|shift)\w*)\b[^.;,]{{0,80}}?\b(?i:to|on|onto)\s+" + _DET + r"{name}(?![A-Za-z0-9])"),
    ("Carried_Out_Through", r"\b(?P<cue>(?i:through|via|using|used|uses|use|over|by means of|utilized|utilizing))\s+" + _DET + r"{name}(?![A-Za-z0-9])"),
    ("Carried_Out_Through", r"\b" + _CONDUCT + r"\b[^.;,]{{0,70}}?\b(?P<cue>(?i:on))\s+" + _DET + r"{name}(?![A-Za-z0-9])"),
    ("Carried_Out_Through", r"\b(?i:upload|post|sav|transfer|back)\w*\b[^.;,]{{0,70}}?\b(?P<cue>(?i:to|onto))\s+" + _DET + r"{name}(?![A-Za-z0-9])"),
    ("Carried_Out_Through", r"\b(?P<cue>(?i:in))\s+(?i:a|an|the)\s+{name}\s+(?i:group|chat|application|app|channel|server|account)\b"),
]
_FEATURE_MEANS = (r"\b(?P<cue>through|via|using|used|uses|by means of|with|utilized|utilizing|enabled|activated|turned on|"
                  r"created|creating|made|making|opened|set up|registered|published|posted|sent|shared|joined|ran|operated|"
                  r"administered|maintained|installed)\s+(?:[\w'-]+\s+){{0,5}}?{term}(?![A-Za-z0-9])")
_CLAUSE_BREAK = re.compile(r"[,;]\s+(?:and|but|while|when|after|before|because|which|who|so)\b|;\s+|\s(?:and then|after|before|when|while|because)\s", re.I)
_LEAD = r"^\s*(?:and\s+|but\s+|then\s+|later\s+|after\s+|before\s+|when\s+|while\s+|because\s+|which\s+|who\s+|so\s+)*"
# a clause whose subject is a third party is never the offender's act ("..., and agents served a warrant on Kitebox")
_THIRD_PARTY = (r"(?:her\s+\w+|his\s+(?:mother|father|parents?)|(?:the\s+)?(?:mother|father|parents?|agents?|officers?|detectives?|"
                r"investigators?|police|law enforcement|government|court|platform|company)\b|an?\s+(?:agent|officer)|NCMEC|FBI|HSI)")
# a platform carries both sides of a conversation, so a clause about the victim ("when Minor Victim 1 wrote back via Kitebox")
# can still state the means of the offender's act; a feature someone else used ("after she used a fake name") cannot
_OTHER_PARTY = (r"(?:she|they|(?:the\s+)?(?:victim|minor)\b|Minor Victim|MV-?\d|Victim\s+\w|Jane Doe|John Doe|an?\s+undercover|the undercover)")
_OTHER_SUBJECT = {"platform": re.compile(_LEAD + _THIRD_PARTY, re.I), "feature": re.compile(_LEAD + "(?:" + _THIRD_PARTY + "|" + _OTHER_PARTY + ")", re.I)}
_NEGATED = re.compile(r"\b(?:not|never|no|without|denied|denies|deny|declined|refused)\b", re.I)


def _own_clause(sentence: str, at: int, kind: str = "feature") -> Optional[Tuple[int, str]]:
    """The clause holding offset ``at``, up to it: (start, text). None when that clause is not the
    opening one and its subject cannot be doing the offender's act ("..., and agents served ...")."""
    start = 0
    for m in _CLAUSE_BREAK.finditer(sentence[:at]):
        start = m.start()
    clause = sentence[start:at]
    if start > 0 and _OTHER_SUBJECT[kind].search(re.sub(r"^[,;\s]+", "", clause)):
        return None
    return start, clause


def sentences(page_n: str) -> Iterator[Tuple[int, int]]:
    """(start, end) of each sentence of a normalized page: split at ". ; ! ?" before a space, not at
    abbreviations or initials, never shorter than 12 characters and never longer than 700."""
    start = 0
    for m in re.finditer(r"[.;!?](?=\s|$)", page_n):
        k = m.end()
        if k - start < 12 or (_ABBREV.search(page_n[max(start, k - 8):k]) and not _LABEL_END.search(page_n[max(start, k - 16):k])):
            continue                                              # "... through Website A." ends a sentence; "John A. Smith" does not
        yield from _capped(page_n, start, k)
        start = k
    if page_n[start:].strip():
        yield from _capped(page_n, start, len(page_n))


def _capped(page_n: str, start: int, end: int) -> Iterator[Tuple[int, int]]:
    while start < end and page_n[start] == " ":
        start += 1
    while end - start > 700:
        cut = page_n.rfind(" ", start, start + 700)
        cut = cut if cut > start else start + 700
        yield start, cut
        start = cut + 1
    if end > start:
        yield start, end


def platforms_in(sentence: str) -> List[Tuple[str, int, int]]:
    """Listed services the sentence names: (name, start, end), longest names first, no overlaps."""
    taken: List[Tuple[int, int]] = []
    out = {}
    for name, pat in _NAME_PATTERNS:
        for m in pat.finditer(sentence):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            if name in AMBIGUOUS and not (_SERVICE_AFTER.search(sentence[m.end():]) or _SERVICE_BEFORE.search(sentence[:m.start()])):
                continue
            taken.append((m.start(), m.end()))
            out.setdefault(name, (name, m.start(), m.end()))
    return sorted(out.values(), key=lambda t: t[1])


def features_in(sentence: str) -> List[Tuple[str, str, int, int]]:
    """Codebook feature phrases the sentence states: (class, phrase, start, end), longest first, no overlaps."""
    taken: List[Tuple[int, int]] = []
    out = {}
    for cls, phrase, pat in _FEATURE_PATTERNS:
        for m in pat.finditer(sentence):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            out.setdefault((cls, phrase), (cls, phrase, m.start(), m.end()))
    return sorted(out.values(), key=lambda t: t[2])


def dates_in(sentence: str) -> List[dict]:
    """Every date the sentence states, as calendar bounds. What a date refers to is not decided here."""
    out, seen, rest = [], set(), sentence
    while True:
        d = N.find_date(rest)
        if not d:
            break
        key = (d["from"], d["to"])
        if key not in seen:
            seen.add(key)
            out.append({"earliest": d["from"], "latest": d["to"], "precision": d["p"]})
        i = rest.find(d["x"])
        rest = rest[:i] + " " * len(d["x"]) + rest[i + len(d["x"]):] if i >= 0 else ""
    return out


def observe(case_id: str, text_root: Path) -> dict:
    """Every platform and feature observation of a case, in reading order."""
    observations: List[dict] = []
    for _, doc, page_no, text in pages_of(case_id, text_root):
        if V.DOC_TYPES[doc["doc_type"]][0] == "PROCEDURAL":      # docket sheets record court business ("hearing held via Zoom")
            continue
        page_n = E.normalize(text)
        page = next(p for p in doc["pages"] if p["pdf_page"] == page_no)
        base = {"doc_id": doc["doc_id"], "pdf_page": page_no, "source_status": V.DOC_TYPES[doc["doc_type"]][0],
                "page_text_sha256": E.sha256_text(page_n),
                "verification": {"status": "VERIFIED", "method": "ocr_text_exact" if page["text_method"] == "ocr" else "text_layer_exact",
                                 "checked_by": RULE_VERSION}}
        for start, end in sentences(page_n):
            s = page_n[start:end]
            found = [("platform", {"platform": ALIASES.get(name, name), "named_as": name}, a, b) for name, a, b in platforms_in(s)]
            found += [("platform", {"platform": label + WITHHELD_SUFFIX, "named_as": label, "withheld": True}, a, b)
                      for label, a, b in withheld_in(s)]
            names = [m.span() for _, pat in _NAME_PATTERNS for m in pat.finditer(s)] + [m.span() for m in _WITHHELD.finditer(s)]
            found += [("service_description", {"service_term": term}, a, b) for term, a, b in descriptions_in(s, names)]
            found += [("feature", {"feature_class": cls, "feature_term": phrase}, a, b) for cls, phrase, a, b in features_in(s)]
            if not found:
                continue
            stated = dates_in(s)
            for kind, what, a, b in sorted(found, key=lambda f: f[2]):
                observations.append({"observation_id": f"o{len(observations) + 1:04d}", "kind": kind, **what, **base,
                                     "char_start": start, "char_end": end, "term_start": start + a, "term_end": start + b,
                                     "quote_sha256": E.sha256_text(s), "quote_word_count": len(s.split()),
                                     "dates_in_sentence": stated, "relations": []})
    return {"schema_version": SCHEMA_VERSION, "rule": RULE_VERSION, "case_id": case_id, "observations": observations}


def _means(kind: str, sentence: str, o: dict) -> Optional[Tuple[str, str]]:
    """(relationship kind, cue word) when the sentence states the act was done by means of the observation."""
    if kind == "platform":
        name = "(?:" + _breakable(o["named_as"]) + "|" + _breakable(o["named_as"].upper()) + ")"
        patterns = [(rel, pat.format(name=name), 0) for rel, pat in _PLATFORM_CUES]
    else:
        patterns = [("Supports_Action", _FEATURE_MEANS.format(term=_breakable(o["feature_term"])), 0 if o["feature_term"] in ("Tor", "VPN") else re.I)]
    for rel, pattern, flags in patterns:
        for m in re.finditer(pattern, sentence, flags):
            own = _own_clause(sentence, m.end(), kind)
            if own is None or m.start() < own[0]:           # another subject's clause, or cue and term in different clauses
                continue
            if _NEGATED.search(sentence[own[0]:m.start("cue")]):
                continue
            return rel, m.group("cue").lower()
    return None


def relate(doc: dict, bundle: dict, text_root: Path) -> dict:
    """Level 3: tie an observation to a published offender act whose cited sentence holds it and states
    the act was done by means of it. Where several published acts cite that sentence, the sentence
    does not say which of them the means belongs to, and nothing is tied (``several_acts`` is set).
    Returns the document with ``relations`` filled."""
    P = {p["passage_id"]: p for p in bundle["passages"]}
    acts = []
    for e in bundle["events"]:
        if V.FAMILY_OF[e["action"]] != "offender":
            continue
        for s in e["support"]:
            if s["facet"] == "action":
                p = P[s["passage_id"]]
                acts.append((p["doc_id"], p["pdf_page"], p["char_start"], p["char_end"], e["event_id"]))
    pages: Dict[tuple, str] = {}
    for o in doc["observations"]:
        o["relations"] = []
        o.pop("several_acts", None)
        o.pop("act_passage_runs_on", None)
        if o["kind"] == "service_description":                  # a description is never tied to an act
            continue
        citing = {eid for d, pg, a, b, eid in acts if (d, pg) == (o["doc_id"], o["pdf_page"]) and a <= o["term_start"] and o["term_end"] <= b}
        if len(citing) > 1:
            o["several_acts"] = len(citing)
            continue
        for d, pg, a, b, eid in acts:
            if (d, pg) != (o["doc_id"], o["pdf_page"]) or not (a <= o["term_start"] and o["term_end"] <= b):
                continue
            if (d, pg) not in pages:
                pages[(d, pg)] = E.normalize(E.read_page(bundle["case_id"], d, pg, text_root) or "")
            # A cited passage can run across a sentence end the coder's splitter does not see ("... through
            # Website A. The defendant ..."). Which of its sentences is the act's own is then unknown, so nothing is tied.
            if a < o["char_start"] - 1 or b > o["char_end"] + 1:
                o["act_passage_runs_on"] = True
                continue
            hit = _means(o["kind"], pages[(d, pg)][a:b], o)
            if hit and all(r["event_id"] != eid for r in o["relations"]):
                o["relations"].append({"event_id": eid, "relationship": hit[0], "cue": hit[1], "basis": "means_stated_in_act_sentence"})
    doc["bundle_case_id"] = bundle["case_id"]
    return doc


def summary(doc: dict) -> dict:
    obs = doc["observations"]
    plat = Counter(o["platform"] for o in obs if o["kind"] == "platform" and not o.get("withheld"))
    held = Counter(o["platform"] for o in obs if o.get("withheld"))
    feat = Counter(o["feature_class"] for o in obs if o["kind"] == "feature")
    desc = Counter(o["service_term"] for o in obs if o["kind"] == "service_description")
    return {"observations": len(obs), "platform_observations": sum(plat.values()),
            "withheld_platform_observations": sum(held.values()), "withheld_platforms": dict(sorted(held.items())),
            "service_description_observations": sum(desc.values()), "service_terms": dict(sorted(desc.items())), "feature_observations": sum(feat.values()),
            "platforms": dict(sorted(plat.items())), "feature_classes": dict(sorted(feat.items())),
            "feature_terms": dict(sorted(Counter(o["feature_term"] for o in obs if o["kind"] == "feature").items())),
            "by_standing": dict(sorted(Counter(o["source_status"] for o in obs).items())),
            "observations_tied_to_an_act": sum(bool(o["relations"]) for o in obs),
            "observations_in_a_sentence_several_acts_cite": sum(bool(o.get("several_acts")) for o in obs),
            "observations_in_an_act_passage_that_runs_across_sentences": sum(bool(o.get("act_passage_runs_on")) for o in obs),
            "observations_with_a_date_in_the_sentence": sum(bool(o["dates_in_sentence"]) for o in obs)}


def check(doc: dict, text_root: Path, bundle: Optional[dict] = None) -> List[str]:
    """Problems with an observations document (empty = sound): every span re-read from the page and
    re-hashed, every name and term on its list, every relation inside its act's cited sentence."""
    problems = []
    terms = {(cls, ph) for cls, phrases in FEATURES.items() for ph in phrases}
    events = {e["event_id"]: e for e in (bundle or {}).get("events", [])}
    passages = {p["passage_id"]: p for p in (bundle or {}).get("passages", [])}
    pages: Dict[tuple, Optional[str]] = {}
    for o in doc["observations"]:
        where = f"{o['observation_id']}"
        key = (o["doc_id"], o["pdf_page"])
        if key not in pages:
            raw = E.read_page(doc["case_id"], o["doc_id"], o["pdf_page"], text_root)
            pages[key] = E.normalize(raw) if raw is not None else None
        page_n = pages[key]
        if page_n is None:
            problems.append(f"{where}: page text not in the store")
            continue
        if E.sha256_text(page_n) != o["page_text_sha256"]:
            problems.append(f"{where}: page text hash differs")
        quote = page_n[o["char_start"]:o["char_end"]]
        if E.sha256_text(quote) != o["quote_sha256"]:
            problems.append(f"{where}: sentence hash differs")
        term = page_n[o["term_start"]:o["term_end"]]
        if not (o["char_start"] <= o["term_start"] < o["term_end"] <= o["char_end"]):
            problems.append(f"{where}: term outside its sentence")
        if o["kind"] == "platform":
            if not listed_platform(o) or not _same(term, o["named_as"]):
                problems.append(f"{where}: not a listed service or placeholder label at that span")
        elif o["kind"] == "service_description":
            if not listed_service_term(o) or service_term(term) != o["service_term"] or not SERVICE.fullmatch(term):
                problems.append(f"{where}: not a generic service description of the fixed grammar at that span")
            if o["relations"] or any(k in o for k in ("platform", "named_as", "withheld", "feature_class", "feature_term")):
                problems.append(f"{where}: a service description is tied to an act or carries a platform or feature field")
        elif (o["feature_class"], o["feature_term"]) not in terms or not _same(term, o["feature_term"]):
            problems.append(f"{where}: not a listed feature phrase at that span")
        for r in o["relations"]:
            e = events.get(r["event_id"])
            if e is None or V.FAMILY_OF[e["action"]] != "offender":
                problems.append(f"{where}: related act {r['event_id']} is not a published offender act")
                continue
            spans = [passages[s["passage_id"]] for s in e["support"] if s["facet"] == "action"]
            if not any(p["doc_id"] == o["doc_id"] and p["pdf_page"] == o["pdf_page"] and p["char_start"] <= o["term_start"]
                       and o["term_end"] <= p["char_end"] for p in spans):
                problems.append(f"{where}: related act {r['event_id']} does not cite this sentence")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("case_id")
    ap.add_argument("--text-root", type=Path, default=E.text_root())
    ap.add_argument("--bundle", type=Path, help="the case's resolved bundle, to derive supported relationships")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    doc = observe(a.case_id, a.text_root)
    bundle = json.loads(a.bundle.read_text(encoding="utf-8")) if a.bundle else None
    if bundle:
        relate(doc, bundle, a.text_root)
    problems = check(doc, a.text_root, bundle)
    if a.out:
        a.out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary(doc), "problems": problems}, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
