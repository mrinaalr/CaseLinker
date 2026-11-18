"""Render the internal adjudication packet, and a public count of what was decided.

    python -m state_machines.coding.adjudication_packet <release> [case ...]

Internal (gitignored; quotes the court records):
    local/adjudication/<release>/packet.html      every item of every case: the question, both
                                                  codings with their passages and PDF page links,
                                                  and a choice limited to what ``adjudication
                                                  apply`` accepts. Choices are kept in the browser
                                                  as you go; "Export" saves one decisions file per
                                                  case (<case>.decisions.json).
Public (no quotes, no names):
    state_machines/data/<release>/ADJUDICATION.md  item and decision counts per case and kind

A decision exists only when a named reviewer records it; this module never writes decisions.
"""
from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

from state_machines.evidence import evidence as E
from state_machines.coding.adjudication import KIND_ORDER, OPTIONS, QUESTIONS
from state_machines.coding.workflow import PILOT_CASES, local_file, source_root

LOCAL = E.REPO_ROOT / "local" / "adjudication"
DATA = E.REPO_ROOT / "state_machines" / "data"


def _dossiers(release: str, cases=None) -> dict:
    cases = cases or PILOT_CASES
    return {c: json.loads((LOCAL / release / f"{c}.dossier.json").read_text(encoding="utf-8")) for c in cases
            if (LOCAL / release / f"{c}.dossier.json").is_file()}


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _pdf_href(dossier: dict, doc_id: str, page: int) -> str:
    doc = next((d for d in dossier["documents"] if d["doc_id"] == doc_id), None)
    if not doc:
        return ""
    path = local_file(dossier["case_id"], doc_id) or source_root() / doc["source_path"]
    return "file://" + str(path).replace(" ", "%20") + f"#page={page}"


def _passages(dossier: dict, passages) -> str:
    return "<ul>" + "".join(
        f"<li><a href='{_esc(_pdf_href(dossier, p['doc_id'], p['pdf_page']))}'>{_esc(p['doc_id'])} p{p['pdf_page']}</a>"
        f" <span class='st'>{_esc(p['source_status'])}</span><blockquote>{_esc(p.get('quote'))}</blockquote></li>"
        for p in passages) + "</ul>"


def _event_html(dossier: dict, view: Optional[dict], who: str) -> str:
    if not view:
        return f"<div class='ev none'><b>{_esc(who)}</b>: not coded</div>"
    line = lambda k, v: f"<br><span class='k'>{k}</span> {_esc(v)}" if v else ""   # noqa: E731
    when = "; ".join(f"{t.get('expression') or ''} {t['earliest']}–{t['latest']} ({t['basis']}, {t['status']})" for t in view["time"])
    return (f"<div class='ev'><b>{_esc(who)}</b> <code>{_esc(view['event_id'])}</code> <b>{_esc(view['action'])}</b>"
            f" [{_esc(view['status'])}, {_esc(view['outcome'])}] actor {_esc(view['actor'])}"
            f"{line('targets', ', '.join(view.get('targets', [])))}{line('with', ', '.join(view.get('co_actors', [])))}"
            f"{line('role open', '; '.join(view.get('unresolved', [])))}"
            f"{line('time', when)}"
            f"{line('affordances', view['affordances'])}{line('harms', view['harms'])}"
            f"{line('platforms', view.get('platforms'))}{line('named', view['platform_mentions'])}"
            f"{line('coder note', view.get('description'))}"
            f"{_passages(dossier, view.get('passages', []))}</div>")


def _relation_html(dossier: dict, r: dict) -> str:
    return (f"<div class='ev'><b>relation</b> <code>{_esc(r['relation_id'])}</code> {_esc(r['from'])} <b>{_esc(r['type'])}</b> {_esc(r['to'])}"
            f" [{_esc(r['status'])}, {_esc(r['basis'])}]{_passages(dossier, r['passages'])}</div>")


