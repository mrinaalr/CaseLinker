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


def extract(case_id: str, text_root: Optional[Path] = None) -> dict:
    """Page text for every PDF of a case into the local store; returns the source manifest.
    A document already in the store (same SHA-256) keeps its id and its page text; a new PDF is added."""
    import pymupdf

    folder = E.text_root(text_root) / case_id
    old = json.loads((folder / "sources.json").read_text(encoding="utf-8"))["documents"] if (folder / "sources.json").is_file() else []
    known = {d["sha256"]: d for d in old}
    used = Counter(re.sub(r"_\d+$", "", d["doc_id"]) for d in old)
    docs, files, seen = [], {}, set()
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
        if word in {"defendant", "defendants", "plaintiff", "date", "filed", "judgment", "judgement"}:
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
    r"\d+\s+F\.\s*\d+d|\d+\s+F\.\s*Supp(?:\.\s*\d+d)?|\d+\s+S\.\s*Ct\.|"
    r"\d+\s+U\.?\s*S\.|\b\d+\s*WL\b|\bWL\s+\d+|\bsupra\b|\bNo\.\s*\d",
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
    head = re.split(r"(?<=[A-Za-z]{3})\.\s+", window, maxsplit=1)[0]
    if _REPORTER.search(head):
        return True
    for cite_start, cite_end in citation_spans(text):
        if cite_start < start + len(window) and cite_end > start:
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
            if lines:
                break
            continue
        if piece in {"/", "\\"}:
            continue
        if _DEFENDANT_LINE.search(piece) and not re.search(r"[A-Za-z]{3}", piece.replace("Defendant", "").replace("Defendants", "")):
            break
        label = _DOCKET_LABEL.search(piece)
        if label:
            piece = piece[:label.start()]
        piece = re.split(r"(?<=[A-Za-z]{2})\.\s+", piece, maxsplit=1)[0]
        piece = piece.strip(" ,;")
        if piece:
            lines.append(piece)
        if _DEFENDANT_LINE.search(raw):
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


def _numbered_people(block: str) -> List[dict]:
    """Defendants written as ``(1) NAME`` under a column caption."""
    people = []
    for match in _NUMBERED_DEFENDANT.finditer(block or ""):
        person = _one_person(match.group(1).strip(" ,.)"))
        if person and not _COMPANY.search(person["full"]):
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
    return left_full == right_sur or right_full == left_sur


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
    primary = [item for item in found if item["doc_type"] in _CHARGING_DOCS | _PLEA_DOCS]
    chosen = primary or found
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
            match = next((party for party in records if len(own) == 1 and _same_party(own[0], party)), None)
            if match is not None and not item["et_al"]:
                by_document[item["doc_id"]] = {"generic": "one", "record": match}
            elif generic == "one":
                by_document[item["doc_id"]] = {"generic": "one", "record": records[0]}
            else:
                by_document[item["doc_id"]] = {"generic": "ambiguous", "record": None}
    from state_machines.coding.parties import defendants_for, other_surnames
    court = str(meta.get("court") or "")
    docket = str(meta.get("docket_number") or "")
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
            if disagreement or item["et_al"] or (own and match is None):
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


_LEAD_PIECE = re.compile(
    r"^(?:"
    r"on\s+or\s+about\s+\w+\s+\d{1,2},?\s+\d{4}\s*,\s*"
    r"|between\s+\w+\s+\d{1,2}\s+and\s+\w+\s+\d{1,2},?\s+\d{4}\s*,\s*"
    r"|between\s+\w+\s+and\s+\w+(?:\s+\w+)?\s+\d{4}\s*,\s*"
    r"|in\s+or\s+(?:around|about)\s+\d{4}\s*,\s*"
    r"|at\s+\d{1,2}:\d{2}\s*[ap]\.?m\.?\s*,\s*"
    r"|(?:on|in|during|after|before)\s+\w+\s+\d{1,2},?\s+\d{4}\s*,\s*"
    r"|(?:on|in|during|after|before)\s+[^,]{0,60},\s*"
    r"|(?:then|later|however|thereafter)\s*,\s*"
    r")",
    re.I,
)
_SUBJECT = re.compile(
    r"((?:[Tt]he\s+)?[Dd]efendant(?:s)?(?:\s+[A-Z][\w'.-]+){0,3}"
    r"|(?:[Tt]he\s+)?[Aa]ccused(?:\s+[A-Z][\w'.-]+){0,3}"
    r"|[A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,3})"
)
_ANY_POSSESSIVE = re.compile(r"\b[\w.\-]+(?:'s|\u2019s)\b")
_PASSIVE = re.compile(
    r"\b(?:was|were|been|be)\s+(?:sent|used|distributed|uploaded|received|stored|transmitted|"
    r"shared|posted|forwarded|asked|told|made|kept|given|taken|viewed|accessed|produced|"
    r"possessed|\w+ed)\b",
    re.I,
)


