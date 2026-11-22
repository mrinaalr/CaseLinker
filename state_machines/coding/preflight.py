"""Read-only check that the ids for one case agree.

A case can be named four ways: the release id, the text-directory id, the
coder-bundle id, and the id in the collected PDF name (``workflow.COLLECTED_AS``).
They should be the same string. Each difference is reported as an alias. The
command reads file names and the ``case_id`` field of ``sources.json`` and of a
coder bundle. It does not open page text, and it does not rename or rewrite an id.

When a ``fp-1`` fingerprint table is supplied, each PACER id (the case id and,
where ``COLLECTED_AS`` differs, the id written on the PDF) is looked up in that
table. A stored id whose current fingerprint is not the one recorded at
collection, or which has no ``fp-1`` row, is reported. So is one fingerprint
shared by several of those ids. The table is optional. Without it, only the
string aliases are checked.

The link itself is a plain string. ``collector/pacer/cases2records.py`` names
each download ``pacer -- {corpus_id} -- {doc type}.pdf``, and ``corpus_id`` is
the press-release id copied onto the case spec. ``COLLECTED_AS`` is a hand map
from a later press-release id to that PDF id. Neither stores a fingerprint or a
docket. A later ingest that mints ids from the article fingerprint reuses an id
only when that text is already stored under it. It does not rewrite the PDF
names or this map. The files stay on the old string. Aligning them after a
renumber needs a stable key (the fingerprint, or the docket on the PACER
manifest) stored with the download. This command only reports the mismatch.

    python -m state_machines.coding.pipeline preflight <case_id> [...] --text-root DIR --out DIR
        [--fingerprints rows.json] [--collected-fingerprints map.json]

The live illustration, checked as ids only: release ``ncmec_2025_1026``, local
text and bundles ``ncmec_2025_1035``, ``COLLECTED_AS`` ``ncmec_2025_1116``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.coding.workflow import COLLECTED_AS

FP_VERSION = "fp-1"


def _case_id_of(path: Path) -> Optional[str]:
    """The ``case_id`` field, or None. The rest of the file is not used."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and isinstance(data.get("case_id"), str):
        return data["case_id"]
    return None


def _text_dir_id(case_id: str, text_root: Path) -> Optional[str]:
    direct = text_root / case_id
    if direct.is_dir():
        return case_id
    if not text_root.is_dir():
        return None
    for child in sorted(p for p in text_root.iterdir() if p.is_dir()):
        sources = child / "sources.json"
        if sources.is_file() and _case_id_of(sources) == case_id:
            return child.name
    return None


def _bundle_ids(case_id: str, out_dir: Path) -> Dict[str, Optional[str]]:
    found = {}
    for coder in ("coder_A", "coder_B"):
        direct = out_dir / coder / f"{case_id}.json"
        if direct.is_file():
            found[coder] = case_id
            continue
        folder = out_dir / coder
        stem = None
        if folder.is_dir():
            for path in sorted(folder.glob("*.json")):
                if _case_id_of(path) == case_id:
                    stem = path.stem
                    break
        found[coder] = stem
    return found


def _pacer_ids(case_ids: List[str], collected: Dict[str, str]) -> List[str]:
    """The press-release id and, when the PDF was named with another id, that id too."""
    out: List[str] = []
    for case_id in case_ids:
        if case_id not in out:
            out.append(case_id)
        alias = collected.get(case_id)
        if alias and alias not in out:
            out.append(alias)
    return out


