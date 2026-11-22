"""Coding tooling: page text, coding drafts, compilation, agreement, outputs.

    python -m state_machines.coding.workflow extract <case_id> [...]      page text + source manifest
    python -m state_machines.coding.workflow check <draft.json>           compile a coder draft and validate it
    python -m state_machines.coding.workflow compile <draft.json> <out>   write the committed bundle (no quote text)
    python -m state_machines.coding.workflow agree <bundle_a> <bundle_b>  agreement between two coders
    python -m state_machines.coding.workflow outputs <bundle> <outdir>    derive, emit graphs, SHACL, report

A coder **draft** is the bundle format with one difference: each passage carries its
``quote`` instead of offsets and hashes. Drafts live in the local store (they contain
source text); ``compile`` locates each quote on its page, records offsets and hashes,
writes the quotes to ``quotes.json`` and emits a bundle with no quote text.

PDFs are read from ``$CASELINKER_PACER_SOURCE`` (default: ontology/PACER in this checkout;
the PDFs are gitignored, so point it at the main checkout). Nothing is written there.

A case id is the corpus id of the press release for the same prosecution, where the corpus holds one.
The PDFs keep the file names they were collected under (``COLLECTED_AS``), and a bundle records each
document under a normalized ``source_path`` (folder, case id, document id) with the file's SHA-256;
the name on disk stays in the local store (``files.json``), because a file name can carry a surname.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V

PILOT_CASES = ("doj_ceos_2025_026", "ncis_2023_001", "svicac_2022_009", "texas_ag_2019_013", "anchorage_pd_2022_006")
# cases collected by crime type sit in their own folders
ANCHOR_DIRS = {"doj_ceos_2025_026": "ENTICEMENT", "doj_ceos_2026_001": "PRODUCTION", "anchorage_pd_2022_007": "SEXTORTION",
               "doj_ceos_2025_007": "ENTERPRISE", "doj_ceos_2026_006": "TRAFFICKING"}
# case id -> the id written in the PDF file names, where the press release has since been renumbered or
# the corpus now holds it under another source (checked 2026-11-18 by the defendant's full name in the press text)
COLLECTED_AS = {"ncmec_2022_575": "ncmec_2022_586", "ncmec_2023_222": "ncmec_2023_224", "ncmec_2025_1026": "ncmec_2025_1116",
                "usss_2021_017": "usss_2021_019", "doj_safe_childhood_2023_420": "ncmec_2023_190"}
DOC_TYPE_WORDS = [  # first match wins; order matters
    ("fourth superseding indictment", "superseding_indictment"), ("second superseding indictment", "superseding_indictment"),
    ("third superseding indictment", "superseding_indictment"), ("superseding indictment", "superseding_indictment"),
    ("statement of offense", "statement_of_offense"), ("statement of facts", "statement_of_facts"),
    ("stipulation of facts", "stipulation_of_facts"), ("factual basis", "factual_basis"), ("factual proffer", "factual_proffer"),
    ("plea transcript", "plea_transcript"), ("plea agreement", "plea_agreement"), ("findings of fact", "findings_of_fact"),
    ("amended judgment", "amended_judgment"), ("statement of reasons", "statement_of_reasons"), ("judgment", "judgment"),
    ("sentencing", "sentencing_memorandum"), ("trial brief", "trial_brief"), ("response in opposition", "brief"),
    ("memorandum opinion", "opinion"), ("criminal complaint", "complaint"),
    ("complaint", "complaint"), ("information", "information"), ("indictment", "indictment"), ("docket", "docket"),
]
MIN_TEXT_CHARS = 300  # per page; below this the page is treated as a scan


def source_root() -> Path:
    return Path(os.environ.get("CASELINKER_PACER_SOURCE", E.REPO_ROOT / "ontology" / "PACER"))


def case_pdfs(case_id: str) -> List[Path]:
    root = source_root()
    if case_id in ANCHOR_DIRS:
        return sorted((root / ANCHOR_DIRS[case_id]).glob("*.pdf"))
    pat = re.compile(rf"-- ?{re.escape(COLLECTED_AS.get(case_id, case_id))} ?--", re.I)
    return sorted(p for p in (root / "BULK_FOLDER").glob("*.pdf") if pat.search(p.name))


def doc_type_of(path: Path) -> str:
    label = path.stem.split("--")[-1].strip().lower()
    for words, kind in DOC_TYPE_WORDS:
        if words in label:
            return kind
    return "other"


def _ocr(page, dpi: int = 300) -> Tuple[str, Optional[float]]:
    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "p.png"
        page.get_pixmap(dpi=dpi).save(str(img))
        text = subprocess.run(["tesseract", str(img), "stdout", "--psm", "6"], capture_output=True, text=True, check=True).stdout
        tsv = subprocess.run(["tesseract", str(img), "stdout", "--psm", "6", "tsv"], capture_output=True, text=True, check=True).stdout
    confs = [float(r.split("\t")[10]) for r in tsv.splitlines()[1:] if len(r.split("\t")) > 11 and r.split("\t")[11].strip()
             and float(r.split("\t")[10]) >= 0]
    return text, (round(sum(confs) / len(confs), 1) if confs else None)


_DISTRICT = re.compile(
    r"((?:NORTHERN|SOUTHERN|EASTERN|WESTERN|MIDDLE|CENTRAL)\s+DISTRICT\s+OF\s+[A-Z]+(?:\s+[A-Z]+)?"
    r"|DISTRICT\s+OF\s+[A-Z]+(?:\s+[A-Z]+)?)",
    re.I,
)
_CASE_NUMBER = re.compile(
    r"\b(?:(?:Case|Criminal|Crim\.?|Cr\.?)\s+(?:No\.?|Number)?|No\.)\s*[:.]?\s*"
    r"([0-9][\w:.-]*(?:\s*\([A-Za-z0-9]+\))?)",
    re.I,
)
_COURT_LINE = re.compile(r"\bDISTRICT\b", re.I)


def _court_lines(text: str) -> str:
    """The court lines only. A caption line after the court is not part of the key."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines() if line.strip()]
    kept = []
    for line in lines:
        if _COURT_LINE.search(line) or (kept and re.match(r"^(?:FOR\s+THE\s+)?[A-Z .]+DISTRICT\b", line, re.I)):
            kept.append(line)
            continue
        if kept:
            break
    return " ".join(kept)


def _normalise_court(text: str) -> Optional[str]:
    """The district name, with whitespace collapsed. Two districts do not share a key."""
    lines = _court_lines(text or "")
    found = _DISTRICT.search(lines or re.sub(r"\s+", " ", text or ""))
    if not found:
        return None
    name = re.split(r"\b(?:CASE|CRIMINAL|CRIM|NO|NUMBER|JUDGMENT|PLAINTIFF|DOCUMENT)\b",
                    found.group(1), maxsplit=1, flags=re.I)[0]
    return " ".join(name.split()).upper().rstrip(".")


def court_and_docket(text: str) -> Tuple[Optional[str], Optional[str]]:
    """District key and case number printed on a filing, when the page states them."""
    court = _normalise_court(text or "")
    number = _CASE_NUMBER.search(text or "")
    return court, (number.group(1).strip() if number else None)


