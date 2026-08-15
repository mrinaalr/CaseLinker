from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

import scripts.quality.check_traceability as traceability
from scripts.quality.check_traceability import MANIFEST_PATH, main, validate_traceability

ROOT = Path(__file__).resolve().parents[2]


def _manifest() -> dict[str, object]:
    value = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _resign(value: dict[str, object]) -> None:
    unhashed = dict(value)
    unhashed.pop("manifest_sha256", None)
    canonical = json.dumps(
        unhashed,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    value["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()


def test_repository_traceability_manifest_is_complete_and_valid() -> None:
    value = _manifest()

    assert validate_traceability(ROOT, value) == ()
    assert main() == 0


def test_traceability_rejects_tampered_identity_missing_path_and_adr_gap() -> None:
    value = _manifest()
    value["manifest_sha256"] = "0" * 64
    value["milestones"][0]["implementation"][0] = "missing.py"
    value["milestones"][0]["adrs"] = []

    findings = validate_traceability(ROOT, value)

    assert "manifest_sha256 does not identify the canonical manifest" in findings
    assert any("does not identify a regular file" in finding for finding in findings)
    assert "ADR traceability must cover every and only docs/adr/*.md file" in findings


def test_traceability_rejects_non_object() -> None:
    assert validate_traceability(ROOT, []) == ("manifest must be an object with string keys",)


def test_traceability_rejects_invalid_top_level_contract() -> None:
    value = _manifest()
    value["unknown"] = True
    del value["implementation_checkpoint"]
    value["schema_version"] = "2.0"
    value["upstream_baseline"] = "ABC"
    value["manifest_sha256"] = "invalid"
    value["milestones"] = []

    findings = validate_traceability(ROOT, value)

    assert "manifest has unknown fields: unknown" in findings
    assert "manifest is missing fields: implementation_checkpoint" in findings
    assert "schema_version must equal 1.0" in findings
    assert "upstream_baseline must be a full lowercase Git object ID" in findings
    assert "manifest_sha256 must be a lowercase SHA-256 digest" in findings
    assert "milestones must be a non-empty array" in findings


def test_traceability_rejects_malformed_milestone_and_duplicate_inputs() -> None:
    value = _manifest()
    milestones = value["milestones"]
    assert isinstance(milestones, list)
    malformed = deepcopy(milestones[0])
    assert isinstance(malformed, dict)
    malformed["id"] = "M99"
    malformed["status"] = "released"
    malformed["title"] = ""
    malformed["commits"] = ["bad", milestones[0]["commits"][0]]
    malformed["implementation"] = [milestones[0]["implementation"][0]]
    malformed["tests"] = "not-an-array"
    malformed["adrs"] = []
    malformed["extra"] = True
    milestones.append(malformed)
    _resign(value)

    findings = validate_traceability(ROOT, value)

    assert any("fields do not match" in finding for finding in findings)
    assert any("status must equal" in finding for finding in findings)
    assert any("title must be" in finding for finding in findings)
    assert any("invalid Git object ID" in finding for finding in findings)
    assert any("commits repeats" in finding for finding in findings)
    assert any("implementation repeats" in finding for finding in findings)
    assert any("tests must be" in finding for finding in findings)
    assert any("milestone IDs" in finding for finding in findings)


def test_traceability_requires_exact_ordered_git_history() -> None:
    value = _manifest()
    milestones = value["milestones"]
    assert isinstance(milestones, list)
    commits = milestones[0]["commits"]
    assert isinstance(commits, list)
    commits[0], commits[1] = commits[1], commits[0]
    _resign(value)

    findings = validate_traceability(ROOT, value)

    assert "milestone commits must exactly cover the ordered proposal history" in findings


def test_traceability_main_rejects_arguments_and_load_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="does not accept arguments"):
        main(["unexpected"])

    monkeypatch.setattr(traceability, "MANIFEST_PATH", Path("missing-traceability.json"))
    assert main() == 2