def _item_body(d: dict, it: dict) -> str:
    k = it["kind"]
    if k in ("order_only_a", "order_only_b"):
        return _relation_html(d, it["relation"]) + _event_html(d, it["from_event"], "from") + _event_html(d, it["to_event"], "to")
    if k == "single_coder_relation":
        return _relation_html(d, it["relation"])
    if k == "possible_same_act":
        return f"<p class='st'>{_esc(it['reason'])}</p>" + _event_html(d, it["event_x"], "event") + _event_html(d, it["event_y"], "event")
    if k == "single_step":
        return _event_html(d, it["agreed"], "agreed") + "<div class='ev'>unordered with: " + _esc(
            [(u["event_id"], u["action"], [(t["earliest"], t["latest"]) for t in u["time"]]) for u in it["unordered_with"]][:20]) + "</div>"
    if k in ("unresolved_role", "platform_recode"):
        return _event_html(d, it["agreed"], "agreed") + (_event_html(d, it.get("coder_b"), "coder B") if k == "platform_recode" else "")
    return _event_html(d, it.get("coder_a"), "coder A") + _event_html(d, it.get("coder_b"), "coder B")


def render_packet(release: str, cases=None) -> Path:
    dossiers = _dossiers(release, cases)
    total = sum(len(d["items"]) for d in dossiers.values())
    parts = [f"""<!doctype html><html><head><meta charset='utf-8'><title>Adjudication: {_esc(release)}</title>
<style>body{{font:14px/1.45 system-ui,sans-serif;margin:24px auto;max-width:1100px;padding:0 16px}}h2{{margin-top:40px}}
.bar{{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:10px 0;z-index:2;display:flex;gap:14px;align-items:center;flex-wrap:wrap}}
.item{{border:1px solid #ccc;border-radius:6px;padding:12px;margin:12px 0}}.item.done{{border-color:#2a7;background:#f6fbf8}}
.item.defer{{border-color:#c80}}.ev{{background:#f6f6f6;padding:8px;margin:6px 0}}.ev.none{{color:#777}}.k{{color:#666;font-size:12px}}
blockquote{{margin:4px 0 4px 16px;color:#333;font-style:italic}}.st{{font-size:12px;color:#555}}.warn{{color:#a00}}
.q{{font-weight:600}}select{{font-size:14px}}textarea{{width:100%;height:40px}}code{{font-size:12px}}</style></head><body>
<h1>Adjudication packet: {_esc(release)}</h1>
<p class='warn'><b>Internal only.</b> Quotes court records. Do not publish, commit or paste elsewhere.</p>
<p>Each choice is one that <code>python -m state_machines.coding.adjudication apply</code> carries out. <b>edit</b> means you change
<code>local/adjudication/{_esc(release)}/agreed/&lt;case&gt;.json</code> yourself before applying. <b>defer</b> blocks the release.
Choices are saved in this browser as you go. "Coder note" is the coder's own wording, never published.</p>
<div class='bar'><label>Reviewer <input id='reviewer' placeholder='name (kept local)'></label>
<span id='progress'></span><button onclick='exportAll()'>Export decisions</button>
<label>Import <input type='file' id='imp' accept='.json' multiple></label></div>"""]
    for case, d in dossiers.items():
        counts = ", ".join(f"{k} {n}" for k, n in sorted(d["counts"].items(), key=lambda kv: KIND_ORDER.index(kv[0])))
        parts.append(f"<h2 id='{_esc(case)}'>{_esc(case)} <span class='st'>{len(d['items'])} items: {_esc(counts)}</span></h2>")
        for it in sorted(d["items"], key=lambda i: (KIND_ORDER.index(i["kind"]), i["item_id"])):
            opts = "".join(f"<option>{_esc(o)}</option>" for o in [*it["options"], "defer"])
            parts.append(f"<div class='item' data-case='{_esc(case)}' data-id='{_esc(it['item_id'])}'><b>{_esc(it['item_id'])}</b>"
                         f"<p class='q'>{_esc(it['question'])}</p>{_item_body(d, it)}"
                         f"<label>Decision <select class='dec'><option></option>{opts}</select></label>"
                         f"<label>Note<textarea class='note'></textarea></label></div>")
    parts.append(f"""<script>
const KEY='adjudication:{_esc(release)}',TOTAL={total};
const store=()=>{{try{{return JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{return {{}}}}}};
function save(){{const s={{reviewer:document.getElementById('reviewer').value,decisions:{{}}}};
document.querySelectorAll('.item').forEach(el=>{{const d=el.querySelector('.dec').value,n=el.querySelector('.note').value;
el.classList.toggle('done',!!d&&d!=='defer');el.classList.toggle('defer',d==='defer');if(d||n)s.decisions[el.dataset.id]={{decision:d,note:n}};}});
try{{localStorage.setItem(KEY,JSON.stringify(s))}}catch(e){{}}
const done=Object.values(s.decisions).filter(x=>x.decision&&x.decision!=='defer').length;
document.getElementById('progress').textContent=done+' of '+TOTAL+' decided';}}
function load(s){{if(s.reviewer)document.getElementById('reviewer').value=s.reviewer;
document.querySelectorAll('.item').forEach(el=>{{const x=(s.decisions||{{}})[el.dataset.id];if(x){{el.querySelector('.dec').value=x.decision||'';el.querySelector('.note').value=x.note||'';}}}});save();}}
function exportAll(){{save();const s=store(),by={{}};
document.querySelectorAll('.item').forEach(el=>{{const c=el.dataset.case;by[c]=by[c]||{{reviewer:s.reviewer,exported:new Date().toISOString(),decisions:{{}}}};
if(s.decisions[el.dataset.id])by[c].decisions[el.dataset.id]=s.decisions[el.dataset.id];}});
Object.entries(by).forEach(([c,o])=>{{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(o,null,1)],{{type:'application/json'}}));
a.download=c+'.decisions.json';a.click();}});}}
document.getElementById('imp').addEventListener('change',e=>{{[...e.target.files].forEach(f=>f.text().then(t=>{{const o=JSON.parse(t),s=store();
s.reviewer=s.reviewer||o.reviewer;s.decisions=Object.assign(s.decisions||{{}},o.decisions||{{}});load(s);}}));}});
document.addEventListener('change',save);document.addEventListener('input',e=>{{if(e.target.id==='reviewer'||e.target.classList.contains('note'))save();}});
load(store());
</script></body></html>""")
    out = LOCAL / release / "packet.html"
    out.write_text("".join(parts), encoding="utf-8")
    return out


