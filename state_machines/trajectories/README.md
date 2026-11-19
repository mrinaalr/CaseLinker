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
| `afh.release_analysis(threshold, case_id)` | $\mathrm{Aff}(c)$, $H(c)$, $\psi$, coverage identity and per-track chain counts for a release (`/api/lifecycle/analysis`) |
| `payload.build_payload()` | The `/lifecycle` payload: events with roles, standing, dates, affordances, harms and page provenance; relations; per-track chains at both thresholds (`/api/lifecycle/cases`) |
