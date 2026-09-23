"""Turn international press PDFs into English before the processor.

The PDF on disk stays in the original language. Ingest is local: English
sources (AFP, QPS, Europol, NCA) pass through, and Portuguese is translated with the
CTranslate2 model under ``models/translate-pt_en/``. No translation API.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

INTERNATIONAL_SOURCES = frozenset({"AFP", "QPS", "BRAZIL PF", "EUROPOL", "NCA"})

_KEEP_LINE = re.compile(
    r"^(?:Source:\s*https?://\S+|Publication date:\s*\S+)\s*$"
)
# PDF extract wraps long Source URLs onto the next line. That fragment has no
# spaces; translating it rewrites the slug before batching stitches it back.
_URL_FRAGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:%~?=&-]*$")
_URL = re.compile(r"https?://\S+")
_PT_WORDS = re.compile(
    r"\b(?:não|polícia|abuso|criança|crianças|operação|prisão|infantojuvenil|"
    r"também|através|apreensão|policial)\b",
    re.IGNORECASE,
)
_PT_ACCENT = re.compile(r"[áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]")
_DROP_TOKENS = frozenset({"</s>", "<unk>", "<s>"})
_MAX_CHARS = 480

_lock = threading.RLock()
_spm = None
_translator = None


class InternationalTranslationError(RuntimeError):
    """Local Portuguese-English translation could not run."""


def is_international_source(source: str | None) -> bool:
    key = (source or "").strip().upper().replace("_", " ")
    return key in INTERNATIONAL_SOURCES


def model_dir() -> Path:
    override = os.environ.get("CASELINKER_PT_EN_MODEL")
    if override:
        return Path(override)
    return (
        Path(__file__).resolve().parents[2]
        / "models"
        / "translate-pt_en"
        / "translate-pt_en-1_9"
    )


def looks_portuguese(text: str) -> bool:
    sample = _URL.sub(" ", text[:12000])
    return len(_PT_WORDS.findall(sample)) >= 2 or len(_PT_ACCENT.findall(sample)) >= 6


def normalize_international_text(
    text: str,
    source: str | None,
    *,
    translate=None,
) -> str:
    """Return English text for an international source.

    ``Source:`` and ``Publication date:`` lines are copied unchanged so case
    URLs and years survive. English text is returned unchanged. ``translate``
    is a test hook; production loads the local pt→en model.
    """
    if not text or not is_international_source(source):
        return text
    if not looks_portuguese(text):
        return text

    fn = translate if translate is not None else _translate_pt_to_en
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    body: list[str] = []

    def flush() -> None:
        if not body:
            return
        block = "".join(body)
        body.clear()
        out.append(_translate_block(block, fn))

    for line in lines:
        stripped = line.strip()
        if _KEEP_LINE.match(line.rstrip("\r\n")) or (
            stripped and " " not in stripped and _URL_FRAGMENT.match(stripped)
        ):
            flush()
            out.append(line)
        else:
            body.append(line)
    flush()
    return "".join(out)


def _translate_block(block: str, translate) -> str:
    if not block.strip():
        return block
    pieces = re.split(r"(\n+)", block)
    rendered: list[str] = []
    for piece in pieces:
        if piece == "" or not piece.strip():
            rendered.append(piece)
            continue
        leading = piece[: len(piece) - len(piece.lstrip())]
        trailing = piece[len(piece.rstrip()) :]
        core = piece.strip()
        translated = _translate_paragraph(core, translate)
        rendered.append(f"{leading}{translated}{trailing}")
    return "".join(rendered)


def _translate_paragraph(paragraph: str, translate) -> str:
    chunks = _chunks(paragraph)
    parts = [translate(chunk) for chunk in chunks]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _chunks(paragraph: str) -> list[str]:
    if len(paragraph) <= _MAX_CHARS:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        while len(sentence) > _MAX_CHARS:
            cut = sentence.rfind(" ", 0, _MAX_CHARS)
            if cut < 40:
                cut = _MAX_CHARS
            chunks.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if buf and len(buf) + 1 + len(sentence) > _MAX_CHARS:
            chunks.append(buf)
            buf = sentence
        elif buf:
            buf = f"{buf} {sentence}"
        else:
            buf = sentence
    if buf:
        chunks.append(buf)
    return chunks or [paragraph]


def _translate_pt_to_en(text: str) -> str:
    sp, translator = _load_model()
    tokens = [tok for tok in sp.encode(text, out_type=str) if tok]
    if not tokens:
        return text
    with _lock:
        translated = translator.translate_batch(
            [tokens],
            replace_unknowns=True,
            max_batch_size=32,
            batch_type="tokens",
            beam_size=4,
            num_hypotheses=1,
            length_penalty=0.2,
            return_scores=False,
        )
    hyp = [tok for tok in translated[0].hypotheses[0] if tok not in _DROP_TOKENS]
    if not hyp:
        raise InternationalTranslationError("local model returned no tokens")
    english = sp.decode_pieces(hyp).replace("▁", " ")
    english = re.sub(r"\s+", " ", english).strip()
    if not english:
        raise InternationalTranslationError("local model returned empty text")
    return english


def _load_model():
    global _spm, _translator
    with _lock:
        if _spm is not None and _translator is not None:
            return _spm, _translator
        directory = model_dir()
        spiece = directory / "sentencepiece.model"
        weights = directory / "model"
        if not spiece.is_file() or not weights.is_dir():
            raise InternationalTranslationError(
                "Portuguese-English model is not on disk at "
                f"{directory}. International ingest translates locally and "
                "does not call a translation API. Unpack translate-pt_en-1_9 "
                "into models/translate-pt_en/."
            )
        import ctranslate2
        import sentencepiece as spm

        processor = spm.SentencePieceProcessor(model_file=str(spiece))
        translator = ctranslate2.Translator(
            str(weights),
            device="cpu",
            inter_threads=1,
            intra_threads=1,
            compute_type="int8",
        )
        _spm = processor
        _translator = translator
        return _spm, _translator
