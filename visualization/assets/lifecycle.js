/* /lifecycle: documented PACER trajectories, one lane per case, and the formal model.
   Data: <script id="lifecycle-payload"> embedded server-side (state_machines/trajectories/payload.py).
   Columns are codebook action groups (categories, not stages); arrows are documented order only. */
(function () {
  "use strict";

  const SVGNS = "http://www.w3.org/2000/svg";
  const REPO = "https://github.com/mrinaalr/CaseLinker/blob/main/";
  const AFF = {
    anonymity: { color: "#c4a1ff", label: "Anonymity" },
    ephemerality: { color: "#f5c46b", label: "Ephemerality" },
    contact_discovery: { color: "#7cb7ff", label: "Contact discovery" },
    unmonitored_communication: { color: "#5fd4a4", label: "Unmonitored communication" },
    distribution_infrastructure: { color: "#ff8a7a", label: "Distribution infrastructure" },
    generative_synthesis: { color: "#f39ac7", label: "Generative synthesis" },
  };
  const GROUPS = [
    ["access", "Access"], ["influence", "Influence"], ["production", "Production"], ["distribution", "Distribution"],
    ["coordination", "Coordination"], ["in_person", "In person"], ["concealment", "Concealment"],
  ];
  const CASE_COLORS = ["#5fd4a4", "#ff9f5a", "#f5c46b", "#ff7a8a", "#a58cff", "#7cb7ff", "#e6a3d8"];
  const STANDING = {
    ALLEGATION: "allegation", SWORN_AFFIDAVIT: "affidavit", ADMITTED: "admitted",
    ADMITTED_UNDER_OATH: "admitted", JUDICIAL_FINDING: "finding", VERDICT_ELEMENT: "verdict",
    COURT_RECORD: "record", ADVOCACY: "advocacy", PROCEDURAL: "docket",
  };
  const TRACK_KIND = { victim: "victim", undercover: "undercover persona", material: "material",
    co_offender_network: "co-offender network", case_procedure: "case procedure" };
  const L = { label: 210, col: 196, w: 176, h: 42, row: 52, top: 40, pad: 16 };

  const state = { payload: null, view: "documented", open: new Set() };

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
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const live = s => s === "DIRECT" || s === "INFERRED";
  const shortDate = ev => {
    const a = ev.time.find(x => live(x.status));
    if (!a) return "undated";
    const d = a.precision === "day" ? a.earliest : a.precision === "year" ? a.earliest.slice(0, 4)
      : a.precision === "month" ? a.earliest.slice(0, 7) : `${a.earliest.slice(0, 7)}…${a.latest.slice(0, 7)}`;
    return (a.basis === "enclosing_window" ? "≈" : "") + d;
  };

  // ---------- documented order over a set of events ----------
  function order(cs, track, ids) {
    const inTrack = new Set(track.events);
    const adj = new Map(track.events.map(e => [e, new Set()]));
    const kind = new Map();
    for (const r of cs.relations) {
      if ((r.type === "BEFORE" || r.type === "MEETS") && live(r.status) && inTrack.has(r.from) && inTrack.has(r.to)) {
        adj.get(r.from).add(r.to);
        kind.set(r.from + ">" + r.to, r.type === "MEETS" ? "meets" : r.status === "DIRECT" ? "direct" : "inferred");
      }
    }
    for (const [a, b] of (track.views.INFERRED || {}).date_order || []) {
      if (!adj.get(a).has(b)) { adj.get(a).add(b); kind.set(a + ">" + b, "date"); }
    }
    const reach = new Map();
    const visit = (n, seen) => { for (const m of adj.get(n)) if (!seen.has(m)) { seen.add(m); visit(m, seen); } return seen; };
    track.events.forEach(e => reach.set(e, visit(e, new Set())));
    const less = (a, b) => reach.get(a).has(b);
    const cover = [];
    for (const a of ids) for (const b of ids) {
      if (a !== b && less(a, b) && !ids.some(c => c !== a && c !== b && less(a, c) && less(c, b))) {
        cover.push({ from: a, to: b, kind: kind.get(a + ">" + b) || "date" });
      }
    }
    const depth = new Map();
    const d = a => {
      if (depth.has(a)) return depth.get(a);
      const p = ids.filter(x => less(x, a));
      const v = p.length ? 1 + Math.max(...p.map(d)) : 0;
      depth.set(a, v);
      return v;
    };
    ids.forEach(d);
    return { cover, depth, less };
  }

  // the track a case is read through: the one with the most offender events
  const mainTrack = cs => cs.tracks.slice().sort((a, b) =>
    b.events.filter(e => cs.events[e].family === "offender").length - a.events.filter(e => cs.events[e].family === "offender").length)[0];

  // ---------- documented view ----------
  function renderDocumented() {
    const host = document.getElementById("doc-canvas");
    host.innerHTML = "";
    const cases = state.payload.cases;
    if (!cases.length) { host.append(el("div", { class: "lifecycle-loading", text: "No PACER release is published yet." })); return; }
    const rows = [];
    cases.forEach((cs, ci) => {
      const main = mainTrack(cs);
      const tracks = state.open.has(cs.case_id) ? [main, ...cs.tracks.filter(t => t !== main)] : [main];
      tracks.forEach((t, ti) => rows.push({ cs, ci, track: t, first: ti === 0, more: cs.tracks.length - 1 }));
    });
    const width = L.label + GROUPS.length * L.col + L.pad;
    const laid = rows.map(r => layoutRow(r));
    const height = L.top + laid.reduce((n, r) => n + r.h, 0) + 8;
    const svg = sv("svg", { class: "lifecycle-svg", width, height });
    svg.append(defs());
    GROUPS.forEach(([, label], i) => {
      const x = L.label + i * L.col;
      svg.append(sv("rect", { x, y: 0, width: L.col, height, class: i % 2 ? "col-band" : "col-band col-band--alt" }));
      svg.append(svText({ x: x + 10, y: 22, class: "col-label" }, label.toUpperCase()));
    });
    let y = L.top;
    for (const r of laid) { drawRow(svg, r, y, width); y += r.h; }
    host.append(svg);
  }

  function layoutRow(r) {
    const { cs, track } = r;
    const ids = track.events.filter(id => cs.events[id].family === "offender" && cs.events[id].group);
    const o = order(cs, track, ids);
    const cols = new Map();
    ids.forEach(id => { const g = cs.events[id].group; if (!cols.has(g)) cols.set(g, []); cols.get(g).push(id); });
    cols.forEach(list => list.sort((a, b) => o.depth.get(a) - o.depth.get(b) || a.localeCompare(b)));
    const stack = Math.max(1, ...[...cols.values()].map(l => l.length));
    const pos = new Map();
    GROUPS.forEach(([g], gi) => (cols.get(g) || []).forEach((id, k) => pos.set(id, { x: L.label + gi * L.col + (L.col - L.w) / 2, y: 10 + k * L.row })));
    const ctx = track.events.filter(id => cs.events[id].family !== "offender");
    return { ...r, ids, o, pos, ctx, h: stack * L.row + 26 };
  }

  function defs() {
    const d = sv("defs");
    for (const [id, cls] of [["arr", "arr-head"], ["arr-dim", "arr-head-dim"]]) {
      const m = sv("marker", { id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" });
      m.append(sv("path", { d: "M0,0 L10,5 L0,10 z", class: cls }));
      d.append(m);
    }
    return d;
  }

  function drawRow(svg, r, y, width) {
    const color = CASE_COLORS[r.ci % CASE_COLORS.length];
    const g = sv("g", { transform: `translate(0,${y})`, class: "row" + (r.first ? "" : " row--sub") });
    g.append(sv("rect", { x: 0, y: 0, width, height: r.h, class: "row-hit" }));   // the lane's whole area, so the trace holds between lines
    if (r.first) g.append(sv("line", { x1: 0, x2: width, y1: 0, y2: 0, class: "row-rule" }));
    g.append(sv("rect", { x: 14, y: 10, width: 3, height: r.h - 22, rx: 1.5, fill: color, opacity: r.first ? 1 : .4 }));
    const head = sv("g", { class: "row-head", tabindex: r.more ? 0 : -1, role: r.more ? "button" : "presentation" });
    if (r.first) {
      head.append(svText({ x: 28, y: 26, class: "case-id", fill: color }, r.cs.case_id));
      head.append(svText({ x: 28, y: 42, class: "case-meta" }, `${TRACK_KIND[r.track.kind] || r.track.kind} track · ${r.ids.length} acts`));
      if (r.more) head.append(svText({ x: 28, y: 58, class: "case-more" }, state.open.has(r.cs.case_id) ? "− fewer tracks" : `+ ${r.more} more track${r.more > 1 ? "s" : ""}`));
    } else {
      head.append(svText({ x: 28, y: 26, class: "case-meta" }, `${TRACK_KIND[r.track.kind] || r.track.kind} track · ${r.ids.length} acts`));
    }
    if (r.more && r.first) {
      const toggle = () => { state.open.has(r.cs.case_id) ? state.open.delete(r.cs.case_id) : state.open.add(r.cs.case_id); renderDocumented(); };
      head.addEventListener("click", toggle);
      head.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    }
    g.append(head);
    const edges = sv("g", { class: "edges" });
    for (const e of r.o.cover) {
      const a = r.pos.get(e.from), b = r.pos.get(e.to);
      if (!a || !b) continue;
      let d;
      if (b.x > a.x) {
        const x1 = a.x + L.w, y1 = a.y + L.h / 2, x2 = b.x - 3, y2 = b.y + L.h / 2, mx = (x1 + x2) / 2;
        d = `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
      } else if (b.x < a.x) {   // documented order running back to an earlier group
        const x1 = a.x + L.w / 2, y1 = a.y + L.h, x2 = b.x + L.w / 2, y2 = b.y + L.h + 3, low = Math.max(y1, y2) + 18;
        d = `M${x1},${y1} C${x1},${low} ${x2},${low} ${x2},${y2}`;
      } else {                  // same group, stacked
        const x = a.x + L.w + 2;
        d = `M${x},${a.y + L.h / 2} C${x + 16},${a.y + L.h / 2} ${x + 16},${b.y + L.h / 2} ${x + 2},${b.y + L.h / 2}`;
      }
      edges.append(sv("path", { d, class: `edge edge-${e.kind}${b.x < a.x ? " edge-back" : ""}`, "data-from": e.from, "data-to": e.to,
        "marker-end": e.kind === "date" ? "url(#arr-dim)" : "url(#arr)" }));
    }
    g.append(edges);
    for (const id of r.ids) {
      const n = drawNode(r.cs.events[id], r.pos.get(id), color);
      n.dataset.id = id;
      // the trace stays lit while the pointer follows its lines; it changes on another act and clears on leaving the case
      const on = () => { clearTimeout(g._off); focusRow(g, r, id); };
      n.addEventListener("mouseenter", on); n.addEventListener("focus", on);
      n.addEventListener("blur", () => focusRow(g, r, null));
      g.append(n);
    }
    if (r.ctx.length) {   // court, police and response events: ticks under the lane
      const t = sv("g", { class: "ctx" });
      r.ctx.forEach((id, i) => {
        const ev = r.cs.events[id];
        const c = sv("g", { class: "ctx-tick", transform: `translate(${28 + i * 12},${r.h - 16})`, tabindex: 0, role: "button" });
        c.append(sv("rect", { x: 0, y: 0, width: 8, height: 8, rx: 2 }));
        c.setAttribute("aria-label", ev.label);
        c.append(Object.assign(sv("title"), { textContent: ev.label }));
        c.addEventListener("click", () => showDetail(ev));
        t.append(c);
      });
      g.append(t);
    }
    g.addEventListener("mouseleave", () => { clearTimeout(g._off); g._off = setTimeout(() => focusRow(g, r, null), 120); });
    g.addEventListener("mouseenter", () => clearTimeout(g._off));
    svg.append(g);
  }

  // hovering an act lights what the record places before and after it; everything else recedes
  function focusRow(g, r, id) {
    const before = id ? new Set(r.ids.filter(x => r.o.less(x, id))) : new Set();
    const after = id ? new Set(r.ids.filter(x => r.o.less(id, x))) : new Set();
    const near = new Set([...before, ...after, ...(id ? [id] : [])]);
    g.classList.toggle("is-focus", !!id);
    g.querySelectorAll(".node").forEach(n => {
      const k = n.dataset.id;
      n.classList.toggle("is-near", near.has(k));
      n.classList.toggle("is-self", k === id);
    });
    g.querySelectorAll(".edge").forEach(e => e.classList.toggle("is-on", near.has(e.dataset.from) && near.has(e.dataset.to)));
    // the lane's caption says what the highlight means
    const meta = g.querySelector(".case-meta");
    if (meta) {
      meta.dataset.rest = meta.dataset.rest || meta.textContent;
      meta.textContent = !id ? meta.dataset.rest
        : before.size + after.size === 0 ? "no documented order"
        : [before.size && `${before.size} before`, after.size && `${after.size} after`].filter(Boolean).join(" · ");
      meta.classList.toggle("is-hint", !!id);
    }
  }

  function drawNode(ev, p, color) {
    const g = sv("g", { class: `node node-${ev.status.toLowerCase()}`, transform: `translate(${p.x},${p.y})`, tabindex: 0, role: "button" });
    g.setAttribute("aria-label", `${ev.label}. Select for sources.`);
    g.append(sv("rect", { width: L.w, height: L.h, rx: 7, class: "node-box", style: `--case:${color}` }));
    const affs = ev.affordances.filter(a => live(a.status));
    g.append(svText({ x: 10, y: 17, class: "node-action" }, clip(ev.label.toUpperCase(), 21 - affs.length)));
    affs.forEach((a, i) => g.append(sv("circle", { cx: L.w - 11 - i * 11, cy: 13, r: 4, fill: AFF[a.class].color,
      class: a.status === "DIRECT" ? "aff-dot" : "aff-dot aff-inferred" })));
    const h0 = [...new Set(ev.harms.filter(h => h.h0 && h.victim_kind === "minor" && live(h.status)).map(h => h.h0))];
    const meta = `${STANDING[ev.standing] || "—"} · ${shortDate(ev)}`;
    g.append(svText({ x: 10, y: 33, class: "node-meta" }, clip(meta, Math.floor((L.w - 16 - 22 * h0.length) / 6.1))));
    h0.forEach((h, i) => {
      const x = L.w - 8 - 22 * (i + 1);
      g.append(sv("rect", { x, y: 24, width: 20, height: 13, rx: 3, class: "harm-tag" }));
      g.append(svText({ x: x + 10, y: 34, class: "harm-text", "text-anchor": "middle" }, h));
    });
    if (ev.outcome !== "completed") g.append(sv("rect", { x: 0, y: L.h - 3, width: L.w, height: 3, rx: 1.5, class: "node-outcome-bar" }));
    const open = () => showDetail(ev);
    g.addEventListener("click", open);
    g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    return g;
  }

  function renderLegend() {
    const host = document.getElementById("legend");
    const item = (sym, label) => el("span", { class: "legend-item" }, sym, label);
    host.append(
      item(el("i", { class: "line line-direct" }), "stated order"),
      item(el("i", { class: "line line-inferred" }), "inferred"),
      item(el("i", { class: "line line-date" }), "from dates"),
      item(el("i", { class: "box box-inferred" }), "inferred act"),
      item(el("i", { class: "box box-harm", text: "h2" }), "harm to a child"),
      item(el("i", { class: "tick" }), "court, police, response"),
      ...Object.values(AFF).map(a => item(el("i", { class: "dot", style: `background:${a.color}` }), a.label)));
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
        el("div", { class: "cl-eyebrow", text: "TRAJECTORIES AND HARMS" }),
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
    const d = sv("defs");
    const m = sv("marker", { id: "toyarr", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto" });
    m.append(sv("path", { d: "M0,0 L10,5 L0,10 z", class: "toy-head" }));
    d.append(m);
    svg.append(d);
    const edge = (p, cls) => svg.append(sv("path", { d: p, class: `toy-edge ${cls}`, "marker-end": "url(#toyarr)" }));
    const label = (x, y, text, cls) => svg.append(svText({ x, y, class: `toy-label ${cls}`, "text-anchor": "middle" }, text));
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
      el("div", { class: "cl-eyebrow", text: ev.id }),
      el("h3", { class: "detail-title", text: ev.label }),
      kv("Evidence", `${ev.status.toLowerCase()} · ${STANDING[ev.standing] || "—"} · ${ev.review}`),
      kv("Actor", `${ev.actor.participant_ref} (${ev.actor.role.replace("_", "-")})`),
      ev.co_actors.length ? kv("With", ev.co_actors.map(c => `${c.participant_ref} (${c.role}, ${c.mode})`).join("; ")) : null,
      ev.targets.length ? kv("Targets", ev.targets.map(t => `${t.participant_ref} (${t.role})`).join("; ")) : null,
      ev.unresolved.length ? kv("Role open", `${ev.unresolved.join(", ")}, decided in adjudication`) : null,
      ev.outcome !== "completed" ? kv("Outcome", ev.outcome.replace(/_/g, " ")) : null,
      kv("When", when),
      ev.affordances.length ? kv("Affordances", ev.affordances.map(a => `${AFF[a.class].label} (${a.basis.replace("_", " ")}, ${a.status.toLowerCase()})`).join("; ")) : null,
      ev.harms.length ? kv("Harms", ev.harms.map(h => `${h.code.replace("HARM_", "").replace(/_/g, " ").toLowerCase()}${h.h0 ? " · " + h.h0 : ""} (${h.victim_kind})`).join("; ")) : null,
      ev.platforms.length ? kv("Platforms", ev.platforms.map(p => `${p.key} (${p.mode}, ${p.audience})`).join("; ")) : null,
      ev.mentions.length ? kv("Named", ev.mentions.join(", ")) : null,
      el("div", { class: "detail-sub", text: "Sources" }),
      el("ul", { class: "prov" }, ev.provenance.map(p => el("li", { text: `${p.doc_type.replace(/_/g, " ")}, page ${p.page} · ${STANDING[p.standing] || p.standing}` }))));
    panel.setAttribute("aria-hidden", "false");
    panel.classList.add("is-open");
    back.classList.add("is-open");
    const close = () => { panel.classList.remove("is-open"); back.classList.remove("is-open"); panel.setAttribute("aria-hidden", "true"); };
    panel.querySelector(".detail-close").addEventListener("click", close);
    back.onclick = close;
    document.addEventListener("keydown", e => { if (e.key === "Escape") close(); }, { once: true });
  }

  // ---------- shell ----------
  function render() {
    for (const v of ["documented", "theory"]) document.getElementById("view-" + v).hidden = state.view !== v;
    if (state.view === "documented") renderDocumented(); else renderTheory();
  }

  function boot() {
    const tag = document.getElementById("lifecycle-payload");
    try { state.payload = tag ? JSON.parse(tag.textContent) : { release: null, cases: [] }; } catch (e) { state.payload = { release: null, cases: [] }; }
    const p = state.payload;
    const events = p.cases.reduce((n, c) => n + c.summary.events, 0);
    document.getElementById("lede").textContent = p.cases.length ? `${p.cases.length} federal cases · ${events} documented events` : "";
    if (p.release && !p.release.adjudicated) {   // only a local preview build is flagged; a shipped release is adjudicated
      const b = document.getElementById("release-banner");
      b.hidden = false;
      b.className = "release-banner is-preview";
      b.textContent = "Preview · not yet adjudicated";
      b.title = `${p.release.id} · schema ${p.release.schema_version} · codebook ${p.release.codebook_version}`;
    }
    document.querySelectorAll("#view-tabs button").forEach(b => b.addEventListener("click", () => {
      state.view = b.dataset.view;
      document.querySelectorAll("#view-tabs button").forEach(x => x.setAttribute("aria-selected", String(x === b)));
      render();
    }));
    renderLegend();
    render();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
