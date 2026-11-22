"""The same transition sets with the second contact transition left out, kept, or with GS in the baseline.

Imports enumerate_transitions and recomputes the sets for each variant. Running
this file also prints that module's output, because the import executes it.
"""
import enumerate_transitions as A
from itertools import combinations
T_full=list(A.T)
def setT(Tl): A.T[:]=Tl
prim=[t for i,t in enumerate(T_full,1) if i!=2]
for name,Tl in [("PRIMARY (no t2)",prim),("CO-PRESENT (with t2)",T_full)]:
    setT(Tl); B,PM=A.BASE,A.PM
    print("\n==",name)
    print("runs P",len(A.runs(B)),"runs P+Q",len(A.runs(PM)))
    dDI,dGS,dQ=A.dpath({A.DI}),A.dpath({A.GS}),A.dpath(A.Q); Sig=dQ-dDI-dGS
    print("|dDI|",len(dDI),"|dGS|",len(dGS),"|dQ|",len(dQ),"|Sigma|",len(Sig))
    print("|supp DI|",len(A.dsupp(A.DI)),"|supp GS|",len(A.dsupp(A.GS)))
    for lab,F,filt,allowed in [("syn",{"syn"},lambda r:True,A.O),("syn cf",{"syn"},A.cfree,A.O),("circ",{"circ"},lambda r:True,A.O),("thr",{"thr"},lambda r:True,A.O),("thr ctrl",{"thr"},lambda r:True,[A.DI,A.GS]),("thr via syn",{"thr"},lambda r:any(t[3]=="syn" for t in r),A.O)]:
        print(" minblock",lab,A.minblock(F,filt,allowed))
    sig=("contact","request")
    print(" single cuts (contact,request):",sorted(o for o in PM if not A.substitutable(sig,o,PM)))
    print(" dominators syn:",sorted(s for s in {t[3] for t in Tl} if A.dominates(s,{"syn"})))
    print(" cf reach syn P,DI,GS,Q:",[bool(A.reach(av,{"syn"},A.cfree)) for av in [B,B|{A.DI},B|{A.GS},PM]])
# GS in baseline (primary)
setT(prim)
B2=A.BASE|{A.GS}
d=A.pil(B2|{A.DI})-A.pil(B2)
print("\nGS-in-baseline (primary): |dpath(DI;P')|",len(d)); [print("  ", x) for x in sorted(d, key=lambda x: (len(x), x))]
setT(T_full)
d=A.pil(B2|{A.DI})-A.pil(B2); print("GS-in-baseline (co-present): |dpath(DI;P')|",len(d))