def extract(case_id: str, text_root: Optional[Path] = None) -> dict:
    """Page text for every PDF of a case into the local store; returns the source manifest.
    A document already in the store (same SHA-256) keeps its id and its page text; a new PDF is added."""
    import pymupdf

    folder = E.text_root(text_root) / case_id
    old = json.loads((folder / "sources.json").read_text(encoding="utf-8"))["documents"] if (folder / "sources.json").is_file() else []
    known = {d["sha256"]: d for d in old}
    used = Counter(re.sub(r"_\d+$", "", d["doc_id"]) for d in old)
    docs, files, seen = [], {}, set()
    court, docket = None, None

    def _notice(text: str) -> None:
        nonlocal court, docket
        found_court, found_number = court_and_docket(text)
        court = court or found_court
        docket = docket or found_number

    pdfs = case_pdfs(case_id)
    if not pdfs:
        raise FileNotFoundError(f"no PDF for case {case_id!r}: expected <source>/BULK_FOLDER/pacer -- {case_id} -- <document type>.pdf "
                                f"under {source_root()}")
    for pdf in pdfs:
        sha = E.sha256_file(pdf)
        if sha in seen:               # the same filing collected under two names is one document
            print(f"{case_id}: {pdf.name!r} repeats a file already read; skipped", file=sys.stderr)
            continue
        seen.add(sha)
        if sha in known:
            doc = known[sha]
            first = folder / doc["doc_id"] / "p0001.txt"
            if first.is_file():
                _notice(first.read_text(encoding="utf-8", errors="replace"))
        else:
            kind = doc_type_of(pdf)
            used[kind] += 1
            doc_id = kind if used[kind] == 1 else f"{kind}_{used[kind]}"
            pages = []
            for i, page in enumerate(pymupdf.open(str(pdf)), 1):
                text = page.get_text()
                if len(text.strip()) >= MIN_TEXT_CHARS:
                    method, conf = "text_layer", None
                else:
                    text, conf = _ocr(page)
                    method = "ocr"
                if i == 1:
                    _notice(text)
                digest = E.write_page(case_id, doc_id, i, text, text_root)
                pages.append({"pdf_page": i, "text_method": method, "page_text_sha256": digest, "court_page_label": None,
                              "ocr_engine": "tesseract 5 (psm 6, 300 dpi)" if method == "ocr" else None,
                              "ocr_mean_confidence": conf, "image_checked": False, "limitations": []})
            doc = {"doc_id": doc_id, "doc_type": kind, "sha256": sha, "ecf_document_number": None, "filed_date": None,
                   "page_count": len(pages), "pages": pages}
        doc["source_path"] = f"{pdf.parent.name}/pacer -- {case_id} -- {doc['doc_id'].replace('_', ' ')}.pdf"
        files[doc["doc_id"]] = str(pdf.relative_to(source_root()))
        docs.append(doc)                      # in file-name order, as collected: a rerun lists a case's documents as before
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "files.json").write_text(json.dumps(files, indent=1, sort_keys=True) + "\n", encoding="utf-8")   # names on disk: local only
    key_path = folder / "case_key.json"
    if v2_active() and (court or docket):
        key_path.write_text(
            json.dumps({"court": court, "docket_number": docket}, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")
    elif key_path.is_file():
        key_path.unlink()
    return {"case_id": case_id, "documents": docs}


def local_file(case_id: str, doc_id: str, text_root: Optional[Path] = None) -> Optional[Path]:
    """The PDF a document was read from, on this machine."""
    path = E.text_root(text_root) / case_id / "files.json"
    name = json.loads(path.read_text(encoding="utf-8")).get(doc_id) if path.is_file() else None
    return source_root() / name if name else None


# --- drafts -----------------------------------------------------------------------------

def compile_draft(draft: dict, text_root: Optional[Path] = None) -> Tuple[dict, Dict[str, str], List[str]]:
    """(bundle, quotes, problems). Problems are quotes that could not be located."""
    bundle = copy.deepcopy(draft)
    pages = {(d["doc_id"], pg["pdf_page"]): pg for d in bundle["documents"] for pg in d["pages"]}
    quotes, problems, passages = {}, [], []
    for p in bundle["passages"]:
        quote = p.pop("quote", "")
        text = E.read_page(bundle["case_id"], p["doc_id"], p["pdf_page"], text_root)
        page = pages.get((p["doc_id"], p["pdf_page"]))
        try:
            if text is None or page is None:
                raise E.QuoteNotFound("no page text for that document and page")
            start, end, q = E.locate(text, quote)
        except E.QuoteNotFound as exc:
            problems.append(f"{p['passage_id']} ({p['doc_id']} p{p['pdf_page']}): {exc}")
            continue
        p.update({"char_start": start, "char_end": end, "quote_sha256": E.sha256_text(q), "quote_word_count": len(q.split())})
        ocr = page["text_method"] == "ocr"
        p["verification"] = {"status": "VERIFIED" if (not ocr or page.get("image_checked")) else "UNVERIFIED",
                             "method": "ocr_plus_page_image" if ocr else "text_layer_exact",
                             "checked_by": draft["coding"]["coder_id"],
                             **({"note": "OCR text located; page image not yet checked"} if ocr and not page.get("image_checked") else {})}
        p.setdefault("court_locator", None)
        quotes[p["passage_id"]] = q
        passages.append(p)
    bundle["passages"] = passages
    return bundle, quotes, problems


def deny_list(case_id: str, text_root: Optional[Path] = None) -> List[str]:
    path = E.text_root(text_root) / case_id / "deny.json"
    return json.loads(path.read_text()) if path.is_file() else []


_CAPTION = re.compile(r"(?:UNITED STATES OF AMERICA|United States of America|UNITED STATES|United States|USA|U\.S\.|CRIMINAL CASE)"
                      r"[^.]{0,60}?(?<![A-Za-z])[Vv][Ss]?\.\s+(?:[)(|:\-]\s*)*([A-Z][A-Za-z.,'\-/\"“” ]{2,120})")
_ALIAS = re.compile(r"\ba/k/a\b|\bA/K/A\b|\baka\b|\bAKA\b|also known as")
_CAPTION_STOP = re.compile(r"\b(?:Defendants?|DEFENDANTS?|Case|CASE|No|NO|Criminal|CRIMINAL|Cr|CR|Docket|DOCKET|Plaintiff|et al)\b|[)(|:\d]")
_NOT_NAME = set("""
united states america defendant defendants plaintiff the and case criminal court district jr sr ii iii iv usa inc llc doe john jane
under seal sealed unknown indictment superseding information complaint judgment amended plea agreement sentencing memorandum
statement facts offense factual basis proffer stipulation order motion notice government response reply brief exhibit count counts
number numbers date filed file filing violation violations title section code page pages docket entry minute sheet warrant arrest
production distribution receipt possession child pornography minor minors sexual exploitation enticement coercion trafficking
conspiracy attempt transportation interstate commerce release detention hearing trial jury grand verdict true bill foreign
for its may first include includes result results fields with from that this was were not his her has have had who which
division eastern western northern southern middle central honorable judge magistrate clerk attorney assistant
""".split())
_NAME_TOKEN = re.compile(r"^[A-Z][A-Za-z'\-]+\.?,?$|^[A-Z]\.,?$")


_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
_GENERIC_ACTOR = re.compile(r"^(?:the\s+)?(?:defendant|accused)$", re.I)
PRONOUN_WORDS = ("he", "him", "his", "she", "her", "they", "them", "their")
_PRONOUN = re.compile(r"^(?:" + "|".join(PRONOUN_WORDS) + r")$", re.I)
_NAMED_ACTOR = re.compile(r"^(?:the\s+)?defendants?\s+(.+)$", re.I)
_POSSESSIVE_ACTOR = re.compile("\\b(?:defendant|accused)(?:'s|\u2019s)\\b", re.I)


def _name_words(raw: str) -> List[str]:
    """The leading run of capitalised words of a caption fragment: a name is at most six words and
    ends at the first word that is not capitalised or is a caption word ("INDICTMENT", "Defendant")."""
    out = []
    for token in raw.replace('"', " ").replace("“", " ").replace("”", " ").split()[:6]:
        word = token.strip(".,'-/").lower()
        if not _NAME_TOKEN.match(token) or word in _NOT_NAME:
            break
        if len(word) >= 3 and word.isalpha():
            out.append(word)
    return out


def _base_deny_tokens(text: str) -> set:
    """The deny tokens the unset-flag path has always produced. Do not change this."""
    names = set()
    for match in _CAPTION.finditer(E.normalize(text or "")):
        for part in _ALIAS.split(match.group(1)):
            names |= set(_name_words(_CAPTION_STOP.split(part)[0]))
    return names


def spacy_model_record() -> dict:
    """Name and version of the spaCy model a v2 run uses. Missing model stops the run."""
    from state_machines.observations.means_parse import load_spacy_model, model_name
    name = model_name()
    try:
        nlp = load_spacy_model(name)
    except Exception as exc:
        raise SystemExit(
            f"v2 coding needs the spaCy model {name}, which is not available ({type(exc).__name__}: {exc})"
        ) from exc
    version = (getattr(nlp, "meta", {}) or {}).get("version")
    return {"model": name, "model_version": version}


def v2_active() -> bool:
    """True when a v2 flag changes published behavior. Unset flags stay on the base path."""
    if os.environ.get("CASELINKER_EXTRACTOR") == "frame-1.0":
        return True
    if os.environ.get("CASELINKER_SECTION_FILTER") == "1":
        return True
    if os.environ.get("CASELINKER_COREFERENCE") == "1":
        return True
    if os.environ.get("CASELINKER_ADJACENT_LEVEL") == "1":
        return True
    if os.environ.get("CASELINKER_MEANS_PARSER") == "dep":
        return True
    if os.environ.get("CASELINKER_MEANS_RULE"):
        return True
    if os.environ.get("CASELINKER_DISAGREEMENT") == "1":
        return True
    policy = os.environ.get("CASELINKER_ACT_POLICY")
    return bool(policy) and policy != "intersection-1.0"


def _caption_tokens(raw: str) -> List[str]:
    """Name words for one caption person. An initial is skipped. A suffix ends the name."""
    out = []
    for token in raw.replace('"', " ").replace("“", " ").replace("”", " ").split()[:8]:
        word = token.strip(".,'-/").lower()
        if word in _SUFFIXES:
            break
        if word in {"defendant", "defendants", "plaintiff", "date", "filed", "judgment", "judgement",
                    "assigned", "magistrate", "usm", "number", "case", "criminal", "no"}:
            break
        if re.fullmatch(r"[a-z]", word):
            continue
        if not re.fullmatch(r"[a-z][a-z'\-]+", word):
            if out:
                break
            continue
        out.append(token.strip(".,"))
    return out


def _one_person(chunk: str) -> Optional[dict]:
    chunk = chunk.strip(" ,;")
    if not chunk:
        return None
    if re.match(r"^[A-Z][A-Za-z'\-]+,\s+[A-Z]", chunk):
        left, right = chunk.split(",", 1)
        surname_words = _caption_tokens(left)
        given = _caption_tokens(right)
        if not surname_words:
            return None
        surname = surname_words[0]
        full = " ".join(given + [surname]) if given else surname
        return {"full": full, "surname": surname}
    words = _caption_tokens(chunk)
    if not words:
        return None
    return {"full": " ".join(words), "surname": words[-1]}


_REPORTER = re.compile(
    r"\d+\s+F\.\s*(?:\d+d|4th)|\d+\s+F\.\s*Supp(?:\.\s*\d+d)?|\d+\s+F\.\s*App['’]?x|"
    r"\bFed\.\s*Appx\.?|\d+\s+L\.\s*Ed\.\s*2d|\d+\s+S\.\s*Ct\.|"
    r"\d+\s+U\.?\s*S\.|\b\d+\s*WL\b|\bWL\s+\d+|\bsupra\b|\bid\.|\bNo\.\s*\d",
    re.I,
)
_CITATION_SIGNAL = re.compile(
    r"\b(?:as\s+held\s+in|see|cf\.|accord|id\.)\s+(?:united\s+states|u\.s\.)\s+v\.?\s*$",
    re.I,
)
_COMPANY = re.compile(r"\b(?:L\.L\.C\.|L\.P\.|LLC|INC|CORP|LTD|CO)\b\.?", re.I)
_COMPANY_PHRASE = re.compile(
    r"(?:^|\band\s+)((?:(?!and\b)[A-Z][\w.'-]+,?\s+){0,8}"
    r"(?:L\.L\.C\.|L\.P\.|LLC|INC|CORP|LTD|CO)\b\.?)",
    re.I,
)
_DOCKET_LABEL = re.compile(
    r"\b(?:date\s+filed|date|filed|judgment|judgement|magistrate|honorable|"
    r"case\s+no|docket)\b",
    re.I,
)
_CASE_V = re.compile(
    r"(?:UNITED STATES OF AMERICA|United States of America|UNITED STATES|United States|USA|U\.S\.|CRIMINAL CASE)"
    r"[^.]{0,240}?(?<![A-Za-z])[Vv][Ss]?\.\s+"
)
_BODY_HEADING = re.compile(
    r"(?:STATEMENT OF FACTS|INTRODUCTION|BACKGROUND|COUNT\b|ARGUMENT|CONCLUSION|"
    r"FINDINGS OF FACT|PROCEDURAL HISTORY|OFFENSE CONDUCT|THE OFFENSE)\b",
    re.I,
)
_DEFENDANT_LINE = re.compile(r"\bDefendants?\.?\s*$", re.I)
_CAPTION_LINE_LIMIT = 40
_CHARGING_DOCS = {"complaint", "information", "indictment", "superseding_indictment"}
_PLEA_DOCS = {"plea_agreement", "plea_transcript", "statement_of_offense"}
_ET_AL = re.compile(r"\bet\s+al\b\.?", re.I)
_SUFFIX_BETWEEN = re.compile(
    r"\b([A-Z][A-Za-z'\-]+),\s+(?:JR|SR|II|III|IV)\.?,\s+([A-Z][A-Za-z'\-]+)\b",
    re.I,
)
_ENTITY_AND = re.compile(
    r"[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*)*\s+AND\s+[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*)*"
    r"\s+(?:LLC|INC|CORP|LTD|CO)\b\.?",
    re.I,
)
_SURNAME_GIVEN = re.compile(
    r"([A-Z][A-Za-z'\-]+),\s+"
    r"([A-Z][A-Za-z'\-]+(?:\s+(?:[A-Z]\.?|[A-Z][A-Za-z'\-]+)){0,3})"
    r"(?=\s*(?:,|;|\band\b|$))"
)
_NUMBERED_DEFENDANT = re.compile(r"(?m)^\s*\(\d+\)\s+([A-Z][A-Za-z' .,()-]{1,80}?)(?=\s*$|\s+\()")
_INLINE_NUMBERED = re.compile(r"\(\d+\)\s+([A-Z][A-Z'\-]+(?:\s+[A-Z][A-Z'\-]+){0,3})")
_SENTENCE_NAME = re.compile(r"\b[A-Z][\w']+\s+(?!and\b|or\b)[a-z]{3,}\b")
_PERSON_SPLIT = re.compile(r"\s*;\s*and\s+|\s*,\s*and\s+|\s+and\s+|\s*;\s*|\s*,\s*", re.I)


def eyecite_version() -> Optional[str]:
    """Installed eyecite version, or None when the package is absent."""
    try:
        import eyecite
        return getattr(eyecite, "__version__", None) or "present"
    except Exception:
        return None


def citation_spans(text: str) -> List[Tuple[int, int]]:
    """Character spans eyecite calls a citation. Empty when eyecite is not installed."""
    if eyecite_version() is None:
        if v2_active():
            raise SystemExit("v2 coding needs eyecite, which is not installed")
        return []
    from eyecite import get_citations
    spans = []
    for cite in get_citations(text or ""):
        span = getattr(cite, "span", None)
        if callable(span):
            span = span()
        if span and len(span) == 2:
            spans.append((int(span[0]), int(span[1])))
    return spans


def _citation_follows(text: str, start: int) -> bool:
    """True when the text just after a 'v.' is a citation, not a caption of defendants."""
    window = text[start:start + 220]
    cut = re.search(r"(?<=[A-Za-z]{3})\.\s+", window)
    abbrev = window[cut.start() - 3:cut.start()] if cut else ""
    head = window[:cut.start()] if cut and abbrev not in {"Fed", "App", "Supp"} else window
    head = re.sub(r"\b(?:Criminal|Cr\.?|Case)\s+No\.\s*\S+", " ", head, flags=re.I)
    head = re.sub(r"\d+\s+U\.S\.C\.\s*\S*", " ", head, flags=re.I)
    pre = text[max(0, start - 80):start]
    if _REPORTER.search(head) or _CITATION_SIGNAL.search(pre):
        return True
    head_end = start + len(head)
    for cite_start, cite_end in citation_spans(text):
        if cite_start < head_end and cite_end > start:
            return True
    return False


def _caption_block(page: str) -> str:
    """Opening lines through the caption. Blank lines inside the caption stay.

    The block ends at a ``Defendant(s).`` line, a body heading, or a line limit.
    """
    kept = []
    for index, line in enumerate((page or "").splitlines()):
        if index >= _CAPTION_LINE_LIMIT:
            break
        if _BODY_HEADING.fullmatch(line.strip().rstrip(".")):
            break
        kept.append(line)
        if _DEFENDANT_LINE.search(line.strip()):
            break
    return "\n".join(kept)


def _split_caption_people(head: str) -> List[str]:
    """People in one caption list. 'SURNAME, Given' stays one person; other commas split.

    A suffix between the surname and the given name stays on that one person.
    An entity name ending in LLC, INC, CORP, LTD, or CO is not split on AND.
    """
    head = _SUFFIX_BETWEEN.sub(r"\1, \2", head)
    entities: List[str] = []

    def _hold_entity(match: re.Match) -> str:
        entities.append(match.group(0))
        return f"\x01{len(entities) - 1}\x01"

    head = _ENTITY_AND.sub(_hold_entity, head)
    held: List[str] = []

    def _surname_ok(match: re.Match) -> bool:
        prefix = head[:match.start()].rstrip()
        return not prefix or bool(re.search(r"(?:^|\band|;)\s*$", " " + prefix, re.I))

    def _hold(match: re.Match) -> str:
        if not _surname_ok(match):
            return match.group(0)
        held.append(f"{match.group(1)}, {match.group(2)}")
        return f"\x00{len(held) - 1}\x00"

    masked = _SURNAME_GIVEN.sub(_hold, head)
    chunks = []
    for chunk in _PERSON_SPLIT.split(masked):
        chunk = chunk.strip(" ,;")
        if not chunk:
            continue
        chunk = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], chunk)
        chunk = re.sub(r"\x01(\d+)\x01", lambda m: entities[int(m.group(1))], chunk)
        if re.fullmatch(r"(?:JR|SR|II|III|IV)\.?", chunk.strip(".,"), re.I):
            continue
        chunks.append(chunk)
    return chunks


