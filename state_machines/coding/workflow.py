"""Pilot tooling: page text, coding drafts, compilation, agreement, outputs.

    python -m state_machines.pilot extract <case_id> [...]      page text + source manifest
    python -m state_machines.pilot check <draft.json>           compile a coder draft and validate it
    python -m state_machines.pilot compile <draft.json> <out>   write the committed bundle (no quote text)
    python -m state_machines.pilot agree <bundle_a> <bundle_b>  agreement between two coders
    python -m state_machines.pilot outputs <bundle> <outdir>    derive, emit graphs, SHACL, report

A coder **draft** is the bundle format with one difference: each passage carries its
``quote`` instead of offsets and hashes. Drafts live in the local store (they contain
source text); ``compile`` locates each quote on its page, records offsets and hashes,
writes the quotes to ``quotes.json`` and emits a bundle with no quote text.

PDFs are read from ``$CASELINKER_PACER_SOURCE`` (default: ontology/PACER in this checkout;
the PDFs are gitignored, so point it at the main checkout). Nothing is written there.
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

PILOT_CASES = ("enticement", "ncis_2023_001", "svicac_2022_009", "texas_ag_2019_013", "anchorage_pd_2022_006")
ANCHOR_DIRS = {"enticement": "ENTICEMENT", "production": "PRODUCTION", "sextortion": "SEXTORTION",
               "enterprise": "ENTERPRISE", "trafficking": "TRAFFICKING"}
DOC_TYPE_WORDS = [  # first match wins; order matters
    ("fourth superseding indictment", "superseding_indictment"), ("second superseding indictment", "superseding_indictment"),
    ("third superseding indictment", "superseding_indictment"), ("superseding indictment", "superseding_indictment"),
    ("statement of offense", "statement_of_offense"), ("statement of facts", "statement_of_facts"),
    ("stipulation of facts", "stipulation_of_facts"), ("factual basis", "factual_basis"), ("factual proffer", "factual_proffer"),
    ("plea transcript", "plea_transcript"), ("plea agreement", "plea_agreement"), ("findings of fact", "findings_of_fact"),
    ("amended judgment", "amended_judgment"), ("statement of reasons", "statement_of_reasons"), ("judgment", "judgment"),
    ("sentencing", "sentencing_memorandum"), ("trial brief", "trial_brief"), ("criminal complaint", "complaint"),
    ("complaint", "complaint"), ("information", "information"), ("indictment", "indictment"), ("docket", "docket"),
]
MIN_TEXT_CHARS = 300  # per page; below this the page is treated as a scan


def source_root() -> Path:
    return Path(os.environ.get("CASELINKER_PACER_SOURCE", E.REPO_ROOT / "ontology" / "PACER"))


def case_pdfs(case_id: str) -> List[Path]:
    root = source_root()
    if case_id in ANCHOR_DIRS:
        return sorted((root / ANCHOR_DIRS[case_id]).glob("*.pdf"))
    pat = re.compile(rf"-- ?{re.escape(case_id)} ?--", re.I)
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
    """Page text for every PDF of a case into the local store; returns the source manifest."""
    import pymupdf

    docs, used = [], Counter()
    for pdf in case_pdfs(case_id):
        kind = doc_type_of(pdf)
        used[kind] += 1
        doc_id = kind if used[kind] == 1 else f"{kind}_{used[kind]}"
        d = pymupdf.open(str(pdf))
        pages = []
        for i, page in enumerate(d, 1):
            text = page.get_text()
            if len(text.strip()) >= MIN_TEXT_CHARS:
                method, conf = "text_layer", None
            else:
                text, conf = _ocr(page)
                method = "ocr"
            sha = E.write_page(case_id, doc_id, i, text, text_root)
            pages.append({"pdf_page": i, "text_method": method, "page_text_sha256": sha, "court_page_label": None,
                          "ocr_engine": "tesseract 5 (psm 6, 300 dpi)" if method == "ocr" else None,
                          "ocr_mean_confidence": conf, "image_checked": False, "limitations": []})
        docs.append({"doc_id": doc_id, "doc_type": kind, "source_path": str(pdf.relative_to(source_root())),
                     "sha256": E.sha256_file(pdf), "ecf_document_number": None, "filed_date": None,
                     "page_count": len(pages), "pages": pages})
    return {"case_id": case_id, "documents": docs}


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
            # overlap size only: preferring same-action pairs would inflate action agreement
            score = sum(max(0, min(x[3], y[3]) - max(x[2], y[2])) for x in sa for y in sb if x[:2] == y[:2])
            if best is None or score > best[0]:
                best = (score, eb["event_id"])
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
    ap = argparse.ArgumentParser(prog="python -m state_machines.pilot")
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
        for case in args.cases:
            manifest = extract(case)
            out = E.text_root() / case / "sources.json"
            out.write_text(json.dumps(manifest, indent=1) + "\n")
            print(case, len(manifest["documents"]), "documents",
                  sum(len(d["pages"]) for d in manifest["documents"]), "pages ->", out)
        return 0
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
