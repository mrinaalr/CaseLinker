# Coding

How a court record becomes an adjudicated bundle. Two coders work from the page text independently; agreement is measured; the author decides every disagreement with the passages in front of them.

**Contents:**
- [Steps](#steps)
- [Agreement](#agreement)
- [Adjudication](#adjudication)

## Steps

| Step | Tool | Output |
|---|---|---|
| 1. Page text | `workflow.py extract` | per page: text (text layer, or OCR with the page image checked) and its hash, under `local/pacer_text/<case_id>/` |
| 2. Draft | each coder, following the [coder guide](../evidence/CODER_GUIDE.md) | a draft bundle per coder, with quotes in the local store |
| 3. Check | `workflow.py check` | validation findings (T01–T19) against the page text |
| 4. Compile | `workflow.py compile` | the coder's bundle: passages located and hashed, quotes kept local |
| 5. Agree | `workflow.py agree` | event matching by passage overlap, action κ, affordance and harm agreement, order agreement |
| 6. Adjudicate | `adjudication.py`, `adjudication_packet.py` | one item per disagreement; a local HTML packet with the passages and a decision form |
| 7. Report | `release_report.py` | agreed cores, derived views, graphs, privacy scan and a release report |

Page text, quotes and the adjudication packet stay in `local/` (gitignored): they contain court text.

## Agreement

Events are matched across coders by the overlap of the passages they cite, never by action code, so agreement is not inflated by matching like with like. Reported per case: event precision, recall and F1; action κ on matched events; affordance agreement per class; harm agreement; order agreement on matched pairs. The agreed core keeps what both coders coded.

## Adjudication

Each disagreement becomes an item: events only one coder found, action, status, actor, harm, time and affordance mismatches, platform codings, order relations only one coder found, and one-step trajectories worth a second look. The packet shows both codings, the passages, links to the PDF pages, and records a decision per item. Decisions turn events and relations `adjudicated`; only then can a release include them.
