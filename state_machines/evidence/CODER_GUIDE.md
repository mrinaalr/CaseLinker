# Coder guide

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
- another coder's draft;
- published bundles and graphs (`state_machines/data/`, `local/releases/`);
- press releases and case summaries.

Code only from the page text.

## What you write

Fill `passages`, `participants`, `events`, `relations` and `tracks`. Leave `documents` as given, except for two things on OCR pages:

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

### Participants

Participants are pseudonymous and persist across the case: `P1`, `P2`, … (CODEBOOK, participants and roles). Legal status lives here, cited; what each participant does lives on the events.

```json
{"participant_ref": "P2", "kind": "person", "age_band": "13-15",
 "legal_status": [{"status": "named_victim", "support": [{"passage_id": "p01", "facet": "legal_status", "status": "DIRECT"}]}]}
```

A group the source treats as one party is a `collective`, with cited `members` and `count` where the source gives them:

```json
{"participant_ref": "P4", "kind": "collective",
 "count": {"min": 3, "max": null, "stated": "at_least", "support": [{"passage_id": "p08", "facet": "count", "status": "DIRECT"}]}}
```

### Events

```json
{"event_id": "e01", "action": "INITIATE_CONTACT", "outcome": "completed",
 "actor": {"participant_ref": "P1", "role": "offender"},
 "co_actors": [], "targets": [{"participant_ref": "P2", "role": "victim"}], "unresolved_participants": [],
 "description": "Defendant first contacts the minor in a public group.",
 "support": [{"passage_id": "p01", "facet": "action", "status": "DIRECT"}],
 "status": "DIRECT",
 "time": {"assertions": [{"expression": "March 2024", "precision": "month", "earliest": "2024-03-01", "latest": "2024-03-31",
                          "basis": "explicit_date", "status": "DIRECT", "passage_ids": ["p09"]}]},
 "repetition": {"kind": "single"},
 "platform_mentions": [], "platform_interactions": [], "channels": [],
 "affordances": [], "candidate_affordances": [], "access": [], "harms": [],
 "review": {"status": "single_coder", "coders": ["coder_A"]}}
```

- **`description`:** your own words, at most 200 characters. No names, initials, handles, phone numbers, emails, addresses or graphic detail. Say "the defendant", "the minor", "the undercover officer".
- **Affordance:** `{"affordance": "unmonitored_communication", "basis": "feature_stated", "feature_term": "private messages", "platform_surface": "Snapchat", "status": "DIRECT", "support": [{"passage_id": "p03", "facet": "feature", "status": "DIRECT"}]}`. This is level C (instrumental). A platform name alone is never level C: record it as a `platform_mentions` entry when the platform is only named, or as a `platform_interactions` entry when the passage says the act went through it (codebook B).
- **Roles:** code only the role the passage supports. A party in the act whose role the source leaves open goes in `unresolved_participants`: `{"participant_ref": "P4", "note": "present; role not stated", "passage_ids": ["p05"]}`.
- **Platform interaction:** `{"platform_surface": "Kik", "platform_key": "Kik", "mode": "through", "audience": "one_to_one", "status": "DIRECT", "support": [{"passage_id": "p04", "facet": "platform", "status": "DIRECT"}]}`. An unnamed platform gets `"platform_key": "unnamed:messaging application"`.
- **Channel:** `{"channel": "sms", "status": "DIRECT", "support": [...]}`. SMS, calls, email, mail and in-person meetings are channels, never platforms.
- **Harm:** `{"harm": "HARM_COERCED_SELF_GENERATED_IMAGERY", "victim_ref": "P2", "victim_kind": "minor", "status": "DIRECT", "support": [...]}`.
- **Access:** `{"form": "person_communicative", "target_ref": "P2", "status": "DIRECT", "support": [...]}`.
- **Time:** one assertion per cited statement of when; keep the source's wording in `expression`. A date that comes only from an enclosing period (a count's date range) is `"basis": "enclosing_window"` and `INFERRED`. Keep conflicting assertions and set `"conflict_flagged": true`. No date in the source means `{"assertions": []}`.

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
| `SAME_ACT` | Two events may describe the same act (often across documents). Always `INFERRED`; keep both events. |

A passage that states relative order ("after that first contact") supports a `DIRECT` `BEFORE` without any date. Leave events unordered when the source does not order them.

### Tracks

One track per victim, undercover persona, material set or co-offender network:

```json
{"track_id": "v1", "kind": "victim", "anchor_ref": "P2", "event_ids": ["e01", "e02"]}
```

## Draft format

The draft is the bundle format of [`schema/case_bundle.schema.json`](schema/case_bundle.schema.json), with one difference: passages carry `quote` instead of offsets and hashes. The compiler adds those.

## Check your draft

From the repository root:

```bash
python -m state_machines.coding.workflow check local/pacer_text/<case_id>/drafts/<coder_id>/draft.json
```

Fix every `QUOTE` and `ERROR` line. `WARNING T04` about unverified OCR pages goes away once you have checked the page image; `WARNING T17` lists the roles left for adjudication.

## Done means

- `check` reports 0 errors.
- Every substantive act of the defendant(s) the documents describe is an event.
- Victim responses and law-enforcement events are recorded wherever they order or interrupt offender conduct.
