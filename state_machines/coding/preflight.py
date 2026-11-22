"""Read-only check that the ids for one case agree.

A case can be named four ways: the release id, the text-directory id, the
coder-bundle id, and the id in the collected PDF name (``workflow.COLLECTED_AS``).
They should be the same string. Each difference is reported as an alias. The
command reads file names and the ``case_id`` field of ``sources.json`` and of a
coder bundle. It does not open page text.

    python -m state_machines.coding.pipeline preflight <case_id> [...] --text-root DIR --out DIR

The live illustration, checked as ids only: release ``ncmec_2025_1026``, local
text and bundles ``ncmec_2025_1035``, ``COLLECTED_AS`` ``ncmec_2025_1116``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.coding.workflow import COLLECTED_AS


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


def preflight(case_ids: List[str], text_root: Path, out_dir: Path, *,
              release_root: Optional[Path] = None,
              collected_as: Optional[Dict[str, str]] = None) -> dict:
    """Aliases among release id, text-dir id, coder-bundle id and the collected PDF id.

    ``ok`` is true when every supplied case agrees on all four. A missing text
    directory or bundle is reported too. No page file is opened.
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
    return {"ok": not aliases, "aliases": aliases}
