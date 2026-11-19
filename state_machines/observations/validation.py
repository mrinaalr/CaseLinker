"""Human check of observations on the real text: a local packet to review, and its score.

    python -m state_machines.observations.validation packet <release_id> [--text-root DIR] [--out local/validation]
    python -m state_machines.observations.validation score <release_id> <decisions.json>

The packet is one local HTML file holding court text; it is never committed. It samples the
release's observations in strata, so the few that matter most are all reviewed:

    relationship   every observation tied to an act (all of them)
    feature        every feature observation (all of them, up to FEATURE_CAP)
    platform       one per (platform, legal standing) pair, then at random up to PLATFORM_N

Two questions per item, answered separately:

    grounding   is the highlighted term in the sentence, at the cited place?
    meaning     platform: does it refer to that online service?
                feature: does the sentence describe that capability?
                relationship: does the sentence state the act was done by means of it?

``score`` writes ``<release>/validation.json``: counts and Wilson 95% intervals per stratum, the
reviewer's initials and date, and no text. The sample is drawn with a fixed seed from the
committed observation files, so the same release gives the same items.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Dict, List

from state_machines.evidence import evidence as E

SEED, PLATFORM_N, FEATURE_CAP = 7, 60, 60
QUESTION = {"platform": "Does it refer to that online service?", "feature": "Does the sentence describe that capability?",
            "withheld": "Is it the record's placeholder for an online service whose name is withheld?",
            "description": "Is it a generic description of an online service (not a named one, not a person's account)?",
            "relationship": "Does the sentence state the act was done by means of it?"}


def sample(root: Path) -> List[dict]:
    """The items to review, drawn from the release's committed observation files."""
    rng = random.Random(SEED)
    every = []
    for path in sorted((root / "observations").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        every += [dict(o, case_id=doc["case_id"]) for o in doc["observations"]]
    key = lambda o: f"{o['case_id']}:{o['observation_id']}"
    items: Dict[str, dict] = {}
    seen: set = set()
    for o in every:
        if o["relations"]:
            items[key(o)] = dict(o, stratum="relationship")
    features = [o for o in every if o["kind"] == "feature" and key(o) not in items]
    for o in (features if len(features) <= FEATURE_CAP else rng.sample(features, FEATURE_CAP)):
        items[key(o)] = dict(o, stratum="feature")
    for o in every:                                              # every case's placeholder labels and every distinct description, by standing
        if key(o) in items or not (o.get("withheld") or o["kind"] == "service_description"):
            continue
        group = (o["case_id"], o.get("platform") or o["service_term"], o["source_status"])
        if group not in seen:
            seen.add(group)
            items[key(o)] = dict(o, stratum="withheld" if o.get("withheld") else "description")
    platforms = [o for o in every if o["kind"] == "platform" and not o.get("withheld") and key(o) not in items]
    by_pair: Dict[tuple, list] = {}
    for o in platforms:
        by_pair.setdefault((o["platform"], o["source_status"]), []).append(o)
    chosen = [rng.choice(group) for _, group in sorted(by_pair.items())]
    rest = [o for o in platforms if o not in chosen]
    rng.shuffle(rest)
    for o in (chosen + rest)[:max(PLATFORM_N, len(chosen))]:
        items[key(o)] = dict(o, stratum="platform")
    return [dict(v, item_id=k) for k, v in sorted(items.items())]


def packet(release_id: str, root: Path, text_root: Path, out: Path) -> Path:
    cards = []
    for it in sample(root):
        page = E.normalize(E.read_page(it["case_id"], it["doc_id"], it["pdf_page"], text_root) or "")
        a, b, s, e = it["char_start"], it["char_end"], it["term_start"], it["term_end"]
        sentence = f"{html.escape(page[a:s])}<mark>{html.escape(page[s:e])}</mark>{html.escape(page[e:b])}"
        claim = (f"refers to a service by the placeholder <b>{html.escape(it['named_as'])}</b>" if it.get("withheld") else
                 f"names the platform <b>{html.escape(it['platform'])}</b>" if it["kind"] == "platform" else
                 f"uses the generic service description <b>{html.escape(it['service_term'])}</b>" if it["kind"] == "service_description" else
                 f"states the feature phrase <b>{html.escape(it['feature_term'])}</b> ({it['feature_class'].replace('_', ' ')})")
        if it["stratum"] == "relationship":
            claim += " and states the act (" + ", ".join(f"{r['event_id']}: {r['relationship'].replace('_', ' ').lower()}" for r in it["relations"]) + ") was done by means of it"
        radios = lambda name, opts: "".join(f'<label><input type="radio" name="{name}" value="{v}"> {v}</label>' for v in opts)
        cards.append(f'''<section class="item" data-id="{it['item_id']}" data-stratum="{it['stratum']}">
<div class="meta">{it['stratum']} · {it['case_id']} · {it['doc_id']} · page {it['pdf_page']} · {it['source_status'].lower()}</div>
<p class="sentence">{sentence}</p><p class="claim">Claim: the sentence {claim}.</p>
<div class="q">Is the highlighted term in the sentence, as cited? {radios(it['item_id'] + '|grounding', ('yes', 'no'))}</div>
<div class="q">{QUESTION[it['stratum']]} {radios(it['item_id'] + '|meaning', ('yes', 'no', 'unclear'))}</div></section>''')
    page_html = f'''<!doctype html><meta charset="utf-8"><title>Observation review: {release_id}</title>
<style>body{{font:15px/1.5 system-ui;max-width:860px;margin:24px auto;padding:0 16px;color:#1b1f1c}}
.item{{border:1px solid #d5dad6;border-radius:8px;padding:12px 16px;margin:14px 0}}.meta{{font:12px ui-monospace,monospace;color:#5d665f}}
mark{{background:#ffe08a}}.claim{{color:#3a433c}}.q{{margin:6px 0}}label{{margin-left:12px}}.done{{border-color:#5fa97a}}
#bar{{position:sticky;top:0;background:#fff;padding:10px 0;border-bottom:1px solid #d5dad6}}button{{font:inherit;padding:6px 14px}}</style>
<div id="bar"><b>{release_id}</b>: <span id="n">0</span> of {len(cards)} reviewed · initials <input id="who" size="4">
<button id="save">Download decisions</button></div>
<p>Local file with court text. Do not share it. Answer both questions for each item; the downloaded file holds answers only, no text.</p>
{"".join(cards)}
<script>
const items=[...document.querySelectorAll('.item')];
const read=()=>Object.fromEntries(items.map(s=>[s.dataset.id,{{stratum:s.dataset.stratum,
 grounding:(s.querySelector('input[name$="|grounding"]:checked')||{{}}).value||null,
 meaning:(s.querySelector('input[name$="|meaning"]:checked')||{{}}).value||null}}]));
document.addEventListener('change',()=>{{const d=read();let n=0;items.forEach(s=>{{const ok=d[s.dataset.id].grounding&&d[s.dataset.id].meaning;
 s.classList.toggle('done',!!ok);n+=ok?1:0}});document.getElementById('n').textContent=n}});
document.getElementById('save').onclick=()=>{{const blob=new Blob([JSON.stringify({{release:"{release_id}",reviewer:document.getElementById('who').value,
 reviewed_on:new Date().toISOString().slice(0,10),decisions:read()}},null,1)],{{type:'application/json'}});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='{release_id}.validation.decisions.json';a.click()}};
</script>'''
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{release_id}.review.html"
    path.write_text(page_html, encoding="utf-8")
    return path


def wilson(k: int, n: int, z: float = 1.96) -> List[float]:
    if not n:
        return [0.0, 1.0]
    p, d = k / n, 1 + z * z / n
    c, h = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(max(0.0, (c - h) / d), 3), round(min(1.0, (c + h) / d), 3)]