def _name_line(fragment: str) -> str:
    """The party lines after 'v.', including a name wrapped onto the next line.

    A line that is only a slash is the wrapped 'and'. A docket label ends the name.
    """
    lines = []
    for raw in (fragment or "").splitlines() or [fragment or ""]:
        piece = raw.strip()
        if not piece:
            continue
        if piece in {"/", "\\"}:
            continue
        closed = re.search(r"\bDefendants?\b", piece)
        if closed:
            piece = piece[:closed.start()]
        label = _DOCKET_LABEL.search(piece)
        if label:
            piece = piece[:label.start()]
        piece = re.split(r"(?<=[A-Za-z]{2})\.\s+", piece, maxsplit=1)[0]
        piece = piece.strip(" ;")
        if piece:
            lines.append(piece)
        if closed:
            break
    return " ".join(lines)


def _attach_aliases(person: dict, indexes: List[int], saved: List[str]) -> None:
    for index in indexes:
        alias = _one_person(saved[index])
        if not alias:
            continue
        person.setdefault("aliases", []).append(alias["full"])
        person.setdefault("alias_surnames", []).append(alias["surname"])


def _alias_and_is_unclean(head: str) -> bool:
    """True when 'and' after an alias is not separated as the next defendant."""
    match = _ALIAS.search(head or "")
    if not match:
        return False
    tail = head[match.end():]
    if re.search(r"[,;]\s*and\b", tail, re.I):
        return False
    return bool(re.search(r"\band\b", tail, re.I))


