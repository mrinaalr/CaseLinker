"""International ingest text stays English without a translation API."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INGEST = ROOT / "src" / "Ingestion Layer"
if str(INGEST) not in sys.path:
    sys.path.insert(0, str(INGEST))

import international_text as it  # noqa: E402


PT_ARTICLE = """PF prende homem por abuso
Publication date: 2026-09-01
Source: https://www.gov.br/pf/pt-br/assuntos/noticias/2026/09/exemplo
A Polícia Federal prendeu um homem por abuso sexual infantojuvenil na operação.
"""

EN_ARTICLE = """Queensland man jailed
Publication date: 2026-08-07
Source: https://www.afp.gov.au/news-centre/media-release/queensland-man-jailed
He was sentenced for child exploitation offences.
"""


def test_english_international_text_is_unchanged():
    calls = []

    def _boom(_text):
        calls.append(1)
        return "should not run"

    out = it.normalize_international_text(EN_ARTICLE, "AFP", translate=_boom)
    assert out == EN_ARTICLE
    assert calls == []


def test_non_international_portuguese_is_unchanged():
    out = it.normalize_international_text(PT_ARTICLE, "DOJ CEOS", translate=lambda s: s.upper())
    assert out == PT_ARTICLE


def test_portuguese_translation_keeps_provenance_lines():
    out = it.normalize_international_text(PT_ARTICLE, "BRAZIL PF", translate=lambda s: s.upper())
    assert "Source: https://www.gov.br/pf/pt-br/assuntos/noticias/2026/09/exemplo" in out
    assert "Publication date: 2026-09-01" in out
    assert "POLÍCIA FEDERAL" in out
    assert "A Polícia Federal prendeu" not in out


def test_missing_model_raises_without_network(monkeypatch, tmp_path):
    monkeypatch.setenv("CASELINKER_PT_EN_MODEL", str(tmp_path / "missing"))
    try:
        it.normalize_international_text(PT_ARTICLE, "BRAZIL PF")
    except it.InternationalTranslationError as exc:
        assert "does not call a translation API" in str(exc)
    else:
        raise AssertionError("expected a local-model error")


def test_local_model_is_deterministic_when_present():
    if not (it.model_dir() / "sentencepiece.model").is_file():
        return
    sample = (
        "Publication date: 2026-09-01\n"
        "Source: https://www.gov.br/pf/pt-br/assuntos/noticias/2026/09/exemplo\n"
        "A Polícia Federal prendeu um homem por armazenamento de material de abuso sexual infantojuvenil.\n"
    )
    first = it.normalize_international_text(sample, "BRAZIL PF")
    second = it.normalize_international_text(sample, "BRAZIL PF")
    assert first == second
    assert "Source: https://www.gov.br/pf/pt-br/assuntos/noticias/2026/09/exemplo" in first
    assert "Publication date: 2026-09-01" in first
    lowered = first.lower()
    assert "police" in lowered or "federal" in lowered
    assert "arrest" in lowered or "man" in lowered
