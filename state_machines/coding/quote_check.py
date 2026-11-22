"""Confirm a stored quote is the page text at the stored offsets.

Read-only. Each coded act, means, actor mention or platform mention is checked
the same way: the passage hash must be the hash of the stored page, and the
page slice at the stored offsets must equal the stored quote, word for word.
A miss is reported with the case id and the item id. This command does not
read ``state_machines/data``, ``local`` or ``caselinker_oxigraph``.

    python -m state_machines.coding.quote_check records.json --pages pages.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

from state_machines.coding.disagreement import refuse_store
from state_machines.evidence import evidence as E

REQUIRED = ("case_id", "item_id", "passage_hash", "char_start", "char_end", "quote")


def quote_item(*, case_id: str, item_id: str, passage_hash: str, char_start: int, char_end: int, quote: str,
               kind: str = "") -> dict:
    """One checkable record. The quote is the exact source sentence (or span)."""
    item = {"case_id": case_id, "item_id": item_id, "passage_hash": passage_hash,
            "char_start": char_start, "char_end": char_end, "quote": quote}
    if kind:
        item["kind"] = kind
    return item


def missing_fields(item: dict) -> List[str]:
    return [name for name in REQUIRED if name not in item or item[name] in ("", None)]


def check_item(item: dict, pages: Dict[str, str]) -> Optional[dict]:
    """A mismatch, or None when the quote is verbatim at the offsets on the hashed page.

    ``stale_hash``: the passage hash is not a stored page.
    ``offset_off``: the quote does occur on that page, but not at these offsets.
    ``paraphrased``: the quote does not occur on that page at all.
    """
    missing = missing_fields(item)
    if missing:
        return {"case_id": item.get("case_id"), "item_id": item.get("item_id"), "problem": "missing_fields",
                "fields": missing}
    page = pages.get(item["passage_hash"])
    if page is None:
        return {"case_id": item["case_id"], "item_id": item["item_id"], "problem": "stale_hash"}
    start, end, quote = item["char_start"], item["char_end"], item["quote"]
    if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(page) and page[start:end] == quote:
        return None
    problem = "offset_off" if isinstance(quote, str) and quote and quote in page else "paraphrased"
    return {"case_id": item["case_id"], "item_id": item["item_id"], "problem": problem}


def check_items(items: List[dict], pages: Dict[str, str]) -> List[dict]:
    return [m for m in (check_item(item, pages) for item in items) if m]


def item_from_span(*, case_id: str, item_id: str, page_text: str, char_start: int, char_end: int, kind: str = "") -> dict:
    """A record whose quote is the page slice. Used for an observation, a passage or a frame slot."""
    return quote_item(case_id=case_id, item_id=item_id, passage_hash=E.sha256_text(page_text),
                      char_start=char_start, char_end=char_end, quote=page_text[char_start:char_end], kind=kind)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("records", type=Path, help="JSON list of quote records")
    ap.add_argument("--pages", type=Path, required=True, help="JSON object of passage hash to page text")
    args = ap.parse_args(argv)
    refuse_store(args.records)
    refuse_store(args.pages)
    items = json.loads(args.records.read_text(encoding="utf-8"))
    pages = json.loads(args.pages.read_text(encoding="utf-8"))
    mismatches = check_items(items, pages)
    json.dump({"checked": len(items), "mismatches": mismatches}, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
