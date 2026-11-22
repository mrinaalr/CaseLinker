"""Enumerate runs of the platform-affordance transition model.

Thirteen transitions, conjunctive support, including the co-present channel.
Prints the runs, the new action sequences, contact-free reachability, the
must-pass states, and the minimum blocking sets. Exit code 0 means the checks passed.

    python3 enumerate_transitions.py
"""
from itertools import combinations, chain

AN, EP, CD, UM, DI, GS = "AN", "EP", "CD", "UM", "DI", "GS"
O = [AN, EP, CD, UM, DI, GS]
# T*: (source, action, annotation, target)
T = [
 ("s0",  "contact",        frozenset({CD, AN}), "ch"),    # t1 anonymous contact discovery
 ("s0",  "contact",        frozenset({DI}),     "ch"),    # t2 co-present shared scene as channel
 ("ch",  "request",        frozenset({UM}),     "img"),   # t3
 ("ch",  "request",        frozenset({UM, EP}), "img"),   # t4 ephemeral request
 ("ch",  "request",        frozenset({UM}),     "ref"),   # t5 refused / blocked
 ("img", "threaten",       frozenset({UM}),     "thr"),   # t6 sextortion with coerced imagery (h4)
 ("img", "circulate",      frozenset({DI}),     "circ"),  # t7 (h3)
 ("s0",  "enter_scene",    frozenset({DI}),     "scene"), # t8 recipient of a shared Memory
 ("s0",  "photograph",     frozenset(),         "near"),  # t9 in-person capture (person access)
 ("scene","reconstruct",   frozenset({GS}),     "lik"),   # t10 render uncaptured viewpoints
 ("near","reconstruct",    frozenset({GS}),     "lik"),   # t11
 ("lik", "synthesize",     frozenset({GS}),     "syn"),   # t12 (h6)
 ("syn", "circulate",      frozenset({DI}),     "circ"),  # t13 (h3)
 ("syn", "contact_threaten", frozenset({CD, UM}), "thr"), # t14 sextortion with synthetic imagery (h4)
]
CONTACT = {"contact", "request", "threaten", "photograph", "contact_threaten"}
BASE = frozenset({AN, EP, CD, UM})
Q = frozenset({DI, GS})

def TP(avail): return [t for t in T if t[2] <= avail]
def runs(avail, start="s0"):
    out = [()]
    frontier = [((), start)]
    while frontier:
        nxt = []
        for r, s in frontier:
            for t in TP(avail):
                if t[0] == s:
                    nxt.append((r + (t,), t[3])); out.append(r + (t,))
        frontier = nxt
    return out
end = lambda r: r[-1][3] if r else "s0"
pi = lambda r: tuple(t[1] for t in r)
eps = lambda r: tuple((t[1], t[2]) for t in r)
aff = lambda r: frozenset().union(*[t[2] for t in r]) if r else frozenset()
lang = lambda av: {eps(r) for r in runs(av)}
pil = lambda av: {pi(r) for r in runs(av)}
def dpath(add, base=BASE): return pil(base | add) - pil(base)
def dsupp(o, base=BASE):
    return {L for L in lang(base | {o}) if tuple(a for a, _ in L) in pil(base) and any(o in X for _, X in L)}
def reach(av, F, filt=lambda r: True): return [r for r in runs(av) if end(r) in F and filt(r)]
cfree = lambda r: not any(t[1] in CONTACT for t in r)
fmt = lambda S: sorted(S, key=lambda x: (len(x), x))

def show(obj):
    """Python repr, with set and frozenset elements sorted so a rerun prints the same bytes."""
    if isinstance(obj, frozenset):
        if not obj:
            return "frozenset()"
        return "frozenset({" + ", ".join(show(x) for x in sorted(obj, key=repr)) + "})"
    if isinstance(obj, set):
        if not obj:
            return "set()"
        return "{" + ", ".join(show(x) for x in sorted(obj, key=repr)) + "}"
    if isinstance(obj, tuple):
        inner = ", ".join(show(x) for x in obj)
        if len(obj) == 1:
            inner += ","
        return "(" + inner + ")"
    if isinstance(obj, list):
        return "[" + ", ".join(show(x) for x in obj) + "]"
    return repr(obj)