def _people_in_caption(fragment: str) -> Tuple[List[dict], bool]:
    """Caption people, and whether the caption was refused as uncertain.

    An alias stays on the person it follows. The next defendant is split off
    before that. A company suffix is not a person. An 'and' jammed onto an
    alias, with no comma or semicolon, refuses the caption.
    """
    head = _name_line(fragment)
    if not head:
        return [], False
    if _alias_and_is_unclean(head):
        return [], True
    original = head
    if re.search(r"\bHOLDINGS\b", original, re.I):
        return [], False
    had_company = bool(_COMPANY.search(original))
    head = _COMPANY_PHRASE.sub(" ", head)
    head = re.sub(r",?\s*Defendants?\.?$", "", head, flags=re.I).strip(" ,")
    saved: List[str] = []

    def _hold_alias(match: re.Match) -> str:
        saved.append(match.group(1).strip(" '\""))
        return f" \x02{len(saved) - 1}\x02 "

    masked = re.sub(
        r"\b(?:a/k/a|aka|also known as)\s+"
        r"((?:'[^']+'|\"[^\"]+\"|(?:[A-Z][\w.'-]+\s+){0,3}[A-Z][\w.'-]+))"
        r"(?=\s*(?:,\s*)?(?:a/k/a|aka|also known as)\b|,\s*(?:and|Defendants?)\b|$)",
        _hold_alias, head, flags=re.I,
    )
    people = []
    pending: List[int] = []
    for chunk in _split_caption_people(masked):
        marks = [int(n) for n in re.findall(r"\x02(\d+)\x02", chunk)]
        plain = re.sub(r"\x02\d+\x02", " ", chunk)
        plain = re.sub(r"^(?:and|or)\s+", "", plain.strip(), flags=re.I)
        if not plain.strip():
            if people:
                _attach_aliases(people[-1], marks, saved)
            else:
                pending.extend(marks)
            continue
        if _COMPANY.search(plain):
            continue
        person = _one_person(plain)
        if not person or _COMPANY.search(person["full"]):
            continue
        person["aliases"] = []
        person["alias_surnames"] = []
        _attach_aliases(person, pending + marks, saved)
        pending = []
        if had_company:
            person["with_company"] = True
        people.append(person)
    return people, False


def _keep_record(record: dict, seen: set) -> bool:
    key = record["full"].lower()
    if key in seen or key in {"united states", "united states of america"}:
        return False
    if record["surname"].lower() in {"united", "states", "america"}:
        return False
    seen.add(key)
    record.setdefault("aliases", [])
    record.setdefault("alias_surnames", [])
    record["key"] = key
    return True


_NUMBERED_LINE = re.compile(r"(?m)^\s*(?:\(\d+\)|\d+\.)\s+(.+?)\s*$")


def _numbered_people(block: str) -> List[dict]:
    """Defendants written as ``(1) NAME``, ``1. NAME`` or ``NAME (1)``."""
    people = []
    seen_lines = _NUMBERED_LINE.findall(block or "") or [match.group(1) for match in _NUMBERED_DEFENDANT.finditer(block or "")]
    for line in seen_lines:
        found, refused = _people_in_caption(line)
        if refused:
            continue
        for person in found:
            if person and not _COMPANY.search(person["full"]):
                people.append(person)
    if not people:
        for match in re.finditer(r"\b([A-Z][A-Z'\-]+(?:\s+[A-Z][A-Z'\-]+){0,3})\s+\(\d+\)", block or ""):
            person = _one_person(match.group(1))
            if person:
                person.setdefault("aliases", [])
                person.setdefault("alias_surnames", [])
                people.append(person)
    return people


def _parse_caption(text: str) -> Tuple[List[dict], bool]:
    """Records from the first real caption in ``text``, and whether it says ``et al``.

    A citation is never a defendant. With eyecite absent, a ``v.`` whose
    following text is a reporter, ``No.``, or ``supra`` is refused, including
    on a page that has no party caption. A refused alias split yields no person.
    """
    block = _caption_block(text or "")
    et_al = bool(_ET_AL.search(block))
    records = []
    seen: set = set()
    for person in _numbered_people(block):
        if _keep_record(person, seen):
            records.append(person)
    if not records:
        for match in _INLINE_NUMBERED.finditer(block):
            person = _one_person(match.group(1).strip(" ,.)"))
            if person and not _COMPANY.search(person["full"]) and _keep_record(person, seen):
                records.append(person)
    if records:
        return records, et_al
    for match in _CASE_V.finditer(block):
        if _citation_follows(block, match.end()):
            continue
        fragment = _ET_AL.sub(" ", block[match.end():])
        if _SENTENCE_NAME.search(_name_line(fragment)):
            return [], False
        people, refused = _people_in_caption(fragment)
        if refused:
            return [], False
        for record in people:
            if _keep_record(record, seen):
                records.append(record)
        if records or people:
            break
    return records, et_al


def defendant_records_in(text: str) -> List[dict]:
    """Defendants in the first case caption of this page, before the body.

    A 'v.' whose raw following text is a reporter citation is not a caption.
    Later captions on the page are not defendants.
    """
    records, _et_al = _parse_caption(text)
    return records


def _same_party(left: dict, right: dict) -> bool:
    """A bare surname and the full name with that surname are one person."""
    if left.get("party_id") and right.get("party_id") and left["party_id"] != right["party_id"]:
        return False
    if left["key"] == right["key"] or left["full"].lower() == right["full"].lower():
        return True
    left_full, right_full = left["full"].lower(), right["full"].lower()
    left_sur, right_sur = left["surname"].lower(), right["surname"].lower()
    if left_full == right_sur or right_full == left_sur:
        return True
    if left_sur == right_sur:
        left_tokens, right_tokens = set(left_full.split()), set(right_full.split())
        return left_tokens <= right_tokens or right_tokens <= left_tokens
    return False


def _fuller(left: dict, right: dict) -> dict:
    return left if len(left["full"].split()) >= len(right["full"].split()) else right


def _absorb(records: List[dict], record: dict) -> None:
    for index, held in enumerate(records):
        if _same_party(held, record):
            records[index] = _fuller(held, record)
            return
    records.append(record)


def _signature(records: List[dict]) -> Tuple[str, ...]:
    return tuple(sorted({record["surname"].lower() for record in records}))


def case_defendants(case_id: str, text_root: Optional[Path] = None) -> dict:
    """Case-level defendants, shared by the coder and by missed-act recovery.

    A charging document (complaint, information, indictment) supplies the caption
    when its type is known. Otherwise every document's first page contributes,
    and a document with no caption contributes nothing. ``et al``, more than one
    person, or two captions that name different people make the generic actor
    ambiguous. No caption at all is ``no_defendant_record``.
    """
    root = E.text_root(text_root) / case_id
    listed = root / "sources.json"
    meta = json.loads(listed.read_text(encoding="utf-8")) if listed.is_file() else {}
    key_path = root / "case_key.json"
    if key_path.is_file():
        meta = {**meta, **json.loads(key_path.read_text(encoding="utf-8"))}
    if listed.is_file():
        documents = meta.get("documents") or []
    else:
        documents = [{"doc_id": path.parent.name, "doc_type": "other"}
                     for path in sorted(root.glob("*/p0001.txt"))]
    found = []
    for doc in documents:
        page = root / doc["doc_id"] / "p0001.txt"
        if not page.is_file():
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        closed = bool(re.search(r"\bDefendants?\b", text) or _BODY_HEADING.search(text))
        nxt = root / doc["doc_id"] / "p0002.txt"
        if not closed and nxt.is_file():
            text = text + "\n" + nxt.read_text(encoding="utf-8", errors="replace")
        records, et_al = _parse_caption(text)
        if not records and not et_al:
            continue
        found.append({"doc_id": doc["doc_id"], "doc_type": doc.get("doc_type") or "other",
                      "records": records, "et_al": et_al})
    # One charging document must not replace another, or a plea that names
    # someone else. The case set is their union. Other documents fill in only
    # when no charging or plea caption exists.
    charging = [item for item in found if item["doc_type"] in _CHARGING_DOCS]
    pleas = [item for item in found if item["doc_type"] in _PLEA_DOCS]
    chosen = charging or pleas or found
    if not chosen:
        records = []
        generic = "no_defendant_record"
        et_al = False
        conflict = False
        by_document = {}
    else:
        signatures = {_signature(item["records"]) for item in chosen}
        conflict = len(signatures) > 1
        et_al = any(item["et_al"] for item in chosen)
        records = []
        for item in chosen:
            for record in item["records"]:
                _absorb(records, record)
        if conflict or et_al or len(records) != 1:
            generic = "ambiguous"
        else:
            generic = "one"
        by_document = {}
        for item in found:
            own = item["records"]
            matches = [party for party in records if len(own) == 1 and _same_party(own[0], party)]
            if len(matches) > 1 or item["et_al"]:
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None, "reason": "ambiguous_surname"}
            elif len(own) > 1:
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None, "reason": "multi_defendant_caption"}
            elif own and not matches and item["doc_type"] in _PLEA_DOCS:
                by_document[item["doc_id"]] = {"generic": "one", "record": own[0]}
            elif own and not matches:
                reason = "other_caption" if item["doc_type"] in _PLEA_DOCS else "caption_mismatch"
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None, "reason": reason}
            elif len(matches) == 1:
                by_document[item["doc_id"]] = {"generic": "one", "record": matches[0]}
            elif generic == "one":
                by_document[item["doc_id"]] = {"generic": "one", "record": records[0]}
            else:
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None, "reason": "multi_defendant_caption"}
    from state_machines.coding.parties import defendants_for, has_entry, other_surnames
    court = str(meta.get("court") or "")
    docket = str(meta.get("docket_number") or "")
    if court and docket and has_entry(court, docket) is False:
        return {"records": [], "generic": "no_defendant_record", "et_al": False, "conflict": False,
                "by_document": {}, "caption_snapshot_disagreement": False, "other_surnames": [],
                "reason": "other_caption"}
    snapshot = defendants_for(court, docket)
    others = other_surnames(court, docket)
    disagreement = False
    if snapshot is not None:
        caption_names = {record["surname"].lower() for record in records}
        snapshot_names = {record["surname"].lower() for record in snapshot}
        disagreement = bool(records) and caption_names != snapshot_names
        records = list(snapshot)
        et_al = False
        conflict = False
        generic = "ambiguous" if disagreement or len(records) != 1 else "one"
        if not records:
            generic = "no_defendant_record"
        by_document = {}
        for item in found:
            own = item["records"]
            match = next((party for party in records if len(own) == 1 and _same_party(own[0], party)), None)
            if own and match is None:
                reason = "other_caption" if item["doc_type"] in _PLEA_DOCS else "caption_mismatch"
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None, "reason": reason}
            elif disagreement or item["et_al"]:
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None}
            elif match is not None:
                by_document[item["doc_id"]] = {"generic": "one", "record": match}
            elif generic == "one":
                by_document[item["doc_id"]] = {"generic": "one", "record": records[0]}
            else:
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None}
    return {"records": records, "generic": generic, "et_al": et_al, "conflict": conflict,
            "by_document": by_document, "caption_snapshot_disagreement": disagreement,
            "other_surnames": sorted(others)}


