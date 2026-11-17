# Theory: affordance-aware state spaces

**Status: theoretical.** Every model here is specified by hand with declared assumptions. None is estimated from the PACER records, and no number here describes offender behaviour.

**Contents:**
- [What is implemented](#what-is-implemented)
- [The construction](#the-construction)
- [How theory meets evidence](#how-theory-meets-evidence)
- [Not implemented, on purpose](#not-implemented-on-purpose)
- [Where this sits](#where-this-sits)

## What is implemented

[`transition_systems.py`](transition_systems.py) implements AfH 2.0 Appendix X as written.

| AfH | Code | Tested by |
|---|---|---|
| $M_P=(S,\mathcal A,\mathcal O(P),T_P,s_0)$, $T_P\subseteq S\times\mathcal A\times 2^{\mathcal O(P)}\times S$ | `TransitionSystem` | unknown affordance rejected |
| finite runs, $\varepsilon$, $\mathcal L(P)=\{\varepsilon(r)\}$ incl. prefixes and failed attempts | `runs`, `epsilon`, `trajectories` | prefixes and the refused branch present |
| $\pi(L)$, $\operatorname{Aff}(L)$ | `pi`, `aff` | — |
| $P\oplus o$ with monotonicity and locality | `add`, `monotone_and_local` | locality enforced; its violation breaks attribution |
| $\Delta_{\mathrm{path}}(o;P)$, $\Delta_{\mathrm{supp}}(o;P)$ | `delta_path`, `delta_supp` | the worked example |
| Proposition: attribution of new pathways | `attribution_holds` | 60 generated systems that satisfy both assumptions, plus a counterexample without locality |
| The worked comparison (contact, request; add $e$, add $g$) | `appendix_x_example` | $\Delta_{\mathrm{path}}(e)=\varnothing$, $L_e\in\Delta_{\mathrm{supp}}(e)$, $(\text{synthesize})\in\Delta_{\mathrm{path}}(g)$ |

Run the tests with `DATABASE_URL='' python -m pytest tests/pacer/test_theory.py`.

## The construction

$$
M_P=(S,\ \mathcal A,\ \mathcal O(P),\ T_P,\ s_0),\qquad \mathcal L(P)=\{\varepsilon(r): r \text{ a finite run of } M_P \text{ from } s_0\}
$$

$$
\Delta_{\mathrm{path}}(o;P)=\pi(\mathcal L(P\oplus o))\setminus\pi(\mathcal L(P)),\qquad
\Delta_{\mathrm{supp}}(o;P)=\{L\in\mathcal L(P\oplus o): \pi(L)\in\pi(\mathcal L(P)),\ o\in\operatorname{Aff}(L)\}
$$

- **Feasibility, not choice.** A run is a possibility in the specified system. It is not an offender's choice, a frequency or a cause.
- **Comparisons are local.** $P\oplus o$ assumes monotonicity and locality. Both are assumptions of the comparison, not laws of platform redesign.
- **No probabilities.** No probabilities are assigned; Appendix X says so.

## How theory meets evidence

Evidence can **test** a model. It never **fits** one.

`admits_prefix(model, actions, action_map)` asks whether a documented action sequence is the action sequence of some run prefix of a specified model. A documented trajectory that no run admits is a counterexample to that model.

What the records cannot do is estimate $T_P$, probabilities, rewards or policies. The reasons:
- court records are partially observed;
- they come from detected and prosecuted cases;
- they are partially ordered;
- they carry legal standing that varies from passage to passage.

A test enforces that no theory module imports the evidence or trajectory packages.

## Not implemented, on purpose

| Idea | Where it appears | Why it is not here |
|---|---|---|
| Transition probabilities $T:S\times A\to\Delta(S)$ | the June 2026 phase machines (removed; git history) | The records do not identify them. Adding one requires its own assumptions and an evidence model. |
| Goal rewards $R_G$, values, Bellman equations | the June 2026 phase machines | Same reason. Nothing in AfH 2.0 §7.2 defines them. |
| Comparative exploitation utility $u(a,g)$ | AfH Appendix Z | Comparative and hand-ranked in the paper, not a computed quantity. §7.2 no longer defines it, so it would need a definition first. |
| Optimal or most probable paths | the June machines | They describe no recorded behaviour, and the records cannot support them. |
| Interventions as removing affordances ($P\ominus o$) | discussed in AfH §6 | Not defined in Appendix X. Defining it needs an assumption symmetric to monotonicity and locality. |

Any of these can be added later as a separate model, with:
- a written assumption list;
- `validation_status = "theoretical"`;
- tests on fictional systems;
- no claim about PACER data.

## Where this sits

```
state_machines/
├── evidence/       canonical: coded court-record events, participants, relations, provenance
├── trajectories/   derived views: partial order, chains, affordance levels, AfH sets
├── graphs/         CASE/UCO/CAC emission and SHACL
├── coding/         coding, agreement and adjudication workflow
└── theory/         this folder: specified models, tested on fictional systems
```

See [`../README.md`](../README.md) for the full architecture.
