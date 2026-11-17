# Extensions

Extensions allow CaseLinker to read new fields. Developers and agents can propose new readers, then rehearse and evaluate them on stored text. See [Repair and expand](../caselinker_mcp/README.md#repair-and-expand) for the MCP tools that build and benchmark them.

| Tool | Does |
|---|---|
| `scaffold_extension` | Writes `extensions/<name>/` |
| `run_gate(extension=…)` | Runs it on a frozen sample of stored cases; reports what the gate keeps and which cases it would move |
| `profile_new_source(path, extension=…)` | Runs it on a new document |

Results live in those reports. Adopting an extension into ingest, or storing its field, is a maintainer decision.

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

## Test

```bash
DATABASE_URL='' .venv/bin/python -m pytest -q extensions/<name>/test_extension.py
```

A gate pass lists the cases a change moves; reading them is the review. Add a row to the table with each extension.