def _strip_lead(text: str) -> str:
    while True:
        match = _LEAD_PIECE.match(text)
        if not match:
            return text
        text = text[match.end():]


def clause_subject(sentence: str) -> str:
    """The grammatical subject of the act's clause, after a leading adverbial or date.

    A possessive (``Smith's mother``, ``the defendant's mother``) is that whole
    phrase, so it is not read as the defendant. A following lowercase word is not
    part of the name. Whether a bare surname is the clause subject is decided by
    the dependency parse, not by a verb list.
    """
    text = _strip_lead((sentence or "").strip())
    possessive = re.match(
        r"((?:[Tt]he\s+[Dd]efendant|[Tt]he\s+[Aa]ccused|[A-Z][\w'.-]+)(?:'s|\u2019s)"
        r"\s+[A-Za-z][\w'.-]+)",
        text,
    )
    if possessive:
        return possessive.group(1)
    match = _SUBJECT.match(text)
    return match.group(1) if match else ""


def is_passive(sentence: str) -> bool:
    """True when the clause's subject is the patient of a passive verb."""
    return bool(_PASSIVE.search(sentence or ""))


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


def _passive_voice(sentence: str):
    """``(recipient, agent)`` when the clause is passive, else None.

    ``no_parser`` when a passive mark is present and spaCy is absent. The
    recipient is nsubjpass. The actor, if named, is the object of ``by``.
    """
    if not is_passive(sentence or ""):
        return None
    nlp = _actor_nlp()
    if nlp is None:
        return "no_parser"
    doc = nlp(sentence or "")
    recipients = [token for token in doc if token.dep_ in {"nsubjpass", "nsubj:pass"}]
    agent = next((token for token in doc if token.dep_ == "pobj" and token.head.text.lower() == "by"), None)
    if not recipients:
        return None
    return recipients[0], agent


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


def _surname_is_subject(sentence: str, surname: str) -> Optional[bool]:
    """True when ``surname`` is nsubj or nsubjpass. None when no parser is available."""
    nlp = _actor_nlp()
    if nlp is None:
        return None
    doc = nlp(sentence or "")
    target = surname.lower()
    return any(token.text.lower() == target and token.dep_ in _SUBJECT_DEPS for token in doc)


_POSSESSIVE_SUBJECT = re.compile(
    r"^(?:the\s+)?defendant(?:'s|\u2019s)\s+\S+",
    re.I,
)
_APPOSITIVE_POSSESSIVE = re.compile(
    r",\s+the\s+defendant(?:'s|\u2019s)\s+\S+\s*,",
    re.I,
)


def _generic_subject(text: str) -> bool:
    """True when the phrase is the words 'the defendant' or 'the accused'."""
    return " ".join((text or "").split()).lower() in {
        "the defendant", "defendant", "the accused", "accused",
    }


def _possessive_other(sentence: str, subject: str) -> bool:
    """True when the subject is 'the defendant's <word>', whatever that word is."""
    if _POSSESSIVE_SUBJECT.match(" ".join((subject or "").split())):
        return True
    return bool(_APPOSITIVE_POSSESSIVE.search(sentence or ""))


