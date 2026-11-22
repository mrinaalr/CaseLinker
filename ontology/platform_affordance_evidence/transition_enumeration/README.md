# Transition enumeration

An enumeration of affordance-transition runs over the platform affordance evidence model: thirteen transitions, the co-present variant that keeps the second contact transition, and the alternative that puts GS in the baseline. These scripts are not part of the extractor. Nothing here reads a case, a bundle, or a database.

`enumerate_transitions.py` is the thirteen-transition model with the co-present channel (t2) included, and the checks on its runs, new action sequences, contact-free reachability, must-pass states, and minimum blocking sets. `enumerate_transition_variants.py` imports that file and recomputes the same sets for the primary model (t2 left out), the co-present model (t2 present), and the alternative that puts GS in the baseline. `independent_checks/` is a second derivation of the same sets. It does not import the canonical scripts.

Run them from this directory:

```bash
python3 enumerate_transitions.py
python3 enumerate_transition_variants.py
python3 independent_checks/enum.py
python3 independent_checks/recompute_transition_sets.py
```

`enumerate_transitions.py` exits 0 when its asserts pass. `enumerate_transition_variants.py` prints the `enumerate_transitions.py` output first, because the import runs that file, and then the three variants. Printed sets are sorted, so a rerun matches `enumerate_transitions.out` and `enumerate_transition_variants.out`.
