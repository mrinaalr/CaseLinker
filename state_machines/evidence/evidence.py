"""Source evidence: page text, normalization, quote location and verification.

Page text and quote text contain the names in the court record, so they live in a
local store outside git (``local/pacer_text/`` or ``$CASELINKER_PACER_TEXT``):

    <root>/<case_id>/<doc_id>/p0001.txt     page text as extracted (text layer or OCR)
    <root>/<case_id>/quotes.json            {passage_id: quote}

Committed bundles hold only locators and SHA-256 hashes of the *normalized* text, so
anyone with the same PDFs can rebuild the store and re-verify every passage.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "­": ""})
_WS = re.compile(r"\s+")


def _join_line_hyphen(text: str) -> str:
    """Drop a hyphen that exists only because a word was broken across a line."""
    return re.sub(r"(?<=[A-Za-z0-9])-\r?\n[ \t]*(?=[A-Za-z0-9])", "", text)


def normalize(text: str, *, join_line_hyphen: bool = False) -> str:
    """NFKC, straight quotes, soft hyphens removed, whitespace collapsed. Case is kept.

    The default is the historical hyphen handling: a line break becomes a space
    and the hyphen stays. Flags-off page hashes and quote offsets use that
    default. ``join_line_hyphen`` drops a hyphen that exists only because a word
    was broken across a line. Frame span offsets stay in ``frames.locate_span``,
    which searches both forms. That map's keep-hyphen form does not insert the
    space this function inserts, so the two are not one convention.
    """
    if join_line_hyphen:
        text = _join_line_hyphen(text)
    return _WS.sub(" ", unicodedata.normalize("NFKC", text).translate(_QUOTES)).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_root(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root)
    env = os.environ.get("CASELINKER_PACER_TEXT")
    return Path(env) if env else REPO_ROOT / "local" / "pacer_text"


def page_path(case_id: str, doc_id: str, pdf_page: int, root: Optional[Path] = None) -> Path:
    return text_root(root) / case_id / doc_id / f"p{pdf_page:04d}.txt"


def read_page(case_id: str, doc_id: str, pdf_page: int, root: Optional[Path] = None) -> Optional[str]:
    path = page_path(case_id, doc_id, pdf_page, root)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def write_page(case_id: str, doc_id: str, pdf_page: int, text: str, root: Optional[Path] = None) -> str:
    """Store raw page text; returns the SHA-256 of its normalized form."""
    path = page_path(case_id, doc_id, pdf_page, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return sha256_text(normalize(text))


def quotes_path(case_id: str, root: Optional[Path] = None) -> Path:
    return text_root(root) / case_id / "quotes.json"


def load_quotes(case_id: str, root: Optional[Path] = None) -> Dict[str, str]:
    path = quotes_path(case_id, root)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def save_quotes(case_id: str, quotes: Dict[str, str], root: Optional[Path] = None) -> None:
    path = quotes_path(case_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(quotes.items())), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


class QuoteNotFound(ValueError):
    pass


def locate(page_text: str, quote: str) -> Tuple[int, int, str]:
    """Offsets of ``quote`` in the normalized page text. Raises if absent or ambiguous."""
    page_n, quote_n = normalize(page_text), normalize(quote)
    if not quote_n:
        raise QuoteNotFound("empty quote")
    start = page_n.find(quote_n)
    if start < 0:
        raise QuoteNotFound("quote not on this page")
    if page_n.find(quote_n, start + 1) >= 0:
        raise QuoteNotFound("quote occurs more than once on this page; lengthen it")
    return start, start + len(quote_n), quote_n


@dataclass(frozen=True)
class Check:
    status: str  # VERIFIED | FAILED | NOT_CHECKABLE
    reason: str = ""


def verify_passage(passage: dict, page_text: Optional[str], expected_page_sha: Optional[str]) -> Check:
    """Re-derive the passage from page text: page hash, offsets, quote hash."""
    if page_text is None:
        return Check("NOT_CHECKABLE", "page text not in the local store")
    page_n = normalize(page_text)
    if expected_page_sha and sha256_text(page_n) != expected_page_sha:
        return Check("FAILED", "page text hash differs from the bundle")
    start, end = passage["char_start"], passage["char_end"]
    if not (0 <= start < end <= len(page_n)):
        return Check("FAILED", "offsets outside the page text")
    if sha256_text(page_n[start:end]) != passage["quote_sha256"]:
        return Check("FAILED", "text at the offsets does not match the quote hash")
    return Check("VERIFIED")
