# Extensions

New readers for CaseLinker, rehearsed and measured on stored text. `run_gate` and `profile_new_source` load it; ingest never does, and nothing it reads is stored. See [Repair and expand](../caselinker_mcp/README.md#repair-and-expand).

| Extension | Field | Type | Kinds | Roles |
|---|---|---|---|---|
| [`restitution`](restitution/) | `restitution` | `money` | `press_release` | `ordered`, `exposure` |

## Contract

`extensions/<name>/extension.py`:

```python
DOCUMENT_KINDS = ("press_release",)   # press_release, pacer, investigative_note, cybertip
FIELDS = {"restitution": "money"}     # new fields only: number, money, duration, literal

def detect_restitution(ctx):          # every detect_* is a detector; ctx.text, ctx.doc_kind, ctx.case_id
    return [{"field": "restitution", "role": "ordered",
             "span_start": s, "span_end": e, "confidence": 0.8}]
```

- The span is the value. The gate reads it from the span and ignores any `value`.
- `FIELDS` and `DOCUMENT_KINDS` are literals; they are parsed, not imported.
- `age`, `sentence`, `investigation_type` stay out of `FIELDS` and go through the core span gate.

`test_extension.py` runs a made-up `SAMPLE` and asserts the kept spans, values and roles. No real text, no names.

## Run

`scaffold_extension(name, field, value_type)` → write the pattern and the test → `run_gate(extension=name)` → `profile_new_source(path, extension=name)`.

```bash
DATABASE_URL='' .venv/bin/python -m pytest -q extensions/<name>/test_extension.py
```

A pass lists the cases a change moves; reading them is the review. Storing a field, a new document kind, or a backfill is the maintainer's call. Add a row to the table with each extension.
