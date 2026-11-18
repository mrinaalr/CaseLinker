# State machines

Federal court records, coded as evidence and represented through documented trajectories. Each case is reconstructed from source-supported actions, participants, temporal relationships, platform interactions, and harms, with provenance and uncertainty preserved.

The underlying event graph serves as the canonical representation from which trajectories, CASE/UCO/CAC knowledge graphs, and the /lifecycle visualization are derived. Separately, the theory layer implements the affordance-aware state-space framework of [Affordances for Harm](https://doi.org/10.5281/zenodo.21347781) (AfH), allowing documented trajectories to be evaluated against formally specified models.

**Contents:**
- [Layers](#layers)
- [Three levels of evidence](#three-levels-of-evidence)
- [The documented event graph](#the-documented-event-graph)
- [From record to release](#from-record-to-release)
- [What a release establishes](#what-a-release-establishes)
- [Use it](#use-it)
- [Code map](#code-map)

## Layers

```mermaid
flowchart LR
  pdf["court records<br/>(local PDFs)"] --> coding["coding/<br/>two local model coders,<br/>agreement, resolution"]
  bench["benchmark/<br/>synthetic gold"] -. "accuracy" .-> coding
  coding --> evidence["evidence/<br/>coded bundles<br/>(canonical)"]
  pdf --> obs["observations/<br/>platforms and features<br/>the record names"]
  obs --> graphs
  evidence --> traj["trajectories/<br/>order, chains,<br/>affordance levels, AfH sets"]
  evidence --> graphs["graphs/<br/>CASE/UCO/CAC, SHACL,<br/>releases"]
  traj --> graphs
  graphs --> ox[("Oxigraph<br/>urn:caselinker:pacer:*")]
  traj --> ui["/lifecycle, API, MCP"]
  theory["theory/<br/>transition systems"] -. "compatibility checks" .-> traj
```

| Layer | What it holds | README |
|---|---|---|
| [`evidence/`](evidence/) | The canonical record: coded events, participants and their event roles, dated assertions, relations, provenance, validation rules | [evidence](evidence/README.md) |
| [`trajectories/`](trajectories/) | Views derived from it: the documented partial order, maximal chains, affordance levels, the AfH sets, the `/lifecycle` payload | [trajectories](trajectories/README.md) |
| [`graphs/`](graphs/) | CASE/UCO/CAC emission with the CASE-UCO SDK, SHACL against the full CAC shape set, releases, Oxigraph loading | [graphs](graphs/README.md) |
| [`observations/`](observations/) | What the record names, read by rule from the pages: listed platforms and codebook feature phrases, each cited to its sentence; and the relationships an act's own sentence supports | [observations](observations/README.md) |
| [`coding/`](coding/) | The workflow that produces bundles: page text, two pinned local model coders, agreement, machine resolution, optional adjudication | [coding](coding/README.md) |
| [`benchmark/`](benchmark/) | Synthetic gold cases (dev, held-out and a blind confirmation split) and the scorer that measures the coders' accuracy on known truth | [benchmark](benchmark/README.md) |
| [`theory/`](theory/) | Finite transition systems for feasible pathways (AfH Appendix X) | [theory](theory/README.md) |

## Three levels of evidence

A record supports three different kinds of claim, and each has its own gate. They are kept in separate graphs and never promoted by proximity.

| Level | Claim | Gate | Graph |
|---|---|---|---|
| 1. Observation | The record names this platform, or states this feature phrase, in this sentence | The term is on a fixed list and on the page | `urn:caselinker:pacer:<case>:observations` |
| 2. Act | The record states someone did this | Two model coders agree on the sentence, the action and the actor | `…:evidence` |
| 3. Supported relationship | The record states the act was done by means of the platform or feature | The observation lies in the act's cited sentence, and that sentence states the means | `…:observations`, pointing at the act |

- **A mention is not use.** A platform named in a filing says nothing about what it was used for.
- **A platform name is not an affordance.** Only a stated feature can count toward one, and only a stated means ties it to an act.
- **A sparse graph is a correct graph.** A case may have observations and no relationship, or acts and no platform.
- **The record is not the model.** A stated feature documents that the capability appears in the case. Whether it enabled the offence is a question for the [theory](theory/README.md) layer, not a fact in the graph.

Release `pacer-v1` holds level 2 and the level-3 relationships its agreed acts carried. Release `pacer-v2` holds the same bundles, byte for byte, and adds level 1, the level-3 relationships derived from it, and a case-level [research table](observations/README.md#research-table) that keeps the three apart. The cases are a selected collection of prosecutions, not a sample of offending.

## The documented event graph

$$
D=(\Pi,\ E,\ R,\ P,\ U)
$$

| | | |
|---|---|---|
| $\Pi$ | participants | role-neutral (P1, P2, …): persons, undercover personas, organizations, collectives; legal status recorded separately, with sources |
| $E$ | events | one per source observation: action, actor and targets with their roles in this event, outcome, dated assertions, affordances, harms, platform interactions |
| $R$ | relations | BEFORE, MEETS, interval relations, INTERRUPTS, RESPONDS_TO, …, and SAME_ACT for possible identity |
| $P$ | provenance | document hash, page, character offsets, quote hash, the passage's legal standing (allegation, admission, finding, …), verification |
| $U$ | uncertainty | an assertion status on every claim (DIRECT, INFERRED, UNSUPPORTED, CONTRADICTED); conflicting dates kept side by side |

The bundle is the canonical artifact. Everything else is a view of it at an evidence threshold $\theta$ (DIRECT, or DIRECT plus INFERRED):

- **Order.** $\prec_{\theta}$ is the transitive closure of admitted BEFORE and MEETS relations and of the order cited dates imply. Pairs it leaves incomparable are reported, not forced.
- **Trajectories.** $L=((a_{1},O_{1}),\ldots,(a_{n},O_{n}))$ is a maximal chain of offender events under $\prec_{\theta}$. $O_{i}$ holds the affordances the record ties to the act. One event can sit in several chains.
- **AfH sets.** $\mathrm{Aff}(L)$, $H(c)$ and $\psi_{\mathcal{C}}(o)$ are computed over the chains and the case's minor-directed harms.

## From record to release

1. **Collect.** [`collector/pacer/`](../collector/pacer/) fetches public dockets into `ontology/PACER/` (local, never committed).
2. **Code.** Two local models (pinned by digest) read the page text and each write a bundle; [`coding/`](coding/README.md) measures their agreement. Court text never leaves the machine.
3. **Resolve.** A fixed rule publishes what both coded (`machine`), or a named reviewer decides every disagreement (`adjudicated`).
4. **Release.** [`graphs/release.py`](graphs/release.py) validates each bundle, derives its views, emits its graphs, runs SHACL, and writes a manifest with hashes and the release's `review_mode`. A bundle with any validation error is refused in every mode.
5. **Load.** `rebuild_oxigraph.py --pacer-release <id> --verify` loads the release with the rest of the corpus and checks the store against the manifest.

## What a release establishes

Three layers of checking, each answering a different question. Passing one says nothing about the next.

| Layer | Question | Checked by |
|---|---|---|
| **Structural** | Is the bundle well formed, and are its views and graphs derived from it deterministically? | JSON Schema, rules T01–T19, CASE-UCO SDK emission, SHACL, `tests/pacer` |
| **Evidence fidelity** | Does each coded claim say what its cited passage says, with the right standing? | Quote and page hashes (T04), standing per passage (T06), two independent coders and their agreement |
| **Resolution** | How were disagreements, open roles and possible retellings settled? | `machine`: a fixed rule publishes only what both coders coded, links possible retellings, keeps open roles open. `adjudicated`: a named reviewer decided each item |

| `review_mode` | Published items | Served on `/lifecycle` and loaded into Oxigraph |
|---|---|---|
| `adjudicated` | decided by a named reviewer | yes |
| `machine` | agreed by two independent coders, resolved by rule | yes, labelled "Machine-coded" |
| `preview` | anything that validates | no (local stores only) |

A machine-coded release reports reliability (agreement between the coders) and, separately, accuracy on the [synthetic benchmark](benchmark/README.md); neither is accuracy on the real cases. Level-C affordances are documented instrumental support, not causal effects; $\psi$ is co-occurrence within a case.

## Use it

```bash
# validate a bundle against its page text
python -c "import json,sys; from state_machines.evidence.validate import validate; \
  [print(f) for f in validate(json.load(open(sys.argv[1])), require_verified=True)]" bundle.json

# build a release and its N-Quads
python -m state_machines.graphs.release build pacer-v1
python -m state_machines.graphs.release nquads pacer-v1

# convert a schema 1.x bundle, and list what needs a person
python -m state_machines.evidence.migrate old.json new.json

# tests
DATABASE_URL='' python -m pytest tests/pacer
```

| Surface | Access | Returns |
|---|---|---|
| [`/lifecycle`](https://caselinker.up.railway.app/lifecycle) | public | documented and theory views of the current adjudicated release |
| `GET /api/lifecycle/cases` | trusted key or localhost | the page payload: events, roles, dates, standing, sources (no quotes, no names) |
| `GET /api/lifecycle/analysis` | trusted key or localhost | chains, unordered pairs, $\mathrm{Aff}(c)$, $H(c)$, $\psi$, coverage identity |
| `GET /api/ontology/pacer` | public | the release manifest: cases, graph IRIs, SHACL status |
| MCP `get_lifecycle_cases`, `get_trajectory_analysis` | trusted key | the two API routes above |

## Code map

| Path | Purpose |
|---|---|
| [`evidence/vocab.py`](evidence/vocab.py) | Every code list: actions, roles, statuses, time bases, relation types, affordance classes, harms |
| [`evidence/schema.py`](evidence/schema.py) | Bundle JSON Schema 2.0, generated from the vocabulary |
| [`evidence/validate.py`](evidence/validate.py) | Rules T01–T19 and the release gate |
| [`evidence/evidence.py`](evidence/evidence.py) | Page text, passages, quote hashes, the local quote store |
| [`evidence/migrate.py`](evidence/migrate.py) | Schema 1.x to 2.0 |
| [`evidence/CODEBOOK.md`](evidence/CODEBOOK.md), [`evidence/CODER_GUIDE.md`](evidence/CODER_GUIDE.md) | What each code means; how to code a case |
| [`trajectories/derive.py`](trajectories/derive.py) | Partial order, chains, interruptions, derivation metadata |
| [`trajectories/affordances.py`](trajectories/affordances.py) | Affordance levels A and B from the shared capability registry |
| [`trajectories/afh.py`](trajectories/afh.py) | $\mathrm{Aff}$, $H(c)$, $\psi$, coverage identity, release analysis |
| [`trajectories/payload.py`](trajectories/payload.py) | The `/lifecycle` payload |
| [`graphs/emit.py`](graphs/emit.py), [`graphs/shacl.py`](graphs/shacl.py), [`graphs/release.py`](graphs/release.py) | Emission, SHACL, releases |
| [`coding/workflow.py`](coding/workflow.py), [`coding/adjudication.py`](coding/adjudication.py) | Coding and adjudication workflow |
| [`theory/transition_systems.py`](theory/transition_systems.py) | AfH Appendix X |
| [`../tests/pacer/`](../tests/pacer/) | Tests for all of the above |
