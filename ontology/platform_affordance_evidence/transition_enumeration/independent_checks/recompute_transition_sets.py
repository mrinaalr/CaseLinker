"""A second derivation of the transition sets. It does not import the canonical scripts."""
from itertools import combinations
T={1:('s0','contact',{'CD','AN'},'ch'),3:('ch','request',{'UM'},'img'),4:('ch','request',{'UM','EP'},'img'),
5:('ch','request',{'UM'},'ref'),6:('img','threaten',{'UM'},'thr'),7:('img','circulate',{'DI'},'circ'),
8:('s0','enter_scene',{'DI'},'scene'),9:('s0','photograph',set(),'near'),10:('scene','reconstruct',{'GS'},'lik'),
11:('near','reconstruct',{'GS'},'lik'),12:('lik','synthesize',{'GS'},'syn'),13:('syn','circulate',{'DI'},'circ'),
14:('syn','contact_threaten',{'CD','UM'},'thr')}
T2={2:('s0','contact',{'DI'},'ch')}
INT={'contact','request','threaten','photograph','contact_threaten'}
P={'AN','EP','CD','UM'}; ALL=P|{'DI','GS'}
def runs(O,TT):
    out=[[]];fr=[[]]
    while fr:
        nf=[]
        for r in fr:
            s=TT[r[-1]][3] if r else 's0'
            for k,(a,b,o,c) in TT.items():
                if a==s and o<=O: nf.append(r+[k])
        out+=nf;fr=nf
    return out
seq=lambda r,TT:tuple(TT[k][1] for k in r)
traj=lambda r,TT:tuple((TT[k][1],frozenset(TT[k][2])) for k in r)
aff=lambda r,TT:set().union(*[TT[k][2] for k in r]) if r else set()
end=lambda r,TT:TT[r[-1]][3] if r else 's0'
S=lambda O,TT=T:{seq(r,TT) for r in runs(O,TT)}
def dpath(base,add,TT=T): return S(base|add,TT)-S(base,TT)
def dsupp(base,o,TT=T): return {traj(r,TT) for r in runs(base|{o},TT) if seq(r,TT) in S(base,TT) and o in aff(r,TT)}
print('runs P',len(runs(P,T)),'runs P+Q',len(runs(ALL,T)))
print('Dpath DI',sorted(dpath(P,{'DI'})));print('Dpath GS',sorted(dpath(P,{'GS'})))
print('Dpath Q',len(dpath(P,{'DI','GS'})))
syn=dpath(P,{'DI','GS'})-dpath(P,{'DI'})-dpath(P,{'GS'});print('Sigma',len(syn),sorted(syn))
print('Dsupp DI',dsupp(P,'DI'),'Dsupp GS',dsupp(P,'GS'))
print("Dpath(DI;P') size",len(dpath(P|{'GS'},{'DI'})))
def reach(O,F,TT=T,phi=lambda r,TT:True): return [r for r in runs(O,TT) if end(r,TT) in F and phi(r,TT)]
noint=lambda r,TT: not any(TT[k][1] in INT for k in r)
for O,n in [(P,'P'),(P|{'DI'},'P+DI'),(P|{'GS'},'P+GS'),(ALL,'P+Q')]:
    print('syn reach',n,len(reach(O,{'syn'})),'no-int',len(reach(O,{'syn'},phi=noint)))
def restr(O,F,TT=T): return {x for x in sorted(seq(r,TT) for r in runs(O,TT) if end(r,TT) in F)}
print('DI|syn',restr(P|{'DI'},{'syn'})&dpath(P,{'DI'}),'GS|syn',restr(P|{'GS'},{'syn'})&dpath(P,{'GS'}))
print('DI|circ',restr(P|{'DI'},{'circ'})&dpath(P,{'DI'}),'GS|circ',restr(P|{'GS'},{'circ'})&dpath(P,{'GS'}))
def dominators(O,F,TT=T):
    rs=reach(O,F,TT); states=set(x[3] for x in TT.values())|{'s0'}
    return {s for s in states if all(s=='s0' or any(TT[k][3]==s for k in r) for r in rs)}
def show_set(s):
    if not s:
        return 'set()'
    return '{' + ', '.join(repr(x) for x in sorted(s, key=repr)) + '}'
for F in ['syn','circ','thr']: print('dominators',F,show_set(dominators(ALL,{F})))
def minblock(rs,TT=T,allowed=ALL):
    for k in range(0,7):
        sols=[set(R) for R in combinations(sorted(allowed),k) if all(aff(r,TT)&set(R) for r in rs)]
        if sols: return sols
    return 'none'
print('h6',minblock(reach(ALL,{'syn'})));print('h6 noint',minblock(reach(ALL,{'syn'},phi=noint)))
print('h3',minblock(reach(ALL,{'circ'})));print('h4',minblock(reach(ALL,{'thr'})))
print('h4 only DI/GS',minblock(reach(ALL,{'thr'}),allowed={'DI','GS'}))
print('h4 via syn',minblock(reach(ALL,{'thr'},phi=lambda r,TT:14 in r)))
TC={**T,**T2}
print('co-present Dsupp DI',len(dsupp(P,'DI',TC)))
print('co-present: all Z.4 sets same?',dpath(P,{'DI'},TC)==dpath(P,{'DI'}),dpath(P,{'GS'},TC)==dpath(P,{'GS'}),
      (dpath(P,{'DI','GS'},TC)-dpath(P,{'DI'},TC)-dpath(P,{'GS'},TC))==syn)
sig=('contact','request')
def kappa(O,TT,s):
    for k in range(1,len(O)+1):
        for R in combinations(sorted(O),k):
            if s not in S(O-set(R),TT): return k,R
    return 'inf'
for O,n in [(P,'P'),(ALL,'P+Q no t2'),(ALL,'P+Q t2')]:
    TT=TC if 't2' in n and 'no' not in n else T
    print('sigma single cuts',n,[o for o in sorted(O) if sig not in S(O-{o},TT)])
print('h4 co-present',minblock(reach(ALL,{'thr'},TC),TC))
del_t=lambda ks:{k:v for k,v in T.items() if k not in ks}
print('delete t10,t11: syn reach',len(reach(ALL,{'syn'},del_t({10,11}))),' thr via syn',len(reach(ALL,{'thr'},del_t({10,11}),lambda r,TT:14 in r)))
print('delete t8: syn noint',len(reach(ALL,{'syn'},del_t({8}),phi=noint)),'syn any',len(reach(ALL,{'syn'},del_t({8}))))
print('transitions primary',len(T),'with t2',len(TC))
