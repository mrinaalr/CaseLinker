"""Synthetic gold PACER cases: the coding is written first, the court documents are rendered from it.

    python -m state_machines.benchmark.generate [--n 40] [--seed 7] [--out state_machines/benchmark/data]

Every case is fictional: invented platforms, "the defendant", "Minor Victim 1", no real names,
dates or places, and clinical court wording only. For each case the generator writes

    <out>/<case_id>/sources.json             documents and pages, as the page-text store holds them
    <out>/<case_id>/<doc_id>/pNNNN.txt       page text (headers, wrapped lines, some hyphenation)
    <out>/<case_id>/gold.json                the gold bundle (schema 2.0): what a correct coder codes

No model writes any text: documents come from fixed templates with several phrasings each, so a
model scored on the benchmark never reads its own wording. Hard cases are built in on purpose and
tagged per gold event (``notes`` holds the tags): order stated only in words, the same act told in
two documents, an allegation the plea never admits, a platform named but not used, level-C
affordances stated or absent, undercover personas, interrupted attempts.
"""
from __future__ import annotations

import argparse
import calendar
import json
import random
import re
import textwrap
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V

OUT = Path(__file__).resolve().parent / "data"
BENCHMARK_VERSION = "benchmark-1.0"
PLATFORMS = ["Chirpline", "Vellum Chat", "Snapwire", "Kitebox", "Orbit Messenger", "Loopit", "Pinehollow"]
STANDING = {d: V.DOC_TYPES[d][0] for d in V.DOC_TYPES}
MONTHS = list(calendar.month_name)[1:]


