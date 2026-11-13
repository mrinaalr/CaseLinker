"""restitution: reads the restitution amount a press release states. Rehearsal only until the maintainer admits it.

The example extension for caselinker_mcp/README.md, "Repair and expand". It raises a
field CaseLinker does not store (restitution), so run_gate and profile_new_source can
measure it while nothing in the corpus changes.

- Every function named detect_* is a detector. It gets a DetectorContext (ctx.text,
  ctx.doc_kind, ctx.case_id) and returns a list of candidates.
- A candidate is field, role, span_start, span_end and confidence. The span is the
  amount itself: the gate reads the value from the span and ignores any other.
- FIELDS lists fields CaseLinker does not already gate, with the value type the gate
  checks the span against.
"""

import re

DOCUMENT_KINDS = ("press_release",)
FIELDS = {"restitution": "money"}

_MONEY = r"(\$\s?\d(?:[\d,]*\d)?(?:\.\d{2})?(?:\s*(?:million|thousand))?)"
# "$5,000 in restitution", "$2,500 restitution"
_AMOUNT_FIRST = re.compile(_MONEY + r"\s+(?:in\s+)?restitution\b", re.IGNORECASE)
# "restitution of $5,000", "restitution in the amount of $5,000", "restitution totaling $5,000"
_AMOUNT_AFTER = re.compile(
    r"\brestitution\s+(?:of|totall?ing|amounting\s+to|in\s+the\s+amount\s+of)\s+" + _MONEY, re.IGNORECASE
)
# "faces up to ... restitution", "could be ordered": the law's ceiling, not an order.
_NOT_ORDERED = re.compile(r"\b(?:faces?|facing|could|may|up\s+to|maximum)\b", re.IGNORECASE)


def detect_restitution(ctx):
    out = []
    for pattern in (_AMOUNT_FIRST, _AMOUNT_AFTER):
        for m in pattern.finditer(ctx.text):
            left = ctx.text[max(0, m.start() - 60):m.start()]
            role = "exposure" if _NOT_ORDERED.search(left) else "ordered"
            out.append({"field": "restitution", "role": role, "span_start": m.start(1), "span_end": m.end(1),
                        "confidence": 0.8})
    return out
