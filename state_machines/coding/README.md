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
| 6. Agreed core | `release_report.py` | what both coders coded, labelled `agreed` |
| 7. Dossier | `adjudication.py dossier` | every open item per case, with fixed decision options |
| 8. Decide | `adjudication_packet.py` | a local HTML packet: both codings, passages, PDF page links, a choice per item; exports `<case>.decisions.json` |
| 9. Apply | `adjudication.py apply` | the adjudicated bundle in the release, validated; refused while anything is undecided |
| 10. Release | `graphs/release.py build` | derived views, graphs, SHACL, manifest; `ADJUDICATION.md` counts what was decided |

Page text, quotes and the adjudication packet stay in `local/` (gitignored): they contain court text.

## Agreement

Events are matched across coders by the overlap of the passages they cite, never by action code, so agreement is not inflated by matching like with like. Reported per case: event precision, recall and F1; action κ on matched events; affordance agreement per class; harm agreement; order agreement on matched pairs. The agreed core keeps what both coders coded.

## Adjudication

```bash
export CASELINKER_PACER_TEXT=<page text store> CASELINKER_PACER_SOURCE=<folder of the PDFs>
python -m state_machines.coding.adjudication dossier <release> <case> [...]
python -m state_machines.coding.adjudication_packet <release> [case ...]      # open local/adjudication/<release>/packet.html
python -m state_machines.coding.adjudication apply <release> <case> local/adjudication/<release>/<case>.decisions.json
python -m state_machines.graphs.release build <release>
```

Each item is one question with a fixed set of answers that `apply` carries out:

| Kind | What it is | Answers |
|---|---|---|
| `only_a`, `only_b` | an event one coder coded and the other did not | include / exclude (`only_b`: exclude / edit) |
| `action_mismatch` | matched events with different action codes | coder A's code / coder B's code / exclude / edit |
| `status_mismatch`, `affordance_mismatch` | different status or level-C affordances | keep (the agreed, weaker or shared) / coder A / coder B / edit |
| `actor_mismatch`, `harm_mismatch`, `time_mismatch` | different actor, harms or dates | keep / the other coder's where it can be applied / edit |
| `order_only_a`, `order_only_b`, `single_coder_relation` | a relation only one coder asserted | include / exclude |
| `platform_recode`, `single_step` | a platform or affordance coding, a one-step trajectory | keep / edit |
| `possible_same_act` | same action, overlapping dates, nothing linking them | same act (adds `SAME_ACT`, INFERRED; both events kept) / distinct |
| `unresolved_role` | a participant whose role the source leaves open | a target role / a co-actor mode / not involved / edit |

`edit` means the reviewer changes the frozen agreed core (`local/adjudication/<release>/agreed/<case>.json`) by hand; `apply` always rebuilds from that file and the decisions, so it can be rerun. `defer` blocks the release. `apply` marks every event and relation `adjudicated` with the reviewer's name and refuses a result that does not validate. Coder A's ids, participants and passages are the agreed core's own; coder B's passages are imported under a `b.` prefix, and anything needing coder B's participants is an `edit`.
