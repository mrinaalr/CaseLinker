# A second derivation of the transition sets. It does not import the canonical scripts.
from itertools import combinations
T={'t1':('s0','contact',{'CD','AN'},'ch'),'t2':('s0','contact',{'DI'},'ch'),
 't3':('ch','request',{'UM'},'img'),'t4':('ch','request',{'UM','EP'},'img'),
 't5':('ch','request',{'UM'},'ref'),'t6':('img','threaten',{'UM'},'thr'),
 't7':('img','circulate',{'DI'},'circ'),'t8':('s0','enter_scene',{'DI'},'scene'),
 't9':('s0','photograph',set(),'near'),'t10':('scene','reconstruct',{'GS'},'lik'),
 't11':('near','reconstruct',{'GS'},'lik'),'t12':('lik','synthesize',{'GS'},'syn'),
 't13':('syn','circulate',{'DI'},'circ'),'t14':('syn','contact_threaten',{'CD','UM'},'thr')}
INT={'contact','request','threaten','photograph','contact_threaten'}
ALL=['AN','EP','CD','UM','DI','GS']; P={'AN','EP','CD','UM'}
def runs(O,cop=False):
    ts={k:v for k,v in T.items() if v[2]<=O and (cop or k!='t2')}
    out=[];st=[('s0',())]
    while st:
        s,r=st.pop(); out.append(r)
        for k,v in ts.items():
            if v[0]==s: st.append((v[3],r+(k,)))
    return out
end=lambda r:T[r[-1]][3] if r else 's0'
seq=lambda r:tuple(T[k][1] for k in r)
uses=lambda r:set().union(*[T[k][2] for k in r]) if r else set()
S=lambda O,c=False:{seq(r) for r in runs(O,c)}
def dpath(Q,base=P,c=False): return S(base|Q,c)-S(base,c)
def dsupp(Q,base=P,c=False):
    old=set(runs(base,c)); os=S(base,c)
    return {r for r in runs(base|Q,c) if r not in old and seq(r) in os}
for c in (False,True):
    print('co-present' if c else 'primary')
    print(' runs P:',len(runs(P,c)),' runs P+Q:',len(runs(P|{'DI','GS'},c)), ' nonempty P:',len(runs(P,c))-1)
    print(' dpath DI:',sorted(dpath({'DI'},c=c)))
    print(' dpath GS:',sorted(dpath({'GS'},c=c)))
    both=dpath({'DI','GS'},c=c); Sig=both-dpath({'DI'},c=c)-dpath({'GS'},c=c)
    print(' |dpath both|:',len(both),' Sigma:',len(Sig),sorted(Sig))
    print(' dsupp DI:',len(dsupp({'DI'},c=c)),sorted(dsupp({'DI'},c=c)),' dsupp GS:',len(dsupp({'GS'},c=c)))
    R=runs(P|{'DI','GS'},c)
    def minblock(rs):
        for k in range(7):
            sols=[set(x) for x in combinations(ALL,k) if all(uses(r)&set(x) for r in rs)]
            if sols: return sols
    tgt={'h6':[r for r in R if end(r)=='syn'],
         'h6 no int':[r for r in R if end(r)=='syn' and not set(seq(r))&INT],
         'h3':[r for r in R if end(r)=='circ'],'h4':[r for r in R if end(r)=='thr'],
         'h4 synth':[r for r in R if end(r)=='thr' and 'syn' in [T[k][3] for k in r]]}
    for n,rs in tgt.items(): print(' minblock',n,minblock(rs))
    h4=tgt['h4']; print(' h4 cut within {DI,GS}:',[x for k in (1,2) for x in combinations(['DI','GS'],k) if all(uses(r)&set(x) for r in h4)])
    # dominators of syn, circ, thr in P+Q
    states={'s0','ch','img','ref','near','scene','lik','syn','circ','thr'}
    for f in ('syn','circ','thr'):
        rs=[r for r in R if end(r)==f]; vis=[{'s0'}|{T[k][3] for k in r} for r in rs]
        print(' dominators',f,sorted(set.intersection(*vis)-{'s0',f}))
print('Pprime=P+GS: dpath DI:',len(dpath({'DI'},base=P|{'GS'})),sorted(dpath({'DI'},base=P|{'GS'})))
# co-present sigma=(contact,request): single removals
for c in (False,True):
    rs=[r for r in runs(set(ALL),c) if seq(r)==('contact','request')]
    print('cop' if c else 'prim','(contact,request) single cuts in P+Q:',[o for o in ALL if all(o in uses(r) for r in rs)])
