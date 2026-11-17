"""Local model coder: a case's page text in, a coded bundle (schema 2.0) out. Nothing leaves the machine.

    python -m state_machines.coding.coder <coder_A|coder_B> <case_id> [...] [--text-root DIR] [--out DIR]

Hybrid reading:

- docket pages are read by a deterministic parser (``docket_acts``) for court procedure only:
  charge, plea, verdict, sentence and notice-of-arrest entries, with their dates;
- form pages of judgments (conditions of supervision, monetary penalties, payment schedules) are
  skipped and counted (``boilerplate``);
- every other page is read by the model, one page at a time. For each act it returns the first
  words of the sentence that states it and its codes, constrained to the codebook by a JSON schema.

Everything else is code:

- the quote is that sentence, located on the page from its first words (exact, after
  normalization) and extended to the sentence end; an act whose words are not on the page, or not
  uniquely, is dropped;
- people are named by their role in the case ("the defendant", "Minor Victim 1"); those labels
  only map acts to participants P1, P2, ... and are never stored;
- descriptions are written from the codes, never from model text;
- a level-C affordance is kept only when its feature words appear in the quote (rule B0);
- a "named platform" that is SMS, phone, email or mail becomes a channel (I3);
- the bundle is validated, and every act that breaks a rule is dropped and logged, until it is clean.

Models are local (Ollama) and pinned by content digest in ``models.json``; a model whose digest
differs is refused. Responses are cached (``local/coder_cache.db``) by model digest and prompt hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V
from state_machines.evidence.validate import errors, validate

HERE = Path(__file__).resolve().parent
MODELS = json.loads((HERE / "models.json").read_text(encoding="utf-8"))
CACHE = E.REPO_ROOT / "local" / "coder_cache.db"
PROMPT_VERSION = "coder-prompt-1.1"
MAX_PAGE_CHARS = 7000
BOILERPLATE = re.compile(r"(STANDARD CONDITIONS OF SUPERVISION|CRIMINAL MONETARY PENALTIES|SCHEDULE OF PAYMENTS|"
                         r"SPECIAL CONDITIONS OF SUPERVISION|ADDITIONAL (?:STANDARD|SPECIAL) CONDITIONS|CERTIFICATE OF SERVICE)", re.I)

_DEF = {  # short definitions from the codebook, for the prompt
    "SEEK_TARGETS": "searches or posts to find people to contact", "INITIATE_CONTACT": "first communication with a specific person",
    "ACQUIRE_REPRESENTATION": "obtains images or identifying information of a person", "ACQUIRE_MATERIAL": "receives or downloads existing abuse material",
    "COMMUNICATE": "sustained communication not coded more specifically", "MISREPRESENT_IDENTITY": "false age or identity in the conversation",
    "BUILD_RAPPORT": "flattery, attention, non-money gifts", "OFFER_INDUCEMENT": "money, goods or drugs offered for sexual conduct or images",
    "SEXUALIZE_COMMUNICATION": "introduces sexual content", "SOLICIT_IMAGERY": "requests sexual images or video",
    "DIRECT_CONDUCT": "instructs specific sexual conduct", "THREATEN_EXPOSURE": "threatens to share images or information",
    "THREATEN_HARM": "threatens violence or other harm", "DIRECT_VICTIM_TO_RECRUIT": "has a victim recruit others",
    "MOVE_CHANNEL": "moves the conversation to another app or medium", "RECREATE_ACCOUNT": "new account after a block or ban",
    "RECONTACT": "resumes contact after a gap or block", "RECEIVE_SELF_GENERATED": "receives images the victim made at his request",
    "RECORD_LIVE_SESSION": "records a live session", "PRODUCE_IN_PERSON": "records abuse in person",
    "SYNTHESIZE_OR_ALTER_IMAGERY": "AI-generated or altered images", "STORE_MATERIAL": "retains material (retention must be stated)",
    "ORGANIZE_MATERIAL": "catalogues a collection", "DISTRIBUTE_MATERIAL": "sends or shares material to others",
    "ADVERTISE_MATERIAL_OR_ACCESS": "advertises material or access", "EXPOSE_TO_VICTIM_NETWORK": "sends a victim's images to her contacts",
    "ADMINISTER_SPACE": "creates or runs a group, server or site", "GATEKEEP_MEMBERSHIP": "vets or admits members",
    "SET_RULES": "posting rules or quotas", "ASSIGN_ROLE": "promotes or ranks members", "COORDINATE_CO_OFFENDERS": "plans with co-offenders",
    "SHARE_TRADECRAFT": "detection-avoidance advice", "PAY_THIRD_PARTY": "pays a facilitator or producer",
    "ARRANGE_MEETING": "arranges an in-person meeting", "TRAVEL_TO_MEET": "travels to a meeting",
    "IN_PERSON_SEXUAL_ABUSE": "hands-on sexual abuse", "ADVERTISE_COMMERCIAL_SEX": "advertises a person for commercial sex",
    "ARRANGE_COMMERCIAL_SEX": "books or transports for commercial sex", "COLLECT_PROCEEDS": "collects commercial sex payments",
    "CONTROL_VICTIM": "harbouring, confiscation, drugs or weapons to control", "CONCEAL_OR_DESTROY_EVIDENCE": "deletes data, discards devices",
    "EVADE_DETECTION": "explicitly avoids detection", "OBSTRUCT_OR_TAMPER": "witness tampering", "FLEE": "flees",
    "RESP_REFUSE": "victim declines", "RESP_BLOCK": "victim blocks the account", "RESP_REPORT": "reports to platform, guardian or police",
    "RESP_DISCLOSE": "victim tells someone", "RESP_PLATFORM_ENFORCE": "platform removes or bans the account",
    "LE_RECEIVE_TIP": "police receive a tip", "LE_UNDERCOVER_ENGAGE": "an undercover persona messages the offender",
    "LE_SURVEIL": "surveillance", "LE_LEGAL_PROCESS": "subpoena or warrant", "LE_SEARCH_SEIZE": "search and seizure",
    "LE_FORENSIC_EXAM": "forensic examination", "LE_INTERVIEW": "interview", "LE_INTERDICT": "interdiction", "LE_ARREST": "arrest",
    "PROC_CHARGE": "charging document filed", "PROC_PLEA": "plea entered", "PROC_VERDICT": "verdict", "PROC_SENTENCE": "sentence imposed",
}
ACTIONS = [a for a in V.ACTION_CODES if a in _DEF]
CHANNEL_WORDS = {"sms": "sms", "text message": "sms", "text messages": "sms", "phone": "voice_call", "telephone": "voice_call",
                 "phone call": "voice_call", "email": "email", "e-mail": "email", "mail": "mail", "in person": "in_person"}

_DATE = {"type": "object", "required": ["x", "from", "to"], "properties": {
    "x": {"type": "string"}, "from": {"type": "string"}, "to": {"type": "string"},
    "p": {"type": "string", "enum": ["day", "month", "season", "year", "range"]}}}
SCHEMA = {
    "type": "object", "required": ["acts"],
    "properties": {"acts": {"type": "array", "items": {
        "type": "object", "required": ["s", "a", "by", "r"],
        "properties": {
            "s": {"type": "string"}, "a": {"type": "string", "enum": ACTIONS},
            "by": {"type": "string"}, "r": {"type": "string", "enum": list(V.ACTOR_ROLES)},
            "to": {"type": "array", "items": {"type": "object", "required": ["w", "r"], "properties": {
                "w": {"type": "string"}, "r": {"type": "string", "enum": list(V.TARGET_ROLES)}}}},
            "o": {"type": "string", "enum": list(V.OUTCOMES)},
            "d": _DATE,
            "pf": {"type": "object", "required": ["n"], "properties": {
                "n": {"type": "string"}, "m": {"type": "string", "enum": list(V.INTERACTION_MODES)},
                "au": {"type": "string", "enum": list(V.AUDIENCES)}}},
            "np": {"type": "string"},
            "af": {"type": "object", "required": ["c", "f"], "properties": {
                "c": {"type": "string", "enum": list(V.AFFORDANCES)}, "f": {"type": "string"}}},
            "h": {"type": "string", "enum": list(V.HARM_CODES)},
            "after": {"type": "string"},
        }}}},
}

PROMPT = """You code a federal court record for a research codebook. Read the ONE page below and list every act it describes.
Answer in compact JSON. For each act:
  s  = the first 8 to 12 words of the sentence that states the act, copied exactly from the page
  a  = the action code (list below)
  by = who acted, named by ROLE, never by personal name: "the defendant", "co-defendant 1", "co-conspirator 1",
       "minor victim 1", "adult victim 1", "an undercover agent", "law enforcement", "the court", "other users"
  r  = the actor's role
  to = who it was done to: [{"w": role name, "r": victim|recipient|counterparty|subject}]
  o  = outcome, if not simply completed
  d  = only if the sentence says when: {"x": those exact words, "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "p": day|month|year|range}
  pf = only if the act was done through a named app, site or service: {"n": its name, "m": through|from|to|acted_on, "au": one_to_one|group|public}
  np = a platform that is only mentioned, not used for the act
  af = only if the sentence names a platform FEATURE used for the act: {"c": class, "f": the feature's exact words}. A platform name alone is never a feature.
  h  = a harm code, only if the sentence documents that harm to the victim
  after = if the sentence says the act came after another act on this page, the first words of that act's sentence
Leave out every field that does not apply. Never guess. Skip legal boilerplate and statutes.
An undercover officer's messages are LE_UNDERCOVER_ENGAGE; the defendant's messages to an undercover persona are offender acts.

Action codes:
{codes}

Document type: {doc_type}. Page {page}.
PAGE:
<<<
{text}
>>>"""


def render_prompt(**fields: str) -> str:
    """PROMPT with its {codes}, {doc_type}, {page} and {text} slots filled (the JSON braces stay literal)."""
    out = PROMPT
    for k, v in fields.items():
        out = out.replace("{" + k + "}", v)
    return out


# --- model access -------------------------------------------------------------------------

def _get(path: str):
    with urllib.request.urlopen(MODELS["runtime"]["base_url"] + path, timeout=30) as r:
        return json.loads(r.read())


def check_model(coder: str) -> dict:
    spec = MODELS["coders"][coder]
    tags = {m["name"]: m["digest"] for m in _get("/api/tags")["models"]}
    have = tags.get(spec["model"])
    if have is None:
        raise SystemExit(f"{spec['model']} is not pulled (ollama pull {spec['model']})")
    if "sha256:" + have != spec["digest"]:
        raise SystemExit(f"{spec['model']}: local digest sha256:{have} differs from the pinned {spec['digest']}")
    return spec


class Cache:
    def __init__(self, path: Path = CACHE):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, model TEXT, digest TEXT, prompt_version TEXT,"
                        " response TEXT, seconds REAL)")

    def get(self, key: str) -> Optional[str]:
        row = self.db.execute("SELECT response FROM calls WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, spec: dict, response: str, seconds: float) -> None:
        self.db.execute("INSERT OR REPLACE INTO calls VALUES (?,?,?,?,?,?)",
                        (key, spec["model"], spec["digest"], PROMPT_VERSION, response, seconds))
        self.db.commit()


def ask(spec: dict, prompt: str, cache: Cache) -> dict:
    key = hashlib.sha256(json.dumps([spec["digest"], PROMPT_VERSION, MODELS["options"], prompt]).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return json.loads(hit)
    body = {"model": spec["model"], "messages": [{"role": "user", "content": prompt}], "stream": False,
            "format": SCHEMA, "options": MODELS["options"], "keep_alive": "30m"}
    if spec.get("think") is False:
        body["think"] = False
    req = urllib.request.Request(MODELS["runtime"]["base_url"] + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        content = json.loads(r.read())["message"]["content"]
    try:
        out = json.loads(content)
    except json.JSONDecodeError:
        out = {"acts": [], "unparsed": True}
    cache.put(key, spec, json.dumps(out), time.time() - t)
    return out


# --- from model answers to a bundle -------------------------------------------------------

_ABBREV = re.compile(r"(?:\b(?:Mr|Mrs|Ms|Dr|No|Nos|Inc|Co|Corp|Jr|Sr|St|v|vs|Ct|Cir|Supp|App|Stat|Sec|U\.S|U\.S\.C|e\.g|i\.e)|\b[A-Z])\.$")


def locate_sentence(page_text: str, start_words: str) -> Tuple[int, int, str]:
    """The sentence that begins with ``start_words``: offsets into the normalized page text.
    Exact match first, then case-insensitive; never fuzzy. Ambiguous starts are refused."""
    page_n, sw = E.normalize(page_text), E.normalize(start_words)
    if len(sw.split()) < 4:
        raise E.QuoteNotFound("first words too short")
    hay, needle = page_n, sw
    i = hay.find(needle)
    if i < 0:
        hay, needle = page_n.lower(), sw.lower()
        i = hay.find(needle)
        if i < 0:
            raise E.QuoteNotFound("first words not on this page")
    if hay.find(needle, i + 1) >= 0:
        raise E.QuoteNotFound("first words occur more than once on this page")
    end = len(page_n)
    for m in re.finditer(r"[.;!?](?=\s|$)", page_n[i + len(sw):]):
        k = i + len(sw) + m.end()
        if not _ABBREV.search(page_n[max(i, k - 8):k]):
            end = k
            break
    end = min(end, i + 700)
    return i, end, page_n[i:end]


_KEYS = {"s": "start", "a": "action", "by": "actor", "r": "actor_role", "o": "outcome", "d": "date",
         "np": "named_platform", "h": "harm"}


def expand(act: dict) -> dict:
    """Compact model keys to the long form used below."""
    out = {_KEYS.get(k, k): v for k, v in act.items()}
    if "to" in act:
        out["targets"] = [{"who": t.get("w", ""), "role": t.get("r")} for t in act.get("to") or []]
    if "pf" in act:
        pf = act["pf"] or {}
        out["platform"] = {"name": pf.get("n", ""), "mode": pf.get("m"), "audience": pf.get("au")}
    if "af" in act:
        af = act["af"] or {}
        out["affordance"] = {"class": af.get("c"), "feature": af.get("f", "")}
    out.setdefault("outcome", "completed")
    return out


_DOCKET_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})\s*$")
_DOCKET_KINDS = [  # entry text (after the entry number) -> procedure code; first match wins
    (re.compile(r"^\s*\d*\s*(?:SUPERSEDING )?(?:INDICTMENT|INFORMATION|COMPLAINT)\b"), "PROC_CHARGE"),
    (re.compile(r"\b(?:JURY )?VERDICT\b"), "PROC_VERDICT"),
    (re.compile(r"^\s*\d*\s*(?:AMENDED )?JUDGMENT\b|Sentencing held|SENTENCING held", re.I), "PROC_SENTENCE"),
    (re.compile(r"PLEA AGREEMENT|Change of Plea Hearing held|Plea entered|pleaded guilty|PLEA of guilty", re.I), "PROC_PLEA"),
    (re.compile(r"Notice of Arrest|Arrest of|Defendant arrested", re.I), "LE_ARREST"),
]


def docket_acts(text: str) -> dict:
    """Court-procedure acts from one docket page, deterministically: one per entry type and date.
    Each quote is the entry's date line and first text line; nothing else on a docket is coded."""
    lines = text.splitlines()
    acts, seen = [], set()
    for i, line in enumerate(lines):
        m = _DOCKET_DATE.match(line.strip())
        if not m or i + 1 >= len(lines):
            continue
        body = lines[i + 1].strip()
        for pat, code in _DOCKET_KINDS:
            if pat.search(body):
                day = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                if (code, day) in seen:
                    break
                seen.add((code, day))
                quote = E.normalize(line.strip() + " " + body)[:240]
                le = code == "LE_ARREST"
                acts.append({"quote": quote, "action": code, "actor": "law enforcement" if le else "the court",
                             "actor_role": "law_enforcement" if le else "court", "targets": [{"who": "the defendant", "role": "subject"}],
                             "outcome": "completed", "parser": True,
                             "date": {"x": line.strip(), "from": day.isoformat(), "to": day.isoformat(), "p": "day"}})
                break
    return {"acts": acts}


def _label(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    s = re.sub(r"\b(the|a|an|said|another)\b", " ", s)
    s = re.sub(r"\b(agents?|officers?|detectives?|police|fbi|hsi|investigators?)\b", "law enforcement", s)
    s = re.sub(r"\bdefendants\b", "defendant", s)
    return re.sub(r"\s+", " ", s).strip() or "unknown"


def _kind_status(label: str, role: str) -> Tuple[str, str]:
    if "undercover" in label or role == "undercover":
        return "persona", "undercover_persona"
    if "co defendant" in label or "codefendant" in label:
        return "person", "charged_defendant"
    if "co conspirator" in label or "coconspirator" in label:
        return "person", "uncharged_coconspirator"
    if "defendant" in label:
        return "person", "charged_defendant"
    if "victim" in label or "minor" in label or "child" in label:
        return "person", "named_victim"
    if "law enforcement" in label:
        return "organization", "law_enforcement"
    if "court" in label or "judge" in label:
        return "organization", "court"
    if role == "platform":
        return "organization", "platform_provider"
    if re.search(r"\b(users|members|others|customers|people|individuals|buyers)\b", label):
        return "collective", "third_party"
    return "person", "third_party"


_ALLOWED_ROLES = {fam: set(r) for fam, r in V.FAMILY_ROLES.items()}


def _date(d: Optional[dict], quote: str) -> Optional[dict]:
    if not d:
        return None
    try:
        lo, hi = date.fromisoformat(d.get("from") or d.get("earliest")), date.fromisoformat(d.get("to") or d.get("latest"))
    except (KeyError, ValueError, TypeError):
        return None
    if lo > hi or not (1990 <= lo.year <= 2030):
        return None
    expr = (d.get("x") or d.get("expression") or "").strip()
    if not expr or E.normalize(expr).lower() not in E.normalize(quote).lower():
        return None
    precision = d.get("p") or d.get("precision")
    precision = precision if precision in V.TIME_PRECISION else ("day" if lo == hi else "range")
    return {"expression": expr[:120], "precision": precision, "earliest": lo.isoformat(), "latest": hi.isoformat(),
            "basis": "date_range" if precision == "range" else "explicit_date", "status": "DIRECT"}


def assemble(case_id: str, sources: dict, answers: List[Tuple[dict, int, str, dict]], coder: str, spec: dict) -> Tuple[dict, Dict[str, str], List[str]]:
    """answers: (document, page number, page text, model answer). Returns (bundle, quotes, log)."""
    log: List[str] = []
    participants: Dict[str, dict] = {}
    labels: Dict[str, str] = {}
    passages: Dict[Tuple[str, int, int, int], str] = {}
    pass_list, quotes, events, relations = [], {}, [], []

    def who(label_raw: str, role: str) -> str:
        lab = _label(label_raw)
        if lab not in labels:
            ref = f"P{len(labels) + 1}"
            labels[lab] = ref
            kind, status = _kind_status(lab, role)
            participants[ref] = {"participant_ref": ref, "kind": kind, "_status": status, "_first": None}
        return labels[lab]

    for doc, page_no, text, ans in answers:
        page_events: List[Tuple[str, str]] = []
        for act in ans.get("acts", []):
            act = expand(act)
            try:
                if act.get("quote"):                       # the docket parser gives the whole entry text
                    start, end, qn = E.locate(text, act["quote"])
                else:
                    start, end, qn = locate_sentence(text, act.get("start") or "")
            except E.QuoteNotFound as exc:
                log.append(f"dropped {doc['doc_id']} p{page_no} {act.get('action')}: quote {exc}")
                continue
            if len(qn.split()) < 4:
                log.append(f"dropped {doc['doc_id']} p{page_no} {act.get('action')}: quote too short")
                continue
            action = act.get("action")
            if action not in _DEF:
                continue
            fam = V.FAMILY_OF[action]
            role = act.get("actor_role")
            if role not in _ALLOWED_ROLES[fam]:
                fixed = {"offender": "offender", "procedure": "court", "law_enforcement": "law_enforcement"}.get(fam)
                if fam == "response" and role not in _ALLOWED_ROLES[fam]:
                    log.append(f"dropped {doc['doc_id']} p{page_no} {action}: actor role {role} cannot perform it")
                    continue
                role = "undercover" if fam == "law_enforcement" and "undercover" in _label(act.get("actor", "")) else fixed
            actor = who(act.get("actor", ""), role)
            if participants[actor]["kind"] == "persona" and role != "undercover":
                log.append(f"dropped {doc['doc_id']} p{page_no} {action}: a persona can only act undercover")
                continue
            key = (doc["doc_id"], page_no, start, end)
            if key not in passages:
                pid = f"q{len(passages) + 1:04d}"
                passages[key] = pid
                ocr = next(p for p in doc["pages"] if p["pdf_page"] == page_no)["text_method"] == "ocr"
                pass_list.append({"passage_id": pid, "doc_id": doc["doc_id"], "pdf_page": page_no, "court_locator": None,
                                  "char_start": start, "char_end": end, "quote_sha256": E.sha256_text(qn),
                                  "quote_word_count": len(qn.split()), "source_status": V.DOC_TYPES[doc["doc_type"]][0],
                                  "verification": {"status": "VERIFIED", "method": "ocr_text_exact" if ocr else "text_layer_exact",
                                                   "checked_by": coder}})
                quotes[f"{coder}:{pid}"] = qn
            pid = passages[key]
            eid = f"e{len(events) + 1:03d}"
            targets = []
            for t in act.get("targets") or []:
                ref = who(t.get("who", ""), "")
                if ref != actor and t.get("role") in V.TARGET_ROLES and all(x["participant_ref"] != ref for x in targets):
                    targets.append({"participant_ref": ref, "role": t["role"]})
            e = {"event_id": eid, "action": action, "actor": {"participant_ref": actor, "role": role}, "co_actors": [],
                 "targets": targets, "unresolved_participants": [], "outcome": act.get("outcome") if act.get("outcome") in V.OUTCOMES else "unknown",
                 "description": f"{action.lower().replace('_', ' ')} by {actor}" + (f" toward {targets[0]['participant_ref']}" if targets else ""),
                 "support": [{"passage_id": pid, "facet": "action", "status": "DIRECT"}], "status": "DIRECT",
                 "time": {"assertions": []}, "repetition": {"kind": "single"}, "platform_mentions": [], "platform_interactions": [],
                 "channels": [], "affordances": [], "candidate_affordances": [], "access": [], "harms": [],
                 "review": {"status": "single_coder", "coders": [coder], "adjudicator": None}}
            if act.get("parser"):
                e["notes"] = "docket-parser"
            d = _date(act.get("date"), qn)
            if d:
                e["time"]["assertions"].append(dict(d, passage_ids=[pid]))
            plat = act.get("platform") or {}
            name = (plat.get("name") or "").strip()
            if name:
                ch = CHANNEL_WORDS.get(name.lower())
                if ch:
                    e["channels"].append({"channel": ch, "status": "DIRECT", "support": [{"passage_id": pid, "facet": "channel", "status": "DIRECT"}]})
                elif name.lower() in qn.lower():
                    key_name = re.sub(r"[^A-Za-z0-9 ._+\-]", "", name)[:60].strip()
                    if key_name and key_name[0].isalnum():
                        e["platform_interactions"].append({
                            "platform_surface": name[:80], "platform_key": key_name,
                            "mode": plat.get("mode") if plat.get("mode") in V.INTERACTION_MODES else "through",
                            "audience": plat.get("audience") if plat.get("audience") in V.AUDIENCES else "unknown",
                            "status": "DIRECT", "support": [{"passage_id": pid, "facet": "platform", "status": "DIRECT"}]})
            named = (act.get("named_platform") or "").strip()
            if named and named.lower() in qn.lower() and named.lower() not in CHANNEL_WORDS and not e["platform_interactions"]:
                e["platform_mentions"].append({"platform_surface": named[:80], "passage_ids": [pid]})
            aff = act.get("affordance") or {}
            feat = (aff.get("feature") or "").strip()
            if aff.get("class") in V.AFFORDANCES and feat and E.normalize(feat).lower() in qn.lower() and fam == "offender":
                e["affordances"].append({"affordance": aff["class"], "basis": "feature_stated", "feature_term": feat[:120],
                                         "platform_surface": (e["platform_interactions"][0]["platform_surface"] if e["platform_interactions"] else None),
                                         "status": "DIRECT", "support": [{"passage_id": pid, "facet": "feature", "status": "DIRECT"}]})
            harm = act.get("harm")
            victims = [t["participant_ref"] for t in targets if t["role"] == "victim"]
            if harm in V.HARM_CODES and victims and fam == "offender":
                vlab = next(k for k, v in labels.items() if v == victims[0])
                e["harms"].append({"harm": harm, "victim_ref": victims[0],
                                   "victim_kind": "minor" if re.search(r"\b(minor|child|girl|boy)\b", vlab) else
                                   ("adult" if "adult" in vlab else "unknown"),
                                   "status": "DIRECT", "support": [{"passage_id": pid, "facet": "action", "status": "DIRECT"}]})
                if harm == "HARM_OTHER":
                    e["harms"][-1]["other_label"] = "unspecified"
            for ref in [actor] + [t["participant_ref"] for t in targets]:
                if participants[ref]["_first"] is None:
                    participants[ref]["_first"] = pid
            events.append(e)
            page_events.append((eid, qn))
            after = E.normalize(act.get("after") or "").lower()
            if len(after.split()) >= 3:
                prior = next((x for x, qx in page_events[:-1] if qx.lower().startswith(after) or after in qx.lower()), None)
                if prior:
                    relations.append({"relation_id": f"r{len(relations) + 1:03d}", "type": "BEFORE", "from_event": prior, "to_event": eid,
                                      "basis": "explicit_sequence_language", "status": "DIRECT",
                                      "support": [{"passage_id": pid, "facet": "time", "status": "DIRECT"}]})
    parts = []
    for ref, p in participants.items():
        if p["_first"] is None:
            continue
        parts.append({"participant_ref": ref, "kind": p["kind"],
                      "legal_status": [{"status": p["_status"], "support": [{"passage_id": p["_first"], "facet": "legal_status", "status": "DIRECT"}]}]})
    tracks: Dict[str, dict] = {}
    kinds = {p["participant_ref"]: (p["kind"], p["legal_status"][0]["status"]) for p in parts}
    for e in events:
        fam = V.FAMILY_OF[e["action"]]
        victims = [t["participant_ref"] for t in e["targets"] if t["role"] == "victim"]
        personas = [t["participant_ref"] for t in e["targets"] if kinds.get(t["participant_ref"], ("",))[0] == "persona"]
        if fam == "procedure" or (fam == "law_enforcement" and not personas):
            tid, kind, anchor = "proc", "case_procedure", None
        elif victims:
            tid, kind, anchor = f"v-{victims[0]}", "victim", victims[0]
        elif personas or kinds.get(e["actor"]["participant_ref"], ("",))[0] == "persona":
            ref = personas[0] if personas else e["actor"]["participant_ref"]
            tid, kind, anchor = f"uc-{ref}", "undercover", ref
        else:
            tid, kind, anchor = f"net-{e['actor']['participant_ref']}", "co_offender_network", e["actor"]["participant_ref"]
        t = tracks.setdefault(tid, {"track_id": tid.lower(), "kind": kind, "event_ids": [], **({"anchor_ref": anchor} if anchor else {})})
        t["event_ids"].append(e["event_id"])
    bundle = {"schema_version": V.SCHEMA_VERSION, "codebook_version": V.CODEBOOK_VERSION, "case_id": case_id,
              "coding": {"coder_id": coder, "method": "agent", "model": f"{spec['model']}@{spec['digest']}",
                         "coded_on": date.today().isoformat(), "blind_to": ["other_coder_bundle", "gold"],
                         "note": f"{PROMPT_VERSION}; local model; page by page"},
              "documents": sources["documents"], "passages": pass_list, "participants": parts,
              "events": events, "relations": relations, "tracks": list(tracks.values())}
    return bundle, quotes, log


def repair(bundle: dict, text_root: Path, deny: List[str]) -> Tuple[dict, List[str]]:
    """Drop every event (and its relations) that breaks a validation rule, until the bundle is clean."""
    log: List[str] = []
    for _ in range(50):
        errs = errors(validate(bundle, text_root=text_root, deny_list=deny, require_verified=True))
        if not errs:
            return bundle, log
        bad_events = {m.group(1) for f in errs for m in [re.match(r"event:(e\d+)", f.where or "")] if m}
        bad_rel = {m.group(1) for f in errs for m in [re.match(r"relation:(r\d+)", f.where or "")] if m}
        if not bad_events and not bad_rel:
            raise SystemExit("unrepairable bundle: " + "; ".join(f"{f.code} {f.where}: {f.message}" for f in errs[:5]))
        for f in errs:
            log.append(f"dropped by {f.code} at {f.where}: {f.message[:120]}")
        bundle["events"] = [e for e in bundle["events"] if e["event_id"] not in bad_events]
        alive = {e["event_id"] for e in bundle["events"]}
        bundle["relations"] = [r for r in bundle["relations"] if r["relation_id"] not in bad_rel
                               and r["from_event"] in alive and r["to_event"] in alive]
        bundle["tracks"] = [dict(t, event_ids=[x for x in t["event_ids"] if x in alive]) for t in bundle["tracks"]]
        bundle["tracks"] = [t for t in bundle["tracks"] if t["event_ids"]]
        used = {p for e in bundle["events"] for p in [e["actor"]["participant_ref"], *[t["participant_ref"] for t in e["targets"]]]}
        bundle["participants"] = [p for p in bundle["participants"] if p["participant_ref"] in used]
    raise SystemExit("repair did not converge")


def pages_of(case_id: str, text_root: Path):
    sources = json.loads((text_root / case_id / "sources.json").read_text(encoding="utf-8"))
    for doc in sources["documents"]:
        for p in doc["pages"]:
            text = E.read_page(case_id, doc["doc_id"], p["pdf_page"], text_root)
            if text and text.strip():
                yield sources, doc, p["pdf_page"], text


def code_case(case_id: str, coder: str, text_root: Path, cache: Optional[Cache] = None, deny: Optional[List[str]] = None,
              progress=None) -> Tuple[dict, Dict[str, str], List[str]]:
    spec = check_model(coder)
    cache = cache or Cache()
    codes = "\n".join(f"{a}: {_DEF[a]}" for a in ACTIONS)
    answers, sources, coverage = [], None, []
    for sources, doc, page_no, full in pages_of(case_id, text_root):
        if doc["doc_type"] == "docket":
            ans, how = docket_acts(full), "docket parser"
        elif doc["doc_type"] in ("judgment", "amended_judgment") and BOILERPLATE.search(full):
            ans, how = {"acts": []}, "skipped: judgment form page"
        else:
            text = full[:MAX_PAGE_CHARS]
            prompt = render_prompt(codes=codes, doc_type=doc["doc_type"].replace("_", " "), page=str(page_no), text=text)
            ans, how = ask(spec, prompt, cache), "model" + (" (truncated)" if len(full) > MAX_PAGE_CHARS else "")
        coverage.append(f"page {doc['doc_id']} p{page_no}: {how}, {len(ans.get('acts', []))} acts")
        answers.append((doc, page_no, full, ans))
        if progress:
            progress(doc["doc_id"], page_no, len(ans.get("acts", [])))
    bundle, quotes, log = assemble(case_id, sources, answers, coder, spec)
    log = coverage + log
    bundle, rlog = repair(bundle, text_root, deny or [])
    return bundle, quotes, log + rlog


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("coder", choices=sorted(MODELS["coders"]))
    ap.add_argument("cases", nargs="+")
    ap.add_argument("--text-root", type=Path, default=E.text_root())
    ap.add_argument("--out", type=Path, default=E.REPO_ROOT / "local" / "coded")
    args = ap.parse_args(argv)
    cache = Cache()
    for case_id in args.cases:
        t = time.time()
        deny_path = args.text_root / case_id / "deny.json"
        deny = json.loads(deny_path.read_text()) if deny_path.is_file() else []
        bundle, quotes, log = code_case(case_id, args.coder, args.text_root, cache, deny)
        out = args.out / args.coder
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{case_id}.json").write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        (out / f"{case_id}.log").write_text("\n".join(log) + "\n", encoding="utf-8")
        store = E.load_quotes(case_id, args.text_root)
        store.update(quotes)
        E.save_quotes(case_id, store, args.text_root)
        print(f"{args.coder} {case_id}: {len(bundle['events'])} events, {len(bundle['relations'])} relations, "
              f"{sum(l.startswith('dropped') for l in log)} dropped, {time.time() - t:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