def defendant_records_for_case(case_id: str, text_root: Optional[Path] = None) -> List[dict]:
    """Defendants for the case. A citation on a later page is not a defendant."""
    return case_defendants(case_id, text_root)["records"]


_ANY_POSSESSIVE = re.compile(r"\b[\w.\-]+(?:'s|\u2019s)\b")


def _require_actor_nlp():
    """The spaCy model. A missing model is an error, not an empty subject."""
    nlp = _actor_nlp()
    if nlp is None:
        from state_machines.observations.means_parse import model_name
        raise SystemExit(f"the spaCy model {model_name()} is not available")
    return nlp


def _noun_phrase(doc, token) -> str:
    """The subject token plus the determiner and possessive that modify it."""
    start = token.i
    for child in token.children:
        if child.dep_ in {"det", "poss", "case", "compound", "amod"} and child.i < start:
            start = child.left_edge.i
    return doc[start:token.i + 1].text


def clause_subject(sentence: str) -> str:
    """The clause subject from the dependency parse.

    A passive ``by`` phrase is the actor. ``the defendant's <word>`` stays that
    whole phrase. A missing model stops a v2 run.
    """
    nlp = _require_actor_nlp()
    doc = nlp(sentence or "")
    agent = next((token for token in doc
                  if token.dep_ == "pobj" and token.head.dep_ == "agent" and token.head.text.lower() == "by"), None)
    if agent is not None:
        return _noun_phrase(doc, agent)
    subjects = [token for token in doc if token.dep_ in _SUBJECT_DEPS]
    if not subjects:
        return ""
    return _noun_phrase(doc, subjects[0])


_ACTOR_NLP = None
_ACTOR_NLP_TRIED = False
_SUBJECT_DEPS = {"nsubj", "nsubjpass", "nsubj:pass"}


def _actor_nlp():
    """The spaCy model for bare-surname subjects, or None when it is not available."""
    global _ACTOR_NLP, _ACTOR_NLP_TRIED
    if _ACTOR_NLP_TRIED:
        return _ACTOR_NLP
    _ACTOR_NLP_TRIED = True
    try:
        from state_machines.observations.means_parse import load_spacy_model, model_name
        _ACTOR_NLP = load_spacy_model(model_name())
    except Exception:
        _ACTOR_NLP = None
    return _ACTOR_NLP


def _known_surnames(records: List[dict]) -> set:
    names = set()
    for record in records or []:
        names.add(record["surname"].lower())
        names.update(name.lower() for name in record.get("alias_surnames") or [])
    return names


def _one_capital(text: str) -> Optional[str]:
    parts = (text or "").split()
    if len(parts) == 1 and re.fullmatch(r"[A-Z][\w'.-]+", parts[0]):
        return parts[0]
    return None


def _token_names_defendant(token, actor_text: str, records: List[dict]) -> bool:
    if token is None:
        return False
    actor = " ".join((actor_text or "").split()).lower()
    word = token.text.lower()
    generic = bool(_GENERIC_ACTOR.fullmatch(actor))
    if word in {"defendant", "accused"} and (generic or word in actor):
        return True
    surnames = _known_surnames(records)
    if word in surnames and (word in actor.split() or generic):
        return True
    return False


_CONDUCT = {"send", "distribute", "upload", "download", "receive", "trade", "message",
             "email", "text", "post", "share", "transmit", "forward"}
_SPEECH = {"say", "tell", "claim", "know", "quote", "report", "state", "write"}
_NEG_VERBS = {"deny", "refuse", "fail", "decline", "neglect", "avoid"}
_UNREAL = {"plan", "intend", "want", "hope", "hop", "wish"}
_DEFENDANT_SOLICIT = {"SOLICIT_IMAGERY", "DIRECT_CONDUCT"}
_PERCEPTION = {"watch", "see", "observe", "look"}
_MODALS = {"would", "could", "may", "might", "should"}
_BLOCKED_CLAUSE = {"advcl", "ccomp", "xcomp", "relcl"}
_ADVERB_COMPOUND = {"later", "then", "thereafter", "also", "next"}


def _is_main_verb(token) -> bool:
    if token.dep_ == "ROOT":
        return True
    seen = set()
    head = token
    while head.dep_ == "conj" and head.i not in seen:
        seen.add(head.i)
        head = head.head
        if head.dep_ == "ROOT":
            return True
    return False


def _clause_of(token) -> Optional[str]:
    """The nearest blocked clause that contains ``token``, if it is not the main clause.

    spaCy returns a new Token object for ``.head``, so identity is not a stop.
    """
    seen = set()
    head = token
    while head.head.i != head.i and head.i not in seen:
        seen.add(head.i)
        if head.dep_ in _BLOCKED_CLAUSE:
            return head.dep_
        head = head.head
    return None


_PERSON_LEMMAS = {
    "victim", "minor", "child", "girl", "boy", "woman", "man", "person",
    "mother", "father", "sister", "brother", "wife", "husband",
}


def _person_object(token, *, names: bool) -> bool:
    """A pronoun or a victim label. A proper name counts only for an influence verb."""
    if any(child.dep_ == "poss" for child in token.children):
        return False
    if token.pos_ == "PRON":
        return True
    if token.lemma_.lower() in _PERSON_LEMMAS:
        return True
    if any(child.lemma_.lower() in _PERSON_LEMMAS for child in token.children):
        return True
    return names and token.pos_ == "PROPN"


def _subject_possessive(child, governor) -> bool:
    """A possessive pronoun on the object resolves to the one subject of this verb.

    ``his phone`` is the subject's instrument. A named possessor does not resolve
    that way, and a bare common noun is not an instrument.
    """
    poss = [grand for grand in child.children if grand.dep_ == "poss" and grand.pos_ == "PRON"]
    if len(poss) != 1:
        return False
    subjects = [token for token in governor.children if token.dep_ in _SUBJECT_DEPS]
    return len(subjects) == 1


def _listed_instrument(token, records) -> bool:
    """A platform or level-C feature the pipeline already recognizes.

    A vocabulary entry that is also a surname or given name on this case's
    caption is not an instrument.
    """
    from state_machines.coding.enrich import feature, known_platform

    words = [child.text for child in token.children if child.dep_ == "compound" and child.i < token.i]
    phrase = " ".join([*words, token.text])
    matched = known_platform(phrase) or known_platform(token.text)
    if matched:
        people = _known_surnames(records or [])
        for record in records or []:
            people |= _given_names(record)
        return matched.lower() not in people
    return feature(phrase) is not None or feature(token.text) is not None


def _controlling_object(governor, records=None):
    """The object that controls an embedded act, or None when the act stays with the subject.

    A listed platform or level-C feature is an instrument. A possessive pronoun
    that resolves to the one subject is that subject's instrument. A person
    controls the act. Any other object is unresolved, and the act is refused.
    """
    person = None
    for child in governor.children:
        if child.dep_ not in {"dobj", "dative", "iobj", "npadvmod"}:
            continue
        if _subject_possessive(child, governor):
            continue
        if _listed_instrument(child, records):
            continue
        if _person_object(child, names=False):
            person = ("person", child)
            continue
        return "unresolved", child
    return person


def _act_verb(doc):
    """The conduct verb the sentence would be coded as, else the root verb.

    An infinitive or a bare complement of the root is the act, whoever its
    controller is. The controller is decided from the governor's object.
    """
    root = next((token for token in doc if token.dep_ == "ROOT"), None)
    if root is not None:
        complement = next((child for child in root.children
                           if child.dep_ in {"xcomp", "ccomp"} and child.pos_ == "VERB"), None)
        if complement is not None:
            return complement
    conduct = [token for token in doc if token.pos_ in {"VERB", "AUX"} and token.lemma_.lower() in _CONDUCT]
    if not conduct:
        return root
    main = [token for token in conduct if _is_main_verb(token)]
    return main[-1] if main else conduct[-1]


def _clause_is_negated(verb) -> bool:
    """A neg dependency, or ``no`` on the verb's object or passive subject."""
    for token in verb.subtree:
        if token.dep_ == "neg":
            return True
        if token.lemma_.lower() in {"no", "none"} and token.dep_ == "det":
            head = token.head
            if head.dep_ in {"dobj", "nsubj", "nsubjpass", "nsubj:pass"} and head.head.i == verb.i:
                return True
            if head.dep_ == "pobj":
                prep = head.head
                if prep.dep_ == "prep" and prep.head.i == verb.i:
                    return True
    return False


def _defendant_said(verb, records=None) -> bool:
    """A complement whose subject is a pronoun and whose main subject is the defendant.

    ``The defendant told the victim that he would share the images`` is his threat.
    """
    if verb is None or _clause_of(verb) != "ccomp":
        return False
    matrix = verb.head
    matrix_subject = next((child for child in matrix.children if child.dep_ in _SUBJECT_DEPS), None)
    own = next((child for child in verb.children if child.dep_ in _SUBJECT_DEPS), None)
    if matrix_subject is None or own is None:
        return False
    if own.pos_ != "PRON":
        return False
    low = matrix_subject.text.lower()
    if low in {"defendant", "accused"}:
        return True
    return bool(records) and len(records) == 1 and low in _known_surnames(records)


