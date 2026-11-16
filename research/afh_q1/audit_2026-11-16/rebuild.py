import sys, json, importlib.util, io, contextlib
from pathlib import Path
from collections import defaultdict
R=Path('/Users/mrinaalramachandran/Projects/CaseLinker'); S=Path(sys.argv[1])
def load(name, p):
    spec=importlib.util.spec_from_file_location(name, p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bc=load('bc', R/'ontology/platform_affordance_evidence/build_candidates.py')
bc.DB=str(R/'caselinker.db'); bc.OUT=str(S/'candidates_fresh.json')
with contextlib.redirect_stdout(io.StringIO()): bc.main()
pe=load('pe', R/'ontology/platform_affordance_evidence/platform_affordance_evidence.py')
pe.DB=str(R/'caselinker.db'); pe.CANDIDATES_FILE=str(S/'candidates_fresh.json'); pe.OUTPUT_DIR=S
with contextlib.redirect_stdout(io.StringIO()): pe.main()
print(json.load(open(S/'candidates_fresh.json'))['summary'])
print(json.load(open(S/'platform_affordance_evidence.json'))['_meta'])
