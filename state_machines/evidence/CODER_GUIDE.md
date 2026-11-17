# Coder guide (pilot)

How to code one PACER case into a draft, step by step. The rules are in [CODEBOOK.md](CODEBOOK.md); read it first.

**Contents:**
- [Inputs](#inputs)
- [Blindness](#blindness)
- [What you write](#what-you-write)
- [Draft format](#draft-format)
- [Check your draft](#check-your-draft)
- [Done means](#done-means)

## Inputs

Everything below is in `local/pacer_text/<case_id>/`. That store is gitignored, because the court text contains names.

| File | What it is |
|---|---|
| `sources.json` | Documents, doc types and per-page text method. Your draft already contains it. |
| `<doc_id>/pNNNN.txt` | Page text (1-based PDF page). Quote from these files. |
| `<doc_id>/pNNNN.png` | Page image. It exists for OCR pages only. |
| `drafts/<coder_id>/draft.json` | Your draft. Edit only your own. |

## Blindness

Do **not** open any of these:
- `state_machines/`;
- any `_facts.txt` (including git history);
- `research/afh-v2-trajectories/evidence/`;
- any `ontology/PACER/**/*.jsonld`;
- `lstar_all_cases.json`;
- press releases;
- another coder's draft.

Code only from the page text.

## What you write

Fill `passages`, `actors`, `events`, `relations` and `tracks`. Leave `documents` as given, except for two things on OCR pages:

- **For every OCR page you quote,** open its PNG and confirm that the quoted words are what the page shows. Then set that page's `image_checked: true`, and add `limitations` if any apply (`strikethrough`, `handwriting`, `redaction`, `stamp_overlap`, `low_contrast`).
- **Never quote struck-through text** as the document's content.

### Passages

Each passage is one quote from one page:

```json
{"passage_id": "p01", "doc_id": "statement_of_offense", "pdf_page": 2,
 "quote": "exact words copied from the page text", "source_status": "ADMITTED"}
```

- Copy the words from `pNNNN.txt`. Whitespace and line breaks may differ; the words may not.
- Use 6–40 words, and make the quote unique on its page.
- `source_status` defaults by document type (CODEBOOK G). Add `"source_status_reason"` if you use anything else.

### Actors

Actors are pseudonymous: `D1` (defendant), `C1` (co-offender), `V1`, `V2` (victims), `UC1` (undercover officer or persona), `LE1` (law enforcement), `G1` (guardian), `PL1` (platform), `T1` (third party), `CT1` (court).

```json
{"actor_ref": "V1", "role": "victim", "victim_kind": "minor", "age_band": "13-15", "description": "minor victim 1"}
```

### Events

```json
{"event_id": "e01", "actor_ref": "D1", "target_refs": ["V1"], "co_actor_refs": [],
 "action": "INITIATE_CONTACT", "outcome": "completed",
 "description": "Defendant first contacts the minor on a messaging app.",
 "support": [{"passage_id": "p01", "facet": "action", "status": "DIRECT"}],
 "status": "DIRECT",
 "time": {"earliest": "2018-10-13", "latest": "2018-10-13", "precision": "day", "basis": "explicit_date", "passage_ids": ["p01"]},
 "repetition": {"kind": "single"},
 "platform_mentions": [{"platform_surface": "Snapchat", "passage_ids": ["p01"]}],
 "affordances": [], "candidate_affordances": [], "access": [], "harms": [],
 "review": {"status": "single_coder", "coders": ["coder_A"]}}
```

- **`description`:** your own words, at most 200 characters. No names, initials, handles, phone numbers, emails, addresses or graphic detail. Say "the defendant", "the minor", "the undercover officer".
- **Affordance:** `{"affordance": "unmonitored_communication", "basis": "feature_stated", "feature_term": "private messages", "platform_surface": "Snapchat", "status": "DIRECT", "support": [{"passage_id": "p03", "facet": "feature", "status": "DIRECT"}]}`. This is level C (instrumental). A platform name alone is never level C: record it as a `platform_mentions` entry when the platform is only named, or as a `platform_interactions` entry when the passage says the act went through it (codebook B).
- **Platform interaction:** `{"platform_surface": "Kik", "status": "DIRECT", "support": [{"passage_id": "p04", "facet": "platform", "status": "DIRECT"}]}`.
- **Harm:** `{"harm": "HARM_COERCED_SELF_GENERATED_IMAGERY", "victim_ref": "V1", "status": "DIRECT", "support": [...]}`.
- **Access:** `{"form": "person_communicative", "target_ref": "V1", "status": "DIRECT", "support": [...]}`.
- **Time:** no date in the source means `{"precision": "none", "basis": "none", "passage_ids": []}`.

### Relations

Add a relation only when a passage, or two dated events, establishes it:

```json
{"relation_id": "r01", "type": "BEFORE", "from_event": "e01", "to_event": "e02",
 "basis": "explicit_sequence_language", "status": "DIRECT",
 "support": [{"passage_id": "p02", "facet": "time", "status": "DIRECT"}]}
```

| Type | Use when |
|---|---|
| `BEFORE` | Known order |
| `MEETS` | Only for explicit "immediately" or "then" sequencing |
| `INTERRUPTS` | e.g. an arrest interrupting an attempt |
| `RESPONDS_TO`, `RESUMES_AFTER`, `REPEATS` | As named |

Leave events unordered when the source does not order them.

### Tracks

One track per victim, undercover persona, material set or co-offender network:

```json
{"track_id": "v1", "kind": "victim", "anchor_ref": "V1", "event_ids": ["e01", "e02"]}
```

## Draft format

The draft is the bundle format of [`schema/case_bundle.schema.json`](schema/case_bundle.schema.json), with one difference: passages carry `quote` instead of offsets and hashes. The compiler adds those.

## Check your draft

From the repository root:

```bash
.venv-phase4/bin/python -m trajectories.pilot check local/pacer_text/<case_id>/drafts/<coder_id>/draft.json
```

Fix every `QUOTE` and `ERROR` line. `WARNING T04` about unverified OCR pages goes away once you have checked the page image.

## Done means

- `check` reports 0 errors.
- Every substantive act of the defendant(s) the documents describe is an event.
- Victim responses and law-enforcement events are recorded wherever they order or interrupt offender conduct.
