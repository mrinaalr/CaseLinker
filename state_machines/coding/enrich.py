"""Deterministic coding of an act's sentence: everything the model is not asked for.

The model names which sentences state acts and their action codes (``coder.PROMPT``). These rules
read the same sentence for the rest, so each field is auditable and identical for both coders:

    targets        victim, undercover persona and recipient mentions ("Minor Victim 1", "MV-1",
                   "an undercover agent", "other users")
    date           the first date the sentence states ("on or about May 2, 2020", "In June 2020",
                   "05/02/2020"), with its exact words and real calendar bounds
    platform       a named service the act went through ("through the Kitebox application", "on Kitebox"),
                   only when the name is on the list of known services (``PLATFORMS``): a username, a
                   place or any other capitalised word is never recorded
    channel        SMS, phone, email, mail (never platforms, I3)
    affordance     level C only when the sentence names the feature (rule B0); feature words from a
                   fixed phrase list per class
    harm           from the action code when its target is a minor, per the codebook's definitions
                   (RECEIVE_SELF_GENERATED is coerced self-generated imagery, ...)
    outcome        attempted, not completed, when the counterparty is an undercover persona
    after          the sentence opens with sequence words ("After ...", "Then", "In response")

Agreement between the two coders on these fields is therefore not a measure of reliability:
reliability is reported on acts and action codes, which the models choose.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from state_machines.evidence import vocab as V

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})

_VICTIM = re.compile(r"\b(?:Minor Victim|Victim|MV|Minor|Child Victim|CV)[\s-]?(\d+)\b|\bthe (?:minor|child|victim)\b", re.I)
# designations by letter or pseudonym, as real filings write them ("Minor Victim A", "Victim B", "Jane Doe 2");
# case-sensitive, and a bare "Victim A" / "Minor I" is not read as a designation
_VICTIM_LETTER = re.compile(r"\b(?:Minor Victim|MINOR VICTIM|Child Victim)[\s-]([A-Z])\b|\b(?:Victim|VICTIM|MV|CV|Minor|MINOR)[\s-]?([B-HJ-Z])\b(?!\.)")
_VICTIM_DOE = re.compile(r"\b(?:Jane|John|JANE|JOHN) (?:Doe|DOE)(?:[\s-]?(?:No\. ?|#)?(\d+))?\b")
_MINOR_WORDS = re.compile(r"\b(?:minor|child|juvenile|years? old|year-old|had not attained|under the age of)\b", re.I)
_PERSONA = re.compile(r"\b(?:an? |the )?undercover (?:agent|officer|employee|detective|persona)\b|\bUC\b|\bOCE\b", re.I)
_RECIPIENTS = re.compile(r"\b(?:other (?:users|members|people|individuals)|\d+ (?:other )?(?:users|members|people)|the (?:group|members))\b", re.I)
_SEQ = re.compile(r"^(?:After|Following|Then|Thereafter|Later|Next|Subsequently|In response|Afterward|Afterwards|Shortly after|"
                  r"The next day|Within (?:a|one|two|\d+) (?:day|days|hour|hours))\b", re.I)
_THEN = re.compile(r"^[^,]{0,80}\b(?:then|thereafter|subsequently|in response)\b", re.I)
_AFTER = re.compile(r"^(?:Shortly after|After|Following)\b", re.I)
REFERENTS = [  # what an "After ..." clause refers to, by the earlier act's code
    (r"first (?:contact|conversation|message|communication)|initial contact", {"INITIATE_CONTACT"}),
    (r"block", {"RESP_BLOCK"}), (r"report", {"RESP_REPORT"}), (r"refus|declin", {"RESP_REFUSE"}),
    (r"meeting|arrang", {"ARRANGE_MEETING"}), (r"arrest", {"LE_ARREST"}), (r"threat", {"THREATEN_EXPOSURE", "THREATEN_HARM"}),
    (r"images|photos|pictures|video", {"RECEIVE_SELF_GENERATED", "SOLICIT_IMAGERY"}),
]
_HEADER = re.compile(r"^Case \S+ Document \S+ Filed \S+ Page \d+ of \d+\s*", re.I)   # a court header glued to a page's first sentence
_DATES = [
    (re.compile(r"(?:on or about |on |in or around |around |about )?(?P<m>[A-Z][a-z]+\.?) (?P<d>\d{1,2}), (?P<y>\d{4})", re.I), "day"),
    (re.compile(r"(?:in or around |in |around |during |by )?(?P<m>[A-Z][a-z]+) (?P<y>\d{4})\b", re.I), "month"),
    (re.compile(r"\b(?P<mm>\d{1,2})/(?P<dd>\d{1,2})/(?P<yyyy>\d{4})\b"), "slash"),
]
_PLATFORM = re.compile(r"\b(?:through|via|using|over|on|onto|to)\s+(?:the\s+)?(?P<n>[A-Z][A-Za-z0-9]+(?:\s[A-Z][A-Za-z0-9]+)?)"
                       r"(?:\s+(?:application|app|platform|messaging|account|service|website|site|chat))?")
_NOT_PLATFORM = {"Minor", "Victim", "MV", "January", "February", "March", "April", "May", "June", "July", "August", "September",
                 "October", "November", "December", "The", "His", "Her", "Count", "Counts", "December", "Defendant", "DEFENDANT",
                 "United", "Court", "Agent", "Agents", "Officer", "Detective", "In", "On", "At", "After", "Before"}
CHANNELS = [(re.compile(r"\btext messages?\b|\bSMS\b", re.I), "sms"), (re.compile(r"\b(?:phone|telephone) calls?\b", re.I), "voice_call"),
            (re.compile(r"\be-?mails?\b", re.I), "email")]
# A bare "website" names a place on the internet, not a capability of one (and "Website A" is a withheld name, not
# evidence of distribution infrastructure); a bare "recommended" is everyday legal wording. Neither is a feature phrase.
FEATURES = {   # class -> phrases a sentence must contain for level C (rule B0)
    "anonymity": ["new account under a different name", "new account under a false name", "fake profile", "false name", "fake name",
                  "fictitious name", "different name", "burner phone", "anonymous account", "conceal his identity", "hide his identity",
                  "Tor", "VPN"],
    "ephemerality": ["disappearing-message", "disappearing message", "view-once", "view once", "self-destructing", "expiring messages",
                     "messages set to disappear", "disappear after"],
    "contact_discovery": ["public group search", "search feature", "public group", "public post", "friend suggestion",
                          "recommended friends", "suggested friends", "friend suggestions", "people you may know",
                          "people nearby", "location feature", "follower list"],
    "unmonitored_communication": ["encrypted", "private messages", "private direct messages", "secret chat", "hidden from his parents",
                                  "hidden from her parents", "vault app"],
    "distribution_infrastructure": ["group chat", "shared link", "cloud storage", "uploaded", "file-sharing", "peer-to-peer", "torrent",
                                    "channel with"],
    "generative_synthesis": ["artificial intelligence", "AI-generated", "AI generated", "morphed", "deepfake", "digitally altered"],
}
HARM_OF_ACTION = {   # codebook definitions: the act documents the harm when its target is a minor
    "RECEIVE_SELF_GENERATED": "HARM_COERCED_SELF_GENERATED_IMAGERY",
    "THREATEN_EXPOSURE": "HARM_EXPOSURE_THREAT",
    "DISTRIBUTE_MATERIAL": "HARM_DISTRIBUTION_RECIRCULATION",
    "EXPOSE_TO_VICTIM_NETWORK": "HARM_EXPOSURE_REALIZED",
    "IN_PERSON_SEXUAL_ABUSE": "HARM_IN_PERSON_SEXUAL_ABUSE",
    "PRODUCE_IN_PERSON": "HARM_PRODUCTION_IN_PERSON_RECORDED",
    "SYNTHESIZE_OR_ALTER_IMAGERY": "HARM_SYNTHETIC_LIKENESS",
    "ADVERTISE_COMMERCIAL_SEX": "HARM_COMMERCIAL_SEXUAL_EXPLOITATION",
    "ARRANGE_COMMERCIAL_SEX": "HARM_COMMERCIAL_SEXUAL_EXPLOITATION",
}


def targets(sentence: str, family: str) -> List[Dict[str, str]]:
    if family in ("procedure", "law_enforcement", "response"):
        return [{"who": "the defendant", "role": "subject"}] if family != "response" else [{"who": "the defendant", "role": "subject"}]
    out = []
    if _PERSONA.search(sentence):
        out.append({"who": "an undercover agent", "role": "counterparty"})
    m, letter, doe = _VICTIM.search(sentence), _VICTIM_LETTER.search(sentence), _VICTIM_DOE.search(sentence)
    first = min((x for x in (m, letter, doe) if x), key=lambda x: x.start(), default=None)
    if first is not None:                      # the first victim the sentence names
        if first is letter:
            c = (letter.group(1) or letter.group(2)).lower()
            label = f"minor victim {c}{ord(c) - 96}"
        elif first is doe:                     # a pseudonym says nothing about age: minor only where the sentence says so
            label = ("minor " if _MINOR_WORDS.search(sentence) else "") + "victim doe " + (doe.group(1) or "1")
        else:
            label = f"minor victim {m.group(1)}" if m.group(1) else "minor victim 1"
        out.append({"who": label, "role": "victim"})
    if _RECIPIENTS.search(sentence):
        out.append({"who": "other users", "role": "recipient"})
    return out


def find_date(sentence: str) -> Optional[dict]:
    for pat, kind in _DATES:
        for m in pat.finditer(sentence):
            try:
                if kind == "slash":
                    d = date(int(m.group("yyyy")), int(m.group("mm")), int(m.group("dd")))
                    lo = hi = d
                    precision = "day"
                else:
                    month = MONTHS.get(m.group("m").lower().rstrip("."))
                    if not month:
                        continue
                    y = int(m.group("y"))
                    if kind == "day":
                        lo = hi = date(y, month, int(m.group("d")))
                        precision = "day"
                    else:
                        lo, hi = date(y, month, 1), date(y, month, calendar.monthrange(y, month)[1])
                        precision = "month"
            except ValueError:
                continue
            if 1990 <= lo.year <= 2030:
                return {"x": m.group(0).strip(), "from": lo.isoformat(), "to": hi.isoformat(), "p": precision}
    return None


_PLATFORM_IN = re.compile(r"\bin (?:a|an|the) (?P<n>[A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+)?) (?:group|chat|application|app|channel|server|account)")


# A name is recorded as a platform only when it is a known service. Anything else after "on", "via" or
# "to" (a username, a nickname, a place, a court body) is left out, so it can never be published.
PLATFORMS = frozenset("""
Instagram Snapchat Facebook Messenger WhatsApp Telegram Kik Discord TikTok Twitter Omegle Skype Zoom FaceTime Signal Wickr Viber
WeChat Line Tumblr Reddit YouTube Twitch Roblox Minecraft Fortnite Xbox PlayStation Steam Grindr Tinder Bumble Whisper MeetMe
Yubo Wizz Monkey Amino Likee LiveMe Periscope Chatroulette Chatstep Musically Vine Pinterest LinkedIn Craigslist Backpage
Dropbox Mega MediaFire iCloud OneDrive Gmail Yahoo Hotmail Outlook Hangouts Freenet BitTorrent eMule Shareaza LimeWire
FrostWire Gnutella Ares PayPal Venmo Zelle CashApp Bitcoin Session Threema Element Matrix Tox Jabber Imgur Flickr Photobucket
MocoSpace Tagged Badoo Skout Hoop Oovoo Paltalk Mewe Gab Parler OnlyFans Patreon Chaturbate Motherless Pornhub Imgsrc
""".split()) | frozenset({"Google Drive", "Google Photos", "Google Hangouts", "Google Chat", "Google Voice", "Cash App", "Apple Pay",
                         "Western Union", "Facebook Messenger", "Kik Messenger", "Yahoo Messenger", "Text Now", "TextNow",
                         "Chat Avenue", "Among Us", "Call of Duty", "Xbox Live", "Play Station"})
FICTIONAL_PLATFORMS = frozenset({"Chirpline", "Vellum Chat", "Snapwire", "Kitebox", "Orbit Messenger", "Loopit", "Pinehollow"})   # the synthetic benchmark's
_KNOWN = {n.lower(): n for n in PLATFORMS | FICTIONAL_PLATFORMS}


def known_platform(name: str) -> Optional[str]:
    """The listed service a captured name is, or None. "Instagram Direct" is Instagram."""
    name = " ".join((name or "").split())
    return _KNOWN.get(name.lower()) or (_KNOWN.get(name.split()[0].lower()) if name else None)


def platform(sentence: str) -> Optional[dict]:
    for m in [*_PLATFORM.finditer(sentence), *_PLATFORM_IN.finditer(sentence)]:
        name = known_platform(m.group("n"))
        if name is None or m.group("n").split()[0] in _NOT_PLATFORM:
            continue
        mode = "to" if re.search(r"\b(?:continue|move|moved|switch|switched)\b[^.]*\b(?:on|to|onto)\s+(?:the\s+)?" + re.escape(name), sentence) else "through"
        audience = "group" if re.search(r"\bgroup\b", sentence, re.I) else ("public" if re.search(r"\bpublic\b", sentence, re.I) else "one_to_one")
        return {"n": name, "m": mode, "au": audience}
    return None


_FEATURE_PATTERNS = [   # whole words only; short proper names ("Tor", "VPN") keep their case, so "operator" is not Tor
    (cls, re.compile(r"(?<![A-Za-z0-9])" + re.escape(ph) + r"(?![A-Za-z0-9])", 0 if ph in ("Tor", "VPN") else re.I))
    for cls, phrases in FEATURES.items() for ph in phrases]


def feature(sentence: str) -> Optional[Tuple[str, str]]:
    for cls, pat in _FEATURE_PATTERNS:
        m = pat.search(sentence)
        if m:
            return cls, m.group(0)
    return None


def enrich(act: dict, sentence: str, family: str) -> dict:
    """Fill the act's non-semantic fields from its sentence. Model-given fields are kept."""
    out = dict(act)
    if "targets" not in out or not out["targets"]:
        out["targets"] = targets(sentence, family)
    if not out.get("date"):
        d = find_date(sentence)
        if d:
            out["date"] = d
    if family == "offender":
        if not out.get("platform"):
            p = platform(sentence)
            if p:
                out["platform"] = {"name": p["n"], "mode": p["m"], "audience": p["au"]}
        if not out.get("affordance"):
            f = feature_as_means(sentence)
            if f:
                out["affordance"] = {"class": f[0], "feature": f[1]}
        victims = [t for t in out["targets"] if t["role"] == "victim"]
        if not out.get("harm") and victims and act.get("action") in HARM_OF_ACTION:
            out["harm"] = HARM_OF_ACTION[act["action"]]
        if any(t["role"] == "counterparty" for t in out["targets"]) and out.get("outcome", "completed") == "completed":
            out["outcome"] = "attempted_not_completed"
    for pat, ch in CHANNELS:
        if pat.search(sentence) and not out.get("platform"):
            out["platform"] = {"name": ch if ch != "sms" else "text message", "mode": "through", "audience": "one_to_one"}
            break
    if sequence_words(sentence) and not out.get("after"):
        out["after"] = "__previous__"
    return out


