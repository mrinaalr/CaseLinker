import json,sqlite3,sys
from collections import defaultdict,Counter
S=sys.argv[1]; R='/Users/mrinaalramachandran/Projects/CaseLinker'
G={'chat','social media','gaming','internet','online','email','dark web','other','webcam platform'}
gen=lambda p:p.lower() in G or p.lower().startswith('unknown')
def pairs(c): return {(cid,e['platform']) for e in c['flat'] for cid in e['case_ids']}
old=pairs(json.load(open(f'{S}/old_cand.json'))); stale=pairs(json.load(open(f'{S}/stale_cand.json'))); new=pairs(json.load(open(f'{S}/candidates_fresh.json')))
ids=lambda P:{c for c,_ in P}
con=sqlite3.connect(f'{R}/caselinker.db'); live={r[0] for r in con.execute('select id from cases')}
print('old generic pairs', Counter(p for _,p in old if gen(p)))
print('old cand', len(ids(old)), 'nongeneric cases', len({c for c,p in old if not gen(p)}), 'labels', len({p for _,p in old}), 'nongeneric labels', len({p for _,p in old if not gen(p)}))
oc=ids(old); print('old cand still in DB', len(oc&live), 'gone', len(oc-live), list(oc-live)[:5])
nc=ids(new); print('fresh cand', len(nc), 'from old cand', len(nc&oc), 'old cases newly candidates?')
print('old cand that are no longer candidates', len(oc-nc), list(sorted(oc-nc))[:8])
sc=ids(stale); print('stale vs fresh: in stale not fresh', len(sc-nc), sorted(sc-nc)[:8], 'in fresh not stale', len(nc-sc), sorted(nc-sc)[:8])
print('stale-not-fresh in live DB', len((sc-nc)&live))
# pair-level changes on surviving old cases
surv=oc&nc
op={x for x in old if x[0] in surv}; np_={x for x in new if x[0] in surv}
print('surviving old cases', len(surv), 'pairs lost', len(op-np_), Counter(p for _,p in op-np_).most_common(8), 'pairs gained', len(np_-op), Counter(p for _,p in np_-op).most_common(8))
# tier changes for same (case,platform)
def tmap(f):
    return {(r['case_id'],r['platform']):r['stated_vs_inferred'] for r in json.load(open(f))['records']}
ot=tmap(f'{S}/old_ev.json'); nt=tmap(f'{S}/platform_affordance_evidence.json')
common=set(ot)&set(nt)
ch=Counter((ot[k],nt[k]) for k in common if ot[k]!=nt[k])
print('common pairs', len(common), 'tier changed', sum(ch.values()), ch.most_common())
ex=[k for k in common if ot[k]=='stated' and nt[k]!='stated'][:6]; print('stated->lower examples', ex)
# cases in fresh that were not in old candidates: created before? approximate: not in old candidate pool
newc=nc-oc
print('fresh cases not in old pool', len(newc))
