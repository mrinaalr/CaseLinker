# Graphs

CASE/UCO/CAC graphs emitted from coded bundles with the CASE-UCO SDK, validated with SHACL, released with a manifest, and loaded into Oxigraph.

**Contents:**
- [Emission](#emission)
- [SHACL](#shacl)
- [Releases](#releases)
- [Oxigraph](#oxigraph)

## Emission

[`emit.py`](emit.py) builds two graphs per case with `case_uco.CASEGraph` (SDK pinned in [`ontology/SDK_VERSION`](../../ontology/SDK_VERSION)). Canonical terms carry the structure; the `clt:` extension ([`ontology/extensions/caselinker-trajectory/0.3.0/`](../../ontology/extensions/caselinker-trajectory/0.3.0/)) carries codes, statuses and two classes no canonical term covers.

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

The trajectory graph is the derived view: one `uco-action:ActionLifecycle` per chain, with `Trajectory_Step` relationships carrying the step index and $O_{i}$. Graphs hold no names and no quote text.

## SHACL

[`shacl.py`](shacl.py) validates against UCO/CASE 1.5.0, gUFO, W3C OA, all 97 CAC 3.1.0 files and the extension shapes. The report separates three outcomes:

| Conformance | Meaning |
|---|---|
| `full` | Every applicable constraint ran and passed |
| `partial` | Everything that ran passed, but applicable upstream constraints could not run as published (listed) |
| `fails` | A constraint that ran was violated |

Violations from upstream shapes known to reject valid UCO data ([`shacl_upstream_defects.json`](shacl_upstream_defects.json)) are counted apart from violations of our own output, and still mean `fails`. A release check passes only with no violations and every applicable skipped constraint waived in [`shacl_waivers.json`](shacl_waivers.json).

## Releases

```bash
python -m state_machines.graphs.release build <release_id>
python -m state_machines.graphs.release nquads <release_id>
```

A release folder `state_machines/data/<release_id>/` holds `cases/` (bundles), `derived/`, `graphs/`, `manifest.json` and the N-Quads file. [`release.py`](release.py) refuses a bundle with a validation error, an unadjudicated event or relation, or an undecided role. `--allow-unreviewed` builds a preview, which the manifest records as `adjudicated: false`.

The manifest records the schema, codebook, derivation rule, extension and SDK versions, and per case the bundle hash, the source-document hashes, the graph IRIs and hashes, the SHACL result and the review counts. Graph IRIs are stable across releases:

```
urn:caselinker:pacer:<case_id>:evidence
urn:caselinker:pacer:<case_id>:trajectories
```

## Oxigraph

The full corpus is rebuilt into an empty store; PACER graphs come from a release.

```bash
# build the corpus and PACER N-Quads without touching a store
python3 scripts/oxigraph/rebuild_oxigraph.py --output /tmp/caselinker.nq.gz --no-load --pacer-release pacer-v1

# load into an empty staging store and verify against the manifest
OXIGRAPH_URL=http://localhost:7878 python3 scripts/oxigraph/rebuild_oxigraph.py \
  --output /tmp/caselinker.nq.gz --skip-build --pacer-release pacer-v1 --verify --min-case-graphs 10000
```

`--verify` checks over SPARQL that:
- every PACER graph in the manifest is present and non-empty;
- no PACER graph outside the release is present;
- no `urn:pacer:kg:*` graph remains;
- each evidence graph has exactly one investigation;
- the store holds at least `--min-case-graphs` press-release case graphs.

**Staging and rollback.**
1. Build the N-Quads and keep the file.
2. Load it into a fresh staging volume and run `--verify` until it passes.
3. Point the service at the verified volume.
4. Keep the previous volume and its N-Quads until the new one has served queries. Rolling back is pointing the service at the previous volume, or bulk-loading the previous N-Quads into an empty one.

The bulk loader requires an empty store; see [`ontology/docs/SPARQL.md`](../../ontology/docs/SPARQL.md).
