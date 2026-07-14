/**
 * Lifecycle swimlane — D3 visualization of PACER CAC state machines (L*_{g,A}).
 */
(function () {
  "use strict";

  const GROOMING = "https://cacontology.projectvic.org/grooming#";
  const SEXTORTION = "https://cacontology.projectvic.org/sextortion#";
  const PLATFORMS = "https://cacontology.projectvic.org/platforms#";
  const UNDERCOVER = "https://cacontology.projectvic.org/undercover#";
  const CAC = "https://cacontology.projectvic.org#";

  const CANONICAL_ROWS = [
    { id: "enticement", color: "#6ee7b7", bg: "#0d1f16", label: "Enticement", short: "ENT" },
    { id: "production", color: "#f97316", bg: "#1a1008", label: "Production", short: "PRD" },
    { id: "sextortion", color: "#fbbf24", bg: "#1a1608", label: "Sextortion", short: "EXT" },
    { id: "enterprise", color: "#f87171", bg: "#1a0d0d", label: "Enterprise", short: "ENP" },
    { id: "trafficking", color: "#c084fc", bg: "#140d1a", label: "Trafficking", short: "TRF" },
  ];

  const MODALITY_STYLE = {
    enticement: { color: "#6ee7b7", bg: "#0d1f16" },
    production: { color: "#f97316", bg: "#1a1008" },
    sextortion: { color: "#fbbf24", bg: "#1a1608" },
    enterprise: { color: "#f87171", bg: "#1a0d0d" },
    trafficking: { color: "#c084fc", bg: "#140d1a" },
    unknown: { color: "#9ca3af", bg: "#141414" },
  };

  const COLUMNS = [
    { key: "initial", type: GROOMING + "InitialContactPhase", label: "InitialContact" },
    { key: "conditioning", type: GROOMING + "ConditioningPhase", label: "Conditioning" },
    { key: "sexualization", type: GROOMING + "SexualizationPhase", label: "Sexualization" },
    { key: "migration", type: PLATFORMS + "ChannelMigrationEvent", label: "ChannelMigration" },
    { key: "exploitation", type: GROOMING + "ExploitationPhase", terminal: false, label: "Exploitation" },
    { key: "threat", type: SEXTORTION + "ThreatMechanism", label: "ThreatMechanism" },
    { key: "coercion", type: SEXTORTION + "CoercionCycle", label: "CoercionCycle" },
    { key: "maintenance", type: GROOMING + "MaintenancePhase", label: "Maintenance" },
    { key: "intervention", type: UNDERCOVER + "StingOperation", label: "Intervention" },
    { key: "terminal", type: GROOMING + "ExploitationPhase", terminal: true, label: "Terminal" },
  ];

  const AFFORDANCE_COLORS = {
    Anonymity: "#6ee7b7",
    Ephemerality: "#fbbf24",
    UnmonitoredCommunication: "#a78bfa",
    ContactDiscovery: "#34d399",
    DistributionInfrastructure: "#60a5fa",
    Coordination: "#fb923c",
    CoercionLeverage: "#f87171",
  };

  const AFFORDANCE_LABELS = {
    Anonymity: "Anonymity",
    Ephemerality: "Ephemerality",
    UnmonitoredCommunication: "Unmonitored comm.",
    ContactDiscovery: "Contact discovery",
    DistributionInfrastructure: "Distribution infra",
    Coordination: "Coordination",
    CoercionLeverage: "Coercion leverage",
  };

  // Enticement victim-exit gate diamonds removed intentionally — do not restore ENTICEMENT_GATES.

  const NODE_W = 200;
  const NODE_H = 100;
  const COL_W = 240;
  const ROW_H = 200;
  const LEFT_PAD = 168;
  const TOP_PAD = 56;
  const HEADER_H = 28;

  function shortType(iri) {
    if (!iri) return "";
    const h = iri.indexOf("#");
    return h >= 0 ? iri.slice(h + 1) : iri.split("/").pop();
  }

  function columnIndex(phase) {
    const t = phase.type;
    if (phase.is_terminal && t === GROOMING + "ExploitationPhase") {
      return COLUMNS.length - 1;
    }
    for (let i = 0; i < COLUMNS.length; i++) {
      const col = COLUMNS[i];
      if (col.terminal) continue;
      if (col.type === t) return i;
    }
    return 4;
  }

  function layoutRow(phases) {
    const used = {};
    return phases.map((phase) => {
      let col = columnIndex(phase);
      const key = col + (phase.is_terminal ? "-t" : "");
      used[key] = (used[key] || 0) + 1;
      const bump = (used[key] - 1) * (NODE_W * 0.45);
      const x = LEFT_PAD + col * COL_W + bump;
      return { phase, x, col };
    });
  }

  function affordanceColor(name) {
    return AFFORDANCE_COLORS[name] || "#9ca3af";
  }

  function arrowPath(x1, y1, x2, y2) {
    const mx = (x1 + x2) / 2;
    return `M${x1},${y1} L${mx},${y1} L${mx},${y2} L${x2},${y2}`;
  }

  function addFlowDots(parent, pathD, color) {
    const g = parent.append("g").attr("class", "flow-dots");
    const svgNs = "http://www.w3.org/2000/svg";
    [0, 1.4].forEach((begin) => {
      const circle = g.append("circle").attr("r", 3).attr("fill", color).attr("class", "flow-dot");
      const motion = document.createElementNS(svgNs, "animateMotion");
      motion.setAttribute("dur", "2.8s");
      motion.setAttribute("repeatCount", "indefinite");
      motion.setAttribute("begin", `${begin}s`);
      motion.setAttribute("path", pathD);
      circle.node().appendChild(motion);
    });
  }

  function maintenanceColumnX() {
    const col = COLUMNS.findIndex((c) => c.key === "maintenance");
    return LEFT_PAD + col * COL_W + NODE_W / 2;
  }

  function renderDisruptionEdge(edgesG, x1, y1, x2, y2, markerId, label) {
    const pathD = arrowPath(x1, y1, x2, y2);
    edgesG
      .append("path")
      .attr("d", pathD)
      .attr("class", "edge-disrupted")
      .attr("fill", "none")
      .attr("stroke", "#f87171")
      .attr("stroke-width", 2.5)
      .attr("stroke-dasharray", "8,5")
      .attr("marker-end", `url(#${markerId})`);

    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    const xg = edgesG.append("g").attr("class", "disruption-x").attr("transform", `translate(${mx},${my})`);
    xg.append("circle").attr("r", 14).attr("class", "disruption-x-bg");
    xg.append("line").attr("x1", -7).attr("y1", -7).attr("x2", 7).attr("y2", 7).attr("class", "disruption-x-stroke");
    xg.append("line").attr("x1", 7).attr("y1", -7).attr("x2", -7).attr("y2", 7).attr("class", "disruption-x-stroke");

    if (label) {
      edgesG
        .append("text")
        .attr("class", "edge-label disruption-edge-label")
        .attr("x", mx)
        .attr("y", my - 22)
        .attr("text-anchor", "middle")
        .text(label);
    }

    const ghostX = maintenanceColumnX();
    const ghostY = y2;
    const ghostStart = x2 + NODE_W * 0.35;
    if (ghostX > ghostStart + 24) {
      const ghostD = `M${ghostStart},${ghostY} L${ghostX},${ghostY}`;
      edgesG.append("path").attr("d", ghostD).attr("class", "edge-blocked-ghost");
      const gx = edgesG
        .append("g")
        .attr("class", "disruption-x ghost-x")
        .attr("transform", `translate(${ghostX},${ghostY})`);
      gx.append("circle").attr("r", 10).attr("class", "disruption-x-bg ghost");
      gx.append("line").attr("x1", -5).attr("y1", -5).attr("x2", 5).attr("y2", 5).attr("class", "disruption-x-stroke");
      gx.append("line").attr("x1", 5).attr("y1", -5).attr("x2", -5).attr("y2", 5).attr("class", "disruption-x-stroke");
    }
  }

  let panelEl, backdropEl, payload;
  let selectedOffenseTypes = new Set(CANONICAL_ROWS.map((r) => r.id));
  let offenseFilterOpen = false;

  function caseOffenseType(caseData) {
    return caseData.modality || caseData.id;
  }

  function filteredCanonicalCases() {
    const cases = payload.canonical_cases || payload.cases || [];
    return cases.filter((c) => selectedOffenseTypes.has(caseOffenseType(c)));
  }

  function filteredCanonicalRows() {
    return CANONICAL_ROWS.filter((r) => selectedOffenseTypes.has(r.id));
  }

  function filteredExpansionCases() {
    return (payload.expansion_cases || []).filter((c) => selectedOffenseTypes.has(caseOffenseType(c)));
  }

  function updateOffenseSummary() {
    const summaryEl = document.getElementById("offense-filter-summary");
    if (!summaryEl) return;
    const allSelected = selectedOffenseTypes.size === CANONICAL_ROWS.length;
    if (allSelected) {
      summaryEl.innerHTML = '<span class="offense-filter-summary-all">All</span>';
      return;
    }
    summaryEl.innerHTML = CANONICAL_ROWS.filter((r) => selectedOffenseTypes.has(r.id))
      .map(
        (r) =>
          `<span class="offense-filter-chip" style="background:${r.color}" title="${escapeHtml(r.label)}"></span>`
      )
      .join("");
  }

  function syncOffenseOptionButtons() {
    document.querySelectorAll(".offense-filter-option").forEach((btn) => {
      const on = selectedOffenseTypes.has(btn.dataset.type);
      btn.classList.toggle("is-on", on);
      btn.classList.toggle("is-off", !on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function applyOffenseFilter() {
    updateOffenseSummary();
    syncOffenseOptionButtons();
    renderSwimlanes();
    renderExpansionSection();
  }

  function setOffenseFilterOpen(open) {
    offenseFilterOpen = open;
    const root = document.getElementById("offense-filter");
    const panel = document.getElementById("offense-filter-panel");
    const trigger = document.getElementById("offense-filter-trigger");
    if (!root || !panel || !trigger) return;
    root.classList.toggle("open", open);
    panel.hidden = !open;
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function toggleOffenseType(typeId) {
    if (selectedOffenseTypes.has(typeId)) {
      if (selectedOffenseTypes.size <= 1) return;
      selectedOffenseTypes.delete(typeId);
    } else {
      selectedOffenseTypes.add(typeId);
    }
    applyOffenseFilter();
  }

  function toggleAllOffenseTypes() {
    const allSelected = selectedOffenseTypes.size === CANONICAL_ROWS.length;
    selectedOffenseTypes = allSelected ? new Set(["enticement"]) : new Set(CANONICAL_ROWS.map((r) => r.id));
    applyOffenseFilter();
  }

  function renderOffenseFilter() {
    const optionsEl = document.getElementById("offense-filter-options");
    const trigger = document.getElementById("offense-filter-trigger");
    const allBtn = document.getElementById("offense-filter-all");
    if (!optionsEl || !trigger) return;

    optionsEl.innerHTML = CANONICAL_ROWS.map(
      (row) =>
        `<button type="button" class="offense-filter-option is-on" data-type="${row.id}" style="--chip-color:${row.color}" aria-pressed="true">${row.short}</button>`
    ).join("");

    optionsEl.querySelectorAll(".offense-filter-option").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleOffenseType(btn.dataset.type);
      });
    });

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      setOffenseFilterOpen(!offenseFilterOpen);
    });

    if (allBtn) {
      allBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleAllOffenseTypes();
      });
    }

    document.addEventListener("click", (e) => {
      const root = document.getElementById("offense-filter");
      if (offenseFilterOpen && root && !root.contains(e.target)) {
        setOffenseFilterOpen(false);
      }
    });

    updateOffenseSummary();
  }

  function openPanel(phase, caseData) {
    const crossAll = (payload.cross_case_all || {})[phase.type] || { count: 0, cases: [] };
    const nLifecycle =
      payload.n_lifecycle
      || payload.n_cases
      || (payload.canonical_cases || payload.cases || []).length
        + (payload.expansion_cases || []).length
      || 0;
    const coverageCount = crossAll.count ?? 0;
    const offenseTypes = crossAll.offense_types || [];
    const ins = (payload.affordance_annotations || []).filter(
      (a) => a.to && a.to.includes(shortType(phase.type))
    );
    const outs = (payload.affordance_annotations || []).filter(
      (a) => a.from && a.from.includes(shortType(phase.type))
    );

    panelEl.innerHTML = `
      <h3>${escapeHtml(phase.label || shortType(phase.type))}</h3>
      <div class="panel-type" title="${escapeHtml(phase.type)}">${escapeHtml(phase.type_display || phase.type)}</div>
      <div class="panel-section">
        <h4>Description</h4>
        <p>${escapeHtml(phase.comment || "—")}</p>
      </div>
      ${
        phase.disrupts_chain
          ? `<div class="panel-section panel-disruption">
        <h4>Chain disruption</h4>
        <p>Law enforcement intervention terminates the offender trajectory before ${
          escapeHtml(phase.disrupted_target || "downstream hands-on exploitation")
        }.</p>
      </div>`
          : ""
      }
      <div class="panel-section">
        <h4>Coverage</h4>
        <p>${coverageCount}/${nLifecycle} cases: ${offenseTypes.join(", ") || "—"}</p>
        ${phase.is_fundamental ? "<p><strong>Appears in all 5 canonical offense types</strong> (fundamental)</p>" : ""}
      </div>
      <div class="panel-section">
        <h4>Transitions in</h4>
        <ul>${ins.length ? ins.map((t) => `<li>${escapeHtml(t.affordance)} (${t.case_count}/${payload.n_canonical || 5})</li>`).join("") : "<li>—</li>"}</ul>
      </div>
      <div class="panel-section">
        <h4>Transitions out</h4>
        <ul>${outs.length ? outs.map((t) => `<li>→ ${escapeHtml(t.affordance)} (${t.case_count}/${payload.n_canonical || 5})</li>`).join("") : "<li>—</li>"}</ul>
      </div>
      <div class="panel-section">
        <h4>Case</h4>
        <p>${escapeHtml(caseCaption(caseData))}</p>
      </div>
    `;
    panelEl.classList.add("open");
    backdropEl.classList.add("open");
  }

  function closePanel() {
    panelEl.classList.remove("open");
    backdropEl.classList.remove("open");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Federal caption for row labels and panel — never corpus_id. */
  function caseCaption(caseData) {
    return caseData.citation || caseData.case_name || caseData.id || "";
  }

  const LSTAR_EQUATION_TEX =
    String.raw`L^{*}_{g,A} = \operatorname{arg}\ \underset{L \in \mathrm{Seq}(A)}{\operatorname{max}} \ \mathbb{E}[U_g(L)]`;

  function renderFundamentalEquation() {
    const host = document.getElementById("fundamental-equation-tex");
    if (!host || typeof katex === "undefined") return;
    try {
      katex.render(LSTAR_EQUATION_TEX, host, {
        displayMode: false,
        throwOnError: false,
      });
    } catch (_) {
      /* keep aria-label on parent if KaTeX fails */
    }
  }

  function renderFundamentalSection() {
    const el = document.getElementById("fundamental-section");
    if (!el) return;
    const names = (payload.fundamental_display || []).map(shortType);
    const ordered = ["InitialContactPhase", "ConditioningPhase", "ExploitationPhase", "MaintenancePhase"].filter(
      (n) => names.includes(n) || (payload.fundamental || []).some((iri) => iri.endsWith(n))
    );
    el.innerHTML = `
      <h2>FUNDAMENTAL — shared across all 5 offense types</h2>
      <p class="fundamental-note">Invariant exploitation structure · L*<sub>g,A</sub> constants · 5/5 offense types</p>
      <div class="fundamental-flow">
        ${ordered
          .map((n, i) => {
            const arrow = i < ordered.length - 1 ? '<span class="bf-arrow">→</span>' : "";
            return `<span class="bf-node">${n}</span>${arrow}`;
          })
          .join("")}
      </div>
      <div class="fundamental-math">
        <p class="fundamental-basis-label">Mathematical basis · Section 7.2</p>
        <div class="fundamental-equation" aria-label="L-star g A equals argmax over L in Seq(A) of expected U_g of L">
          <span id="fundamental-equation-tex" class="fundamental-equation-tex"></span>
        </div>
        <p class="fundamental-basis-text">
          Five PACER trajectories diverge by goal <i>g</i> and exploitation modality, but their CAC phase types are drawn from the same stage set.
          The fundamental stages are the build blocks of exploitation pathways in all five cases — stages where an intervention degrades every trajectory simultaneously,
          not only one offense type. Distinct trajectories; invariant stages.
        </p>
        <a class="fundamental-paper-link" href="https://mrinaalr.github.io/website/Affordance%2C%20Misuse%2C%20Harm%2C%20Kill%20Chain.pdf" target="_blank" rel="noopener noreferrer">
          Affordances for Harm: How Offenders Misuse Platform Capabilities to Exploit Children, and Where to Intervene — Eq.&nbsp;(1) and §6.2 contact-chain regularity
        </a>
      </div>
    `;
    renderFundamentalEquation();
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function renderStats() {
    const nTotal = payload.n_cases
      || (payload.canonical_cases || payload.cases || []).length
      + (payload.expansion_cases || []).length
      || 5;
    setText("stat-cases", nTotal);
    setText("stat-canonical", nTotal);
    setText("stat-stages", payload.canonical_stage_count || "—");
    setText("stat-transitions", payload.shared_transition_count || "—");
  }

  function expansionRows(cases) {
    return cases.map((caseData) => {
      const style = MODALITY_STYLE[caseData.modality] || MODALITY_STYLE.unknown;
      return {
        id: caseData.id,
        color: style.color,
        bg: style.bg,
        expansion: true,
      };
    });
  }

  function fundamentalColumns() {
    const fundamentalCols = new Set();
    (payload.fundamental || []).forEach((iri) => {
      COLUMNS.forEach((col, i) => {
        if (col.type === iri && !col.terminal) fundamentalCols.add(i);
        if (iri === GROOMING + "ExploitationPhase" && col.terminal) fundamentalCols.add(i);
      });
    });
    ["InitialContactPhase", "ConditioningPhase", "ExploitationPhase", "MaintenancePhase"].forEach((name) => {
      COLUMNS.forEach((col, i) => {
        if (col.label.replace(/Phase$/, "") === name.replace(/Phase$/, "") || col.type.endsWith(name)) {
          if (name === "ExploitationPhase" && col.terminal) fundamentalCols.add(i);
          else if (name !== "ExploitationPhase" || !col.terminal) {
            if (col.type.endsWith(name)) fundamentalCols.add(i);
          }
        }
      });
    });
    return fundamentalCols;
  }

  function renderSwimlaneCanvas(hostId, rows, caseList, options) {
    const opts = options || {};
    const markerId = opts.markerId || "arrow";
    const showDecorations = opts.showDecorations !== false;
    const nCanonical = payload.n_canonical || 5;

    const caseMap = {};
    caseList.forEach((c) => {
      caseMap[c.id] = c;
    });

    const fundamentalCols = fundamentalColumns();
    const width = LEFT_PAD + COLUMNS.length * COL_W + 80;
    const height = TOP_PAD + rows.length * ROW_H + 40;
    const host = document.getElementById(hostId);
    if (!host) return;
    host.innerHTML = "";

    const svg = d3
      .select(host)
      .append("svg")
      .attr("class", "lifecycle-svg")
      .attr("width", width)
      .attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`);

    svg
      .append("defs")
      .append("marker")
      .attr("id", markerId)
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 8)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "context-stroke");

    const fundamentalG = svg.append("g").attr("class", "fundamental-columns");
    fundamentalCols.forEach((col) => {
      rows.forEach((_, ri) => {
        fundamentalG
          .append("rect")
          .attr("class", "fundamental-col")
          .attr("x", LEFT_PAD + col * COL_W - 12)
          .attr("y", TOP_PAD + ri * ROW_H - 8)
          .attr("width", COL_W)
          .attr("height", ROW_H)
          .attr("rx", 6);
      });
    });

    COLUMNS.forEach((col, i) => {
      svg
        .append("text")
        .attr("class", "col-header")
        .attr("x", LEFT_PAD + i * COL_W + NODE_W / 2)
        .attr("y", TOP_PAD - 12)
        .text(col.label);
    });

    rows.forEach((row, ri) => {
      const caseData = caseMap[row.id];
      if (!caseData) return;

      const y0 = TOP_PAD + ri * ROW_H;
      const cy = y0 + ROW_H / 2;
      const gRow = svg.append("g").attr("class", "row").attr("data-case", row.id);

      gRow
        .append("rect")
        .attr("x", 8)
        .attr("y", y0 + 20)
        .attr("width", 4)
        .attr("height", ROW_H - 40)
        .attr("fill", row.color)
        .attr("rx", 2);

      if (row.expansion) {
        gRow
          .append("text")
          .attr("class", "row-label")
          .attr("x", 20)
          .attr("y", cy - 8)
          .attr("fill", row.color)
          .text(caseData.modality_label || caseData.offense_type || row.id.toUpperCase());
        gRow
          .append("text")
          .attr("class", "row-citation")
          .attr("x", 20)
          .attr("y", cy + 10)
          .text(caseCaption(caseData));
      } else {
        gRow
          .append("text")
          .attr("class", "row-label")
          .attr("x", 20)
          .attr("y", cy - 8)
          .attr("fill", row.color)
          .text(caseData.offense_type || row.id.toUpperCase());
        gRow
          .append("text")
          .attr("class", "row-citation")
          .attr("x", 20)
          .attr("y", cy + 10)
          .text(caseData.citation || "");
      }

      const laid = layoutRow(caseData.phases || []);
      const edgesG = gRow.append("g").attr("class", "edges");

      for (let i = 0; i < laid.length - 1; i++) {
        const a = laid[i];
        const b = laid[i + 1];
        const x1 = a.x + NODE_W;
        const y1 = cy;
        const x2 = b.x;
        const y2 = cy;
        const trans = (caseData.transitions || [])[i] || {};
        const aff = trans.affordance_name || "Anonymity";
        const color = affordanceColor(aff);
        const disrupted = trans.disrupts_chain || b.phase.disrupts_chain;

        if (disrupted) {
          renderDisruptionEdge(
            edgesG,
            x1,
            y1,
            x2,
            y2,
            markerId,
            "chain disrupted"
          );
        } else {
          const pathD = arrowPath(x1, y1, x2, y2);

          edgesG
            .append("path")
            .attr("d", pathD)
            .attr("fill", "none")
            .attr("stroke", color)
            .attr("stroke-width", 2)
            .attr("marker-end", `url(#${markerId})`);

          const lx = (x1 + x2) / 2;
          const ly = cy - 10;
          edgesG
            .append("text")
            .attr("class", "edge-label")
            .attr("x", lx)
            .attr("y", ly)
            .attr("text-anchor", "middle")
            .text(AFFORDANCE_LABELS[aff] || aff);

          addFlowDots(edgesG, pathD, color);
        }
      }

      if (showDecorations && row.id === "sextortion") {
        const threat = laid.find((l) => l.phase.type === SEXTORTION + "ThreatMechanism");
        const cycle = laid.find((l) => l.phase.type === SEXTORTION + "CoercionCycle");
        if (threat && cycle) {
          const tx = threat.x + NODE_W / 2;
          const ty = cy + NODE_H / 2 + 8;
          const cx = cycle.x + NODE_W / 2;
          const cy2 = cy + NODE_H / 2 + 8;
          const arcD = `M${cx},${cy2 + 4} Q${(tx + cx) / 2},${cy + NODE_H + 52} ${tx},${ty + 4}`;
          gRow.append("path").attr("class", "coercion-arc").attr("d", arcD);
          addFlowDots(gRow, arcD, "#f87171");
        }
      }

      const nodesG = gRow.append("g").attr("class", "nodes");
      laid.forEach((item) => {
        const { phase, x } = item;
        const nx = x;
        const ny = cy - NODE_H / 2;

        const ng = nodesG
          .append("g")
          .attr("class", "stage-node")
          .attr("transform", `translate(${nx},${ny})`)
          .on("click", (event) => {
            event.stopPropagation();
            openPanel(phase, caseData);
          });

        ng
          .append("rect")
          .attr("width", NODE_W)
          .attr("height", NODE_H)
          .attr("rx", 10)
          .attr("fill", row.bg)
          .attr("stroke", phase.disrupts_chain ? "#f87171" : row.color)
          .attr("stroke-width", phase.disrupts_chain ? 2 : 1.5)
          .attr("stroke-dasharray", phase.disrupts_chain ? "6,3" : null);

        ng
          .append("text")
          .attr("class", "node-class")
          .attr("x", 12)
          .attr("y", 22)
          .attr("fill", row.color)
          .text(phase.short_type || shortType(phase.type));

        if (phase.is_fundamental || phase.coverage === nCanonical) {
          ng
            .append("text")
            .attr("class", "coverage-badge")
            .attr("x", NODE_W - 10)
            .attr("y", 20)
            .attr("text-anchor", "end")
            .text(`${nCanonical}/${nCanonical}`);
        } else if (phase.coverage) {
          ng
            .append("text")
            .attr("class", "coverage-badge")
            .attr("x", NODE_W - 10)
            .attr("y", 20)
            .attr("text-anchor", "end")
            .text(`${phase.coverage}/${nCanonical}`);
        }

        const label = phase.label || "";
        const words = label.split(" ");
        let line1 = label;
        let line2 = "";
        if (label.length > 28) {
          line1 = words.slice(0, Math.ceil(words.length / 2)).join(" ");
          line2 = words.slice(Math.ceil(words.length / 2)).join(" ");
        }
        ng
          .append("text")
          .attr("class", "node-label")
          .attr("x", 12)
          .attr("y", 52)
          .attr("fill", "#e8f0ea")
          .text(line1);
        if (line2) {
          ng
            .append("text")
            .attr("class", "node-label")
            .attr("x", 12)
            .attr("y", 68)
            .attr("fill", "#e8f0ea")
            .text(line2);
        }

        if (phase.disrupts_chain) {
          ng
            .append("text")
            .attr("class", "disruption-badge")
            .attr("x", NODE_W - 10)
            .attr("y", NODE_H - 10)
            .attr("text-anchor", "end")
            .text("DISRUPTED");
        }
      });
    });
  }

  function renderSwimlanes() {
    const canonicalCases = filteredCanonicalCases();
    const rows = filteredCanonicalRows();
    renderSwimlaneCanvas("lifecycle-canvas", rows, canonicalCases, {
      markerId: "arrow-canonical",
      showDecorations: selectedOffenseTypes.has("sextortion"),
    });
  }

  function renderExpansionSection() {
    const expansionCases = filteredExpansionCases();
    const section = document.getElementById("expansion-section");
    if (!section || expansionCases.length === 0) {
      if (section) section.hidden = true;
      return;
    }

    section.hidden = false;

    renderSwimlaneCanvas(
      "lifecycle-canvas-expansion",
      expansionRows(expansionCases),
      expansionCases,
      {
        markerId: "arrow-expansion",
        showDecorations: expansionCases.some((c) => c.chain_disrupted),
      }
    );
  }

  function renderLegend() {
    const el = document.getElementById("affordance-legend");
    if (!el) return;
    const items = Object.keys(AFFORDANCE_COLORS)
      .map(
        (k) =>
          `<span class="legend-item"><span class="dot" style="background:${AFFORDANCE_COLORS[k]}"></span>${AFFORDANCE_LABELS[k] || k}</span>`
      )
      .join("");
    el.innerHTML = `<span class="legend-title">Affordance classes →</span>${items}
      <span class="legend-item legend-disruption"><span class="dot disruption-dot"></span>Chain disruption (LE sting)</span>`;
  }

  function init() {
    panelEl = document.getElementById("detail-panel");
    backdropEl = document.getElementById("detail-backdrop");
    backdropEl.addEventListener("click", closePanel);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (offenseFilterOpen) setOffenseFilterOpen(false);
        else closePanel();
      }
    });

    try {
      const embedded = document.getElementById("lifecycle-payload");
      if (!embedded || !embedded.textContent.trim()) {
        throw new Error("Lifecycle payload missing — open /lifecycle via the CaseLinker server.");
      }
      payload = JSON.parse(embedded.textContent);
      renderOffenseFilter();
      renderStats();
      renderSwimlanes();
      renderFundamentalSection();
      renderExpansionSection();
      renderLegend();
    } catch (err) {
      document.getElementById("lifecycle-canvas").innerHTML = `<div class="lifecycle-error">Failed to load lifecycle data: ${escapeHtml(err.message)}</div>`;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