def _verb_block(verb, records=None) -> Optional[str]:
    """Why this verb is not a publishable main-clause act, or None."""
    if verb is None:
        return "actor_rejected"
    if _defendant_said(verb):
        return None
    if _clause_is_negated(verb):
        return "negated"
    if verb.lemma_.lower() in _NEG_VERBS or verb.head.lemma_.lower() in _NEG_VERBS and _clause_of(verb) == "xcomp":
        return "negated"
    if verb.lemma_.lower() in _UNREAL or (verb.head.lemma_.lower() in _UNREAL and _clause_of(verb) == "xcomp"):
        return "modal_conditional"
    if any(child.dep_ == "aux" and child.lemma_.lower() in _MODALS for child in verb.children):
        return "modal_conditional"
    if any(child.dep_ == "mark" and child.lemma_.lower() in {"if", "unless"} for child in verb.children):
        return "modal_conditional"
    where = _clause_of(verb)
    if where == "ccomp":
        marked = any(child.dep_ == "mark" for child in verb.children)
        own_subject = any(child.dep_ in _SUBJECT_DEPS for child in verb.children)
        if marked or verb.head.lemma_.lower() in _SPEECH or not own_subject:
            return "reported_speech"
    if where == "xcomp" and verb.head.lemma_.lower() in _NEG_VERBS:
        return "negated"
    if where in {"xcomp", "ccomp"}:
        own = next((child for child in verb.children if child.dep_ in _SUBJECT_DEPS), None)
        if own is not None and own.dep_ in {"nsubjpass", "nsubj:pass"}:
            agent = next((child for child in verb.children if child.dep_ == "agent"), None)
            if agent is None:
                return "passive_subject"
        control = _controlling_object(verb.head, records)
        if control is not None:
            return "actor_rejected"
        if where == "ccomp" and own is None:
            return "actor_rejected"
        if where == "xcomp":
            return None
    if where in _BLOCKED_CLAUSE:
        return "subordinate_clause"
    if not _is_main_verb(verb):
        return "subordinate_clause"
    return None


def _hit_for(record: dict, records: List[dict], scope: Optional[dict], generic: Optional[str]) -> dict:
    if scope is not None and generic == "one" and _same_party(record, scope):
        record = scope
    alone = len(records) == 1
    canonical = "the defendant" if alone else "defendant " + record["full"]
    return {"canonical": canonical, "record": record, "generic": alone}


def _defendant_is_other_argument(verb, subject) -> bool:
    """True when ``the defendant`` is an object or recipient of the act verb."""
    if verb is None:
        return False
    subject_i = subject.i if subject is not None else -1

    def _hit(token) -> bool:
        return token.i != subject_i and token.text.lower() == "defendant"

    for token in verb.children:
        if _hit(token) and token.dep_ in {"dobj", "dative", "iobj", "attr", "oprd", "pobj"}:
            return True
        if token.dep_ in {"prep", "dative"}:
            if any(_hit(child) and child.dep_ == "pobj" for child in token.children):
                return True
    return False


_COURTESY = {"mr", "mister"}
_ROLE_TITLE = {"agent", "officer", "detective", "dr", "doctor", "victim", "special", "sgt", "sergeant"}
_FEMININE = {"ms", "mrs", "miss"}


def _given_names(record: dict) -> set:
    parts = [part.strip(".").lower() for part in record["full"].split()[:-1]]
    return {part for part in parts if part}


def _name_modifiers(subject):
    """Left compounds of a surname: courtesy titles, role titles, and given names."""
    titles, givens = [], []
    for child in subject.children:
        if child.dep_ != "compound" or child.i > subject.i:
            continue
        low = child.text.strip(".").lower()
        if child.pos_ == "ADV" or low in _ADVERB_COMPOUND or low in {"defendant", "accused"}:
            continue
        if low in _COURTESY or low in _ROLE_TITLE or low in _FEMININE:
            titles.append(low)
        else:
            givens.append(child.text.strip("."))
    return titles, givens


def _other_given_on_page(surname: str, record: dict, page_text: str) -> bool:
    """Another capitalized given name in the page shares this surname."""
    known = _given_names(record) | {record["surname"].lower()}
    for alias in record.get("aliases") or []:
        parts = [part.lower() for part in alias.split()]
        if parts and parts[-1] == surname.lower():
            known.update(parts[:-1])
    for match in re.finditer(rf"\b([A-Z][A-Za-z']+)\s+{re.escape(surname)}\b", page_text or ""):
        given = match.group(1).lower()
        if given in known or given in _ADVERB_COMPOUND or given in {"defendant", "accused"}:
            continue
        return True
    return False


def _someone_else_in_a_subordinate(verb) -> bool:
    """``watched as Minor Victim 1 produced`` is not the defendant's act."""
    if verb is None or verb.lemma_.lower() not in _PERCEPTION:
        return False
    for child in verb.children:
        if child.dep_ != "advcl":
            continue
        other = next((token for token in child.children if token.dep_ in _SUBJECT_DEPS), None)
        if other is not None and other.text.lower() not in {"defendant", "accused"}:
            return True
    return False


def _conflicts_with_record(subject, record, page_text: str) -> bool:
    """A given name, initial, or role title that is not this defendant."""
    titles, givens = _name_modifiers(subject)
    if any(title in _ROLE_TITLE for title in titles):
        return True
    known = _given_names(record)
    if any(title in _FEMININE for title in titles) and not givens and known:
        return True
    for given in givens:
        low = given.lower()
        if low == "defendant":
            continue
        if len(low) <= 2:
            if not any(name.startswith(low[:1]) for name in known):
                return True
        elif low not in known:
            return True
    if not givens and not titles:
        surname = subject.text.lower()
        doc = subject.doc
        for token in doc:
            if token.i == subject.i or token.text.lower() != surname:
                continue
            others = [child.text.strip(".").lower() for child in token.children
                      if child.dep_ == "compound" and child.i < token.i]
            others = [name for name in others
                      if name not in _COURTESY and name not in _FEMININE and name not in _ROLE_TITLE
                      and name != "defendant"]
            if any(name not in known for name in others):
                return True
    return False


def _subject_decision(subject, records, generic, scope, other_surnames, actor_text, page_text=""):
    """``(hit, None)`` or ``(None, reason)`` for one main-clause subject token."""
    if subject is None:
        return None, "actor_rejected"
    if subject.text.strip(".").lower() in _SUFFIXES:
        surname = next((child for child in subject.children
                        if child.dep_ == "compound" and child.text.lower() in _known_surnames(records)), None)
        if surname is not None:
            subject = surname
    partners = [child for child in subject.children if child.dep_ == "conj"]
    if subject.dep_ == "conj":
        partners = [subject.head, *[child for child in subject.head.children if child.dep_ == "conj" and child.i != subject.i]]
    if partners:
        if any(token.dep_ == "preconj" and token.lemma_.lower() == "neither" for token in subject.children) or any(
                token.dep_ == "cc" and token.lemma_.lower() == "nor" for token in subject.children):
            return None, "negated"
        group = [subject, *partners]
        surnames = _known_surnames(records)
        ours = [token for token in group if token.text.lower() in {"defendant", "accused"} or token.text.lower() in surnames]
        others = [token for token in group if token not in ours]
        charged_other = {token.text.lower() for token in others} & surnames
        if len(ours) == 1 and others and not charged_other and len(records) == 1:
            return _hit_for(records[0], records, scope, generic), None
        return None, "coordinated_subject"
    if any(child.dep_ == "appos" for child in subject.children):
        return None, "appositive_relation"
    if any(child.dep_ == "prep" and any(g.text.lower() == "defendant" for g in child.subtree) for child in subject.children):
        return None, "appositive_relation"
    word = subject.text.lower()
    phrase = _noun_phrase(subject.doc, subject)
    if word in PRONOUN_WORDS or _PRONOUN.fullmatch(phrase):
        if _defendant_said(subject.head, records) and len(records) == 1:
            return _hit_for(records[0], records, scope, generic), None
        if subject.dep_ not in _SUBJECT_DEPS:
            return None, "pronoun_object"
        return None, "actor_rejected"
    if word in {"defendant", "accused"}:
        if any(child.dep_ == "case" for child in subject.children):
            return None, "appositive_relation"
        if scope is not None and generic == "one":
            return _hit_for(scope, records, scope, generic), None
        if len(records) == 1 and generic == "one":
            return _hit_for(records[0], records, scope, generic), None
        if len(records) > 1:
            return None, "multi_defendant_caption"
        return None, "no_defendant_record"
    found = match_actor(phrase, records, generic=generic, other_surnames=other_surnames)
    if not found or found.get("drop"):
        bare = match_actor(subject.text, records, generic=generic, other_surnames=other_surnames)
        found = bare or found
    if found and found.get("ambiguous"):
        return None, "ambiguous_surname"
    if found and found.get("drop"):
        return None, found["drop"]
    if not found or "canonical" not in found:
        named = match_actor(actor_text, records, generic=generic, other_surnames=other_surnames)
        if named and named.get("ambiguous"):
            return None, "ambiguous_surname"
        if (subject is not None and _one_capital(actor_text)
                and actor_text.lower() == subject.text.lower()
                and subject.text.lower() not in _known_surnames(records)):
            return None, "surname_not_established"
        return None, "actor_rejected"
    if _PRONOUN.fullmatch(" ".join((actor_text or "").split())) and subject.dep_ not in _SUBJECT_DEPS:
        return None, "pronoun_object"
    if _other_given_on_page(subject.text, found["record"], page_text):
        return None, "ambiguous_surname"
    if _conflicts_with_record(subject, found["record"], page_text):
        titles, givens = _name_modifiers(subject)
        if not titles and not givens:
            return None, "ambiguous_surname"
        return None, "actor_rejected"
    return found, None


