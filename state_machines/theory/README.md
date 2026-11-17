# Theory: affordance-aware state spaces

Finite transition systems for examining how technological affordances shape feasible actions and trajectories. Includes formal constructions, pathway comparisons, and compatibility checks against documented trajectories.

**Contents:**
- [The construction](#the-construction)
- [Code map](#code-map)
- [Attribution of new pathways](#attribution-of-new-pathways)
- [Compatibility with documented trajectories](#compatibility-with-documented-trajectories)
- [Scope](#scope)

## The construction

AfH 2.0, Appendix X. A model fixes states, actions and the affordances available in an environment $P$:

$$
M_P = (S,\ \mathcal A,\ \mathcal O(P),\ T_P,\ s_0), \qquad T_P \subseteq S \times \mathcal A \times 2^{\mathcal O(P)} \times S
$$

A tuple $(s, a, O, s')$ says action $a$, supported by affordances $O$, can move the process from $s$ to $s'$. Transitions carry no probabilities. A finite run starts at $s_0$; $\varepsilon$ erases its states and keeps the ordered (action, affordance-set) pairs:

$$
\mathcal L(P) = \{\varepsilon(r) : r \text{ a finite run of } M_P \text{ from } s_0\}
$$

$\mathcal L(P)$ includes prefixes and failed attempts (a refused request is a transition to a refused state). Adding one affordance $o$ gives $P \oplus o$, compared with $P$ through two sets:

$$
\Delta_{\mathrm{path}}(o;P) = \pi(\mathcal L(P\oplus o)) \setminus \pi(\mathcal L(P))
$$

$$
\Delta_{\mathrm{supp}}(o;P) = \{L \in \mathcal L(P\oplus o) : \pi(L) \in \pi(\mathcal L(P)),\ o \in \mathrm{Aff}(L)\}
$$

$\Delta_{\mathrm{path}}$ holds newly feasible action sequences; $\Delta_{\mathrm{supp}}$ holds new ways of carrying out sequences that were already feasible. Neither says an offender would choose a pathway or that harm would change.

## Code map

All of it is in [`transition_systems.py`](transition_systems.py); tests are in [`tests/pacer/test_theory.py`](../../tests/pacer/test_theory.py).

| Concept | Code | Test |
|---|---|---|
| model $M_P$ | `TransitionSystem` | rejects an affordance outside $\mathcal O(P)$ |
| runs, $\varepsilon$, $\mathcal L(P)$ | `runs`, `epsilon`, `trajectories` | prefixes and the refused branch are present |
| $\pi$, $\mathrm{Aff}$ | `pi`, `aff` | used throughout |
| $P \oplus o$, monotonicity, locality | `add`, `monotone_and_local` | `add` refuses a transition that does not use $o$ |
| $\Delta_{\mathrm{path}}$, $\Delta_{\mathrm{supp}}$ | `delta_path`, `delta_supp` | the worked example below |
| attribution | `attribution_holds` | see [below](#attribution-of-new-pathways) |
| compatibility with evidence | `admits_partial_order`, `admits_prefix` | see [below](#compatibility-with-documented-trajectories) |

**Worked example** (`appendix_x_example`, from the paper). States: an image is accessible but there is no channel; a channel exists; material obtained; refused. Contact is supported by contact discovery, a request by private messaging. The tests reproduce the paper's three results:

| Comparison | Result |
|---|---|
| add ephemerality to the request | $\Delta_{\mathrm{path}} = \varnothing$; the contact, request trajectory with ephemerality is in $\Delta_{\mathrm{supp}}$ |
| add generative synthesis | $(\text{synthesize}) \in \Delta_{\mathrm{path}}$, a sequence with no contact |

Each holds for this toy system only.

## Attribution of new pathways

**Proposition.** If every transition in $T_{P\oplus o} \setminus T_P$ uses $o$ (locality), then every trajectory $L \in \mathcal L(P\oplus o)$ with $\pi(L) \in \Delta_{\mathrm{path}}(o;P)$ has $o \in \mathrm{Aff}(L)$.

**Proof.** Let $L = \varepsilon(r)$ for a run $r$ of $M_{P\oplus o}$ from $s_0$, with $\pi(L) \in \Delta_{\mathrm{path}}(o;P)$. If every transition of $r$ were in $T_P$, $r$ would be a run of $M_P$ and $\pi(L) \in \pi(\mathcal L(P))$, a contradiction. So $r$ uses some $t = (s, a, O, s') \in T_{P\oplus o} \setminus T_P$, and $o \in O$ by locality. $\varepsilon$ keeps $O$ as one step of $L$, so $o \in \mathrm{Aff}(L)$. $\square$

The argument holds for any run that realises $L$. It uses locality only: monotonicity ($T_P \subseteq T_{P\oplus o}$) is not needed for this proposition, and a test introduces $o$ non-monotonically to confirm the code agrees. Monotonicity matters for reading $\Delta_{\mathrm{supp}}$ as "what was feasible stays feasible".

The tests also check the proposition by enumeration on 60 generated systems that satisfy both assumptions, and show it fails on a system that breaks locality. Those checks guard the implementation; the proof is the argument above.

## Compatibility with documented trajectories

This implementation uses documented trajectories to evaluate compatibility with independently specified theoretical models. It does not estimate transition structures, probabilities or rewards from PACER observations.

`admits_partial_order(model, actions, order, action_map)` takes the documented events of one track, their documented partial order, and a mapping from coded actions to model actions. It searches every ordering consistent with the documented order, and returns an admitted ordering or `None`. Events the record leaves unordered are never forced into one arbitrary sequence. (`admits_prefix` checks a single, already-ordered sequence.)

A `None` result says no source-consistent ordering runs in the model under that mapping. It counts against the model's coverage only when:
- the action mapping is right;
- the model claims to admit that kind of conduct.

Otherwise it marks the limits of the model.

No module in this folder imports the evidence or trajectory packages, and a test enforces it.

## Scope

- Models are specified by hand, with their assumptions listed on the model (`assumptions`, `validation_status = "theoretical"`).
- Results hold for the specified system, within the run length searched (`max_len`).
- Architecture and the empirical layers: [`../README.md`](../README.md).
