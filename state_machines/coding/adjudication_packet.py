"""Render the internal adjudication packet and the public adjudication summary.

    python -m state_machines.adjudication_packet <release>

Internal (gitignored; contains court-record quotes):
    local/adjudication/<release>/packet.html          one page, all cases: both codings, passages,
                                                      PDF page links, agent recommendation, agent
                                                      challenge, and a decision form that exports
                                                      decisions.json
Public (committed; no quotes, no names):
    trajectories/data/<release>/ADJUDICATION_SUMMARY.md

Agent recommendations and challenges are labelled as AI output. A decision exists only when a
named human reviewer records one in decisions.json; this module never writes decisions.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from state_machines.evidence import evidence as E
from state_machines.evidence import vocab as V
from state_machines.coding.workflow import PILOT_CASES, deny_list, source_root
from state_machines.evidence.validate import identifier_hits

LOCAL = E.REPO_ROOT / "local" / "adjudication"
DATA = E.REPO_ROOT / "state_machines" / "data"
KIND_ORDER = ["only_a", "only_b", "action_mismatch", "status_mismatch", "actor_mismatch", "affordance_mismatch",
              "harm_mismatch", "time_mismatch", "platform_recode", "order_only_a", "order_only_b", "single_step"]


def _load(release: str):
    rec = json.loads((LOCAL / release / "recommendations.json").read_text())
    recs = {i["item_id"]: i for r in rec["results"] for i in r["items"]}
    vers = {v["item_id"]: v for r in rec["results"] for v in r["verdicts"]}
    rulings = rec["rulings"]["rulings"] if isinstance(rec["rulings"], dict) else rec["rulings"]
    dossiers = {c: json.loads((LOCAL / release / f"{c}.dossier.json").read_text()) for c in PILOT_CASES
                if (LOCAL / release / f"{c}.dossier.json").is_file()}
    return recs, vers, rulings, dossiers


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _pdf_href(dossier: dict, doc_id: str, page: int) -> str:
    doc = next((d for d in dossier["documents"] if d["doc_id"] == doc_id), None)
    if not doc:
        return ""
    return "file://" + str(source_root() / doc["source_path"]).replace(" ", "%20") + f"#page={page}"


def _event_html(dossier: dict, view: Optional[dict], who: str) -> str:
    if not view:
        return f"<div class='ev none'><b>{who}</b>: not coded</div>"
    rows = "".join(
        f"<li><a href='{_esc(_pdf_href(dossier, p['doc_id'], p['pdf_page']))}'>{_esc(p['doc_id'])} p{p['pdf_page']}</a>"
        f" {_esc(p.get('court_locator') or '')} <span class='st'>{_esc(p['source_status'])}</span>"
        f"<blockquote>{_esc(p.get('quote'))}</blockquote></li>" for p in view.get("passages", []))
    return (f"<div class='ev'><b>{who}</b> <code>{_esc(view['event_id'])}</code> {_esc(view['actor'])} "
            f"<b>{_esc(view['action'])}</b> [{_esc(view['status'])}, {_esc(view['outcome'])}] "
            f"time {_esc(view['time'])}<br>{_esc(view['description'])}"
            f"<br>affordances {_esc(view['affordances'])} harms {_esc(view['harms'])} platforms {_esc(view['platform_mentions'])}"
            f"<br>tracks {_esc(view['tracks'])}<ul>{rows}</ul></div>")


def render_packet(release: str) -> Path:
    recs, vers, rulings, dossiers = _load(release)
    parts = ["""<!doctype html><html><head><meta charset='utf-8'><title>Adjudication packet</title>