def _day(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


class Case:
    """Accumulates documents, participants, events and relations; renders pages; emits gold."""

    def __init__(self, case_id: str, rng: random.Random, heldout: bool = False):
        self.id, self.rng, self.heldout = case_id, rng, heldout
        self.docs: Dict[str, dict] = {}
        self.sentences: Dict[str, List[str]] = {}
        self.participants: List[dict] = []
        self.events: List[dict] = []
        self.relations: List[dict] = []
        self.tracks: Dict[str, dict] = {}
        self.passages: List[dict] = []          # passage_id, doc_id, sentence index
        self._n = 0

    # --- building ---------------------------------------------------------------------------
    def doc(self, doc_id: str, doc_type: str) -> str:
        self.docs[doc_id] = {"doc_id": doc_id, "doc_type": doc_type}
        self.sentences[doc_id] = []
        return doc_id

    def say(self, doc_id: str, sentence: str) -> str:
        """Add a sentence to a document; returns its passage id (the whole sentence is the quote)."""
        self._n += 1
        pid = f"s{self._n:03d}"
        self.sentences[doc_id].append(heldout_style(sentence) if self.heldout else sentence)
        self.passages.append({"passage_id": pid, "doc_id": doc_id, "index": len(self.sentences[doc_id]) - 1})
        return pid

    def filler(self, doc_id: str, sentence: str) -> None:
        self.sentences[doc_id].append(heldout_style(sentence) if self.heldout else sentence)

    def participant(self, ref: str, kind: str, status: str, pid: str, **extra) -> None:
        p = {"participant_ref": ref, "kind": kind,
             "legal_status": [{"status": status, "support": [{"passage_id": pid, "facet": "legal_status", "status": "DIRECT"}]}]}
        p.update(extra)
        self.participants.append(p)

    def event(self, eid: str, action: str, actor: str, role: str, pid: str, *, targets=(), when=None, tags=(),
              outcome="completed", affordance=None, platform=None, mention=None, harm=None, status="DIRECT",
              co_actors=(), track="v1") -> dict:
        e = {"event_id": eid, "action": action, "actor": {"participant_ref": actor, "role": role},
             "co_actors": [dict(c) for c in co_actors], "targets": [{"participant_ref": r, "role": t} for r, t in targets],
             "unresolved_participants": [], "outcome": outcome,
             "description": f"{action.lower().replace('_', ' ')} (synthetic)", "notes": " ".join(sorted(set(tags))),
             "support": [{"passage_id": pid, "facet": "action", "status": status}], "status": status,
             "time": {"assertions": []}, "repetition": {"kind": "single"},
             "platform_mentions": [], "platform_interactions": [], "channels": [],
             "affordances": [], "candidate_affordances": [], "access": [], "harms": [],
             "review": {"status": "adjudicated", "coders": ["coder_gold"], "adjudicator": BENCHMARK_VERSION}}
        if when:
            expression, lo, hi, precision = when
            e["time"]["assertions"].append({"expression": expression, "precision": precision, "earliest": lo.isoformat(),
                                            "latest": hi.isoformat(), "basis": "explicit_date", "status": "DIRECT",
                                            "passage_ids": [pid]})
        if platform:
            name, mode, audience = platform
            e["platform_interactions"].append({"platform_surface": name, "platform_key": name, "mode": mode, "audience": audience,
                                               "status": "DIRECT", "support": [{"passage_id": pid, "facet": "platform", "status": "DIRECT"}]})
        if mention:
            e["platform_mentions"].append({"platform_surface": mention, "passage_ids": [pid]})
        if affordance:
            cls, term, surface = affordance
            e["affordances"].append({"affordance": cls, "basis": "feature_stated", "feature_term": term, "platform_surface": surface,
                                     "status": "DIRECT", "support": [{"passage_id": pid, "facet": "feature", "status": "DIRECT"}]})
        if harm:
            e["harms"].append({"harm": harm, "victim_ref": "P2", "victim_kind": "minor", "status": "DIRECT",
                               "support": [{"passage_id": pid, "facet": "action", "status": "DIRECT"}]})
        self.events.append(e)
        if track:
            self.tracks.setdefault(track, {"track_id": track, "kind": {"v1": "victim", "uc1": "undercover", "proc": "case_procedure",
                                                                         "net1": "co_offender_network"}[track],
                                           "anchor_ref": {"v1": "P2", "uc1": "P5", "proc": None, "net1": "P1"}[track],
                                           "event_ids": []})["event_ids"].append(eid)
        return e

    def relation(self, typ: str, a: str, b: str, pid: Optional[str], basis="explicit_sequence_language", status="DIRECT"):
        self.relations.append({"relation_id": f"r{len(self.relations) + 1:02d}", "type": typ, "from_event": a, "to_event": b,
                               "basis": basis, "status": status,
                               "support": [{"passage_id": pid, "facet": "time", "status": status}] if pid else []})

    # --- rendering --------------------------------------------------------------------------
    def render(self, out: Path) -> dict:
        case_dir = out / self.id
        docs, page_of = [], {}
        number = self.rng.randint(100, 999)
        for k, (doc_id, meta) in enumerate(self.docs.items(), start=1):
            sents = self.sentences[doc_id]
            per_page = self.rng.randint(5, 8)
            chunks = [sents[i:i + per_page] for i in range(0, len(sents), per_page)] or [[]]
            pages = []
            for pno, chunk in enumerate(chunks, start=1):
                header = f"Case 1:24-cr-00{number} Document {k * 7} Filed 0{k}/1{k}/24 Page {pno} of {len(chunks)}"
                body, rendered = [], []
                for s in chunk:
                    r = self._wrap(s)
                    rendered.append(r)
                    body.append(r)
                text = header + "\n\n" + "\n".join(body) + f"\n\n{pno}\n"
                sha = E.write_page(self.id, doc_id, pno, text, out)
                pages.append({"pdf_page": pno, "text_method": "text_layer", "page_text_sha256": sha, "court_page_label": str(pno),
                              "ocr_engine": None, "ocr_mean_confidence": None, "image_checked": False, "limitations": []})
                for s, r in zip(chunk, rendered):
                    page_of[(doc_id, s)] = (pno, text, r)
            docs.append({"doc_id": doc_id, "doc_type": meta["doc_type"],
                         "source_path": f"SYNTHETIC/{self.id} -- {meta['doc_type'].replace('_', ' ')}.pdf",
                         "sha256": E.sha256_text(self.id + doc_id), "ecf_document_number": str(k * 7), "filed_date": None,
                         "page_count": len(pages), "pages": pages})
        (case_dir / "sources.json").write_text(json.dumps({"case_id": self.id, "documents": docs}, indent=1), encoding="utf-8")
        passages = []
        for p in self.passages:
            s = self.sentences[p["doc_id"]][p["index"]]
            pno, text, rendered = page_of[(p["doc_id"], s)]
            start, end, q = E.locate(text, rendered)
            doc_type = self.docs[p["doc_id"]]["doc_type"]
            passages.append({"passage_id": p["passage_id"], "doc_id": p["doc_id"], "pdf_page": pno, "court_locator": None,
                             "char_start": start, "char_end": end, "quote_sha256": E.sha256_text(q),
                             "quote_word_count": len(q.split()), "source_status": STANDING[doc_type],
                             "verification": {"status": "VERIFIED", "method": "text_layer_exact", "checked_by": "coder_gold"}})
        gold = {"schema_version": V.SCHEMA_VERSION, "codebook_version": V.CODEBOOK_VERSION, "case_id": self.id,
                "coding": {"coder_id": "coder_gold", "method": "human", "model": None, "coded_on": "2026-11-17",
                           "blind_to": [], "note": f"{BENCHMARK_VERSION}: synthetic gold, written before the documents"},
                "documents": docs, "passages": passages, "participants": self.participants,
                "events": self.events, "relations": self.relations,
                "tracks": [{k: v for k, v in t.items() if v is not None} for t in self.tracks.values()]}
        (case_dir / "gold.json").write_text(json.dumps(gold, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return gold

    def _wrap(self, sentence: str) -> str:
        width = self.rng.randint(62, 84)
        lines = textwrap.wrap(sentence, width=width, break_long_words=False, break_on_hyphens=False)
        if len(lines) > 1 and self.rng.random() < 0.25:          # a word hyphenated across a line break
            i = self.rng.randrange(len(lines) - 1)
            nxt = lines[i + 1].split(" ")
            w = nxt[0]
            if len(w) >= 8 and w.isalpha():
                cut = len(w) // 2
                lines[i] = lines[i] + " " + w[:cut] + "-"
                lines[i + 1] = " ".join([w[cut:]] + nxt[1:])
        return "\n".join(lines)


# --- the held-out register ---------------------------------------------------------------------
# Held-out cases are written in a register the development cases never use, taken from how real
# filings often read: capitalised party names, victim abbreviations, "on or about", statutory
# phrasing. The facts (the gold) are the same kind; only the wording is unseen.
_HELDOUT = [
    (r"\bthe defendant's\b", "DEFENDANT's"), (r"\bThe defendant's\b", "DEFENDANT's"),
    (r"\b[Tt]he defendant\b", "DEFENDANT"), (r"\bMinor Victim 1\b", "MV-1"),
    (r"sexually explicit images of herself", "images depicting herself engaged in sexually explicit conduct"),
    (r"sexually explicit images", "images depicting sexually explicit conduct"),
    (r"first contacted", "initiated contact with"), (r"\bfirst communicated with\b", "began communicating with"),
    (r"^On (?!or about)([A-Z][a-z]+ \d)", r"On or about \1"), (r"^In ([A-Z][a-z]+ \d{4}),", r"In or around \1,"),
    (r"\bthreatened to\b", "made a threat to"), (r"\bblocked\b", "blocked and stopped responding to"),
]


def heldout_style(sentence: str) -> str:
    for pat, rep in _HELDOUT:
        sentence = re.sub(pat, rep, sentence)
    return sentence


# --- scenarios ---------------------------------------------------------------------------------

def _pick(rng: random.Random, options: List[str], **kw) -> str:
    return rng.choice(options).format(**kw)


def build_case(case_id: str, rng: random.Random, heldout: bool = False) -> Case:
    c = Case(case_id, rng, heldout)
    kind = rng.choice(["sextortion", "sextortion", "meeting", "undercover", "distribution"])
    p1, p2 = rng.sample(PLATFORMS, 2)
    start = date(rng.randint(2019, 2024), rng.randint(1, 10), rng.randint(1, 20))
    month = (f"{MONTHS[start.month - 1]} {start.year}", start.replace(day=1),
             start.replace(day=calendar.monthrange(start.year, start.month)[1]), "month")
    later = start + timedelta(days=rng.randint(10, 40))
    arrest = later + timedelta(days=rng.randint(5, 60))

    dk = c.doc("docket", "docket")
    ind = c.doc("indictment", "indictment")
    sof = c.doc("sof", rng.choice(["statement_of_offense", "factual_basis", "statement_of_facts"]))
    memo = c.doc("memo", "sentencing_memorandum") if rng.random() < 0.7 else None

    # procedure (docket): court acts, dated
    charge = arrest + timedelta(days=rng.randint(10, 40))
    plea = charge + timedelta(days=rng.randint(60, 200))
    p_charge = c.say(dk, f"{charge:%m/%d/%Y} INDICTMENT returned as to the defendant (1) on counts 1-3.")
    c.participant("P4", "organization", "court", p_charge)
    c.participant("P1", "person", "charged_defendant", p_charge)
    c.event("e90", "PROC_CHARGE", "P4", "court", p_charge, targets=[("P1", "subject")],
            when=(f"{charge:%m/%d/%Y}", charge, charge, "day"), track="proc", tags=["procedure"])
    p_plea = c.say(dk, f"{plea:%m/%d/%Y} PLEA AGREEMENT; the defendant (1) pleaded guilty to count 1 before the court.")
    c.event("e91", "PROC_PLEA", "P4", "court", p_plea, targets=[("P1", "subject")],
            when=(f"{plea:%m/%d/%Y}", plea, plea, "day"), track="proc", tags=["procedure"])
    c.filler(dk, f"{plea + timedelta(days=3):%m/%d/%Y} ORDER setting sentencing hearing.")
    c.filler(ind, "THE GRAND JURY CHARGES THAT: at all times relevant to this Indictment, the following facts applied.")
    c.filler(sof, "The parties stipulate that the following facts are true and that the government would prove them at trial.")

    victim_line = c.say(sof, _pick(rng, [
        "Minor Victim 1 was a fourteen-year-old girl who used the {p} application.",
        "At the relevant times, Minor Victim 1 was a minor girl who lived in another state and used {p}."], p=p1))
    if kind != "undercover":
        c.participant("P2", "person", "named_victim", victim_line, age_band="13-15")

    if kind == "undercover":
        post = c.say(sof, _pick(rng, [
            "In {m}, the defendant posted a message in a public {p} group seeking to meet a young girl.",
            "During {m}, the defendant published a public post on {p} asking whether any young girls wanted to talk."],
            m=month[0], p=p1))
        c.event("e01", "SEEK_TARGETS", "P1", "offender", post, when=month, platform=(p1, "through", "public"),
                track="uc1", tags=["undercover"])
        uc = c.say(sof, f"An undercover agent posing as a thirteen-year-old girl responded to the post on {p1}.")
        c.participant("P5", "persona", "undercover_persona", uc)
        c.event("e02", "LE_UNDERCOVER_ENGAGE", "P5", "undercover", uc, targets=[("P1", "subject")], track="uc1", tags=["undercover"])
        c.relation("BEFORE", "e01", "e02", uc)
        sol = c.say(sof, "After that response, the defendant asked the undercover agent to send sexually explicit images.")
        c.event("e03", "SOLICIT_IMAGERY", "P1", "offender", sol, targets=[("P5", "counterparty")],
                outcome="attempted_not_completed", track="uc1", tags=["undercover", "explicit_order"])
        c.relation("BEFORE", "e02", "e03", sol)
        meet = c.say(sof, f"On {_day(later)}, the defendant arranged to meet the undercover agent at a restaurant.")
        c.event("e04", "ARRANGE_MEETING", "P1", "offender", meet, targets=[("P5", "counterparty")],
                when=(_day(later), later, later, "day"), track="uc1", tags=["undercover"])
        trav = c.say(sof, f"On {_day(arrest)}, the defendant drove to the restaurant to meet the undercover agent.")
        c.event("e05", "TRAVEL_TO_MEET", "P1", "offender", trav, targets=[("P5", "counterparty")],
                outcome="interrupted", when=(_day(arrest), arrest, arrest, "day"), track="uc1", tags=["undercover", "interrupted"])
        arr = c.say(sof, f"Agents arrested the defendant at the restaurant on {_day(arrest)}.")
        c.participant("P3", "organization", "law_enforcement", arr)
        c.event("e06", "LE_ARREST", "P3", "law_enforcement", arr, targets=[("P1", "subject")],
                when=(_day(arrest), arrest, arrest, "day"), track="uc1", tags=["interrupted"])
        c.relation("INTERRUPTS", "e06", "e05", arr)
        return c

    # victim scenarios
    found = rng.random() < 0.5
    contact = c.say(sof, _pick(rng, [
        "In {m}, the defendant found Minor Victim 1 through the public group search feature on {p} and first contacted her there.",
        "In {m}, the defendant used the public group search feature on {p} to find Minor Victim 1 and sent her a first message."]
        if found else [
        "In {m}, the defendant first contacted Minor Victim 1 through the {p} application.",
        "Minor Victim 1 first communicated with the defendant on {p} in {m}."], m=month[0], p=p1))
    c.event("e01", "INITIATE_CONTACT", "P1", "offender", contact, targets=[("P2", "victim")], when=month,
            platform=(p1, "through", "one_to_one"),
            affordance=("contact_discovery", "public group search feature", p1) if found else None,
            tags=["level_c"] if found else ["no_level_c"])
    lie = c.say(sof, _pick(rng, ["The defendant told Minor Victim 1 that he was seventeen years old, which was not true.",
                                 "The defendant falsely told Minor Victim 1 that he was a sixteen-year-old boy."]))
    c.event("e02", "MISREPRESENT_IDENTITY", "P1", "offender", lie, targets=[("P2", "victim")], tags=["undated"])
    move = c.say(sof, _pick(rng, ["After that first contact, the defendant told Minor Victim 1 to continue their conversation on {q}.",
                                  "After their first conversation, the defendant directed Minor Victim 1 to move their chat to {q}."], q=p2))
    c.event("e03", "MOVE_CHANNEL", "P1", "offender", move, targets=[("P2", "victim")], platform=(p2, "to", "one_to_one"),
            tags=["explicit_order", "undated"])
    c.relation("BEFORE", "e01", "e03", move)
    eph = rng.random() < 0.5
    sol = c.say(sof, _pick(rng, ["On {d}, the defendant used the disappearing-message feature on {q} to ask Minor Victim 1 to send sexually explicit images of herself."]
                       if eph else ["On {d}, the defendant asked Minor Victim 1 to send sexually explicit images of herself over {q}."],
                       d=_day(later), q=p2))
    c.event("e04", "SOLICIT_IMAGERY", "P1", "offender", sol, targets=[("P2", "victim")],
            when=(_day(later), later, later, "day"), platform=(p2, "through", "one_to_one"),
            affordance=("ephemerality", "disappearing-message feature", p2) if eph else None,
            tags=["level_c"] if eph else ["no_level_c"])
    recv = c.say(sof, _pick(rng, ["In response, Minor Victim 1 sent the defendant two sexually explicit images of herself.",
                                  "Minor Victim 1 then sent the defendant three sexually explicit images, as he had asked."]))
    c.event("e05", "RECEIVE_SELF_GENERATED", "P1", "offender", recv, targets=[("P2", "victim")],
            harm="HARM_COERCED_SELF_GENERATED_IMAGERY", tags=["explicit_order", "undated", "harm"])
    c.relation("BEFORE", "e04", "e05", recv)
    nxt = "e05"
    if kind in ("sextortion", "distribution"):
        block = c.say(sof, "Minor Victim 1 then blocked the defendant's account.")
        c.event("e06", "RESP_BLOCK", "P2", "victim", block, targets=[("P1", "subject")], tags=["response", "explicit_order"])
        c.relation("BEFORE", nxt, "e06", block)
        recreate = c.say(sof, _pick(rng, [
            "After Minor Victim 1 blocked his account, the defendant created a new account under a different name to conceal his identity and contacted her again.",
            "Following the block, the defendant made a new account under a false name to hide his identity and messaged Minor Victim 1 again."]))
        c.event("e07", "RECREATE_ACCOUNT", "P1", "offender", recreate, targets=[("P2", "victim")],
                affordance=("anonymity", "new account under a different name" if "different name" in c.sentences[sof][-1]
                            else "new account under a false name", p2), tags=["level_c", "explicit_order"])
        c.relation("BEFORE", "e06", "e07", recreate)
        threat_day = later + timedelta(days=rng.randint(3, 12))
        threat = c.say(sof, f"On {_day(threat_day)}, the defendant threatened to send the images to the friends of Minor Victim 1 unless she sent more.")
        c.event("e08", "THREATEN_EXPOSURE", "P1", "offender", threat, targets=[("P2", "victim")],
                when=(_day(threat_day), threat_day, threat_day, "day"), harm="HARM_EXPOSURE_THREAT", tags=["harm"])
        nxt = "e08"
        if kind == "distribution" or rng.random() < 0.4:
            n = rng.randint(3, 9)
            grp = rng.random() < 0.5
            dist = c.say(sof, f"The defendant later posted the images in a {p2} group chat with {n} members."
                         if grp else f"The defendant later sent the images to at least {n} other users of {p2}.")
            c.participant("P6", "collective", "third_party", dist,
                          count={"min": n, "max": n if grp else None, "stated": "exact" if grp else "at_least",
                                 "support": [{"passage_id": dist, "facet": "count", "status": "DIRECT"}]})
            c.event("e09", "DISTRIBUTE_MATERIAL", "P1", "offender", dist, targets=[("P2", "victim"), ("P6", "recipient")],
                    platform=(p2, "through", "group" if grp else "one_to_one"),
                    affordance=("distribution_infrastructure", "group chat", p2) if grp else None,
                    harm="HARM_DISTRIBUTION_RECIRCULATION", tags=["harm", "explicit_order"] + (["level_c"] if grp else ["no_level_c"]))
            c.relation("BEFORE", "e07", "e09", dist)
    if kind == "meeting":
        meet_day = later + timedelta(days=rng.randint(5, 20))
        meet = c.say(sof, f"On {_day(meet_day)}, the defendant arranged to meet Minor Victim 1 at a hotel.")
        c.event("e10", "ARRANGE_MEETING", "P1", "offender", meet, targets=[("P2", "victim")], when=(_day(meet_day), meet_day, meet_day, "day"))
        trav = c.say(sof, "The next day, the defendant drove to the hotel to meet Minor Victim 1.")
        c.event("e11", "TRAVEL_TO_MEET", "P1", "offender", trav, targets=[("P2", "victim")], tags=["explicit_order"])
        c.relation("BEFORE", "e10", "e11", trav)
        abuse = c.say(sof, "At the hotel, the defendant engaged in sexual contact with Minor Victim 1.")
        c.event("e12", "IN_PERSON_SEXUAL_ABUSE", "P1", "offender", abuse, targets=[("P2", "victim")],
                harm="HARM_IN_PERSON_SEXUAL_ABUSE", tags=["harm", "explicit_order"])
        c.relation("BEFORE", "e11", "e12", abuse)
        nxt = "e12"
    # a platform named but not used
    if rng.random() < 0.6:
        p3 = rng.choice([p for p in PLATFORMS if p not in (p1, p2)])
        exam = c.say(sof, f"A forensic examination of the defendant's phone found the {p3} application installed.")
        c.participant("P3", "organization", "law_enforcement", exam)
        c.event("e20", "LE_FORENSIC_EXAM", "P3", "law_enforcement", exam, targets=[("P1", "subject")], mention=p3,
                track="proc", tags=["mention_only"])
    # the same act told again: an indictment count restating the solicitation, with a date
    retell = c.say(ind, _pick(rng, ["COUNT ONE. On or about {d}, the defendant asked Minor Victim 1 to send sexually explicit images of herself.",
                                    "COUNT ONE. On or about {d}, the defendant solicited sexually explicit images from Minor Victim 1."],
                              d=_day(later)))
    c.event("e30", "SOLICIT_IMAGERY", "P1", "offender", retell, targets=[("P2", "victim")],
            when=(f"on or about {_day(later)}", later, later, "day"), tags=["retelling", "allegation"])
    c.relation("SAME_ACT", "e04", "e30", retell, basis="coder_inference", status="INFERRED")
    # an allegation the plea never admits
    if rng.random() < 0.5:
        alleg = c.say(ind, "COUNT THREE. The defendant also threatened to harm Minor Victim 1 if she told anyone about their messages.")
        c.event("e31", "THREATEN_HARM", "P1", "offender", alleg, targets=[("P2", "victim")], tags=["allegation_only"])
    if memo:
        c.filler(memo, "The government respectfully submits this memorandum in aid of sentencing.")
        if kind in ("sextortion", "distribution"):
            again = c.say(memo, "The defendant threatened to expose the images of Minor Victim 1 to her friends, which the government contends caused her fear.")
            c.event("e40", "THREATEN_EXPOSURE", "P1", "offender", again, targets=[("P2", "victim")],
                    harm="HARM_EXPOSURE_THREAT", tags=["retelling", "advocacy", "harm"])
            c.relation("SAME_ACT", "e08", "e40", again, basis="coder_inference", status="INFERRED")
        else:
            c.filler(memo, "The defendant's conduct warrants a sentence at the top of the guidelines range.")
    return c


def generate(n: int = 40, seed: int = 7, out: Path = OUT) -> List[dict]:
    rng = random.Random(seed)
    golds, splits = [], {}
    for i in range(1, n + 1):
        heldout = i > n // 2          # the second half: never used to tune prompts or rules
        case_id = f"synth_{i:03d}"
        splits[case_id] = "heldout" if heldout else "dev"
        golds.append(build_case(case_id, random.Random(rng.randrange(1 << 30)), heldout).render(out))
    (out / "MANIFEST.json").write_text(json.dumps({"benchmark": BENCHMARK_VERSION, "seed": seed, "cases": [g["case_id"] for g in golds],
                                                   "splits": splits,
                                                   "schema_version": V.SCHEMA_VERSION, "codebook_version": V.CODEBOOK_VERSION},
                                                  indent=1) + "\n", encoding="utf-8")
    return golds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    golds = generate(args.n, args.seed, args.out)
    print(f"{len(golds)} synthetic cases, {sum(len(g['events']) for g in golds)} gold events → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