def _strip_heading(text: str) -> str:
    """Drop a count or paragraph label. A courtesy title such as Mr. stays."""
    return re.sub(
        r"^(?:count\s+(?:[0-9]+|[ivxlcdm]+|[a-z]+)\s*[:.)-]|[0-9]+[.)]|\([0-9]+\))\s+",
        "", (text or "").strip(), count=1, flags=re.I)


_PASSIVE_MARK = re.compile(
    r"\b(?:was|were|been|be)\s+(?:sent|used|distributed|uploaded|received|stored|transmitted|"
    r"shared|posted|forwarded|asked|told|made|kept|given|taken|viewed|accessed|produced|"
    r"possessed|\w+ed)\b",
    re.I,
)
_APPOSITIVE_POSSESSIVE = re.compile(r",\s+the\s+defendant(?:'s|\u2019s)\s+\S+\s*,", re.I)


def _plain_actor(sentence: str, actor_text: str, records: List[dict]) -> Tuple[Optional[dict], Optional[str]]:
    """A missing parse never publishes. Embedded clauses refuse with the rest.

    Bare surnames and passives are ``no_parser``. A possessive, an appositive,
    or a generic actor with no parsed subject is ``actor_rejected``. A capital
    token that is not a caption surname is ``surname_not_established``.
    """
    actor = " ".join((actor_text or "").split())
    if _PASSIVE_MARK.search(sentence or ""):
        return None, "no_parser"
    if (_APPOSITIVE_POSSESSIVE.search(sentence or "") or _POSSESSIVE_ACTOR.search(actor)
            or _ANY_POSSESSIVE.search(actor) or _POSSESSIVE_ACTOR.search(sentence or "")):
        return None, "actor_rejected"
    token = _one_capital(actor)
    if token and token.lower() not in {"defendant", "accused"}:
        if token.lower() not in _known_surnames(records):
            return None, "surname_not_established"
        return None, "no_parser"
    return None, "actor_rejected"


