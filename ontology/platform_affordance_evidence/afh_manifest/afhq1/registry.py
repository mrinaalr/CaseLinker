"""Merge dated capability research (config/capability_sources/*.yaml) into config/platforms.yaml.

Research rows give, per (platform, capability): native yes/partial/no, default_on, first_available,
ended, confidence (documented / approximate / uncertain) and dated evidence. Merge rules:

- ephemerality and generative_synthesis count only when native is "yes": live voice, expiring share
  links and creator-side texture tools are not auto-deleting messages or image synthesis of people.
- the other classes count "yes" and "partial" (flagged native: partial).
- first_available null with native yes/partial: since = platform launch year, date_confidence uncertain.
- labels the research did not cover keep their platforms-1 row, marked needs_author_check.

Run: python -m afhq1.registry  (from ontology/platform_affordance_evidence/afh_manifest)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

import yaml

from .snapshot import RESEARCH

SOURCES = RESEARCH / "config" / "capability_sources"
PLATFORMS = RESEARCH / "config" / "platforms.yaml"
STRICT_NATIVE = {"ephemerality", "generative_synthesis"}
# contact_discovery is "on for every use" only where meeting strangers is the core function
# (random chat, dating, game matchmaking, classifieds). Feed suggestions (People You May Know,
# Quick Add) are shown by default, but a documented contact may have started offline.
CONTACT_DISCOVERY_DEFAULT_FAMILIES = {"anonymous_chat", "dating", "game", "classifieds", "chat_room"}
# Coding decisions applied on top of the research rows (each is recorded in the merged row).
OVERRIDES = {
    ("Snapchat", "generative_synthesis"): {"first_available": "2023-08", "note_override":
        "research coded 2015 AR Lenses as manipulation; AfH GenerativeSynthesis means generative AI, so dated to Dreams (2023-08)"},
}
CLASS_KEYS = ("anonymity", "ephemerality", "contact_discovery", "unmonitored_communication",
              "distribution_infrastructure", "generative_synthesis")


def _year(v):
    if v in (None, "", "null"):
        return None
    m = re.match(r"^(\d{4})", str(v))
    return int(m.group(1)) if m else None


def _native(v) -> str:
    if v is True:
        return "yes"
    if v is False:
        return "no"
    return str(v or "no").lower()


def research_rows() -> Dict[str, dict]:
    out = {}
    for path in sorted(SOURCES.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for label, row in (doc.get("platforms") or {}).items():
            out[label] = {**row, "_file": path.name}
    return out


def merge() -> dict:
    current = yaml.safe_load(PLATFORMS.read_text(encoding="utf-8"))
    research = research_rows()
    research_rows_cache = research
    merged = {}
    for label, row in current["platforms"].items():
        new = {k: v for k, v in row.items() if k not in ("capabilities", "note")}
        if label not in research_rows_cache:
            if row.get("note"):
                new["note"] = row["note"]
        r = research.get(label)
        if r is None:
            caps = {k: {"since": v, "default_on": False, "native": "yes", "confidence": "needs_author_check"}
                    for k, v in (row.get("capabilities") or {}).items()}
            if row.get("capabilities") is not None or caps:
                new["capabilities"] = caps
            if caps:
                new["basis"] = "platforms-1 (not covered by dated research)"
            merged[label] = new
            continue
        launched = _year(r.get("launched"))
        new["launched"] = launched
        if _year(r.get("ended")):
            new["until"] = _year(r.get("ended"))
        caps = {}
        for key in CLASS_KEYS:
            c = dict((r.get("capabilities") or {}).get(key) or {})
            override = OVERRIDES.get((label, key))
            if override:
                c.update({k: v for k, v in override.items() if k != "note_override"})
            native = _native(c.get("native"))
            if native == "no" or (key in STRICT_NATIVE and native != "yes"):
                continue
            since = _year(c.get("first_available"))
            date_conf = c.get("confidence") or "uncertain"
            if since is None:
                since, date_conf = launched, "uncertain"
            if since is None:
                continue
            caps[key] = {
                "since": since,
                "first_available": str(c.get("first_available")) if c.get("first_available") else None,
                "ended": _year(c.get("ended")),
                "native": native,
                "default_on": str(c.get("default_on")).lower() in ("yes", "true") and (
                    key != "contact_discovery" or row.get("family") in CONTACT_DISCOVERY_DEFAULT_FAMILIES),
                "confidence": date_conf,
                "sources": len(c.get("evidence") or []),
                **({"override": override["note_override"]} if override else {}),
            }
        new["capabilities"] = caps
        new["basis"] = f"capability_sources/{r['_file']}"
        merged[label] = new
    return {"version": "platforms-2", "basis_default": "dated research; see capability_sources/", "platforms": merged}


HEADER = """# Platform registry for the AfH 2.0 Q1 manifest. Generated by afhq1/registry.py from
# config/capability_sources/*.yaml (dated research, 2026-11-17) and platforms-1 for labels the
# research did not cover. Edit the sources, then regenerate; do not hand-edit capability rows.
#
# status: specific | technology | generic | ambiguous_alias | excluded (see README).
# capabilities.<class>: since (first year natively available), first_available (as sourced),
#   ended, native (yes | partial), default_on (every use passes through it by design),
#   confidence (documented | approximate | uncertain | needs_author_check), sources (count).
# Capability rows never count as evidence that an offender used the capability.
"""


def write() -> Path:
    doc = merge()
    PLATFORMS.write_text(HEADER + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    return PLATFORMS


if __name__ == "__main__":
    print(write())


def check_urls(timeout: int = 12) -> dict:
    """HEAD (then GET) every cited evidence URL; record HTTP status only. Reachability, not content."""
    import json
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    urls = sorted({e["url"] for r in research_rows().values()
                   for c in (r.get("capabilities") or {}).values() if isinstance(c, dict)
                   for e in (c.get("evidence") or []) if isinstance(e, dict) and e.get("url")})

    def status(url: str) -> str:
        for method in ("-I", "-r0-0"):
            out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-L", "--max-time", str(timeout),
                                  "-A", "Mozilla/5.0 (research link check)", method, url], capture_output=True, text=True)
            code = out.stdout.strip() or "000"
            if code.startswith(("2", "3")):
                return code
        return code

    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = dict(zip(urls, pool.map(status, urls)))
    path = SOURCES / "url_check.json"
    path.write_text(json.dumps({"checked_urls": len(codes), "status": codes}, indent=1, sort_keys=True) + "\n")
    return codes
