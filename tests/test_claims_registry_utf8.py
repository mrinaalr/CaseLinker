"""The PR A carry-over: paper claims registry must be well-formed UTF-8."""

from __future__ import annotations

from pathlib import Path


def test_claims_registry_is_utf8_and_restores_en_dashes():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify" / "paper" / "claims_registry.py"
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    assert "\ufffd" not in text
    assert b"\xe2\xff\xff" not in raw
    assert "Corpus timespan is 2002–2026." in text
    assert "3,128 platform–case records." in text
    assert "N=7,426 – no case documents exploitation without initial contact." in text