def decide_actor(sentence: str, actor_text: str, records: Optional[List[dict]] = None,
                 generic: Optional[str] = None, scope: Optional[dict] = None,
                 other_surnames: Optional[List[str]] = None,
                 caption_reason: Optional[str] = None,
                 page_text: Optional[str] = None,
                 act_code: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """``(match, reason code)``. A reason means the act is not published.

    This is the only actor decision. A clause is published only when its act
    verb is a main-clause verb, the subject is the defendant or one unique
    name, and the clause is not negated, modal, coordinated, or modified by
    an appositive. A pronoun subject is refused.
    """
    records = list(records or [])
    if generic is None:
        generic = "no_defendant_record" if not records else ("one" if len(records) == 1 else "ambiguous")
    if caption_reason and _GENERIC_ACTOR.fullmatch(" ".join((actor_text or "").split())):
        return None, caption_reason
    if generic == "no_defendant_record" or not records:
        return None, "no_defendant_record"
    if _actor_nlp() is None:
        if v2_active():
            from state_machines.observations.means_parse import model_name
            raise SystemExit(f"v2 coding needs the spaCy model {model_name()}, which is not available")
        return _plain_actor(sentence, actor_text, records)
    nlp = _require_actor_nlp()
    doc = nlp(_strip_heading(sentence or ""))
    verb = _act_verb(doc)
    if (verb is not None and verb.dep_ in {"xcomp", "ccomp"} and _controlling_object(verb.head, records)
            and act_code in _DEFENDANT_SOLICIT):
        verb = verb.head
    blocked = _verb_block(verb, records)
    if blocked == "reported_speech" and _defendant_said(verb, records):
        blocked = None
    if blocked:
        return None, blocked

    def _subject_of(head):
        found = next((token for token in doc if token.dep_ in _SUBJECT_DEPS and token.head == head), None)
        if found is None and head.dep_ == "conj":
            return _subject_of(head.head)
        return found

    if verb is not None and verb.dep_ == "xcomp" and _controlling_object(verb.head, records) is None:
        verb = verb.head
    subject = _subject_of(verb) if verb is not None else None
    if _someone_else_in_a_subordinate(verb) or _defendant_is_other_argument(verb, subject):
        return None, "actor_rejected"
    if re.search(r"\b(?:watched|saw|observed)\s+as\s+(?!the\s+defendant\b)", sentence or "", re.I):
        return None, "actor_rejected"
    wanted = " ".join((actor_text or "").split()).lower()
    if subject is not None and wanted and subject.text.lower() not in wanted and "defendant" not in wanted:
        in_advcl = [token for token in doc if token.text.lower() in wanted.split() and _clause_of(token) == "advcl"]
        if in_advcl:
            return None, "subordinate_clause"
    if "defendant" in wanted:
        mention = next((token for token in doc if token.text.lower() == "defendant"), None)
        if mention is not None and _clause_of(mention) == "advcl" and (subject is None or subject.text.lower() != "defendant"):
            return None, "subordinate_clause"
    agent = next((token for token in doc if token.dep_ == "pobj" and token.head.dep_ == "agent"
                  and token.head.head == verb), None)
    if subject is not None and subject.dep_ in {"nsubjpass", "nsubj:pass"}:
        if agent is not None and _token_names_defendant(agent, actor_text, records):
            subject = agent
        elif _token_names_defendant(subject, actor_text, records):
            return None, "passive_subject"
    if _PRONOUN.fullmatch(" ".join((actor_text or "").split())):
        pronoun = next((token for token in doc if token.text.lower() == actor_text.strip().lower()), None)
        if pronoun is not None and _defendant_said(pronoun.head):
            subject = pronoun
        elif pronoun is None or pronoun.dep_ not in _SUBJECT_DEPS or not _is_main_verb(pronoun.head):
            return None, "pronoun_object"
        else:
            subject = pronoun
    hit, reason = _subject_decision(subject, records, generic, scope, other_surnames, actor_text,
                                    page_text if page_text is not None else sentence)
    if reason:
        return None, reason
    if _GENERIC_ACTOR.fullmatch(" ".join((actor_text or "").split())) or _PRONOUN.fullmatch(" ".join((actor_text or "").split())):
        return hit, None
    proposed = match_actor(actor_text, records, generic=generic, other_surnames=other_surnames)
    if proposed and proposed.get("ambiguous"):
        return None, "ambiguous_surname"
    if proposed and proposed.get("canonical") and hit and not _same_party(proposed["record"], hit["record"]):
        return None, "actor_rejected"
    return hit, None


def _record_hit(record: dict, records: List[dict]) -> dict:
    canonical = "the defendant" if len(records) == 1 else "defendant " + record["full"]
    return {"canonical": canonical, "record": record, "generic": False}


def match_actor(text: str, records: List[dict], *, generic: Optional[str] = None,
                other_surnames: Optional[List[str]] = None) -> Optional[dict]:
    """The caption defendant ``text`` names.

    ``the defendant``, ``defendant`` and ``accused`` match only when the caption
    names exactly one defendant. A possessive phrase does not match. A bare surname
    matches only when that token is capitalized. A full name and ``Defendant <Name>``
    match in any case.
    """
    raw = " ".join((text or "").split())
    if not raw or _ANY_POSSESSIVE.search(raw) or _POSSESSIVE_ACTOR.search(raw):
        return None
    if _GENERIC_ACTOR.fullmatch(raw):
        status = generic
        if status is None:
            status = "no_defendant_record" if not records else ("one" if len(records) == 1 else "ambiguous")
        if status == "no_defendant_record" or not records:
            return {"drop": "no_defendant_record"}
        if status != "one":
            return {"ambiguous": True}
        return {"canonical": "the defendant", "record": records[0], "generic": True}
    named = _NAMED_ACTOR.fullmatch(raw)
    target = " ".join((named.group(1) if named else raw).split())
    parts = [part for part in target.split() if part.lower().strip(".") not in _SUFFIXES]
    low = " ".join(parts).lower()
    if not low:
        return None
    full_hits = []
    for record in records:
        forms = [record["full"].lower(), *[alias.lower() for alias in record.get("aliases", [])]]
        if low in forms:
            full_hits.append(record)
    if len(full_hits) > 1:
        return {"ambiguous": True}
    if len(full_hits) == 1:
        return _record_hit(full_hits[0], records)
    if len(parts) > 1:
        actor_tokens = set(low.split())
        subset = [record for record in records
                  if actor_tokens <= set(record["full"].lower().split())
                  and record["surname"].lower() in actor_tokens]
        if len(subset) > 1:
            return {"ambiguous": True}
        if len(subset) == 1:
            return _record_hit(subset[0], records)
    if len(parts) == 1 and (named or parts[0][:1].isupper()):
        hits = []
        for record in records:
            surnames = [record["surname"].lower(), *[name.lower() for name in record.get("alias_surnames", [])]]
            if parts[0].lower() in surnames:
                hits.append(record)
        blocked = parts[0].lower() in {name.lower() for name in (other_surnames or [])}
        if blocked or len(hits) > 1:
            return {"ambiguous": True}
        if len(hits) == 1:
            return _record_hit(hits[0], records)
    return None


def same_actor(left: str, right: str, records: List[dict], *, generic: Optional[str] = None) -> bool:
    """True when both phrases are the same defendant, ignoring case on a full phrase."""
    if not left or not right:
        return False
    if " ".join(left.split()).lower() == " ".join(right.split()).lower():
        if _PRONOUN.fullmatch(left.strip()):
            return True
        found = match_actor(left, records, generic=generic)
        return bool(found) and not found.get("ambiguous") and not found.get("drop")
    a, b = match_actor(left, records, generic=generic), match_actor(right, records, generic=generic)
    if not a or not b or a.get("ambiguous") or b.get("ambiguous"):
        return False
    return a["canonical"] == b["canonical"]


def build_deny(case_id: str, text_root: Optional[Path] = None) -> List[str]:
    """Names from the case captions. With every v2 flag unset this is the base token list.

    A v2 flag may add tokens from the caption records. It does not drop a base token.
    """
    root = E.text_root(text_root) / case_id
    names = set()
    for page in sorted(root.glob("*/p*.txt")):
        text = page.read_text(encoding="utf-8", errors="replace")
        names |= _base_deny_tokens(text)
    if v2_active():
        for record in defendant_records_for_case(case_id, text_root):
            names |= {word.strip(".,") for word in record["full"].lower().replace(",", " ").split() if word.strip(".,")}
            for alias in record.get("aliases", []):
                names |= {word.strip(".,") for word in alias.lower().replace(",", " ").split() if word.strip(".,")}
    terms = sorted(names)
    (root / "deny.json").write_text(json.dumps(terms, indent=1) + "\n", encoding="utf-8")
    return terms


def check(draft_path: Path, text_root: Optional[Path] = None) -> int:
    from state_machines.evidence.validate import validate

    draft = json.loads(draft_path.read_text())
    bundle, _, problems = compile_draft(draft, text_root)
    for msg in problems:
        print("QUOTE", msg)
    findings = validate(bundle, text_root=text_root, deny_list=deny_list(bundle["case_id"], text_root))
    for f in findings:
        print(f.severity.upper(), f.code, f.where, f.message)
    n_err = len(problems) + sum(f.severity == "error" for f in findings)
    print(f"{len(bundle['events'])} events, {len(bundle['passages'])} passages located, {n_err} errors")
    return 1 if n_err else 0


def write_bundle(bundle: dict, quotes: Dict[str, str], out: Path, text_root: Optional[Path] = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    store = E.load_quotes(bundle["case_id"], text_root)
    store.update({f"{bundle['coding']['coder_id']}:{k}": v for k, v in quotes.items()})
    E.save_quotes(bundle["case_id"], store, text_root)


# --- agreement --------------------------------------------------------------------------

def _spans(bundle: dict, event: dict) -> List[Tuple[str, int, int, int]]:
    ps = {p["passage_id"]: p for p in bundle["passages"]}
    return [(ps[s["passage_id"]]["doc_id"], ps[s["passage_id"]]["pdf_page"], ps[s["passage_id"]]["char_start"],
             ps[s["passage_id"]]["char_end"]) for s in event["support"] if s["facet"] == "action" and s["passage_id"] in ps]


def _overlap(a, b) -> bool:
    return any(x[0] == y[0] and x[1] == y[1] and x[2] < y[3] and y[2] < x[3] for x in a for y in b)


def match_events(a: dict, b: dict) -> List[Tuple[str, str]]:
    """Greedy one-to-one matching of offender events by overlapping action passages, same actor role."""
    role = lambda bundle, e: e["actor"]["role"]  # noqa: E731
    pairs, used = [], set()
    for ea in sorted(a["events"], key=lambda e: e["event_id"]):
        sa = _spans(a, ea)
        best = None
        for eb in sorted(b["events"], key=lambda e: e["event_id"]):
            if eb["event_id"] in used or role(a, ea) != role(b, eb) or not _overlap(sa, _spans(b, eb)):
                continue
            sb = _spans(b, eb)
            # overlap size decides; the action code only breaks an exact tie, which happens when one
            # sentence holds several acts (both cite the same passage). It never outweighs overlap.
            score = sum(max(0, min(x[3], y[3]) - max(x[2], y[2])) for x in sa for y in sb if x[:2] == y[:2])
            key = (score, eb["action"] == ea["action"])
            if best is None or key > best[0]:
                best = (key, eb["event_id"])
        if best:
            used.add(best[1])
            pairs.append((ea["event_id"], best[1]))
    return pairs


def _kappa(x: List[str], y: List[str]) -> Optional[float]:
    n = len(x)
    if n == 0:
        return None
    po = sum(i == j for i, j in zip(x, y)) / n
    cx, cy = Counter(x), Counter(y)
    pe = sum(cx[k] * cy[k] for k in set(cx) | set(cy)) / (n * n)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def agreement(a: dict, b: dict) -> dict:
    pairs = match_events(a, b)
    ea, eb = {e["event_id"]: e for e in a["events"]}, {e["event_id"]: e for e in b["events"]}
    n_a, n_b, m = len(a["events"]), len(b["events"]), len(pairs)
    prec, rec = (m / n_b if n_b else 0), (m / n_a if n_a else 0)
    f1 = round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0
    actions_a = [ea[i]["action"] for i, _ in pairs]
    actions_b = [eb[j]["action"] for _, j in pairs]
    per_class = {}
    for o in V.AFFORDANCES:
        xa = ["1" if any(x["affordance"] == o and x["status"] in ("DIRECT", "INFERRED") for x in ea[i]["affordances"]) else "0" for i, _ in pairs]
        xb = ["1" if any(x["affordance"] == o and x["status"] in ("DIRECT", "INFERRED") for x in eb[j]["affordances"]) else "0" for _, j in pairs]
        per_class[o] = {"kappa": _kappa(xa, xb), "a_yes": xa.count("1"), "b_yes": xb.count("1"),
                        "both_yes": sum(p == q == "1" for p, q in zip(xa, xb))}
    jacc = []
    for i, j in pairs:
        sa = {x["affordance"] for x in ea[i]["affordances"] if x["status"] in ("DIRECT", "INFERRED")}
        sb = {x["affordance"] for x in eb[j]["affordances"] if x["status"] in ("DIRECT", "INFERRED")}
        jacc.append(1.0 if not (sa | sb) else len(sa & sb) / len(sa | sb))
    harms_a = [",".join(sorted({h["harm"] for h in ea[i]["harms"]})) or "-" for i, _ in pairs]
    harms_b = [",".join(sorted({h["harm"] for h in eb[j]["harms"]})) or "-" for _, j in pairs]
    rel = lambda bundle: {(r["from_event"], r["to_event"]) for r in bundle["relations"] if r["type"] in V.ORDER_RELATIONS}  # noqa: E731
    ra, rb = rel(a), rel(b)
    amap = dict(pairs)
    matched_pairs = [(x, y) for x in amap for y in amap if x != y]
    order_a = [(x, y) in ra for x, y in matched_pairs]
    order_b = [(amap[x], amap[y]) in rb for x, y in matched_pairs]
    both_ordered = sum(p and q for p, q in zip(order_a, order_b))
    return {
        "events": {"coder_a": n_a, "coder_b": n_b, "matched": m, "precision_vs_a": round(prec, 3),
                   "recall_vs_a": round(rec, 3), "f1": f1},
        "action_code": {"exact": sum(x == y for x, y in zip(actions_a, actions_b)), "of": m, "kappa": _kappa(actions_a, actions_b)},
        "affordance_per_class": per_class,
        "affordance_set_jaccard_mean": round(sum(jacc) / len(jacc), 3) if jacc else None,
        "harm_set": {"exact": sum(x == y for x, y in zip(harms_a, harms_b)), "of": m, "kappa": _kappa(harms_a, harms_b)},
        "order_on_matched_pairs": {"a_ordered": sum(order_a), "b_ordered": sum(order_b), "both": both_ordered},
        "pairs": pairs,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m state_machines.coding.workflow")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract").add_argument("cases", nargs="+")
    sub.add_parser("check").add_argument("draft", type=Path)
    c = sub.add_parser("compile")
    c.add_argument("draft", type=Path)
    c.add_argument("out", type=Path)
    g = sub.add_parser("agree")
    g.add_argument("a", type=Path)
    g.add_argument("b", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        failed = 0
        for case in args.cases:
            try:
                manifest = extract(case)
            except Exception as exc:                  # noqa: BLE001 - one unreadable case is reported, the batch goes on
                failed += 1
                print(f"{case}: NOT extracted: {type(exc).__name__}: {exc}", file=sys.stderr)
                continue
            out = E.text_root() / case / "sources.json"
            out.write_text(json.dumps(manifest, indent=1) + "\n")
            print(case, len(manifest["documents"]), "documents",
                  sum(len(d["pages"]) for d in manifest["documents"]), "pages ->", out)
            for d in manifest["documents"]:
                if d["doc_type"] == "other":          # an unrecognised label would give every passage the standing PROCEDURAL
                    print(f"{case}: {d['doc_id']} has no recognised document type in its file name; rename the file", file=sys.stderr)
                    failed += 1
        return 1 if failed else 0
    if args.cmd == "check":
        return check(args.draft)
    if args.cmd == "compile":
        bundle, quotes, problems = compile_draft(json.loads(args.draft.read_text()))
        if problems:
            print("\n".join(problems))
            return 1
        write_bundle(bundle, quotes, args.out)
        print(args.out)
        return 0
    if args.cmd == "agree":
        a, b = json.loads(args.a.read_text()), json.loads(args.b.read_text())
        print(json.dumps(agreement(a, b), indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
