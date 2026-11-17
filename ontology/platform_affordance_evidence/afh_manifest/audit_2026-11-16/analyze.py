import json, sqlite3, re, sys
from collections import defaultdict, Counter
R='/Users/mrinaalramachandran/Projects/CaseLinker'; S=sys.argv[1]
GENERIC={'chat','social media','gaming','internet','online','email','dark web','other','webcam platform'}
def generic(p): return p.lower() in GENERIC or p.lower().startswith('unknown')
ev=json.load(open(f'{S}/platform_affordance_evidence.json'))
cand=json.load(open(f'{S}/candidates_fresh.json'))
recs=ev['records']
con=sqlite3.connect(f'{R}/caselinker.db')
meta={}
for cid,src,yr,topics,url in con.execute("select id,source,json_extract(raw_data,'$.year'),case_topics,source_url from cases"):
    meta[cid]=dict(src=src,yr=int(yr) if yr else None,topics=json.loads(topics or '[]'),url=url)
out={}
out['total_cases']=len(meta); out['sources']=len({m['src'] for m in meta.values()})
out['years']=Counter(m['yr'] for m in meta.values())
# fingerprint dupes
fp=defaultdict(list)
for cid,f in con.execute("select case_id,fingerprint from case_fingerprints"): fp[f].append(cid)
dg=[v for v in fp.values() if len(v)>1]
out['fingerprint_dup_groups']=len(dg); out['fingerprint_dup_cases']=sum(len(v) for v in dg); out['fp_examples']=dg[:4]
out['fingerprinted']=sum(len(v) for v in fp.values())
def tiers(rs):
    bc=defaultdict(set)
    for r in rs: bc[r['case_id']].add(r['stated_vs_inferred'])
    return dict(cases=len(bc),stated=sum('stated' in t for t in bc.values()),
        inferred_only=sum('inferred' in t and 'stated' not in t for t in bc.values()),
        named_only=sum(t=={'named_only'} for t in bc.values()), records=len(rs),
        rec_stated=sum(r['stated_vs_inferred']=='stated' for r in rs),
        rec_inferred=sum(r['stated_vs_inferred']=='inferred' for r in rs),
        rec_named=sum(r['stated_vs_inferred']=='named_only' for r in rs)), bc
out['all_labels'],_=tiers(recs)
ng=[r for r in recs if not generic(r['platform'])]
out['nongeneric'],bc_ng=tiers(ng)
out['nongeneric_labels']=len({r['platform'] for r in ng})
out['cand_cases_nongeneric']=len({c for e in cand['flat'] if not generic(e['platform']) for c in e['case_ids']})
out['cand_pairs_nongeneric']=sum(len(e['case_ids']) for e in cand['flat'] if not generic(e['platform']))
out['generic_label_pairs']={e['platform']:len(e['case_ids']) for e in cand['flat'] if generic(e['platform'])}
out['text_not_found']=sum(1 for r in ng if r.get('_text_not_found'))
out['psa_excl']=len(ev['excluded_platforms'])
# per platform
pp={}
for p in sorted({r['platform'] for r in ng}):
    t,_=tiers([r for r in ng if r['platform']==p]); t['type']=next(r['platform_type'] for r in ng if r['platform']==p); pp[p]=t
out['per_platform']=pp
# role buckets on stated records
st=[r for r in ng if r['stated_vs_inferred']=='stated']
out['role_stated']=Counter(r['platform_role_in_offense'] for r in st)
out['role_inferred']=Counter(r['platform_role_in_offense'] for r in ng if r['stated_vs_inferred']=='inferred')
# cue scan on evidence sentences (quote is truncated; re-pull full sentence unavailable) -> scan whole case text near platform
CUES={'Anonymity':r'anonym|fake (?:profile|account|persona|name)|posed as|pretend(?:ed|ing) to be|posing as|false identit|alias|username|screen ?name|catfish',
 'Ephemerality':r'disappear|ephemeral|self-destruct|auto-?delet|vanish|snap(?:s)? (?:that|which) (?:disappear|delete)|deleted after',
 'ContactDiscovery':r'random(?:ly)? (?:match|pair|chat)|met (?:the )?(?:victim|minor|child|girl|boy) (?:on|through|via)|friend request|found (?:the )?(?:victim|minor)|search(?:ed)? for (?:minor|child|girl|boy)|quick add|befriend',
 'UnmonitoredCommunication':r'private (?:message|chat|conversation)|direct message|\bdms?\b|encrypt|one-on-one|secret',
 'DistributionInfrastructure':r'upload|distribut|shar(?:e|ed|ing)|trad(?:e|ed|ing)|group chat|channel|server|link|peer-to-peer|p2p|download',
 'GenerativeSynthesis':r'ai-generated|artificial intelligence|generat(?:e|ed|ive)|deepfake|morph|manipulat|synthetic|nudif|face-?swap|stable diffusion'}
