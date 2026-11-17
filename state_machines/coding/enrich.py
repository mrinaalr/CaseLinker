"""Deterministic coding of an act's sentence: everything the model is not asked for.

The model names which sentences state acts and their action codes (``coder.PROMPT``). These rules
read the same sentence for the rest, so each field is auditable and identical for both coders:

    targets        victim, undercover persona and recipient mentions ("Minor Victim 1", "MV-1",
                   "an undercover agent", "other users")
    date           the first date the sentence states ("on or about May 2, 2020", "In June 2020",
                   "05/02/2020"), with its exact words and real calendar bounds
    platform       a named service the act went through ("through the Kitebox application", "on Kitebox")
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
_PERSONA = re.compile(r"\b(?:an? |the )?undercover (?:agent|officer|employee|detective|persona)\b|\bUC\b|\bOCE\b", re.I)
_RECIPIENTS = re.compile(r"\b(?:other (?:users|members|people|individuals)|\d+ (?:other )?(?:users|members|people)|the (?:group|members))\b", re.I)
_SEQ = re.compile(r"^(?:After|Following|Then|Thereafter|Later|Next|Subsequently|In response|Afterward|Afterwards|Shortly after|"
                  r"The next day|Within (?:a|one|two|\d+) (?:day|days|hour|hours))\b", re.I)
_THEN = re.compile(r"^[^,]{0,80}\b(?:then|thereafter|subsequently|in response)\b", re.I)
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
FEATURES = {   # class -> phrases a sentence must contain for level C (rule B0)
    "anonymity": ["new account under a different name", "new account under a false name", "fake profile", "false name", "fake name",
                  "fictitious name", "different name", "burner phone", "anonymous account", "conceal his identity", "hide his identity",
                  "Tor", "VPN"],
    "ephemerality": ["disappearing-message", "disappearing message", "view-once", "view once", "self-destructing", "expiring messages",
                     "messages set to disappear", "disappear after"],
    "contact_discovery": ["public group search", "search feature", "public group", "public post", "friend suggestion",
                          "recommended", "people nearby", "location feature", "follower list"],
    "unmonitored_communication": ["encrypted", "private messages", "private direct messages", "secret chat", "hidden from his parents",
                                  "hidden from her parents", "vault app"],
    "distribution_infrastructure": ["group chat", "shared link", "cloud storage", "uploaded", "file-sharing", "peer-to-peer", "torrent",
                                    "website", "channel with"],
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
    for m in _VICTIM.finditer(sentence):
        label = f"minor victim {m.group(1)}" if m.group(1) else "minor victim 1"
        if all(t["who"] != label for t in out):
            out.append({"who": label, "role": "victim"})
        break
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


def platform(sentence: str) -> Optional[dict]:
    for m in [*_PLATFORM.finditer(sentence), *_PLATFORM_IN.finditer(sentence)]:
        name = m.group("n").strip()
        first = name.split()[0]
        if first in _NOT_PLATFORM or len(name) < 3:
            continue
        mode = "to" if re.search(r"\b(?:continue|move|moved|switch|switched)\b[^.]*\b(?:on|to|onto)\s+(?:the\s+)?" + re.escape(name), sentence) else "through"
        audience = "group" if re.search(r"\bgroup\b", sentence, re.I) else ("public" if re.search(r"\bpublic\b", sentence, re.I) else "one_to_one")
        return {"n": name, "m": mode, "au": audience}
    return None


def feature(sentence: str) -> Optional[Tuple[str, str]]:
    low = sentence.lower()
    for cls, phrases in FEATURES.items():
        for ph in phrases:
            i = low.find(ph.lower())
            if i >= 0:
                return cls, sentence[i:i + len(ph)]
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
            f = feature(sentence)
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
    if (_SEQ.search(sentence.strip()) or _THEN.search(sentence)) and not out.get("after"):
        out["after"] = "__previous__"
        out["after_hint"] = sentence.split(",")[0][:120]
    return out
