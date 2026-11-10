"""Checksum-pinned data must survive checkout byte for byte on every platform (#55).

``data/gazetteer/`` and ``data/agency_registry/`` are pinned by SHA-256 over raw
bytes. A Windows clone with git's default ``core.autocrlf`` rewrote their LF
endings to CRLF, the digests stopped matching, and every grounding test failed at
the gate before any grounding logic ran. The fix is a ``.gitattributes`` rule that
marks those paths ``-text`` so git never converts them.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "src" / "Processing Layer"
PINNED_DIRS = ("data/gazetteer", "data/agency_registry")


def _pinned_files(rel: str) -> list[Path]:
    d = ROOT / rel
    manifest = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
    return [d / "MANIFEST.json", *(d / name for name in manifest["files"])]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def _in_git_checkout() -> bool:
    if shutil.which("git") is None:
        return False
    try:
        return _git("rev-parse", "--is-inside-work-tree").strip() == "true"
    except subprocess.CalledProcessError:
        return False


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROC / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def _crlf_copy(rel: str, tmp_path: Path) -> Path:
    """What a default Windows checkout did to the directory: LF becomes CRLF in every file."""
    dst = tmp_path / Path(rel).name
    dst.mkdir()
    for src in _pinned_files(rel):
        (dst / src.name).write_bytes(src.read_bytes().replace(b"\n", b"\r\n"))
    return dst


def test_pinned_data_is_marked_no_conversion():
    """Fails without .gitattributes: git would then rewrite these bytes on Windows."""
    if not _in_git_checkout():
        pytest.skip("not a git checkout; attributes cannot be queried")
    paths = [str(p.relative_to(ROOT)) for rel in PINNED_DIRS for p in _pinned_files(rel)]
    rows = _git("check-attr", "text", "--", *paths).splitlines()
    bad = [row for row in rows if not row.endswith(": text: unset")]
    assert not bad, "checksum-pinned files git may still convert:\n" + "\n".join(bad)


def test_pinned_files_committed_with_lf_only():
    """-text stops conversion both ways, so the committed bytes themselves must stay LF."""
    with_cr = [p.name for rel in PINNED_DIRS for p in _pinned_files(rel) if b"\r" in p.read_bytes()]
    assert not with_cr, f"pinned files containing carriage returns: {with_cr}"


def test_crlf_gazetteer_fails_the_pin(tmp_path):
    lg = _load("location_grounding")
    with pytest.raises(lg.GazetteerError, match="checksum mismatch"):
        lg.require_gazetteer(_crlf_copy("data/gazetteer", tmp_path))


def test_crlf_agency_registry_fails_the_pin(tmp_path):
    ag = _load("agency_grounding")
    with pytest.raises(ag.AgencyRegistryError, match="Checksum mismatch"):
        ag.require_agency_registry(_crlf_copy("data/agency_registry", tmp_path))