PM = BASE | Q
print("Baseline O(P) =", sorted(BASE), " Q =", sorted(Q))
print("runs: P =", len(runs(BASE)), " P+Q =", len(runs(PM)))
dDI, dGS, dQ = dpath({DI}), dpath({GS}), dpath(Q)
print("\nDelta_path(DI) =", fmt(dDI)); print("Delta_path(GS) =", fmt(dGS)); print("Delta_path({DI,GS}) =", fmt(dQ))
Sigma = dQ - dDI - dGS
print("Sigma(DI,GS) =", fmt(Sigma))
sDI, sGS = dsupp(DI), dsupp(GS)
print("Delta_supp(DI) =", show(fmt(sDI))); print("Delta_supp(GS) =", show(fmt(sGS)))
assert dDI == {("enter_scene",), ("contact", "request", "circulate")}
assert dGS == {("photograph", "reconstruct"), ("photograph", "reconstruct", "synthesize"),
               ("photograph", "reconstruct", "synthesize", "contact_threaten")}
assert Sigma == {("enter_scene", "reconstruct"), ("enter_scene", "reconstruct", "synthesize"),
                 ("enter_scene", "reconstruct", "synthesize", "circulate"),
                 ("enter_scene", "reconstruct", "synthesize", "contact_threaten"),
                 ("photograph", "reconstruct", "synthesize", "circulate")}
assert len(sDI) == 5 and sGS == set()
# C1b: every run realising a Sigma sequence uses both DI and GS
for r in runs(PM):
    if pi(r) in Sigma: assert Q <= aff(r)
print("C1b check: every run realising a Sigma sequence uses {DI,GS}: OK")

# C2c: contact-free reachability of h6 state 'syn'
F6 = {"syn"}
cf = {name: bool(reach(av, F6, cfree)) for name, av in
      [("P", BASE), ("P+DI", BASE | {DI}), ("P+GS", BASE | {GS}), ("P+Q", PM)]}
print("\ncontact-free reachable 'syn':", cf)
assert cf == {"P": False, "P+DI": False, "P+GS": False, "P+Q": True}
print("reachable 'syn' at all:", {n: bool(reach(av, F6)) for n, av in [("P", BASE), ("P+DI", BASE | {DI}), ("P+GS", BASE | {GS}), ("P+Q", PM)]})

# C3a dominators in P+Q
states = {t[0] for t in T} | {t[3] for t in T}
def dominates(s, F, av=PM): return all(s in {"s0"} | {t[3] for t in r} for r in reach(av, F))
for F, name in [({"syn"}, "h6 syn"), ({"circ"}, "h3 circ"), ({"thr"}, "h4 thr")]:
    print(f"dominators of {name}:", sorted(s for s in states if s != "s0" and dominates(s, F)))
assert sorted(s for s in states if s != "s0" and dominates(s, {"syn"})) == ["lik", "syn"]

# exact minimum blocking sets over all 64 subsets (conjunctive removal)
subsets = list(chain.from_iterable(combinations(O, k) for k in range(7)))
assert len(subsets) == 64
def blocks(R, F, filt=lambda r: True):
    return not reach(PM - frozenset(R), F, filt)
def minblock(F, filt=lambda r: True, allowed=O):
    ok = [set(R) for R in subsets if set(R) <= set(allowed) and blocks(R, F, filt)]
    if not ok: return None, []
    m = min(len(R) for R in ok); return m, [sorted(R) for R in ok if len(R) == m]
results = {}
for label, F, filt, allowed in [
    ("h6 syn", {"syn"}, lambda r: True, O),
    ("h6 syn, contact-free runs", {"syn"}, cfree, O),
    ("h3 circ", {"circ"}, lambda r: True, O),
    ("h4 thr", {"thr"}, lambda r: True, O),
    ("h4 thr, team-controllable {DI,GS} only", {"thr"}, lambda r: True, [DI, GS]),
    ("h4 thr via synthetic leverage (runs through syn)", {"thr"}, lambda r: any(t[3] == "syn" for t in r), O),
]:
    results[label] = minblock(F, filt, allowed); print(f"min blocking set [{label}]:", results[label])