def _distinguished_from_defendant(sentence: str, records: List[dict]) -> bool:
    """True when the subject is someone the sentence sets apart from the defendant."""
    if _possessive_other(sentence, clause_subject(sentence)):
        return True
    nlp = _actor_nlp()
    if nlp is None:
        return False
    doc = nlp(sentence or "")
    surnames = _known_surnames(records)
    reflexive = any(token.text.lower() in {"herself", "himself"} for token in doc)
    defendant_is_other = any(token.text.lower() == "defendant" and token.dep_ in {"dative", "dobj", "pobj"} for token in doc)
    surname_is_subject = any(token.text.lower() in surnames and token.dep_ == "nsubj" for token in doc)
    return bool(reflexive and defendant_is_other and surname_is_subject)


def _bare_surname_reason(sentence: str, text: str, records: List[dict]) -> Optional[str]:
    """Why a bare surname may not be the actor, or None when this phrase is not one.

    Establishment is the case's parsed surnames. The dependency parse decides
    whether that token is the clause subject. No parser means ``no_parser``.
    """
    token = _one_capital(text)
    if token is None or token.lower() in {"defendant", "defendants", "accused", "he", "she", "they", "him", "her", "the", "a", "an"}:
        return None
    if token.lower() not in _known_surnames(records):
        return "surname_not_established"
    parsed = _surname_is_subject(sentence, token)
    if parsed is None:
        return "no_parser"
    if parsed:
        return None
    return "actor_rejected"


def decide_actor(sentence: str, actor_text: str, records: Optional[List[dict]] = None,
                 generic: Optional[str] = None, scope: Optional[dict] = None,
                 other_surnames: Optional[List[str]] = None) -> Tuple[Optional[dict], Optional[str]]:
    """``(match, drop reason)`` for one act. A reason means the act is not published.

    The coder and missed-act recovery both use this. A full name, ``Defendant
    <Surname>``, and ``the defendant`` do not need the parser. A bare surname does.
    """
    records = list(records or [])
    if generic is None:
        generic = "no_defendant_record" if not records else ("one" if len(records) == 1 else "ambiguous")
    if generic == "no_defendant_record" or not records:
        return None, "no_defendant_record"
    subject = clause_subject(sentence)
    voice = _passive_voice(sentence)
    agent_is_actor = False
    if voice == "no_parser":
        return None, "no_parser"
    if voice:
        recipient, agent = voice
        if _token_names_defendant(recipient, actor_text, records):
            return None, "passive_subject"
        if agent and _token_names_defendant(agent, actor_text, records):
            subject = agent.text
            agent_is_actor = True
    if _GENERIC_ACTOR.fullmatch(" ".join((actor_text or "").split())):
        if not agent_is_actor and not _generic_subject(subject):
            return None, "actor_rejected"
        if scope is not None and generic == "one":
            alone = len(records) == 1
            canonical = "the defendant" if alone else "defendant " + scope["full"]
            return {"canonical": canonical, "record": scope, "generic": True}, None
        if generic != "one":
            return None, "ambiguous"
    if _distinguished_from_defendant(sentence, records):
        return None, "actor_rejected"
    if not agent_is_actor:
        for candidate in (actor_text, subject):
            reason = _bare_surname_reason(sentence, candidate, records)
            if reason:
                return None, reason
    if re.fullmatch(r"(?:he|him|she|her|they|them|their)", " ".join((actor_text or "").split()), re.I):
        return None, None
    found = match_actor(actor_text, records, generic=generic, other_surnames=other_surnames)
    if found and found.get("drop"):
        return None, found["drop"]
    if found and found.get("ambiguous"):
        return None, "ambiguous"
    if not same_actor(actor_text, subject, records, generic=generic):
        return None, "actor_rejected"
    if not found or "canonical" not in found:
        return None, "actor_rejected"
    return found, None


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
        if re.fullmatch(r"(?:he|him|she|her|they|them|their)", left.strip(), re.I):
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
            names |= set(record["full"].lower().split())
            for alias in record.get("aliases", []):
                names |= set(alias.lower().split())
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
