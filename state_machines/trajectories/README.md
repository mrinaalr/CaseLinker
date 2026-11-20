# Trajectories

Views derived from a coded bundle: the order the record establishes, the trajectories read from it, the affordances at each step, and the AfH sets. Every view is computed at an evidence threshold $\theta$, DIRECT or DIRECT plus INFERRED, and carries its derivation metadata (rule version, threshold, input hash).

**Contents:**
- [Documented order](#documented-order)
- [Chains](#chains)
- [Affordance levels](#affordance-levels)
- [AfH sets](#afh-sets)
- [Outputs](#outputs)

## Documented order

$\prec_{\theta}$ is the transitive closure of:
- BEFORE and MEETS relations whose status is admitted at $\theta$ (relative chronology stated in a passage is direct evidence even without dates);
- the order cited dates imply: $a \prec b$ when every admitted dated assertion of $a$ ends before every admitted dated assertion of $b$ starts.

Dates from an enclosing window are INFERRED, so they order events only at the INFERRED threshold. An event with contradictory dates gives no date order. `SAME_ACT` never creates order. Pairs of events that $\prec_{\theta}$ leaves incomparable are reported as `unordered_pairs`.

## Chains

$$
L=((a_{1},O_{1}),\ldots,(a_{n},O_{n}))
$$

A trajectory is a maximal chain of offender events of one track under $\prec_{\theta}$. $a_{i}$ is the coded action and $O_{i}$ the instrumental affordances the record ties to it. Consecutive steps mean "documented as later", not "came next"; a step is marked immediate only when MEETS joins the pair. Response, law-enforcement and court events never become steps; an INTERRUPTS relation attaches them to the step they interrupt.

A chain is a view of the event graph: it leaves out events that are unordered with it, and one event can sit in several chains. Chains are not counted as cases or histories. A track with more than 256 chains is truncated and flagged.

## Affordance levels

Three levels, kept apart. Only level C enters $O_{i}$.

| Level | Claim | Evidence | Where |
|---|---|---|---|
| **A** available | The platform offered the capability when the event happened | The shared capability registry: dated, sourced entries per platform | `available_affordances` |
| **B** action-relevant | The act went through (or moved to) that platform, and the capability bears on that kind of act | A platform interaction in the record, plus A, plus the relevance table R(action) | `action_relevant_affordances` |
| **C** instrumental | The record ties the capability to the act | A coded affordance with a passage naming the feature or mechanism | `affordances` ($O_{i}$) |

Availability (A) at an event is **supported** when the registry entry is native and documented and the event lies inside its period; **uncertain** for an approximate or unknown date, a partial feature, an undated event or a boundary overlap; **unsupported** otherwise (left out). An approximate date never becomes supported. Only interactions with mode `through` or `to` reach level B; acting on a platform (deleting an account) and unnamed platforms do not. A coded configuration (a feature switched on) is carried beside the registry's default.

The registry is the one the AfH Q1 work maintains (`research/afh_q1/config/capability_sources/*.yaml`, or `CASELINKER_CAPABILITY_SOURCES`). Every level here is **event-level** (`level_unit: event`). Q1's levels are **case-level**: a press release's sentence about a platform. Case-level associations are never promoted to event-level claims.

## The analysis frame

$O_{i}$ is level C only. On `pacer-v1` the stated-means rule ties no feature to an agreed act, so it is empty. That is the rule's output, not a finding that no record states one: the rule misses `doj_ceos_2026_001` `e149`, where an admitted statement gives VPN use as the means (`o0093`; the cue is too far from the term). That column stays empty. A platform name, and a capability the registry says the platform offered, are not written into it.

Each derived step stores that split in `claims`: `stated_platform_means`, `candidate_capabilities` (level B), `available_on_platform` (level A, excluding B), `documented_feature_use` ($O_{i}$), and `how_used` (always null). `candidate_affordances` on the same step is a coder annotation. It is not a registry candidate and it is not copied into `claims`. The derivation record names the act policy, `intersection-1.0`: an act is in the bundle only when both coders cited the same sentence, action, and actor. The acts in `pacer-v1` were not recoded. `capability_registry_loaded` is false on those files, so their `candidate_capabilities` are empty. That is the registry being absent, not a finding that the platforms offered nothing.

The thing you analyze is the frame beside that column. [`digest.py`](digest.py) reads the committed dataset and the registry and writes three files. It does not modify the dataset and it does not emit graphs.

```bash
python -m state_machines.trajectories.digest pacer-v1 --registry <capability_sources> --out <dir>
```

| File | What it is |
|---|---|
| `digest.json` | Every chain, with the date when the act has one, the platform the sentence names, registry candidates, capabilities the platform offered that are not relevant to this act, documented feature use, and any researcher notes |
| `digest.md` | The same, as a page |
| `index.html` | A coding bench. No filing text. You record Used, Not used, or Unclear for a capability the frame already shows |

[`claims.py`](claims.py) is the split. [`use_notes.py`](use_notes.py) accepts a note only from a person (`basis` is `researcher_inference`), only for a capability already on that step or a feature phrase stated in that case, and never copies the note into $O_{i}$. The codebook's rules for the note are in [section J](../evidence/CODEBOOK.md).

Run against the Q1 registry, the frame for these 30 is 202 steps, 8 of them carrying a platform interaction both coders coded (the observation layer ties a 9th, `ncmec_2022_575` `e077`, from the sentence; the split reads coder annotations only), each of those 8 carrying at least one registry candidate, 87 stated feature phrases, and 0 documented feature uses. Two candidates are `supported`: unmonitored communication on `doj_ceos_2026_001` `e050` and `e056`, both dated inside a documented registry period. The other candidates are `uncertain` because the act is undated or the registry date is approximate. Ephemerality is a candidate on a communications act through Snapchat, and it is not a candidate on contact or distribution. It is availability, not use.

## AfH sets

$$
\mathrm{Aff}(L)=\bigcup_{i=1}^{n} O_{i},\qquad
\psi_{\mathcal{C}}(o)=\{h\in\mathcal{H}_{0}:\exists c\in\mathcal{C},\ o\in\mathrm{Aff}(c)\wedge h\in H(c)\}
$$

In `pacer-v1` the stated-means rule ties no feature to an agreed act (one known miss: `doj_ceos_2026_001`, act `e149`, observation `o0093`), so $O_{i}$ and $\mathrm{Aff}(c)$ are empty for every case, $\psi_{\mathcal{C}}$ is empty, and the coverage identity holds vacuously; `release_analysis` reports `cases_with_an_affordance` so that this is visible. $\mathrm{Aff}(c)$ is the union over a case's chains. $H(c)$ holds the case's minor-directed harm categories $h_{1}$–$h_{6}$. $\psi_{\mathcal{C}}$ records co-occurrence within a case. [`afh.py`](afh.py) also checks the coverage identity $\bigcup_{o}\psi_{\mathcal{C}}(o)=\bigcup_{c:\mathrm{Aff}(c)\neq\varnothing}H(c)$.

## Outputs

| Function | Returns |
|---|---|
| `derive.derive(bundle, threshold)` | Per track: chains with steps (action, $O_{i}$, levels A and B, outcome, interruptions), unordered pairs, possible-identity pairs, time conflicts, excluded events |
| `derive.derived_json(...)` | The same, as deterministic JSON |
| `afh.release_analysis(threshold, case_id)` | $\mathrm{Aff}(c)$, $H(c)$, $\psi$, coverage identity and per-track chain counts for a dataset (`/api/lifecycle/analysis`) |
| `payload.build_payload()` | The `/lifecycle` payload: events with roles, standing, dates, affordances, harms and page provenance; relations; per-track chains at both thresholds (`/api/lifecycle/cases`) |
| `digest.release_digest(root, registry)` | The analysis frame: chains, stated platforms, registry candidates, documented feature use, researcher notes |
| `claims.claims(step)` | The same step split into stated platform, candidates, and documented use. Candidates are not copied into $O_{i}$ |
| `use_notes.validate(notes, offered)` | Researcher use notes. A model basis is refused. A note cannot name a capability the frame does not contain |