texts={cid:t or '' for cid,t in con.execute("select id,json_extract(raw_data,'$.case_text') from cases where id in (%s)"%','.join("'%s'"%c for c in {r['case_id'] for r in ng}))}
def sents_with(text,p):
    terms=[p.lower()]+{'Twitter / X':['twitter'],'Gen AI':['artificial intelligence','ai-generated','ai generated'],'Mega.nz':['mega'],'Xbox Live':['xbox'],'Facebook Messenger':['messenger']}.get(p,[])
    out=[]
    for s in re.split(r'(?<=[.!?])\s+',text[:6000]):
        sl=s.lower()
        if any(t in sl for t in terms): out.append(sl)
    return out
cue_cases=defaultdict(lambda: defaultdict(set)); cue_plat=defaultdict(lambda: defaultdict(set)); cue_tier=defaultdict(Counter)
for r in ng:
    ss=sents_with(texts.get(r['case_id'],''),r['platform'])
    for k,rx in CUES.items():
        if any(re.search(rx,s) for s in ss):
            cue_cases[k][r['stated_vs_inferred']].add(r['case_id']); cue_plat[k][r['platform']].add(r['case_id'])
out['cue']={k:{'cases_any':len(set().union(*v.values())),'stated_cases':len(v['stated']),'inferred_cases':len(v['inferred']-v['stated']),'named_only_cases':len(v['named_only']-v['stated']-v['inferred']),
  'platforms':len(cue_plat[k]),'top_platforms':sorted(((p,len(c)) for p,c in cue_plat[k].items()),key=lambda x:-x[1])[:6]} for k,v in cue_cases.items()}
# platform type x topics for stated cases
tt=defaultdict(Counter)
for r in st:
    for t in meta[r['case_id']]['topics']: tt[r['platform_type']][t]+=1
out['type_topics']={k:v.most_common(6) for k,v in tt.items()}
# temporal by publication year
yr=defaultdict(lambda: Counter())
srcyr=defaultdict(set)
for cid,m in meta.items():
    y=m['yr']; yr[y]['cases']+=1; srcyr[y].add(m['src'])
    if m['src']=='NCMEC': yr[y]['ncmec']+=1
for cid,t in bc_ng.items():
    y=meta[cid]['yr']; yr[y]['named']+=1
    if 'stated' in t: yr[y]['stated']+=1
platyr=defaultdict(set)
for r in st: platyr[meta[r['case_id']]['yr']].add(r['platform'])
out['by_year']={y:dict(v, sources=len(srcyr[y]), stated_platforms=len(platyr[y])) for y,v in sorted(yr.items(), key=lambda x:(x[0] is None, x[0]))}
out['source_of_stated']=Counter(meta[c]['src'] for c,t in bc_ng.items() if 'stated' in t).most_common(10)
# role by era for stated
era=lambda y: '2002-2014' if y and y<=2014 else ('2015-2019' if y and y<=2019 else ('2020-2022' if y and y<=2022 else '2023-2026'))
re_=defaultdict(Counter); ptyp=defaultdict(Counter)
for r in st:
    e=era(meta[r['case_id']]['yr']); re_[e][r['platform_role_in_offense']]+=1; ptyp[e][r['platform_type']]+=1
out['role_by_era']=re_; out['ptype_by_era']=ptyp
out['era_counts']=Counter(era(m['yr']) for m in meta.values())
out['era_stated_cases']=Counter(era(meta[c]['yr']) for c,t in bc_ng.items() if 'stated' in t)
out['era_sources']={e:len({m['src'] for m in meta.values() if era(m['yr'])==e}) for e in out['era_counts']}
json.dump(out,open(f'{S}/inventory.json','w'),indent=1,default=str)
for k,v in out.items():
    if k not in ('per_platform','by_year'): print(k,':',json.dumps(v,default=str)[:900])