assert results["h6 syn"] == (1, [["GS"]])
assert results["h6 syn, contact-free runs"] == (1, [["DI"], ["GS"]])
assert results["h3 circ"] == (1, [["DI"]])
assert results["h4 thr"] == (1, [["UM"]])
assert results["h4 thr, team-controllable {DI,GS} only"] == (None, [])
assert results["h4 thr via synthetic leverage (runs through syn)"][1] == [["CD"], ["UM"], ["GS"]]
# Theorem (cut): blocking iff R hits Aff of every simple run (acyclic => all runs simple)
for R in subsets:
    for F in [{"syn"}, {"circ"}, {"thr"}]:
        assert blocks(R, F) == all(set(R) & aff(r) for r in reach(PM, F))
print("cut characterisation (blocks iff R hits every run's Aff): OK on 64 subsets x 3 targets")

# C3c substitution / kappa
def kappa(sigma, av):
    real = [aff(r) for r in runs(av) if pi(r) == sigma]
    for k in range(7):
        for R in combinations(sorted(av), k):
            if all(set(R) & A for A in real): return k, sorted(R)
    return float("inf"), None
sig = ("contact", "request")
def substitutable(sigma, o, av): return sigma in pil(av - {o})
print("\nsubstitution for (contact, request):")
for name, av in [("P", BASE), ("P+Q", PM)]:
    must = sorted(o for o in av if not substitutable(sig, o, av))
    print(f"  {name}: kappa={kappa(sig, av)[0]}, single-affordance cuts (not substitutable) = {must}")
assert sorted(o for o in BASE if not substitutable(sig, o, BASE)) == ["AN", "CD", "UM"]
assert sorted(o for o in PM if not substitutable(sig, o, PM)) == ["UM"]
sig2 = ("enter_scene", "reconstruct", "synthesize")
print("kappa(enter_scene, reconstruct, synthesize) in P+Q =", kappa(sig2, PM))

# C5 ordinal comparison, '|_F' = some run with that sequence reaches F
def restrict(D, F, av):
    return {s for s in D if any(pi(r) == s and end(r) in F for r in runs(av))}
dDI_F, dGS_F = restrict(dDI, {"syn"}, BASE | {DI}), restrict(dGS, {"syn"}, BASE | {GS})
print("\nC5: Delta_path(DI)|syn =", fmt(dDI_F), " Delta_path(GS)|syn =", fmt(dGS_F))
assert dDI_F == set() and dGS_F == {("photograph", "reconstruct", "synthesize")}

# Interventions as changes to T* (transition deletions)
def without(ids):
    keep = [t for i, t in enumerate(T, 1) if i not in ids]
    return keep
def reach_T(Tlist, F, av=PM, filt=lambda r: True):
    global T
    old = T; T = Tlist
    try: return bool(reach(av, F, filt))
    finally: T = old
print("\ninterventions (transition deletions in T*):")
iv = {"I1 capture-geometry constraint (delete t10,t11 reconstruct)": {10, 11},
      "I2 gate scene entry for scenes with minors (delete t8)": {8},
      "I3 no co-presence channel with minors (delete t2)": {2}}
for k, ids in iv.items():
    Tn = without(ids)
    r = {"syn": reach_T(Tn, {"syn"}), "syn contact-free": reach_T(Tn, {"syn"}, filt=cfree),
         "thr via syn": reach_T(Tn, {"thr"}, filt=lambda r: any(t[3] == "syn" for t in r))}
    print(" ", k, r)
assert reach_T(without({10, 11}), {"syn"}) is False
assert reach_T(without({8}), {"syn"}, filt=cfree) is False and reach_T(without({8}), {"syn"}) is True
old = T; T = without({2})
assert sorted(o for o in PM if not substitutable(sig, o, PM)) == ["AN", "CD", "UM"]
T = old
print("I3 restores CD and AN as single-affordance cuts for (contact, request): OK")
print("\nALL CHECKS PASSED")
