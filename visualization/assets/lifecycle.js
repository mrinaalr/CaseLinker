/* /lifecycle: documented PACER event graphs, derived trajectories, and the formal model.
   Data: <script id="lifecycle-payload"> embedded server-side (state_machines/trajectories/payload.py).
   Columns follow documented order only; nothing here is a probability, phase or estimated path. */
(function () {
  "use strict";

  const SVGNS = "http://www.w3.org/2000/svg";
  const REPO = "https://github.com/mrinaalr/CaseLinker/blob/main/";
  const AFF = {
    anonymity: { color: "#c4a1ff", label: "Anonymity" },
    ephemerality: { color: "#f5c46b", label: "Ephemerality" },
    contact_discovery: { color: "#7cb7ff", label: "Contact discovery" },
    unmonitored_communication: { color: "#5fd4a4", label: "Unmonitored comm." },
    distribution_infrastructure: { color: "#ff8a7a", label: "Distribution infra." },
    generative_synthesis: { color: "#f39ac7", label: "Generative synthesis" },
  };
  const STANDING = {
    ALLEGATION: "allegation", SWORN_AFFIDAVIT: "affidavit", ADMITTED: "admitted",
    ADMITTED_UNDER_OATH: "admitted", JUDICIAL_FINDING: "finding", VERDICT_ELEMENT: "verdict",
    COURT_RECORD: "record", ADVOCACY: "advocacy", PROCEDURAL: "docket",
  };
  const TRACK_KIND = { victim: "Victim track", undercover: "Undercover persona", material: "Material",
    co_offender_network: "Co-offender network", case_procedure: "Case procedure" };
  const NODE = { w: 190, h: 64, hc: 40, col: 226, row: 80, pad: 22, head: 70 };

  const state = { payload: null, caseIdx: 0, view: "documented", threshold: "INFERRED", context: true };

  // ---------- helpers ----------
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v);
    }
    kids.flat().forEach(k => k != null && n.append(k));
    return n;
  };
  const sv = (tag, attrs = {}) => {
    const n = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };
  const svText = (attrs, text) => { const t = sv("text", attrs); t.textContent = text; return t; };
  const tex = (src, display = false) => {
    const span = el("span", { class: display ? "eq" : "m" });
    if (window.katex) window.katex.render(src, span, { displayMode: display, throwOnError: false });
    else span.textContent = src;
    return span;
  };
  const admissible = s => (state.threshold === "DIRECT" ? s === "DIRECT" : s === "DIRECT" || s === "INFERRED");
  const shortDate = ev => {
    const t = ev.time.filter(a => admissible(a.status));
    if (!t.length) return ev.time.length ? "date inferred" : "undated";
    const a = t[0];
    const d = a.precision === "day" ? a.earliest : a.precision === "month" ? a.earliest.slice(0, 7)
      : a.precision === "year" ? a.earliest.slice(0, 4) : `${a.earliest.slice(0, 7)}…${a.latest.slice(0, 7)}`;
    return (a.basis === "enclosing_window" ? "≈" : "") + d + (ev.time_conflict ? " ⚠" : "");
  };
  const roleLine = ev => {
    const t = ev.targets.map(x => `${x.participant_ref} ${x.role}`).join(", ");
    return `${ev.actor.participant_ref} ${ev.actor.role.replace("_", "-")}` + (t ? ` → ${t}` : "");
  };
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  // ---------- documented order within one track ----------
  function trackOrder(cs, track, shown) {
    const ids = new Set(track.events);
    const adj = new Map(track.events.map(e => [e, new Set()]));
    const kinds = new Map();
    for (const r of cs.relations) {
      if ((r.type === "BEFORE" || r.type === "MEETS") && admissible(r.status) && ids.has(r.from) && ids.has(r.to)) {
        adj.get(r.from).add(r.to);
        kinds.set(r.from + ">" + r.to, r.type === "MEETS" ? "meets" : r.status === "DIRECT" ? "direct" : "inferred");
      }
    }
    for (const [a, b] of (track.views[state.threshold] || {}).date_order || []) {
      if (!adj.get(a).has(b)) { adj.get(a).add(b); kinds.set(a + ">" + b, "date"); }
    }
    const reach = new Map();
    const visit = (n, seen) => { for (const m of adj.get(n)) if (!seen.has(m)) { seen.add(m); visit(m, seen); } return seen; };
    track.events.forEach(e => reach.set(e, visit(e, new Set())));
    const less = (a, b) => reach.get(a).has(b);
    const vis = track.events.filter(e => shown.has(e));
    const ordered = vis.filter(a => vis.some(b => b !== a && (less(a, b) || less(b, a))));
    const loose = vis.filter(a => !ordered.includes(a));
    const cover = [];   // covering pairs among shown events: a < b with no shown c between
    for (const a of ordered) for (const b of ordered) {
      if (a !== b && less(a, b) && !ordered.some(c => c !== a && c !== b && less(a, c) && less(c, b))) {
        cover.push({ from: a, to: b, kind: kinds.get(a + ">" + b) || "transitive" });
      }
    }
    const rank = new Map();
    const rk = a => {
      if (rank.has(a)) return rank.get(a);
      const preds = ordered.filter(p => less(p, a));
      const r = preds.length ? 1 + Math.max(...preds.map(rk)) : 0;
      rank.set(a, r);
      return r;
    };
    ordered.forEach(rk);
    return { ordered, loose, cover, rank };
  }

  // ---------- documented view ----------
  function renderDocumented() {
    const cs = state.payload.cases[state.caseIdx];
    const host = document.getElementById("doc-canvas");
    host.innerHTML = "";
    if (!cs) { host.append(el("div", { class: "lifecycle-loading", text: "No PACER release is published yet." })); return; }
    const lanes = [];
    let width = 0, y = 0;
    for (const track of cs.tracks) {
      const shown = new Set(track.events.filter(id => state.context || cs.events[id].family === "offender"));
      if (!shown.size) continue;
      const o = trackOrder(cs, track, shown);
      const cols = new Map();
      o.ordered.forEach(id => { const r = o.rank.get(id); if (!cols.has(r)) cols.set(r, []); cols.get(r).push(id); });
      const key = id => (cs.events[id].time[0] || {}).earliest || "9999";
      cols.forEach(list => list.sort((a, b) => key(a).localeCompare(key(b)) || a.localeCompare(b)));
      const nCols = cols.size ? Math.max(...cols.keys()) + 1 : 0;
      const looseRows = Math.min(3, o.loose.length);
      const looseCols = Math.ceil(o.loose.length / Math.max(1, looseRows));
      const rows = Math.max(1, looseRows, ...[...cols.values()].map(l => l.length));
      const h = NODE.head + rows * NODE.row + 6;
      const looseX = NODE.pad + nCols * NODE.col + (nCols ? 40 : 0);
      width = Math.max(width, looseX + looseCols * NODE.col + NODE.pad);
      lanes.push({ track, o, cols, y, h, looseX, looseRows });
      y += h + 14;
    }
    width = Math.max(width, 760);
    const svg = sv("svg", { class: "lifecycle-svg", width, height: y + 2 });
    const defs = sv("defs");
    for (const [id, color] of [["arr", "#c9d2cc"], ["arr-dim", "#7f8a82"], ["arr-int", "#ff8a7a"]]) {
      const m = sv("marker", { id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
      m.append(sv("path", { d: "M0,0 L10,5 L0,10 z", fill: color }));
      defs.append(m);
    }
    svg.append(defs);
    for (const lane of lanes) drawLane(svg, cs, lane, width);
    host.append(svg);
  }

  function drawLane(svg, cs, lane, width) {
    const { track, o, cols, y, h, looseX, looseRows } = lane;
    const g = sv("g", { transform: `translate(0,${y})` });
    g.append(sv("rect", { x: 0, y: 0, width, height: h, rx: 10, class: "lane-bg" }));
    const view = track.views[state.threshold] || {};
    g.append(svText({ x: 16, y: 22, class: "lane-title" }, `${TRACK_KIND[track.kind] || track.kind}${track.anchor ? " · " + track.anchor : ""}`));
    g.append(svText({ x: 16, y: 38, class: "lane-meta" }, `${track.events.length} events`));
    const pos = new Map();
    cols.forEach((list, r) => list.forEach((id, i) => pos.set(id, { x: NODE.pad + r * NODE.col, y: NODE.head + i * NODE.row })));
    o.loose.forEach((id, i) => pos.set(id, { x: looseX + Math.floor(i / looseRows) * NODE.col, y: NODE.head + (i % looseRows) * NODE.row }));
    if (o.loose.length) {
      g.append(sv("rect", { x: looseX - 12, y: NODE.head - 24, width: width - looseX + 2, height: h - NODE.head + 18, rx: 8, class: "loose-zone" }));
      g.append(svText({ x: looseX, y: NODE.head - 9, class: "loose-label" }, "ORDER NOT DOCUMENTED"));
    }
    const nh = id => (cs.events[id].family === "offender" ? NODE.h : NODE.hc);
    const edges = sv("g", { class: "edges" });
    for (const e of o.cover) {
      const a = pos.get(e.from), b = pos.get(e.to);
      const x1 = a.x + NODE.w, y1 = a.y + nh(e.from) / 2, x2 = b.x - 3, y2 = b.y + nh(e.to) / 2;
      const mx = (x1 + x2) / 2;
      edges.append(sv("path", { d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, class: `edge edge-${e.kind}`,
        "marker-end": e.kind === "date" || e.kind === "transitive" ? "url(#arr-dim)" : "url(#arr)" }));
    }
    for (const r of cs.relations) {
      const a = pos.get(r.from), b = pos.get(r.to);
      if (!a || !b || !admissible(r.status)) continue;
      if (r.type === "INTERRUPTS") {
        const ax = a.x + NODE.w / 2, bx = b.x + NODE.w / 2, low = Math.max(a.y + nh(r.from), b.y + nh(r.to)) + 14;
        edges.append(sv("path", { d: `M${ax},${a.y + nh(r.from)} C${ax},${low} ${bx},${low} ${bx},${b.y + nh(r.to) + 3}`,
          class: "edge edge-interrupt", "marker-end": "url(#arr-int)" }));
      } else if (r.type === "SAME_ACT" && r.status === "INFERRED") {
        edges.append(sv("line", { x1: a.x + NODE.w / 2, y1: a.y + nh(r.from) / 2, x2: b.x + NODE.w / 2, y2: b.y + nh(r.to) / 2, class: "edge edge-same" }));
      }
    }
    g.append(edges);
    for (const [id, p] of pos) g.append(drawNode(cs.events[id], p));
    svg.append(g);
  }

  function drawNode(ev, p) {
    const ctx = ev.family !== "offender";
    const h = ctx ? NODE.hc : NODE.h;
    const g = sv("g", { class: `node${ctx ? " node-ctx" : ""} node-${ev.status.toLowerCase()}`, transform: `translate(${p.x},${p.y})`, tabindex: 0, role: "button" });
    g.setAttribute("aria-label", `${ev.label}. ${roleLine(ev)}. Select for sources.`);
    g.append(sv("rect", { width: NODE.w, height: h, rx: 7, class: "node-box" }));
    const affs = ev.affordances.filter(a => admissible(a.status));
    g.append(svText({ x: 10, y: 17, class: "node-action" }, clip(ev.label.toUpperCase(), affs.length ? 22 - affs.length : 24)));
    affs.forEach((a, i) => g.append(sv("circle", { cx: NODE.w - 12 - i * 12, cy: 13, r: 4.5, fill: AFF[a.class].color,
      class: a.status === "DIRECT" ? "aff-dot" : "aff-dot aff-inferred" })));
    g.append(svText({ x: 10, y: 32, class: "node-roles" }, clip(roleLine(ev), 30)));
    if (!ctx) {
      const h0 = [...new Set(ev.harms.filter(x => x.h0 && x.victim_kind === "minor" && admissible(x.status)).map(x => x.h0))];
      const room = Math.floor((NODE.w - 18 - 24 * h0.length - (ev.unresolved.length ? 58 : 0)) / 6.2);  // 10px mono ≈ 6px/char
      g.append(svText({ x: 10, y: 53, class: "node-meta" }, clip(`${STANDING[ev.standing] || "—"} · ${shortDate(ev)}`, room)));
      let x = NODE.w - 8 - (ev.unresolved.length ? 54 : 0);
      for (const hm of h0.map(h => ({ h0: h }))) {
        x -= 22;
        g.append(sv("rect", { x, y: 42, width: 20, height: 14, rx: 3, class: "harm-tag" }));
        g.append(svText({ x: x + 10, y: 52.5, class: "harm-text", "text-anchor": "middle" }, hm.h0));
      }
    }
    if (ev.outcome !== "completed") {
      g.append(svText({ x: NODE.w - 8, y: ctx ? 32 : 32, class: "node-outcome", "text-anchor": "end" },
        ev.outcome.replace("_not_completed", "").replace(/_/g, " ")));
    }
    if (ev.unresolved.length) {
      g.append(svText({ x: NODE.w - 8, y: ctx ? h - 6 : 53, class: "node-unresolved", "text-anchor": "end" }, "role open"));
    }
    const open = () => showDetail(ev);
    g.addEventListener("click", open);
    g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    return g;
  }

  function renderLegend() {
    const host = document.getElementById("legend");
    host.innerHTML = "";
    const item = (sym, label) => el("span", { class: "legend-item" }, sym, label);
    host.append(
      el("div", { class: "legend-row" }, el("span", { class: "legend-head", text: "Event" }),
        item(el("i", { class: "box box-direct" }), "stated directly"),
        item(el("i", { class: "box box-inferred" }), "inferred"),
        item(el("i", { class: "box box-ctx" }), "response, law enforcement, court"),
        item(el("i", { class: "box box-harm", text: "h2" }), "harm to a minor (H₀)"),
        item(el("span", { class: "legend-mono", text: "admitted" }), "strongest legal standing of the cited passages")),
      el("div", { class: "legend-row" }, el("span", { class: "legend-head", text: "Order" }),
        [["direct", "stated in a passage"], ["inferred", "inferred"], ["meets", "immediately after"],
          ["date", "from cited dates"], ["interrupt", "interrupts"], ["same", "possibly the same act"]]
          .map(([k, l]) => item(el("i", { class: `line line-${k}` }), l))),
      el("div", { class: "legend-row" }, el("span", { class: "legend-head", text: "Affordance" }),
        Object.values(AFF).map(a => item(el("i", { class: "dot", style: `background:${a.color}` }), a.label))));
  }

  // ---------- derived view ----------
  function renderDerived() {
    const cs = state.payload.cases[state.caseIdx];
    const host = document.getElementById("derived");
    host.innerHTML = "";
    if (!cs) return;
    const affCase = new Set(), hCase = new Set();
    cs.tracks.forEach(t => ((t.views[state.threshold] || {}).aff || []).forEach(a => affCase.add(a)));
    Object.values(cs.events).forEach(e => e.harms.forEach(h => { if (h.h0 && h.victim_kind === "minor" && admissible(h.status)) hCase.add(h.h0); }));
    const pills = (xs, f) => (xs.length ? xs.map(f) : [el("span", { class: "cl-muted", text: "∅" })]);
    host.append(el("div", { class: "cl-card cl-card--pad sets" },
      el("div", { class: "set" }, tex("\\operatorname{Aff}(c)"),
        el("div", { class: "set-values" }, pills([...affCase].sort(), a => el("span", { class: "pill", style: `--c:${AFF[a].color}` }, AFF[a].label)))),
      el("div", { class: "set" }, tex("H(c)\\subseteq\\mathcal{H}_{0}"),
        el("div", { class: "set-values" }, pills([...hCase].sort(), x => el("span", { class: "pill pill-harm", text: x }))))));
    for (const t of cs.tracks) {
      const v = t.views[state.threshold];
      if (!v || !v.chains.length) continue;
      const body = el("div", { class: "cl-card__body" });
      v.chains.slice(0, 10).forEach((chain, i) => {
        const steps = chain.map(id => {
          const ev = cs.events[id];
          return el("span", { class: "step" }, ev.label, ev.affordances.filter(a => admissible(a.status))
            .map(a => el("i", { class: "dot", style: `background:${AFF[a.class].color}`, title: AFF[a.class].label })));
        });
        const aff = new Set(chain.flatMap(id => cs.events[id].affordances.filter(a => admissible(a.status)).map(a => a.class)));
        body.append(el("div", { class: "chain" }, el("span", { class: "chain-id", text: `L${i + 1}` }),
          el("div", { class: "chain-steps" }, steps.flatMap((s, k) => (k ? [el("span", { class: "chain-arrow", text: "→" }), s] : [s]))),
          el("span", { class: "chain-aff", text: aff.size ? [...aff].map(a => AFF[a].label).join(" · ") : "∅" })));
      });
      if (v.chains.length > 10) body.append(el("div", { class: "cl-muted cl-small more", text: `+ ${v.chains.length - 10} more chains` }));
      host.append(el("div", { class: "cl-card chain-card" },
        el("div", { class: "cl-card__head" },
          el("div", { class: "cl-card__title", text: `${TRACK_KIND[t.kind] || t.kind}${t.anchor ? " · " + t.anchor : ""}` }),
          el("span", { class: "cl-muted cl-small", text: `${v.chains.length} chains${v.truncated ? " (truncated)" : ""} · ${v.unordered_pairs} unordered pairs` })),
        body));
    }
  }

  // ---------- theory view ----------
  function renderTheory() {
    const host = document.getElementById("theory");
    if (host.dataset.done) return;
    host.dataset.done = "1";
    const row = (label, src, note) => el("div", { class: "eq-row" }, el("div", { class: "eq-label", text: label }), tex(src, true),
      note ? el("p", { class: "eq-note", text: note }) : null);
    host.append(
      el("div", { class: "cl-card cl-card--pad" },
        el("div", { class: "cl-eyebrow", text: "TRAJECTORIES AND HARMS · COMPUTED FROM THE RECORD" }),
        row("Trajectory", "L=((a_{1},O_{1}),\\ldots,(a_{n},O_{n})),\\quad a_{i}\\in\\mathcal{A},\\; O_{i}\\subseteq\\mathcal{O}(P)",
          "On this page: a maximal chain of the documented order, with Oᵢ the affordances the record ties to the act."),
        row("Associated affordances", "\\operatorname{Aff}(L)=\\bigcup_{i=1}^{n} O_{i}"),
        row("Affordance–harm association", "\\psi_{\\mathcal{C}}(o)=\\{h\\in\\mathcal{H}_{0}:\\exists c\\in\\mathcal{C},\\; o\\in\\operatorname{Aff}(c)\\wedge h\\in H(c)\\}",
          "Co-occurrence within a case."),
        row("Coverage identity", "\\bigcup_{o\\in\\mathcal{O}}\\psi_{\\mathcal{C}}(o)=\\bigcup_{c\\in\\mathcal{C},\\,\\operatorname{Aff}(c)\\neq\\varnothing} H(c)\\subseteq\\mathcal{H}_{\\mathcal{C}}")),
      el("div", { class: "cl-card cl-card--pad" },
        el("div", { class: "cl-eyebrow", text: "STATE-SPACE CONSTRUCTION · APPENDIX X" }),
        row("Model", "M_{P}=(S,\\mathcal{A},\\mathcal{O}(P),T_{P},s_{0}),\\qquad T_{P}\\subseteq S\\times\\mathcal{A}\\times 2^{\\mathcal{O}(P)}\\times S",
          "Transitions are possibilities under stated assumptions; they carry no probabilities."),
        row("Feasible trajectories", "\\mathcal{L}(P)=\\{\\varepsilon(r): r\\text{ a finite run of }M_{P}\\text{ from }s_{0}\\}"),
        row("New pathways", "\\Delta_{\\mathrm{path}}(o;P)=\\pi(\\mathcal{L}(P\\oplus o))\\setminus\\pi(\\mathcal{L}(P))"),
        row("New support", "\\Delta_{\\mathrm{supp}}(o;P)=\\{L\\in\\mathcal{L}(P\\oplus o):\\pi(L)\\in\\pi(\\mathcal{L}(P)),\\; o\\in\\operatorname{Aff}(L)\\}"),
        toyDiagram(),
        el("p", { class: "eq-note" }, "The worked comparison from Appendix X. Adding ephemerality to the request gives existing sequences new support, ",
          tex("\\Delta_{\\mathrm{path}}(e;P)=\\varnothing"), "; adding generative synthesis opens a sequence with no contact, ",
          tex("(\\text{synthesize})\\in\\Delta_{\\mathrm{path}}(g;P)"), ". Documented trajectories are checked for compatibility with a specified model.")),
      el("div", { class: "theory-links" },
        el("a", { href: REPO + "state_machines/README.md", target: "_blank", rel: "noopener", text: "State machines README" }),
        el("a", { href: REPO + "state_machines/theory/README.md", target: "_blank", rel: "noopener", text: "Theory README" }),
        el("a", { href: REPO + "state_machines/evidence/CODEBOOK.md", target: "_blank", rel: "noopener", text: "Codebook" })));
  }

  function toyDiagram() {
    const svg = sv("svg", { viewBox: "0 0 660 250", class: "toy", role: "img", "aria-label": "Appendix X toy transition system" });
    const defs = sv("defs");
    const m = sv("marker", { id: "toyarr", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto" });
    m.append(sv("path", { d: "M0,0 L10,5 L0,10 z", class: "toy-head" }));
    defs.append(m);
    svg.append(defs);
    const edge = (d, cls) => svg.append(sv("path", { d, class: `toy-edge ${cls}`, "marker-end": "url(#toyarr)" }));
    const label = (x, y, text, cls, anchor = "middle") => svg.append(svText({ x, y, class: `toy-label ${cls}`, "text-anchor": anchor }, text));
    edge("M84,170 L274,170", "");
    edge("M324,162 L534,114", "");
    edge("M324,178 L534,220", "");
    edge("M314,150 C370,92 470,88 536,102", "toy-e");
    edge("M76,150 C170,28 460,22 540,94", "toy-g");
    label(180, 160, "contact · contact discovery", "");
    label(422, 120, "request · private messaging", "");
    label(410, 224, "request refused", "");
    label(430, 84, "request · + ephemerality", "toy-e");
    label(312, 40, "synthesize · generative synthesis", "toy-g");
    for (const [id, x, y, desc] of [["s₀", 60, 170, "image accessible"], ["s₁", 300, 170, "channel"], ["s₂", 560, 106, "material obtained"], ["s₃", 560, 226, "refused"]]) {
      svg.append(sv("circle", { cx: x, cy: y, r: 22, class: "toy-state" }));
      svg.append(svText({ x, y: y + 5, class: "toy-id", "text-anchor": "middle" }, id));
      svg.append(svText({ x, y: y + (y > 200 ? -30 : 38), class: "toy-desc", "text-anchor": "middle" }, desc));
    }
    return svg;
  }

  // ---------- detail panel ----------
  function showDetail(ev) {
    const panel = document.getElementById("detail-panel");
    const back = document.getElementById("detail-backdrop");
    const kv = (k, v) => el("div", { class: "kv" }, el("span", { class: "k", text: k }), el("span", { class: "v", text: v }));
    const when = ev.time.length
      ? ev.time.map(a => `${a.earliest === a.latest ? a.earliest : a.earliest + " – " + a.latest} (${a.precision}, ${a.basis.replace(/_/g, " ")}, ${a.status.toLowerCase()})`).join("; ") + (ev.time_conflict ? "; dates conflict" : "")
      : "undated";
    panel.innerHTML = "";
    panel.append(
      el("button", { class: "detail-close", type: "button", "aria-label": "Close", text: "×" }),
      el("div", { class: "cl-eyebrow", text: `${ev.id} · ${ev.family} action` }),
      el("h3", { class: "detail-title", text: ev.label }),
      kv("Evidence", `${ev.status.toLowerCase()} · strongest standing ${STANDING[ev.standing] || "—"} · ${ev.review}`),
      kv("Actor", `${ev.actor.participant_ref} (${ev.actor.role})`),
      ev.co_actors.length ? kv("With", ev.co_actors.map(c => `${c.participant_ref} (${c.role}, ${c.mode})`).join("; ")) : null,
      ev.targets.length ? kv("Targets", ev.targets.map(t => `${t.participant_ref} (${t.role})`).join("; ")) : null,
      ev.unresolved.length ? kv("Role open", `${ev.unresolved.join(", ")}: decided in adjudication`) : null,
      kv("Outcome", ev.outcome.replace(/_/g, " ")),
      kv("When", when),
      ev.affordances.length ? kv("Affordances", ev.affordances.map(a => `${AFF[a.class].label} (${a.basis.replace("_", " ")}, ${a.status.toLowerCase()})`).join("; ")) : null,
      ev.harms.length ? kv("Harms", ev.harms.map(h => `${h.code.replace("HARM_", "").replace(/_/g, " ").toLowerCase()}${h.h0 ? " · " + h.h0 : ""} (${h.victim_kind}, ${h.status.toLowerCase()})`).join("; ")) : null,
      ev.platforms.length ? kv("Platforms", ev.platforms.map(p => `${p.key} (${p.mode}, ${p.audience})`).join("; ")) : null,
      ev.mentions.length ? kv("Named", ev.mentions.join(", ")) : null,
      el("div", { class: "detail-sub", text: "Sources" }),
      el("ul", { class: "prov" }, ev.provenance.map(p => el("li", { text: `${p.doc_type.replace(/_/g, " ")}, page ${p.page} · ${STANDING[p.standing] || p.standing} · ${p.verification.toLowerCase()}` }))));
    panel.setAttribute("aria-hidden", "false");
    panel.classList.add("is-open");
    back.classList.add("is-open");
    const close = () => { panel.classList.remove("is-open"); back.classList.remove("is-open"); panel.setAttribute("aria-hidden", "true"); };
    panel.querySelector(".detail-close").addEventListener("click", close);
    back.onclick = close;
    document.addEventListener("keydown", e => { if (e.key === "Escape") close(); }, { once: true });
  }

  // ---------- shell ----------
  function renderStats() {
    const p = state.payload;
    const cs = p.cases;
    const sum = k => cs.reduce((n, c) => n + c.summary[k], 0);
    document.getElementById("lede").textContent = cs.length ? `${cs.length} federal cases · ${sum("events")} documented events` : "";
    const banner = document.getElementById("release-banner");
    if (p.release) {
      banner.hidden = false;
      banner.className = "release-banner " + (p.release.adjudicated ? "is-ok" : "is-preview");
      banner.textContent = p.release.adjudicated ? "Adjudicated" : "Preview · not yet adjudicated";
      banner.title = `${p.release.id} · schema ${p.release.schema_version} · codebook ${p.release.codebook_version}`;
    }
  }

  function renderChips() {
    const host = document.getElementById("case-chips");
    host.innerHTML = "";
    state.payload.cases.forEach((c, i) => {
      const b = el("button", { type: "button", class: "case-chip", "aria-pressed": String(i === state.caseIdx), text: c.case_id });
      b.addEventListener("click", () => { state.caseIdx = i; renderChips(); render(); });
      host.append(b);
    });
  }

  function render() {
    for (const v of ["documented", "derived", "theory"]) document.getElementById("view-" + v).hidden = state.view !== v;
    document.getElementById("threshold").hidden = state.view === "theory";
    document.getElementById("case-chips").parentElement.classList.toggle("is-theory", state.view === "theory");
    if (state.view === "documented") renderDocumented();
    if (state.view === "derived") renderDerived();
    if (state.view === "theory") renderTheory();
  }

  function wire() {
    document.querySelectorAll("#view-tabs button").forEach(b => b.addEventListener("click", () => {
      state.view = b.dataset.view;
      document.querySelectorAll("#view-tabs button").forEach(x => x.setAttribute("aria-selected", String(x === b)));
      render();
    }));
    document.querySelectorAll("#threshold button").forEach(b => b.addEventListener("click", () => {
      state.threshold = b.dataset.threshold;
      document.querySelectorAll("#threshold button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
      render();
    }));
    document.getElementById("show-context").addEventListener("change", e => { state.context = e.target.checked; render(); });
    document.querySelectorAll(".m[data-tex]").forEach(n => n.replaceWith(tex(n.dataset.tex)));
  }

  function boot() {
    const tag = document.getElementById("lifecycle-payload");
    try { state.payload = tag ? JSON.parse(tag.textContent) : { release: null, cases: [] }; } catch (e) { state.payload = { release: null, cases: [] }; }
    wire();
    renderStats();
    renderChips();
    renderLegend();
    render();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