def score(root: Path, decisions: dict) -> dict:
    """Counts per stratum from a reviewer's decisions. Refuses a file that does not cover the sample."""
    expected = {it["item_id"]: it["stratum"] for it in sample(root)}
    given = decisions["decisions"]
    missing = [k for k in expected if not (given.get(k, {}).get("grounding") and given.get(k, {}).get("meaning"))]
    if missing or set(given) - set(expected):
        raise SystemExit(f"decisions do not match the sample: {len(missing)} unanswered, {len(set(given) - set(expected))} unknown")
    out = {}
    for stratum in ("platform", "withheld", "description", "feature", "relationship"):
        ids = [k for k, s in expected.items() if s == stratum]
        if not ids:
            continue
        g = sum(given[k]["grounding"] == "yes" for k in ids)
        m = Counter(given[k]["meaning"] for k in ids)
        out[stratum] = {"reviewed": len(ids), "grounded": g, "grounded_interval_95": wilson(g, len(ids)),
                        "meaning_yes": m["yes"], "meaning_no": m["no"], "meaning_unclear": m["unclear"],
                        "meaning_yes_interval_95": wilson(m["yes"], len(ids))}
    return {"reviewer": decisions.get("reviewer") or "", "reviewed_on": decisions.get("reviewed_on"), "seed": SEED,
            "note": ("platform items are a stratified sample; withheld and description items are one per case, term and standing; "
                     "feature and relationship items are all of them"), "strata": out}


def main(argv=None) -> int:
    from state_machines.graphs.release import DATA
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("packet"); p.add_argument("release_id"); p.add_argument("--text-root", type=Path, default=E.text_root())
    p.add_argument("--out", type=Path, default=E.REPO_ROOT / "local" / "validation")
    s = sub.add_parser("score"); s.add_argument("release_id"); s.add_argument("decisions", type=Path)
    a = ap.parse_args(argv)
    root = DATA / a.release_id
    if a.cmd == "packet":
        print(packet(a.release_id, root, a.text_root, a.out), f"({len(sample(root))} items)")
    else:
        result = score(root, json.loads(a.decisions.read_text(encoding="utf-8")))
        (root / "validation.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