_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
NGRAM = 4


def _source_ngrams(cases) -> set:
    grams = set()
    for c in cases:
        for q in E.load_quotes(c).values():
            words = [w.lower() for w in _WORD.findall(q)]
            grams |= {tuple(words[i:i + NGRAM]) for i in range(len(words) - NGRAM + 1)}
    return grams


def _redact(text: str, grams: set) -> str:
    """Replace every run of words that reproduces >= NGRAM consecutive words of a court-record
    quote with [quote]. Matching is on the stored quotes themselves, not on quote marks."""
    toks = list(_WORD.finditer(text))
    words = [t.group(0).lower() for t in toks]
    covered = [False] * len(toks)
    for i in range(len(toks) - NGRAM + 1):
        if tuple(words[i:i + NGRAM]) in grams:
            for k in range(i, i + NGRAM):
                covered[k] = True
    out, pos, i = [], 0, 0
    while i < len(toks):
        if covered[i]:
            j = i
            while j + 1 < len(toks) and covered[j + 1]:
                j += 1
            out.append(text[pos:toks[i].start()] + "[quote]")
            pos, i = toks[j].end(), j + 1
        else:
            i += 1
    return "".join(out) + text[pos:]


def render_summary(release: str, cases=None) -> Path:
    """Counts only: items per case and kind, and decisions once decision files exist. No text."""
    dossiers = _dossiers(release, cases)
    L = [f"# Adjudication: {release}", "",
         "Counts of the items a named reviewer decided for each case of this release. The items, their passages and the "
         "decisions themselves stay local (`local/adjudication/`), because they quote the court records.", "",
         "| case | items | decided | deferred or open |", "|---|---:|---:|---:|"]
    by_kind, by_choice = Counter(), Counter()
    for c, d in dossiers.items():
        f = LOCAL / release / f"{c}.decisions.json"
        chosen = json.loads(f.read_text(encoding="utf-8")).get("decisions", {}) if f.is_file() else {}
        decided = 0
        for it in d["items"]:
            by_kind[it["kind"]] += 1
            x = (chosen.get(it["item_id"]) or {}).get("decision", "")
            if x in it["options"]:
                decided += 1
                by_choice[(it["kind"], x)] += 1
        L.append(f"| `{c}` | {len(d['items'])} | {decided} | {len(d['items']) - decided} |")
    L += ["", "| kind | items | decisions |", "|---|---:|---|"]
    for k in KIND_ORDER:
        if by_kind[k]:
            L.append(f"| `{k}` | {by_kind[k]} | " + ", ".join(f"{o} {by_choice[(k, o)]}" for o in OPTIONS[k] if by_choice[(k, o)]) + " |")
    out = DATA / release / "ADJUDICATION.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m state_machines.coding.adjudication_packet <release> [case ...]")
    rel = sys.argv[1]
    cases = sys.argv[2:] or None
    print(render_packet(rel, cases))
    print(render_summary(rel, cases))
