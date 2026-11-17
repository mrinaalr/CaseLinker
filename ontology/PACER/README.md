# PACER source documents (local only)

This folder is where the PACER court records live on a researcher's machine: the PDFs fetched by [`collector/pacer/`](../../collector/pacer/) (`cases2records.py`, `corpus2pacer.py`). They are **not** in git. Only this README and the cost log, `BULK_FOLDER/pacer_cost.csv`, are tracked.

| What | Where |
|---|---|
| Source PDFs and their page text | here, and in `local/pacer_text/<case_id>/` (both gitignored) |
| Coded evidence, derived trajectories, CASE/UCO/CAC graphs | [`state_machines/`](../../state_machines/README.md); releases in `state_machines/data/<release_id>/` |
| Graphs in the SPARQL store | named graphs `urn:caselinker:pacer:<case_id>:evidence` and `…:trajectories` |

Keep a checksummed backup of the PDFs somewhere access-controlled: they are the evidence every coded event cites.