def fingerprint_checks(case_ids: List[str], table: List[dict], *,
                       collected_fingerprints: Optional[Dict[str, str]] = None,
                       collected_as: Optional[Dict[str, str]] = None) -> dict:
    """Compare PACER ids with an ``fp-1`` fingerprint table. Nothing is written.

    ``table`` rows are ``case_id``, ``fingerprint``, and ``normalization_version``.
    ``collected_fingerprints`` is the digest recorded for that id when the PACER
    file was collected, keyed by the stored id. A row from another normalization
    is not a current ``fp-1`` mapping.
    """
    collected_fingerprints = collected_fingerprints or {}
    collected = COLLECTED_AS if collected_as is None else collected_as
    current: Dict[str, str] = {}
    other_version: Dict[str, str] = {}
    for row in table:
        case_id = row.get("case_id") or ""
        version = row.get("normalization_version") or FP_VERSION
        if not case_id:
            continue
        if version != FP_VERSION:
            other_version.setdefault(case_id, version)
            continue
        current[case_id] = row.get("fingerprint") or ""
    mismatches = []
    for stored in _pacer_ids(case_ids, collected):
        collected_fp = collected_fingerprints.get(stored) or ""
        if stored in other_version and stored not in current:
            mismatches.append({
                "case_id": stored, "kind": "fingerprint_other_version",
                "collected_fingerprint": collected_fp, "current_fingerprint": "",
                "normalization_version": other_version[stored],
            })
            continue
        now = current.get(stored)
        if now is None:
            mismatches.append({
                "case_id": stored, "kind": "fingerprint_none",
                "collected_fingerprint": collected_fp, "current_fingerprint": "",
            })
        elif collected_fp and collected_fp != now:
            mismatches.append({
                "case_id": stored, "kind": "fingerprint_different",
                "collected_fingerprint": collected_fp, "current_fingerprint": now,
            })
    groups: Dict[str, List[str]] = {}
    for stored in _pacer_ids(case_ids, collected):
        digest = current.get(stored)
        if digest:
            groups.setdefault(digest, []).append(stored)
    shared = [{"fingerprint": digest, "case_ids": ids} for digest, ids in sorted(groups.items()) if len(ids) > 1]
    return {"normalization_version": FP_VERSION, "mismatches": mismatches, "shared": shared}


def preflight(case_ids: List[str], text_root: Path, out_dir: Path, *,
              release_root: Optional[Path] = None,
              collected_as: Optional[Dict[str, str]] = None,
              fingerprint_table: Optional[List[dict]] = None,
              collected_fingerprints: Optional[Dict[str, str]] = None) -> dict:
    """Aliases among release id, text-dir id, coder-bundle id and the collected PDF id.

    ``ok`` is true when every supplied case agrees on all four and, if a
    fingerprint table was passed, none of the fingerprint checks fire. A missing
    text directory or bundle is reported too. No page file is opened and no id
    is rewritten.
    """
    collected = COLLECTED_AS if collected_as is None else collected_as
    aliases = []
    for case_id in case_ids:
        if release_root is not None and not (release_root / "cases" / f"{case_id}.json").is_file():
            cases = release_root / "cases"
            if cases.is_dir():
                for path in sorted(cases.glob("*.json")):
                    if _case_id_of(path) == case_id and path.stem != case_id:
                        aliases.append({"case_id": case_id, "kind": "release_file", "release_id": case_id,
                                        "other_id": path.stem})
                        break
        text_id = _text_dir_id(case_id, text_root)
        if text_id is None:
            aliases.append({"case_id": case_id, "kind": "text_dir_missing", "release_id": case_id, "other_id": ""})
        elif text_id != case_id:
            aliases.append({"case_id": case_id, "kind": "text_dir", "release_id": case_id, "other_id": text_id})
        bundles = _bundle_ids(case_id, out_dir)
        seen = set()
        for coder, stem in bundles.items():
            if stem is None:
                aliases.append({"case_id": case_id, "kind": "coder_bundle_missing", "release_id": case_id,
                                "other_id": coder})
            elif stem != case_id and stem not in seen:
                seen.add(stem)
                aliases.append({"case_id": case_id, "kind": "coder_bundle", "release_id": case_id, "other_id": stem})
        pdf_id = collected.get(case_id, case_id)
        if pdf_id != case_id:
            aliases.append({"case_id": case_id, "kind": "collected_as", "release_id": case_id, "other_id": pdf_id})
    report = {"ok": not aliases, "aliases": aliases}
    if fingerprint_table is not None:
        fingerprints = fingerprint_checks(
            case_ids, fingerprint_table, collected_fingerprints=collected_fingerprints, collected_as=collected)
        report["fingerprints"] = fingerprints
        if fingerprints["mismatches"] or fingerprints["shared"]:
            report["ok"] = False
    return report