<style>body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:1200px}h2{margin-top:40px}
.item{border:1px solid #ccc;border-radius:6px;padding:12px;margin:12px 0}.ev{background:#f6f6f6;padding:8px;margin:6px 0}
.ev.none{color:#777}blockquote{margin:4px 0 4px 16px;color:#333;font-style:italic}.agent{background:#eef3ff;padding:8px;margin:6px 0}
.chal{background:#fff4e5;padding:8px;margin:6px 0}.st{font-size:12px;color:#555}.warn{color:#a00}
label{display:block;margin-top:6px}textarea{width:100%;height:48px}code{font-size:12px}</style></head><body>
<h1>Internal adjudication packet</h1>
<p class='warn'><b>Internal only.</b> Contains quotations from court records. Do not publish, commit or paste elsewhere.</p>
<p><b>Agent output is not a decision.</b> "Agent recommendation" and "Agent challenge" were produced by AI agents (claude-opus-5-5)
reading the page text; they are not independent human reviewers. Record decisions in the form; use "Export decisions" to save
<code>decisions.json</code> beside this file.</p>
<label>Reviewer <input id='reviewer' placeholder='name or initials (kept local)'></label>
<button onclick='exportDecisions()'>Export decisions</button>
<h2>Cross-case rulings (codebook)</h2>"""]
    for r in rulings:
        parts.append(f"<div class='item' data-id='{_esc(r['question_id'])}'><b>{_esc(r['question_id'])}</b> {_esc(r['question'])}"
                     f"<ol>{''.join(f'<li>{_esc(o)}</li>' for o in r['options'])}</ol>"
                     f"<div class='agent'><b>Agent recommendation:</b> {_esc(r['recommended'])}<br>{_esc(r['reason'])}"
                     f"<br><span class='st'>affects {len(r['affected_items'])} items; evidence {_esc(', '.join(r['evidence_locators']))}</span></div>"
                     "<label>Decision <select class='dec'><option></option><option>accept recommendation</option><option>choose other option</option><option>defer</option></select></label>"
                     "<label>Ruling / note<textarea class='note'></textarea></label></div>")
    for case, d in dossiers.items():
        parts.append(f"<h2>{_esc(case)}</h2><p>{_esc(d['counts'])}</p>")
        items = sorted(d["items"], key=lambda i: (KIND_ORDER.index(i["kind"]), i["item_id"]))
        for it in items:
            rec, ver = recs.get(it["item_id"], {}), vers.get(it["item_id"], {})
            body = []
            if it["kind"] in ("order_only_a", "order_only_b"):
                body.append(_event_html(d, it["from_event"], "from"))
                body.append(_event_html(d, it["to_event"], "to"))
                body.append(f"<div class='ev'>relation {_esc(it['relation']['type'])} [{_esc(it['relation']['status'])}, {_esc(it['relation']['basis'])}]"
                            f"<ul>{''.join(f'<li>{_esc(s[chr(100)+chr(111)+chr(99)+chr(95)+chr(105)+chr(100)])} p{s[chr(112)+chr(100)+chr(102)+chr(95)+chr(112)+chr(97)+chr(103)+chr(101)]}<blockquote>{_esc(s.get(chr(113)+chr(117)+chr(111)+chr(116)+chr(101)))}</blockquote></li>' for s in it['support'])}</ul></div>")
            elif it["kind"] == "single_step":
                body.append(_event_html(d, it["event"], "agreed event"))
                body.append(f"<div class='ev'>unordered with: {_esc([(u['event_id'], u['action'], u['time']) for u in it['unordered_with']][:15])}</div>")
            else:
                body.append(_event_html(d, it.get("coder_a"), "coder A"))
                body.append(_event_html(d, it.get("coder_b"), "coder B"))
            parts.append(
                f"<div class='item' data-id='{_esc(it['item_id'])}'><b>{_esc(it['item_id'])}</b> <i>{_esc(it['kind'])}</i>"
                + "".join(body)
                + f"<div class='agent'><b>Agent recommendation:</b> {_esc(rec.get('recommendation'))} ({_esc(rec.get('confidence'))})"
                  f"<br>{_esc(rec.get('proposed_coding'))}<br><i>{_esc(rec.get('reason'))}</i>"
                  f"<br><span class='st'>{_esc(', '.join(rec.get('evidence_locators', [])))} {_esc(rec.get('single_step_cause') if it['kind']=='single_step' else '')}</span>"
                  f"{('<br><b>Codebook question:</b> ' + _esc(rec['codebook_question'])) if rec.get('codebook_question') else ''}</div>"
                + f"<div class='chal'><b>Agent challenge:</b> {_esc(ver.get('verdict'))} {_esc(ver.get('problem'))}"
                  f"{('<br><b>Alternative:</b> ' + _esc(ver['alternative'])) if ver.get('alternative') else ''}</div>"
                + "<label>Decision <select class='dec'><option></option><option>accept recommendation</option><option>accept challenge alternative</option>"
                  "<option>accept coder A</option><option>accept coder B</option><option>other (see note)</option><option>defer</option></select></label>"
                  "<label>Coding / note<textarea class='note'></textarea></label></div>")
    parts.append("""<script>
function exportDecisions(){const out={reviewer:document.getElementById('reviewer').value,exported:new Date().toISOString(),decisions:{}};
document.querySelectorAll('.item').forEach(el=>{const d=el.querySelector('.dec').value,n=el.querySelector('.note').value;
if(d||n)out.decisions[el.dataset.id]={decision:d,note:n};});
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{type:'application/json'}));
a.download='decisions.json';a.click();}
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


def render_summary(release: str) -> Path:
    recs, vers, rulings, dossiers = _load(release)
    deny = sorted({w for c in dossiers for w in deny_list(c)})
    L = [f"# Pilot adjudication summary: {release}", "",
         "**Status: awaiting human review.** Nothing below is a decision.",
         "",
         "- **Agent output:** every recommendation and challenge was produced by AI agents (claude-opus-5-5) reading the page text. They are not independent human reviewers.",
         "- **Decisions:** the author records them in the internal packet (`local/adjudication/<release>/packet.html`, gitignored because it quotes the court records).",
         "- **Privacy:** this summary holds no quotations and no personal identifiers.", ""]
    total = sum(len(d["items"]) for d in dossiers.values())
    kinds = Counter(i["kind"] for d in dossiers.values() for i in d["items"])
    L += [f"## Items: {total} across {len(dossiers)} cases", "", "| kind | count |", "|---|---:|"]
    L += [f"| {k} | {kinds[k]} |" for k in KIND_ORDER if kinds[k]]
    rc = Counter(i["recommendation"] for i in recs.values())
    vc = Counter(v["verdict"] for v in vers.values())
    L += ["", "## Agent recommendations and challenges", "",
          "| recommendation | count |", "|---|---:|"] + [f"| {k} | {n} |" for k, n in rc.most_common()]
    L += ["", f"Challenge verdicts: upheld {vc.get('upheld', 0)}, partly refuted {vc.get('partly_refuted', 0)}, refuted {vc.get('refuted', 0)}. "
          "Every partly refuted or refuted item needs a human decision. Upheld items still need one; the agreement of two agents is not verification."]
    per_case = defaultdict(Counter)
    for k, v in vers.items():
        per_case[k.split(".")[0]][v["verdict"]] += 1
    L += ["", "| case | items | upheld | partly refuted | refuted |", "|---|---:|---:|---:|---:|"]
    for c, d in dossiers.items():
        pc = per_case[c]
        L.append(f"| `{c}` | {len(d['items'])} | {pc['upheld']} | {pc['partly_refuted']} | {pc['refuted']} |")
    ss = defaultdict(Counter)
    for k, i in recs.items():
        if ".single_step." in k:
            ss[k.split(".")[0]][i["single_step_cause"]] += 1
    causes = ["unrecognized_explicit_ordering", "incomplete_source_chronology", "event_fragmentation", "matching_error", "genuine_parallel_or_unrelated"]
    L += ["", "## Why agreed trajectories have one step (agent diagnosis, pending review)", "",
          "| case | " + " | ".join(causes) + " |", "|---|" + "---:|" * len(causes)]
    for c in dossiers:
        L.append(f"| `{c}` | " + " | ".join(str(ss[c][x]) for x in causes) + " |")
    L += ["",
          "- **`unrecognized_explicit_ordering`:** a cited passage orders the event, but neither coder coded the relation. Each such recommendation names the passage.",
          "- **`incomplete_source_chronology`:** the documents give no order. These stay unordered.",
          "- **No order was added automatically.** `add_order` recommendations are proposals only."]
    grams = _source_ngrams(dossiers)
    L += ["", "## Cross-case codebook rulings for the author", "",
          f"Any run of {NGRAM}+ words that reproduces a court-record quote is replaced by `[quote]`; the internal packet has them.", ""]
    for r in rulings:
        L += [f"### {r['question_id']}", "", _redact(r["question"], grams), ""] + [f"- {_redact(o, grams)}" for o in r["options"]] + \
             ["", f"**Agent recommendation:** {_redact(r['recommended'], grams)}", "", _redact(r["reason"], grams), "",
              f"Affects {len(r['affected_items'])} items. Evidence: {', '.join(r['evidence_locators'])}.", ""]
    text = "\n".join(L) + "\n"
    leaked = [g for g in _source_ngrams(dossiers) if " ".join(g) in " ".join(w.lower() for w in _WORD.findall(text))]
    if leaked:
        raise SystemExit(f"summary blocked: {len(leaked)} verbatim source 4-grams remain")
    # Our own identifiers (case ids, ruling ids, page tokens, document ids, codes) have the shape
    # of handles; remove exactly those before scanning, so the guard still catches real ones.
    safe = set(dossiers) | {r["question_id"] for r in rulings} | set(V.ACTION_CODES) | set(V.HARM_CODES) | \
        set(V.AFFORDANCES) | {doc["doc_id"] for d in dossiers.values() for doc in d["documents"]}
    scan = re.sub(r"\bp\d{4}\b", " ", text)
    for tok in sorted(safe, key=len, reverse=True):
        scan = scan.replace(tok, " ")
    hits = identifier_hits(scan, deny)
    if hits:
        raise SystemExit(f"summary blocked: possible identifiers {sorted(set(hits))}")
    out = DATA / release / "ADJUDICATION_SUMMARY.md"
    out.write_text(text, encoding="utf-8")
    return out


if __name__ == "__main__":
    rel = sys.argv[1] if len(sys.argv) > 1 else "pilot-v0"
    print(render_packet(rel))
    print(render_summary(rel))