def feature_as_means(sentence: str) -> Optional[Tuple[str, str]]:
    """(class, phrase) when the sentence states a listed feature as the means of what it describes ("used the
    disappearing-message feature to ...", "created a new account under a false name"). Level C is instrumental
    use (codebook B): a phrase that only stands in the sentence ("the Tor network conceals its users", "did not
    use a fake name", a feature the victim used) is a mention, kept by the observation layer, not level C."""
    from state_machines.observations.observe import _means       # the one stated-means rule, shared by both layers
    for cls, pat in _FEATURE_PATTERNS:
        m = pat.search(sentence)
        if m and _means("feature", sentence, {"feature_term": m.group(0)}):
            return cls, m.group(0)
    return None


def sequence_words(sentence: str) -> bool:
    """The sentence states its place in a sequence ("After ...", "Then", "... then ...", "In response")."""
    s = _HEADER.sub("", sentence).strip()
    return bool(_SEQ.search(s) or _THEN.search(s))


def stated_prior(sentence: str, start: int, earlier: List[Tuple[str, str, int, bool]]) -> Optional[str]:
    """The earlier act a sequence sentence places itself after, or None. Never a guess.

    ``earlier`` lists the acts before this one in the same document, in reading order, as (event id,
    action code, end offset of its sentence, on the same page). Two cases give a relation:

    * the opening clause names the earlier act ("After that first contact", "Following the block"):
      the nearest earlier act with that code. If no such act was coded, nothing is linked.
    * the sentence only says "then", "in response", "thereafter", or "After ..." with no act named:
      the act stated in the sentence immediately before it on the page. If that sentence holds no
      coded act, nothing is linked.
    """
    s = _HEADER.sub("", sentence).strip()
    if not (_SEQ.search(s) or _THEN.search(s)):
        return None
    if _AFTER.search(s):
        clause = s.split(",")[0]
        wanted = next((codes for pat, codes in REFERENTS if re.search(pat, clause, re.I)), None)
        if wanted:
            named = [t for t in earlier if t[1] in wanted and not (t[3] and t[2] > start)]
            return named[-1][0] if named else None
    adjacent = [t for t in earlier if t[3] and 0 <= start - t[2] <= 2]
    return adjacent[-1][0] if adjacent else None
