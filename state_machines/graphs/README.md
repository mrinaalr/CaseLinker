# Graphs

CASE/UCO/CAC graphs emitted from coded bundles with the CASE-UCO SDK, checked with SHACL (CaseLinker's own shapes pass; the upstream CAC `ActionSemanticsShape` defect is reported apart, [CAC-Ontology#74](https://github.com/Project-VIC-International/CAC-Ontology/issues/74)), released with a manifest, and loaded into Oxigraph.

**Contents:**
- [Emission](#emission)
- [SHACL](#shacl)
- [Datasets](#datasets)
- [Oxigraph](#oxigraph)

## Emission

[`emit.py`](emit.py) builds two graphs per case (three with observations) with `case_uco.CASEGraph` (SDK pinned in [`ontology/SDK_VERSION`](../../ontology/SDK_VERSION)). Canonical terms carry the structure; the `clt:` extension ([`ontology/extensions/caselinker-trajectory/0.3.0/`](../../ontology/extensions/caselinker-trajectory/0.3.0/)) carries codes, statuses and two classes no canonical term covers.

| Record | Graph |
|---|---|
| case | `case-investigation:Investigation`, objects = documents |
| document | `uco-observable:ObservableObject` with file facet and SHA-256 hash |
| participant | `uco-identity:Person`, `uco-identity:Identity` (undercover persona), `uco-identity:Organization`, or `clt:Collective` |
| legal status | `Has_Legal_Status` relationship to the investigation, cited |
| event | `uco-action:Action` with performer, participants, objects |
| event role | `Has_Event_Role` relationship from participant to action |
| dated assertion | `clt:TimeAssertion`, one per assertion, cited |
| relation | `uco-core:Relationship` (`Occurs_Before`, `Immediately_Before`, `Interrupts`, `Possibly_Same_Act`, …) |
| affordance (level C) | an individual of the CAC affordance class, `Supports_Action` the action |
| platform | `uco-action:instrument`, plus `Carried_Out_Through` / `Moved_From` / `Moved_To` / `Acted_On` |
| harm | `Documents_Harm` relationship to the victim, with victim kind and H0 category |
| evidence | `oa:Annotation` targeting a page and character range of the document; quote hash only |

A dataset built with `--observations` adds a third graph per case, `urn:caselinker:pacer:<case>:observations`: what the record names, as W3C Web Annotations, with no new vocabulary ([observations](../observations/README.md#graph)).

| Record | Graph |
|---|---|
| platform observation | `oa:Annotation`, `oa:motivatedBy oa:identifying`, body = the platform |
| feature observation | `oa:Annotation`, `oa:motivatedBy oa:classifying`, body = the CAC affordance class, `clt:featureTerm` = the phrase; no individual of the class |
| supported relationship | `Carried_Out_Through`, `Moved_To` or `Supports_Action` under the evidence graph's IRIs, with an evidence annotation on the observation's own target |

Why each `clt:` term exists, and which could move to an existing term, is recorded in the [extension's README](../../ontology/extensions/caselinker-trajectory/README.md).

The trajectory graph is the derived view: one `uco-action:ActionLifecycle` per chain, with `Trajectory_Step` relationships carrying the step index and $O_{i}$. `ActionLifecycle` and `uco-action:phase` are UCO's names for a sequence of actions and its link to them; no phase model is asserted, and a chain exists only where the record documents the order. Graphs hold no names and no quote text.

## SHACL

[`shacl.py`](shacl.py) validates against UCO/CASE 1.5.0, gUFO, W3C OA, all 97 CAC 3.1.0 files and the extension shapes. The report separates three outcomes:

| Conformance | Meaning |
|---|---|
| `full` | Every applicable constraint ran and passed |
| `partial` | Everything that ran passed, but applicable upstream constraints could not run as published (listed) |
| `fails` | A constraint that ran was violated |

Violations from upstream shapes known to reject valid UCO data ([`shacl_upstream_defects.json`](shacl_upstream_defects.json)) are counted apart from violations of our own output, and still mean `fails`. For `pacer-v1` the `fails` come from CAC's `ActionSemanticsShape`, which targets every `uco-action:Action`, including `ActionLifecycle`; it is filed upstream as Project-VIC-International/CAC-Ontology#74 with a patch in #75, and the graphs validate against that shape once the patch is in the vendored CAC. Nothing is added to a graph (a performer, an object, a start time) to make the check pass. A dataset check passes only with no violations and every applicable skipped constraint waived in [`shacl_waivers.json`](shacl_waivers.json).

## Datasets

```bash
python -m state_machines.graphs.release build <release_id>
python -m state_machines.graphs.release nquads <release_id>
```

A dataset folder `state_machines/data/<release_id>/` holds `derived/`, `graphs/`, `manifest.json`, `lifecycle.json` and the run report, and, when built with observations, `observations/`, `research_table.json`/`.csv` and (once reviewed) `validation.json` (committed: codes, dates, page references and hashes, no text), and `cases/` (the bundles, local: they hold coder text). [`release.py`](release.py) refuses a bundle with a validation error in every mode. `--mode adjudicated` (default) also refuses an unadjudicated item or an undecided role; `--mode machine` requires every item agreed by both coders and keeps open roles open; `--mode preview` accepts anything that validates. The manifest records `review_mode`, and per case the passages verified against OCR text only.

The manifest records the schema, codebook, derivation rule, extension and SDK versions, and per case the bundle hash, the source-document hashes, the graph IRIs and hashes, the SHACL result and the review counts. Graph IRIs are stable across datasets:

```
urn:caselinker:pacer:<case_id>:evidence        actions, participants, roles, relations, provenance
urn:caselinker:pacer:<case_id>:trajectories    derived order and affordance views; every lifecycle and step names its derivation rule and threshold
urn:caselinker:pacer:<case_id>:observations    platforms, placeholder-labelled services, generic service descriptions and feature phrases the record names, each cited; relationships a sentence supports (releases built with observations)
```

| Dataset | Holds |
|---|---|
| `pacer-v1` | 30 cases, 284 agreed acts: evidence, trajectory and observation graphs per case, `observations/`, the case-level research table and the affordance evidence matrix |

An affordance individual in these graphs is level C: the sentence states the feature as the means. On `pacer-v1` there are none. Registry candidates and researcher use notes are not emitted here. They are the [analysis frame](../trajectories/README.md#the-analysis-frame), computed when you want to read the 30, and a later rebuild of the dataset reproduces the graphs from the same bundles.

## Oxigraph

The full corpus is rebuilt into an empty store; PACER graphs come from a dataset. `--pacer-graphs all` (default) loads evidence, trajectory and observation graphs, `--pacer-graphs evidence` the evidence graphs only. Adjudicated and machine-coded datasets load; a preview is refused unless `--allow-preview`, which accepts only a local store.

```bash
# build the corpus and PACER N-Quads without touching a store
python3 scripts/oxigraph/rebuild_oxigraph.py --output /tmp/caselinker.nq.gz --no-load --pacer-release pacer-v1

# load into an empty staging store and verify against the manifest
OXIGRAPH_URL=http://localhost:7878 python3 scripts/oxigraph/rebuild_oxigraph.py \
  --output /tmp/caselinker.nq.gz --skip-build --pacer-release pacer-v1 --verify --min-case-graphs 10000
```

`--verify` checks over SPARQL that:
- exactly the selected graph kinds of the dataset are present, each non-empty;
- each evidence graph has one investigation and no derived lifecycles, and no trajectory graph holds an investigation;
- every trajectory states its derivation rule and threshold;
- no `urn:pacer:kg:*` graph remains;
- the store holds at least `--min-case-graphs` press-release case graphs.

**Staging and rollback.**
1. Build the N-Quads and keep the file.
2. Load it into a fresh staging volume and run `--verify` until it passes.
3. Point the service at the verified volume.
4. Keep the previous volume and its N-Quads until the new one has served queries. Rolling back is pointing the service at the previous volume, or bulk-loading the previous N-Quads into an empty one.

The bulk loader requires an empty store; see [`ontology/docs/SPARQL.md`](../../ontology/docs/SPARQL.md).
