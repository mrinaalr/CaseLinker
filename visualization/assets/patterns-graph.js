    /* ============================================================
     * CAC Ontology Knowledge Graph visualizer
     * ------------------------------------------------------------
     * Boot: GET /api/ontology/cases?pool=compare (curated 200 metadata only).
     * Big Bang: ?pool=all — half-sample at graph_output/big_bang/
     * Universe (secret): double-click Exit Big Bang → ?pool=universe
     * Analysis (secret): triple-click Exit Universe → ?pool=analysis (big_bang.py 1000)
     *
     * There is no embedded graph data. Run
     *     python ontology/features_to_cac.py <case_id>
     * and refresh the page to see new cases in the selector.
     * ============================================================ */

    // ---------- Endpoints (only source of truth) ----------
    const API_CASES_URL = '/api/ontology/cases';
    const MAX_COMPARE_CASES = 200;
    /** Cases merged per tick when building client-side (fallback if /api/ontology/merged unavailable). */
    const BIG_BANG_FETCH_BATCH = 80;
    const UNIVERSE_FETCH_BATCH = 80;
    const ANALYSIS_FETCH_BATCH = 80;
    const COMPARE_MERGE_BATCH = 40;
    /** Full D3 re-layout every N merge batches (fewer = smoother; each paint restarts the simulation). */
    const MERGE_RENDER_EVERY_N_BATCHES = 2;
    const BANG_EXIT_DBLCLICK_MS = 320;

    // ---------- Runtime state ----------
    let COMPARE_POOL = [];           // Catalog metadata (Big Bang / lookup paths); not preloaded into UI
    let SESSION_CASES = [];          // Cases the user has loaded this session (chip tray)
    let BIG_BANG_POOL = [];          // Big Bang half-sample (pool=all)
    let UNIVERSE_POOL = [];          // Secret full corpus (pool=universe)
    let ANALYSIS_POOL = [];          // Bridge-dense 1000 (pool=analysis, big_bang.py)
    let DEFAULT_COMPARE_POOL = [];   // Restored after a corpus lookup
    let CORPUS_GRAPH_TOTAL = 0;      // Total graphs in universe (for labels)
    let GRAPH_MANIFEST = '';         // Invalidates stored merged graph when graphs change
    let CURRENT_CASE_ID = null;
    let MODE = 'single';
    let SELECTED_CASES = new Set();
    let BIG_BANG_MODE = false;
    let UNIVERSE_MODE = false;
    let ANALYSIS_MODE = false;
    let bangExitClickTimer = null;
    let universeExitClicks = 0;
    let universeExitTimer = null;
    const JSONLD_CACHE = Object.create(null);
    let CURRENT_FLAT_NODES = null;       // last unfiltered flat model for canvas filters
    let LOOKUP_CASE_IDS = [];            // last SPARQL ontology lookup hits
    let CORPUS_SOURCE = 'cases';         // 'cases' | 'pacer'
    let PACER_CATALOG = [];
    let PACER_MATCHES = [];
    let PACER_LOADED = []; // [{ id, path, flat }] accumulate in Compare Open
    const SPARQL_URL = (function resolveSparqlUrl() {
        // Local uvicorn has no Oxigraph unless OXIGRAPH_URL is set. Prefer the
        // public store so the Ontology & Graphs SPARQL panel works out of the box.
        // Deployed same-origin keeps /sparql (and its rate limits / proxy).
        try {
            const host = (window.location && window.location.hostname) || '';
            if (host === 'localhost' || host === '127.0.0.1') {
                return 'https://caselinker.up.railway.app/sparql';
            }
        } catch (_) { /* ignore */ }
        return '/sparql';
    })();
    const API_PACER_URL = '/api/ontology/pacer';

    // ---------- Vocabulary constants ----------
    const BASE_IRI           = 'https://caselinker.up.railway.app/resource/';
    const RDFS_LABEL         = 'http://www.w3.org/2000/01/rdf-schema#label';
    const CAC_HAS_CONFIDENCE = 'https://cacontology.projectvic.org/core#hasConfidence';
    const NLP_GRAPH_REGEX    = /\/graphs\/nlp$/;
    const RESERVED_KEYS      = new Set(['@id', '@type', '@context', '_isNlp']);

    const SPINE_COLORS = {
        EnduringEntity:   { fill: '#3b82f6', label: 'Enduring Entity', stroke: '#1d4ed8' },
        Event:            { fill: '#ef4444', label: 'Event',            stroke: '#b91c1c' },
        Role:             { fill: '#22c55e', label: 'Role',             stroke: '#15803d' },
        Phase:            { fill: '#a855f7', label: 'Phase',            stroke: '#7e22ce' },
        Situation:        { fill: '#f97316', label: 'Situation',        stroke: '#c2410c' },
        AssessmentResult: { fill: '#eab308', label: 'Assessment / NLP', stroke: '#a16207' },
        Unknown:          { fill: '#9ca3af', label: 'Other',            stroke: '#6b7280' }
    };

    // ---------- URI helpers ----------
    function localName(uri) {
        if (!uri) return uri;
        // Compact JSON-LD terms (cac:VictimRole) from PACER CASE-UCO graphs.
        if (typeof uri === 'string' && uri.includes(':') && !/^https?:\/\//i.test(uri) && !uri.startsWith('urn:')) {
            const c = uri.lastIndexOf(':');
            if (c > 0) return uri.slice(c + 1) || uri;
        }
        const h = uri.lastIndexOf('#'), s = uri.lastIndexOf('/');
        return uri.slice(Math.max(h, s) + 1) || uri;
    }
    function shortId(uri) {
        return uri && uri.startsWith(BASE_IRI) ? uri.slice(BASE_IRI.length) : localName(uri);
    }
    function shortPropKey(uri) {
        if (!uri || uri.startsWith('@')) return uri;
        return localName(uri);
    }
    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ---------- JSON-LD value unwrapping ----------
    function unwrapValue(v) {
        if (v == null) return null;
        if (typeof v === 'object' && '@value' in v) return v['@value'];
        if (typeof v === 'object' && '@id' in v)    return { '@id': v['@id'] };
        return v;
    }
    function firstLiteral(arr) {
        if (!Array.isArray(arr) || !arr.length) return null;
        const v = unwrapValue(arr[0]);
        return (v != null && typeof v !== 'object') ? v : null;
    }

    // ---------- Flatten rdflib Dataset (array of named graphs) ----------
    function mergeNamedGraphs(jsonLd) {
        if (!Array.isArray(jsonLd)) {
            return jsonLd['@graph'] ? jsonLd['@graph'] : [];
        }
        const nodeMap = {};
        jsonLd.forEach(namedGraph => {
            const isNlpGraph = NLP_GRAPH_REGEX.test(namedGraph['@id'] || '');
            (namedGraph['@graph'] || []).forEach(node => {
                if (!node['@id']) return;
                const id = node['@id'];
                if (!nodeMap[id]) {
                    nodeMap[id] = Object.assign({}, node);
                    nodeMap[id]._isNlp = isNlpGraph;
                    return;
                }
                const ex = nodeMap[id];
                Object.keys(node).forEach(k => {
                    if (k === '@id') return;
                    if (k === '@type') {
                        const ea = Array.isArray(ex[k]) ? ex[k] : (ex[k] ? [ex[k]] : []);
                        const na = Array.isArray(node[k]) ? node[k] : (node[k] ? [node[k]] : []);
                        ex[k] = [...new Set([...ea, ...na])];
                    } else if (!(k in ex)) {
                        ex[k] = node[k];
                    } else if (Array.isArray(ex[k]) && Array.isArray(node[k])) {
                        ex[k] = [...ex[k], ...node[k]];
                    }
                });
                if (isNlpGraph) ex._isNlp = true;
            });
        });
        return Object.values(nodeMap);
    }

    // ---------- Type-based helpers ----------
    function shortType(typeVal) {
        if (!typeVal) return 'Entity';
        const arr = Array.isArray(typeVal) ? typeVal : [typeVal];
        const SPINE_BASES = /^(EnduringEntity|Occurrent|Event|Role|Phase|Situation|OrganizationLikeEntity|DigitalSystemEntity|PersonLikeEntity|CustodialRelationship)$/;
        const domain = arr.find(t => !SPINE_BASES.test(localName(t)));
        return localName(domain || arr[0]);
    }
    function inferSpineBranch(node) {
        const s = (Array.isArray(node['@type']) ? node['@type'] : [node['@type'] || ''])
                    .map(localName).join(' ');
        if (/Phase/i.test(s))                                                              return 'Phase';
        if (/Role|Victim|Offender|Predator|Investigator/i.test(s))                         return 'Role';
        if (/AssessmentResult|Confidence|Classification|Sentence|PrisonSentence/i.test(s)) return 'AssessmentResult';
        if (/Situation|Pattern|Progression/i.test(s))                                      return 'Situation';
        if (/Event|Action|Operation|Offense|Incident|Abuse|Violation|Grooming|Sextortion|Production|Conspiracy|Investigation|CACInvestigation/i.test(s))
                                                                                           return 'Event';
        return 'EnduringEntity';
    }

    // ---------- Display label for a node ----------
    function nodeLabel(node) {
        const lbl = firstLiteral(node[RDFS_LABEL]);
        if (lbl) return String(lbl);

        const path = shortId(node['@id']);
        const st   = shortType(node['@type']);

        const conf = firstLiteral(node[CAC_HAS_CONFIDENCE]);
        if (conf != null) return 'Confidence: ' + conf;

        const ageKey = Object.keys(node).find(k => /ageEstimate|victimAge/.test(localName(k)));
        if (ageKey) {
            const age = firstLiteral(node[ageKey]);
            if (age != null) {
                if (path.includes('victim')) return 'Victim (age ' + age + ')';
                const n = (path.match(/offender\/(\d+)/) || [])[1] || '';
                return 'Offender' + (n ? ' ' + n : '') + ' (age ' + age + ')';
            }
        }

        if (path.includes('/nlp/') && !path.includes('/confidence')) return 'NLP\u2009·\u2009' + st;
        if (path.includes('/nlp/') &&  path.includes('/confidence')) return 'Confidence result';
        if (/^case\/[^/]+$/.test(path)) return 'Investigation: ' + path.replace('case/', '');

        // Path-based readable labels (fallback)
        const PATH_LABELS = {
            'role/victim/1':         'Victim (role)',
            'role/offender/1':       'Offender 1 (role)',
            'role/offender/2':       'Offender 2 (role)',
            'person/victim/1':       'Person: Victim',
            'person/offender/1':     'Person: Offender 1',
            'person/offender/2':     'Person: Offender 2',
            'event/production':      'CSAM Production',
            'event/csam':            'CSAM Incident',
            'event/hands-on':        'Contact Offense',
            'event/conspiracy':      'Conspiracy',
            'event/trust-violation': 'Custodial Abuse',
            'operation':             'Proactive Op.',
            'relationship/family':   'Family Relationship',
            'phase/convicted':       'Sentencing Phase',
            'phase/arrested':        'Arrest Phase',
            'facet/production':      'Content Facet',
            'facet/csam':            'Content Facet'
        };
        for (const [fragment, name] of Object.entries(PATH_LABELS)) {
            if (path.endsWith(fragment)) return name;
        }
        return st || path;
    }

    // ---------- Detail-panel value formatter ----------
    function formatPropertyValue(val, idToLabel) {
        if (val == null) return '—';
        if (typeof val === 'object' && '@value' in val) return String(val['@value']);
        if (typeof val === 'object' && '@id' in val) {
            return idToLabel[val['@id']] || shortId(val['@id']);
        }
        if (Array.isArray(val)) {
            return val.map(item => {
                if (item && typeof item === 'object' && '@id' in item)
                    return idToLabel[item['@id']] || shortId(item['@id']);
                if (item && typeof item === 'object' && '@value' in item)
                    return String(item['@value']);
                return String(item);
            }).join(', ');
        }
        return String(val);
    }

    // ---------- Build D3 nodes/links from a flat node array ----------
    // ``flatNodes`` is a deduplicated array of plain JSON-LD node objects
    // (each with @id, @type, properties). Node objects may also carry our
    // own bookkeeping fields ``_isNlp`` / ``_isShared`` / ``_cases``.
    function caseIdFromNodeUri(uri) {
        const m = String(uri || '').match(/\/case\/([^/#?]+)/);
        return m ? decodeURIComponent(m[1]) : null;
    }

    function annotateFlatNodesWithCase(flat, caseId) {
        if (!caseId || !Array.isArray(flat)) return flat;
        flat.forEach(n => {
            if (!Array.isArray(n._cases) || !n._cases.length) {
                n._cases = [caseId];
            }
        });
        return flat;
    }

    function resolveNodeCaseId(node) {
        if (node && node.cases && node.cases[0]) return node.cases[0];
        if (CURRENT_CASE_ID) return CURRENT_CASE_ID;
        if (node && node.raw && Array.isArray(node.raw._cases) && node.raw._cases[0]) {
            return node.raw._cases[0];
        }
        return caseIdFromNodeUri(node && (node.id || (node.raw && node.raw['@id'])));
    }

    function buildGraphModel(flatNodes) {
        const idSet     = new Set(flatNodes.map(n => n['@id']).filter(Boolean));
        const idToLabel = {};
        flatNodes.forEach(n => { if (n['@id']) idToLabel[n['@id']] = nodeLabel(n); });

        const nodes = flatNodes.filter(n => n['@id']).map(n => {
            const types     = Array.isArray(n['@type']) ? n['@type'] : (n['@type'] ? [n['@type']] : []);
            const isInvNode = types.some(t => /CACInvestigation/.test(localName(t)))
                              || /\/case\/[^/]+$/.test(n['@id']);
            let cases = Array.isArray(n._cases) ? n._cases.slice() : [];
            // Single-case loads historically omitted ``_cases`` (Compare stamps
            // them in mergeAcrossCases). Fall back so Open case text works.
            if (!cases.length && CURRENT_CASE_ID) cases = [CURRENT_CASE_ID];
            if (!cases.length) {
                const fromUri = caseIdFromNodeUri(n['@id']);
                if (fromUri) cases = [fromUri];
            }
            return {
                id:        n['@id'],
                label:     nodeLabel(n),
                spine:     inferSpineBranch(n),
                isNlp:     !!n._isNlp || n['@id'].includes('/nlp/'),
                isShared:  !!n._isShared,
                cases:     cases,
                isInvestigation: isInvNode,
                raw:       n,
                shortType: shortType(n['@type'])
            };
        });

        const links = [];
        flatNodes.forEach(srcNode => {
            const sid = srcNode['@id'];
            if (!sid) return;
            Object.keys(srcNode).forEach(key => {
                if (RESERVED_KEYS.has(key)) return;
                const val = srcNode[key];
                const refs = [];
                if (val && typeof val === 'object' && val['@id']) refs.push(val);
                else if (Array.isArray(val)) val.forEach(item => {
                    if (item && typeof item === 'object' && item['@id']) refs.push(item);
                });
                refs.forEach(ref => {
                    if (idSet.has(ref['@id'])) {
                        links.push({
                            source:   sid,
                            target:   ref['@id'],
                            property: shortPropKey(key),
                            id:       sid + '|' + key + '|' + ref['@id']
                        });
                    }
                });
            });
        });

        const degree = {};
        nodes.forEach(n => { degree[n.id] = 0; });
        links.forEach(l => {
            degree[l.source] = (degree[l.source] || 0) + 1;
            degree[l.target] = (degree[l.target] || 0) + 1;
        });
        nodes.forEach(n => {
            n.degree = degree[n.id] || 0;
            // Base radius from degree, then bump for special roles.
            let r = 7 + Math.min(n.degree * 1.8, 14);
            if (n.isShared)         r = Math.max(r * 1.5, 16);
            if (n.isInvestigation)  r = Math.max(r * 1.2, 14);
            n.radius = r;
        });
        return { nodes, links, idToLabel };
    }

    // Legacy single-case entry: takes a single JSON-LD doc (Dataset or
    // single-graph form), merges its named graphs, and returns the model.
    function parseJsonLdGraph(jsonLd) {
        const flat = mergeNamedGraphs(jsonLd);
        annotateFlatNodesWithCase(flat, CURRENT_CASE_ID);
        CURRENT_FLAT_NODES = flat;
        return buildGraphModel(flat);
    }

    // ---------- Cross-case merging ----------
    // Given { case_id: jsonLd, ... }, return a deduplicated flat node array
    // where each node carries ``_cases`` (the case IDs that referenced it)
    // and ``_isShared`` (true when ``_cases.length > 1``).
    function mergeAcrossCases(perCaseJsonLd) {
        const merged = Object.create(null);  // @id -> node
        const order  = Object.keys(perCaseJsonLd);

        for (const caseId of order) {
            const flat = mergeNamedGraphs(perCaseJsonLd[caseId]);
            for (const node of flat) {
                const nid = node['@id'];
                if (!nid) continue;
                if (!merged[nid]) {
                    // Clone shallowly so we don't mutate stored JSON-LD docs.
                    const copy = Object.assign({}, node);
                    if (Array.isArray(node['@type'])) {
                        copy['@type'] = node['@type'].slice();
                    }
                    copy._cases = [caseId];
                    copy._isNlp = !!node._isNlp;
                    merged[nid] = copy;
                    continue;
                }
                const ex = merged[nid];
                // Track case lineage.
                if (!ex._cases.includes(caseId)) ex._cases.push(caseId);
                if (node._isNlp) ex._isNlp = true;
                // Merge keys.
                Object.keys(node).forEach(k => {
                    if (k === '@id' || k === '_cases' || k === '_isNlp') return;
                    if (k === '@type') {
                        const ea = Array.isArray(ex[k]) ? ex[k] : (ex[k] ? [ex[k]] : []);
                        const na = Array.isArray(node[k]) ? node[k] : (node[k] ? [node[k]] : []);
                        ex[k] = [...new Set([...ea, ...na])];
                        return;
                    }
                    if (!(k in ex)) { ex[k] = node[k]; return; }
                    // Both have the key: if arrays, dedupe by id+value.
                    if (Array.isArray(ex[k]) && Array.isArray(node[k])) {
                        const seen = new Set(ex[k].map(serializeRdfTerm));
                        for (const item of node[k]) {
                            const key = serializeRdfTerm(item);
                            if (!seen.has(key)) { ex[k].push(item); seen.add(key); }
                        }
                    }
                });
            }
        }

        const flat = Object.values(merged);
        flat.forEach(n => { n._isShared = (n._cases.length > 1); });
        return flat;
    }

    function createFlatStore() {
        return Object.create(null);
    }

    function flatStoreToArray(store) {
        return Object.values(store).map(n => {
            n._isShared = (n._cases && n._cases.length > 1);
            return n;
        });
    }

    function mergeOneCaseIntoStore(store, caseId, jsonLd) {
        const flat = mergeNamedGraphs(jsonLd);
        for (const node of flat) {
            const nid = node['@id'];
            if (!nid) continue;
            if (!store[nid]) {
                const copy = Object.assign({}, node);
                if (Array.isArray(node['@type'])) copy['@type'] = node['@type'].slice();
                copy._cases = [caseId];
                copy._isNlp = !!node._isNlp;
                store[nid] = copy;
                continue;
            }
            const ex = store[nid];
            if (!ex._cases.includes(caseId)) ex._cases.push(caseId);
            if (node._isNlp) ex._isNlp = true;
            Object.keys(node).forEach(k => {
                if (k === '@id' || k === '_cases' || k === '_isNlp') return;
                if (k === '@type') {
                    const ea = Array.isArray(ex[k]) ? ex[k] : (ex[k] ? [ex[k]] : []);
                    const na = Array.isArray(node[k]) ? node[k] : (node[k] ? [node[k]] : []);
                    ex[k] = [...new Set([...ea, ...na])];
                    return;
                }
                if (!(k in ex)) { ex[k] = node[k]; return; }
                if (Array.isArray(ex[k]) && Array.isArray(node[k])) {
                    const seen = new Set(ex[k].map(serializeRdfTerm));
                    for (const item of node[k]) {
                        const key = serializeRdfTerm(item);
                        if (!seen.has(key)) { ex[k].push(item); seen.add(key); }
                    }
                }
            });
        }
    }

    const LS_MERGED_PREFIX = 'caselinker-patterns-merged:';
    const LS_CATALOG_KEY = 'caselinker-patterns-catalog-compare';
    const LS_CATALOG_ALL_KEY = 'caselinker-patterns-catalog-all';
    const LS_CATALOG_UNIVERSE_KEY = 'caselinker-patterns-catalog-universe';
    const LS_CATALOG_ANALYSIS_KEY = 'caselinker-patterns-catalog-analysis';
    const LS_MODE_KEY = 'caselinker-patterns-mode';
    const LS_GRAPH_PREFIX = 'caselinker-patterns-graph:';
    let CASE_SELECTOR_WIRED = false;

    function loadLocalMerged(pool, manifest) {
        if (!manifest) return null;
        try {
            const raw = localStorage.getItem(LS_MERGED_PREFIX + pool + ':' + manifest);
            if (!raw) return null;
            const flat = JSON.parse(raw);
            return Array.isArray(flat) && flat.length ? flat : null;
        } catch (_) { return null; }
    }

    function saveLocalMerged(pool, manifest, flatNodes) {
        if (!manifest || !flatNodes || !flatNodes.length) return;
        try {
            localStorage.setItem(LS_MERGED_PREFIX + pool + ':' + manifest, JSON.stringify(flatNodes));
        } catch (_) { /* quota */ }
    }

    async function fetchServerMerged(pool) {
        const local = loadLocalMerged(pool, GRAPH_MANIFEST);
        if (local) {
            return { flat_nodes: local, n_cases: null, manifest: GRAPH_MANIFEST };
        }
        const resp = await fetch('/api/ontology/merged?pool=' + encodeURIComponent(pool), { cache: 'default' });
        if (!resp.ok) return null;
        const payload = await resp.json();
        if (payload.flat_nodes && payload.flat_nodes.length) {
            saveLocalMerged(pool, payload.manifest || GRAPH_MANIFEST, payload.flat_nodes);
        }
        return payload;
    }

    async function renderMergedWithProgress(caseEntries, pool, titleLabel) {
        const titleEl = document.getElementById('case-title');
        ensureGraphSvg();

        // Pre-merged payload is only valid for the full pool (200 or Big Bang).
        // Hand-picked 2–199 must merge client-side from selected JSON-LD only.
        const useServerMerge =
            pool === 'all' ||
            pool === 'universe' ||
            pool === 'analysis' ||
            (pool === 'compare' && caseEntries.length >= COMPARE_POOL.length);
        const merged = useServerMerge ? await fetchServerMerged(pool) : null;
        if (merged && merged.flat_nodes && merged.flat_nodes.length) {
            const n = merged.n_cases || caseEntries.length;
            titleEl.textContent = titleLabel + ' · ' + n + ' cases';
            if (pool === 'compare') setTitleCompare(merged.flat_nodes, caseEntries.map(c => c.case_id));
            renderGraphFromFlat(merged.flat_nodes);
            return;
        }

        const store = createFlatStore();
        const total = caseEntries.length;
        const batchSize =
            pool === 'analysis' ? ANALYSIS_FETCH_BATCH :
            pool === 'universe' ? UNIVERSE_FETCH_BATCH :
            pool === 'all' ? BIG_BANG_FETCH_BATCH :
            COMPARE_MERGE_BATCH;
        let loaded = 0;
        let firstPaint = false;
        let batchIndex = 0;

        for (let i = 0; i < total; i += batchSize) {
            const batch = caseEntries.slice(i, i + batchSize);
            const docs = await Promise.all(batch.map(c => fetchCase(c)));
            batch.forEach((c, j) => mergeOneCaseIntoStore(store, c.case_id, docs[j]));
            loaded += batch.length;
            batchIndex += 1;
            const flat = flatStoreToArray(store);
            titleEl.textContent = titleLabel + ' · ' + loaded + ' / ' + total + ' cases…';
            const shouldPaint =
                flat.length &&
                (batchIndex === 1 ||
                    batchIndex % MERGE_RENDER_EVERY_N_BATCHES === 0 ||
                    loaded >= total);
            if (shouldPaint) {
                if (pool === 'compare' && loaded >= 2) setTitleCompare(flat, caseEntries.slice(0, loaded).map(c => c.case_id));
                renderGraphFromFlat(flat);
                firstPaint = true;
            }
            await new Promise(resolve => requestAnimationFrame(resolve));
        }

        const finalFlat = flatStoreToArray(store);
        titleEl.textContent = titleLabel + ' · ' + total + ' cases merged';
        if (pool === 'compare') setTitleCompare(finalFlat, caseEntries.map(c => c.case_id));
        renderGraphFromFlat(finalFlat);
        if (!firstPaint && !finalFlat.length) {
            showCompareEmpty('No graph data loaded.');
        }
    }


    function serializeRdfTerm(v) {
        if (v && typeof v === 'object') {
            if ('@id' in v)    return 'id:' + v['@id'];
            if ('@value' in v) return 'v:' + (v['@type'] || '') + ':' + v['@value'];
        }
        return 'lit:' + String(v);
    }

    // ---------- Legend ----------
    function buildLegend() {
        const el = document.getElementById('legend');
        const order = ['EnduringEntity','Event','Role','Phase','Situation','AssessmentResult','Unknown'];
        el.innerHTML = order.map(key => {
            const c = SPINE_COLORS[key];
            return '<span class="legend-item"><span class="legend-swatch" style="background:' + c.fill + '"></span>' + c.label + '</span>';
        }).join('') +
        '<span class="legend-item"><span class="legend-swatch" style="background:transparent;border:2px dashed #eab308"></span>NLP-derived</span>' +
        '<span class="legend-item"><span class="legend-swatch" style="background:transparent;border:2.5px solid #f59e0b"></span>Shared across cases</span>';
    }

    // ---------- Detail panel ----------
    function showNodeDetail(node, idToLabel) {
        const placeholder = document.getElementById('detail-placeholder');
        const content     = document.getElementById('detail-content');
        placeholder.style.display = 'none';
        content.style.display     = 'block';

        const spine  = node.spine;
        const colors = SPINE_COLORS[spine] || SPINE_COLORS.Unknown;
        const raw    = node.raw;
        const SKIP_KEYS = new Set(['@id', '@type', '_isNlp', '_isShared', '_cases']);
        let rows = '';
        Object.keys(raw).sort().forEach(key => {
            if (SKIP_KEYS.has(key)) return;
            rows += '<tr><th>' + escapeHtml(shortPropKey(key)) + '</th><td>' +
                    escapeHtml(formatPropertyValue(raw[key], idToLabel)) + '</td></tr>';
        });
        const typeStr  = Array.isArray(raw['@type']) ? raw['@type'].map(shortType).join(', ') : (raw['@type'] || '');
        const nlpBadge    = node.isNlp    ? '<span class="spine-badge" style="background:#b45309;margin-left:6px">NLP</span>' : '';
        const sharedBadge = node.isShared
            ? '<span class="spine-badge" style="background:#f59e0b;color:#1f2937;margin-left:6px">Shared · ' + node.cases.length + '</span>'
            : '';

        const sharedBlock = (node.isShared && node.cases && node.cases.length > 1)
            ? '<p style="margin-top:10px;font-size:0.85rem;color:var(--text-dim,#6b7280)">' +
              '<span style="font-weight:600;color:#f59e0b">Shared across:</span> ' +
              node.cases.map(escapeHtml).join(', ') + '</p>'
            : '';

        const typeHint = shortType(raw['@type']);
        const openCaseId = resolveNodeCaseId(node);
        const actions =
            '<div class="detail-actions">' +
              '<button type="button" class="btn" id="detail-find-similar" data-type="' +
                escapeHtml(typeHint) + '">Find similar cases</button>' +
              (openCaseId
                ? '<button type="button" class="btn" id="detail-open-case" data-case="' +
                  escapeHtml(openCaseId) + '">Open case text</button>'
                : '') +
            '</div>';

        content.innerHTML =
            '<p class="node-heading">' + escapeHtml(node.label) + '</p>' +
            '<p class="node-type">' + escapeHtml(typeStr) + '</p>' +
            '<span class="spine-badge" style="background:' + colors.fill + '">' +
                escapeHtml(colors.label) + '</span>' + nlpBadge + sharedBadge +
            sharedBlock +
            actions +
            (rows ? '<table class="prop-table"><tbody>' + rows + '</tbody></table>' : '');

        const similarBtn = document.getElementById('detail-find-similar');
        if (similarBtn) {
            similarBtn.addEventListener('click', () => {
                const t = similarBtn.getAttribute('data-type') || '';
                if (!t) return;
                const classSelect = document.getElementById('lookup-class');
                const opts = Array.from(classSelect.options);
                const match = opts.find(o => o.value && localName(o.value) === t);
                if (match) classSelect.value = match.value;
                else {
                    // Fall back: filter canvas by type substring.
                    document.getElementById('filter-type').value = t;
                    applyCanvasFilter();
                    setLookupStatus('Filtered canvas to type containing “' + t + '”.');
                    return;
                }
                runOntologyLookup();
            });
        }
        const openBtn = document.getElementById('detail-open-case');
        if (openBtn) {
            openBtn.addEventListener('click', () => {
                window.open(caseVizUrl(openBtn.getAttribute('data-case')), '_blank', 'noopener');
            });
        }
    }

    // ---------- D3 force-directed render ----------
    function ensureGraphSvg() {
        let container = document.getElementById('graph-container');
        // If an empty/error state replaced our SVG, rebuild the SVG element.
        if (!document.getElementById('graph-svg')) {
            container.innerHTML =
                '<svg id="graph-svg"></svg>' +
                '<div class="graph-hint">Drag nodes · scroll to zoom · click nodes to add paths · click background to clear</div>' +
                '<div id="edge-tooltip" class="edge-tooltip"></div>';
        }
        return container;
    }

    function renderGraph(jsonLd) {
        // Accept either a raw JSON-LD document or a pre-merged sentinel
        // ``{ __preMerged: flatNodes }`` produced by Compare mode.
        const model = (jsonLd && Array.isArray(jsonLd.__preMerged))
            ? buildGraphModel(jsonLd.__preMerged)
            : parseJsonLdGraph(jsonLd);
        const { nodes, links, idToLabel } = model;
        const container = ensureGraphSvg();
        const width  = container.clientWidth;
        const height = container.clientHeight;

        const svg = d3.select('#graph-svg');
        svg.selectAll('*').remove();
        svg.attr('viewBox', [0, 0, width, height]);

        const g = svg.append('g');
        svg.call(d3.zoom().scaleExtent([0.01, 16]).on('zoom', event => g.attr('transform', event.transform)));

        const linkData = links.map(l => ({ ...l }));
        const nodeData = nodes.map(n => ({ ...n }));

        const simulation = d3.forceSimulation(nodeData)
            .force('link',      d3.forceLink(linkData).id(d => d.id).distance(72).strength(0.55))
            .force('charge',    d3.forceManyBody().strength(-420))
            .force('center',    d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(d => d.radius + 6));

        const defs = svg.append('defs');
        linkData.forEach((link, i) => {
            const markerId = 'arrow-' + i;
            defs.append('marker')
                .attr('id', markerId)
                .attr('viewBox', '0 -4 8 8')
                .attr('refX', 14).attr('refY', 0)
                .attr('markerWidth', 6).attr('markerHeight', 6)
                .attr('orient', 'auto')
                .append('path')
                .attr('d', 'M0,-4L8,0L0,4')
                .attr('fill', 'rgba(148,163,184,0.75)');
            link.markerId = markerId;
        });

        const selectedIds = new Set();
        function setHighlight() {
            const neighborIds = new Set();
            if (selectedIds.size > 0) {
                selectedIds.forEach(activeId => {
                    neighborIds.add(activeId);
                    linkData.forEach(l => {
                        const sid = typeof l.source === 'object' ? l.source.id : l.source;
                        const tid = typeof l.target === 'object' ? l.target.id : l.target;
                        if (sid === activeId) neighborIds.add(tid);
                        if (tid === activeId) neighborIds.add(sid);
                    });
                });
            }
            const hasSelection = selectedIds.size > 0;
            nodeSel.attr('opacity', d => !hasSelection || neighborIds.has(d.id) ? 1 : 0.2);
            nodeSel.select('circle.node-disc').attr('stroke-width', d => {
                if (!selectedIds.has(d.id)) {
                    if (d.isShared) return 3.5;
                    if (d.isNlp) return 2.5;
                    return 2;
                }
                return d.isShared ? 4.5 : 3.5;
            });
            linkSel.attr('stroke-opacity', d => {
                if (!hasSelection) return 0.55;
                const sid = typeof d.source === 'object' ? d.source.id : d.source;
                const tid = typeof d.target === 'object' ? d.target.id : d.target;
                return (selectedIds.has(sid) || selectedIds.has(tid)) ? 0.95 : 0.08;
            });
            labelSel.attr('opacity', d => !hasSelection || neighborIds.has(d.id) ? 1 : 0.15);
        }

        const linkSel = g.append('g').attr('class', 'links')
            .selectAll('line').data(linkData).enter().append('line')
            .attr('stroke', 'rgba(148,163,184,0.7)')
            .attr('stroke-width', 1.2)
            .attr('marker-end', d => 'url(#' + d.markerId + ')')
            .on('mouseenter', function(event, d) {
                const tip = document.getElementById('edge-tooltip');
                tip.textContent = d.property;
                tip.style.display = 'block';
                tip.style.left = (event.offsetX + 12) + 'px';
                tip.style.top  = (event.offsetY -  8) + 'px';
                d3.select(this).attr('stroke', '#fbbf24').attr('stroke-width', 2);
            })
            .on('mousemove', function(event) {
                const tip = document.getElementById('edge-tooltip');
                tip.style.left = (event.offsetX + 12) + 'px';
                tip.style.top  = (event.offsetY -  8) + 'px';
            })
            .on('mouseleave', function() {
                document.getElementById('edge-tooltip').style.display = 'none';
                d3.select(this).attr('stroke', 'rgba(148,163,184,0.7)').attr('stroke-width', 1.2);
            });

        const nodeSel = g.append('g').attr('class', 'nodes')
            .selectAll('g').data(nodeData).enter().append('g')
            .style('cursor', 'pointer')
            .call(d3.drag()
                .on('start', (event, d) => {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
                .on('end', (event, d) => {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null; d.fy = null;
                }));

        nodeSel.append('circle')
            .attr('class', 'node-disc')
            .attr('r', d => d.radius)
            .attr('fill',   d => (SPINE_COLORS[d.spine] || SPINE_COLORS.Unknown).fill)
            .attr('stroke', d => {
                if (d.isShared) return '#f59e0b';
                if (d.isNlp)    return '#fbbf24';
                return (SPINE_COLORS[d.spine] || SPINE_COLORS.Unknown).stroke;
            })
            .attr('stroke-width', d => {
                if (d.isShared) return 3.5;
                if (d.isNlp)    return 2.5;
                return 2;
            })
            .attr('stroke-dasharray', d => d.isNlp && !d.isShared ? '4 2' : null)
            .on('click', (event, d) => {
                event.stopPropagation();
                if (selectedIds.has(d.id)) {
                    selectedIds.delete(d.id);
                } else {
                    selectedIds.add(d.id);
                }
                setHighlight();
                showNodeDetail(d, idToLabel);
            });

        // Bridge badge: small circle with the share count, only on shared nodes.
        nodeSel.filter(d => d.isShared)
            .append('g').attr('class', 'shared-marker')
            .each(function(d) {
                const sel = d3.select(this);
                const offset = d.radius * 0.78;
                sel.append('circle')
                    .attr('cx', offset).attr('cy', -offset)
                    .attr('r', 8)
                    .attr('fill', '#f59e0b')
                    .attr('stroke', '#1a2332')
                    .attr('stroke-width', 1.5)
                    .attr('pointer-events', 'none');
                sel.append('text')
                    .text(d.cases.length)
                    .attr('x', offset).attr('y', -offset + 3.5)
                    .attr('text-anchor', 'middle')
                    .attr('font-size', '10px')
                    .attr('font-weight', '700')
                    .attr('font-family', "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif")
                    .attr('fill', '#1f2937')
                    .attr('pointer-events', 'none');
            });

        const labelSel = nodeSel.append('text')
            .text(d => d.label.length > 22 ? d.label.slice(0, 20) + '\u2026' : d.label)
            .attr('x', d => d.radius + 5).attr('y', 4)
            .attr('fill', 'rgba(255,255,255,0.92)')
            .attr('font-size', '10px')
            .attr('font-family', "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif")
            .attr('pointer-events', 'none');

        // Investigation nodes get a subtle case-id sub-label only when more
        // than one investigation is present (Compare mode).
        const investigationCount = nodeData.filter(d => d.isInvestigation).length;
        if (investigationCount > 1) {
            nodeSel.filter(d => d.isInvestigation)
                .append('text')
                .text(d => (d.cases && d.cases[0]) ? d.cases[0] : '')
                .attr('x', d => d.radius + 5).attr('y', 18)
                .attr('fill', 'rgba(251,191,36,0.85)')
                .attr('font-size', '9px')
                .attr('font-family', "'SFMono-Regular', Consolas, 'Liberation Mono', monospace")
                .attr('pointer-events', 'none');
        }

        svg.on('click', () => {
            selectedIds.clear();
            setHighlight();
            document.getElementById('detail-placeholder').style.display = 'block';
            document.getElementById('detail-content').style.display = 'none';
        });

        simulation.on('tick', () => {
            linkSel.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                   .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
            nodeSel.attr('transform', d => 'translate(' + d.x + ',' + d.y + ')');
        });

        window.addEventListener('resize', () => {
            const w = container.clientWidth, h = container.clientHeight;
            svg.attr('viewBox', [0, 0, w, h]);
            simulation.force('center', d3.forceCenter(w / 2, h / 2));
            simulation.alpha(0.3).restart();
        });
    }

    // ---------- Title rendering ----------
    function setTitleSingle(jsonLd, caseId) {
        const titleEl = document.getElementById('case-title');
        const flat = mergeNamedGraphs(jsonLd);
        const inv = flat.find(n => n['@id'] && /\/case\/[^/]+$/.test(n['@id']));
        let label = caseId;
        if (inv) {
            const src = firstLiteral(inv['http://purl.org/dc/terms/source']);
            const id  = firstLiteral(inv['http://purl.org/dc/terms/identifier']);
            const yr  = firstLiteral(inv['https://cacontology.projectvic.org#hasPhaseBeginPoint']);
            if (src || id) {
                const year = (yr || '').slice(0, 4);
                label = src ? src + (year ? ' ' + year : '') : (id || caseId);
            }
        }
        titleEl.textContent = 'Knowledge Graph: ' + label + ' · ' + flat.length + ' nodes  (' + caseId + ')';
    }

    function setTitleCompare(flatNodes, caseIds) {
        const titleEl = document.getElementById('case-title');
        const sharedCount = flatNodes.filter(n => n._isShared).length;
        titleEl.textContent =
            'Knowledge Graph: ' + caseIds.length + ' cases · ' +
            sharedCount + ' shared node' + (sharedCount === 1 ? '' : 's') +
            '  (' + caseIds.join(', ') + ')';
    }

    // ---------- Selector rendering ----------
    // Build the URL that opens this case in Audit.
    // Relative path so it works locally and on the deployed Railway host.
    function caseVizUrl(caseId) {
        return '/audit?case=' + encodeURIComponent(caseId);
    }

    function loadCachedCatalog() {
        try {
            const raw = sessionStorage.getItem(LS_CATALOG_KEY);
            if (!raw) return null;
            const payload = JSON.parse(raw);
            return payload && Array.isArray(payload.cases) ? payload : null;
        } catch (_) {
            return null;
        }
    }

    function saveCachedCatalog(payload) {
        try {
            sessionStorage.setItem(LS_CATALOG_KEY, JSON.stringify(payload));
        } catch (_) { /* quota */ }
    }

    function applyCatalogPayload(payload) {
        COMPARE_POOL = Array.isArray(payload.cases) ? payload.cases : [];
        CORPUS_GRAPH_TOTAL = payload.corpus_total || COMPARE_POOL.length;
        GRAPH_MANIFEST = payload.graph_manifest || '';
        BIG_BANG_POOL = [];
        UNIVERSE_POOL = [];
        ANALYSIS_POOL = [];
        const bangBtnEl = document.getElementById('big-bang-btn');
        if (bangBtnEl) {
            bangBtnEl.title = 'Merge Big Bang half-sample (' + (CORPUS_GRAPH_TOTAL ? '~' + Math.round(CORPUS_GRAPH_TOTAL / 2) : '?') + ' graphs)';
        }
    }

    function wireCaseSelectorOnce() {
        if (CASE_SELECTOR_WIRED) return;
        CASE_SELECTOR_WIRED = true;
        const modeToggle = document.getElementById('mode-toggle');
        if (modeToggle) {
            modeToggle.addEventListener('click', (ev) => {
                const modeBtn = ev.target.closest('button[data-mode]');
                if (!modeBtn) return;
                setMode(modeBtn.dataset.mode);
            });
            modeToggle.addEventListener('dblclick', (ev) => {
                const compareTab = ev.target.closest('button[data-mode="compare"]');
                if (!compareTab) return;
                ev.preventDefault();
                toggleSelectAll();
            });
        }
        const sel = document.getElementById('case-selector');
        if (!sel) return;
        sel.addEventListener('click', (ev) => {
            const link = ev.target.closest('.chip-link');
            if (link) {
                ev.stopPropagation();
                const chip = link.closest('.case-chip');
                if (chip) window.open(caseVizUrl(chip.dataset.caseId), '_blank', 'noopener');
                return;
            }
            const chip = ev.target.closest('.case-chip');
            if (!chip || BIG_BANG_MODE || UNIVERSE_MODE || ANALYSIS_MODE) return;
            const entry = SESSION_CASES.find(c => c.case_id === chip.dataset.caseId)
                || COMPARE_POOL.find(c => c.case_id === chip.dataset.caseId);
            if (entry) onChipClick(entry);
        });
    }

    function rememberSessionCases(entries) {
        (entries || []).forEach(e => {
            if (!e || !e.case_id) return;
            if (!SESSION_CASES.some(c => c.case_id === e.case_id)) SESSION_CASES.push(e);
            if (!COMPARE_POOL.some(c => c.case_id === e.case_id)) COMPARE_POOL.push(e);
        });
        renderCaseSelector(SESSION_CASES);
    }

    function renderCaseSelector(cases) {
        const sel = document.getElementById('case-selector');
        wireCaseSelectorOnce();
        sel.querySelectorAll('.case-chip').forEach(c => c.remove());
        const frag = document.createDocumentFragment();
        cases.forEach(c => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'case-chip';
            btn.dataset.caseId = c.case_id;
            const idSpan = document.createElement('span');
            idSpan.className = 'chip-id';
            idSpan.textContent = c.case_id;
            const link = document.createElement('span');
            link.className = 'chip-link';
            link.textContent = '\u2197';
            link.setAttribute('role', 'link');
            link.setAttribute('aria-label', 'Open ' + c.case_id + ' in Audit');
            link.title = 'Open ' + c.case_id + ' in Audit';
            btn.appendChild(idSpan);
            btn.appendChild(link);
            frag.appendChild(btn);
        });
        sel.appendChild(frag);
        sel.hidden = CORPUS_SOURCE === 'pacer' || cases.length === 0;
        syncChipState();
    }

    function cacheKeyForCase(caseId) {
        return LS_GRAPH_PREFIX + (GRAPH_MANIFEST || 'v0') + ':' + caseId;
    }

    function loadCachedGraph(caseId) {
        try {
            const raw = sessionStorage.getItem(cacheKeyForCase(caseId));
            return raw ? JSON.parse(raw) : null;
        } catch (_) {
            return null;
        }
    }

    function saveCachedGraph(caseId, jsonLd) {
        try {
            sessionStorage.setItem(cacheKeyForCase(caseId), JSON.stringify(jsonLd));
        } catch (_) { /* quota — drop oldest graph entries if needed */ }
    }

    // Reflects current MODE + selection state in the chip DOM.
    function syncChipState() {
        const sel = document.getElementById('case-selector');
        sel.classList.toggle('compare-mode', MODE === 'compare');
        document.querySelectorAll('#mode-toggle button').forEach(b => {
            const active = b.dataset.mode === MODE;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        document.querySelectorAll('#case-selector .case-chip').forEach(c => {
            const cid = c.dataset.caseId;
            const active = (MODE === 'compare')
                ? SELECTED_CASES.has(cid)
                : (cid === CURRENT_CASE_ID);
            c.classList.toggle('active', active);
        });
    }

    function onChipClick(caseEntry) {
        if (BIG_BANG_MODE || UNIVERSE_MODE || ANALYSIS_MODE) return;
        if (MODE === 'single') {
            if (caseEntry.case_id === CURRENT_CASE_ID) return;
            loadAndRenderSingle(caseEntry);
            return;
        }
        // Compare mode: toggle membership.
        const cid = caseEntry.case_id;
        if (SELECTED_CASES.has(cid)) SELECTED_CASES.delete(cid);
        else                          SELECTED_CASES.add(cid);
        syncChipState();
        refreshCompareView().then(() => syncOpenButtons());
    }

    function setMode(newMode) {
        if (newMode !== 'single' && newMode !== 'compare') return;
        if (newMode === MODE) return;
        MODE = newMode;
        try {
            sessionStorage.setItem(LS_MODE_KEY, MODE);
        } catch (_) { /* ignore */ }
        if (newMode === 'compare') {
            // Seed selection with the case the user was last viewing.
            SELECTED_CASES = new Set(CURRENT_CASE_ID ? [CURRENT_CASE_ID] : []);
            syncChipState();
            refreshCompareView();
        } else {
            SELECTED_CASES.clear();
            BIG_BANG_MODE = false;
            UNIVERSE_MODE = false;
            ANALYSIS_MODE = false;
            const bangBtn = document.getElementById('big-bang-btn');
            if (bangBtn) {
                bangBtn.classList.remove('active');
                bangBtn.textContent = 'Big Bang';
            }
            const target = SESSION_CASES.find(c => c.case_id === CURRENT_CASE_ID)
                        || SESSION_CASES[0]
                        || (CURRENT_CASE_ID ? caseEntryFromId(CURRENT_CASE_ID) : null);
            syncChipState();
            if (target) loadAndRenderSingle(target);
            else showPressReleaseIdle();
        }
    }

    // ---------- Loading ----------
    async function fetchCase(caseEntry) {
        if (JSONLD_CACHE[caseEntry.case_id]) {
            return JSONLD_CACHE[caseEntry.case_id];
        }
        const cached = loadCachedGraph(caseEntry.case_id);
        if (cached) {
            JSONLD_CACHE[caseEntry.case_id] = cached;
            return cached;
        }
        const resp = await fetch(caseEntry.path, { cache: 'default' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status + ' for ' + caseEntry.case_id);
        const data = await resp.json();
        JSONLD_CACHE[caseEntry.case_id] = data;
        saveCachedGraph(caseEntry.case_id, data);
        return data;
    }

    async function loadAndRenderSingle(caseEntry) {
        CURRENT_CASE_ID = caseEntry.case_id;
        try {
            sessionStorage.setItem('caselinker-patterns-last-case', caseEntry.case_id);
        } catch (_) { /* ignore */ }
        syncChipState();
        try {
            const jsonLd = await fetchCase(caseEntry);
            setTitleSingle(jsonLd, caseEntry.case_id);
            renderGraph(jsonLd);
        } catch (err) {
            console.error('Failed to load graph', caseEntry, err);
            showLoadError(caseEntry.case_id, err);
        }
        syncOpenButtons();
    }

    async function refreshCompareView() {
        if (BIG_BANG_MODE || UNIVERSE_MODE || ANALYSIS_MODE) return;
        const selected = SESSION_CASES.filter(c => SELECTED_CASES.has(c.case_id));
        const titleEl = document.getElementById('case-title');

        if (selected.length === 0) {
            titleEl.textContent = 'Compare mode · select cases from search or chips';
            showCompareEmpty('Search and load cases, then select two or more to compare.');
            syncOpenButtons();
            return;
        }
        if (selected.length === 1) {
            titleEl.textContent = 'Compare mode · ' + selected[0].case_id + ' (select another to compare)';
            showCompareEmpty('Select two or more cases to see cross-case connections.');
            syncOpenButtons();
            return;
        }
        if (selected.length > MAX_COMPARE_CASES) {
            titleEl.textContent = 'Too many cases selected (' + selected.length + ')';
            showCompareEmpty(
                'Select up to ' + MAX_COMPARE_CASES + ' cases from the stratified pool. ' +
                'Use Big Bang below to merge the full corpus slice.'
            );
            syncOpenButtons();
            return;
        }

        try {
            await renderMergedWithProgress(selected, 'compare', 'Compare');
        } catch (err) {
            console.error('Failed to load compare graphs', selected, err);
            showLoadError(selected.map(c => c.case_id).join(', '), err);
        }
        syncOpenButtons();
    }

    function resetToCompareUi() {
        BIG_BANG_MODE = false;
        UNIVERSE_MODE = false;
        ANALYSIS_MODE = false;
        universeExitClicks = 0;
        if (universeExitTimer) {
            clearTimeout(universeExitTimer);
            universeExitTimer = null;
        }
        const btn = document.getElementById('big-bang-btn');
        if (btn) {
            btn.classList.remove('active');
            btn.textContent = 'Big Bang';
            btn.disabled = false;
        }
        SELECTED_CASES.clear();
        syncChipState();
        if (MODE === 'compare') refreshCompareView();
        else if (SESSION_CASES[0]) loadAndRenderSingle(SESSION_CASES[0]);
        else showPressReleaseIdle();
    }

    async function loadCatalogPool(pool, storageKey) {
        let payload = null;
        try {
            const raw = sessionStorage.getItem(storageKey);
            if (raw) payload = JSON.parse(raw);
        } catch (_) { /* ignore */ }
        if (!payload || !Array.isArray(payload.cases) || !payload.cases.length) {
            const resp = await fetch(API_CASES_URL + '?pool=' + encodeURIComponent(pool), { cache: 'default' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            payload = await resp.json();
            try {
                sessionStorage.setItem(storageKey, JSON.stringify(payload));
            } catch (_) { /* quota */ }
        }
        if (payload.corpus_total) CORPUS_GRAPH_TOTAL = payload.corpus_total;
        if (payload.graph_manifest) GRAPH_MANIFEST = payload.graph_manifest;
        return payload;
    }

    async function enterBigBang() {
        const btn = document.getElementById('big-bang-btn');
        BIG_BANG_MODE = true;
        UNIVERSE_MODE = false;
        ANALYSIS_MODE = false;
        MODE = 'compare';
        btn.classList.add('active');
        btn.textContent = 'Exit Big Bang';
        btn.disabled = true;
        syncChipState();
        const titleEl = document.getElementById('case-title');
        titleEl.textContent = 'Big Bang · loading catalog…';
        showCompareEmpty('Loading Big Bang sample…');

        try {
            if (!BIG_BANG_POOL.length) {
                const payload = await loadCatalogPool('all', LS_CATALOG_ALL_KEY);
                BIG_BANG_POOL = Array.isArray(payload.cases) ? payload.cases : [];
            }
            if (!BIG_BANG_POOL.length) {
                showCompareEmpty('No graphs in graph_output/big_bang yet. Run graph generation first.');
                resetToCompareUi();
                return;
            }
            showCompareEmpty('Big Bang · building corpus graph…');
            await renderMergedWithProgress(BIG_BANG_POOL, 'all', 'Big Bang');
            restoreGraphChrome();
        } catch (err) {
            console.error('Big Bang merge failed', err);
            resetToCompareUi();
            showLoadError('big-bang', err);
        } finally {
            btn.disabled = false;
        }
    }

    async function activateUniverse() {
        if (bangExitClickTimer) {
            clearTimeout(bangExitClickTimer);
            bangExitClickTimer = null;
        }
        const btn = document.getElementById('big-bang-btn');
        BIG_BANG_MODE = false;
        UNIVERSE_MODE = true;
        ANALYSIS_MODE = false;
        MODE = 'compare';
        btn.classList.add('active');
        btn.textContent = 'Exit Universe';
        btn.disabled = true;
        syncChipState();
        const titleEl = document.getElementById('case-title');
        titleEl.textContent = 'Universe · loading catalog…';
        showCompareEmpty('Loading full universe…');

        try {
            if (!UNIVERSE_POOL.length) {
                const payload = await loadCatalogPool('universe', LS_CATALOG_UNIVERSE_KEY);
                UNIVERSE_POOL = Array.isArray(payload.cases) ? payload.cases : [];
            }
            if (!UNIVERSE_POOL.length) {
                showCompareEmpty('No graphs in graph_output/universe yet.');
                resetToCompareUi();
                return;
            }
            showCompareEmpty('Universe · building full graph…');
            await renderMergedWithProgress(UNIVERSE_POOL, 'universe', 'Universe');
            restoreGraphChrome();
        } catch (err) {
            console.error('Universe merge failed', err);
            resetToCompareUi();
            showLoadError('universe', err);
        } finally {
            btn.disabled = false;
        }
    }

    async function activateAnalysis() {
        if (universeExitTimer) {
            clearTimeout(universeExitTimer);
            universeExitTimer = null;
        }
        universeExitClicks = 0;
        const btn = document.getElementById('big-bang-btn');
        BIG_BANG_MODE = false;
        UNIVERSE_MODE = false;
        ANALYSIS_MODE = true;
        MODE = 'compare';
        btn.classList.add('active');
        btn.textContent = 'Exit Analysis';
        btn.disabled = true;
        syncChipState();
        const titleEl = document.getElementById('case-title');
        titleEl.textContent = 'Analysis · loading catalog…';
        showCompareEmpty('Loading analysis graphs…');

        try {
            if (!ANALYSIS_POOL.length) {
                const payload = await loadCatalogPool('analysis', LS_CATALOG_ANALYSIS_KEY);
                ANALYSIS_POOL = Array.isArray(payload.cases) ? payload.cases : [];
            }
            if (!ANALYSIS_POOL.length) {
                showCompareEmpty(
                    'No graphs in graph_output/analysis yet. Run big_bang.py --target 1000 then populate_analysis_graphs.py'
                );
                resetToCompareUi();
                return;
            }
            showCompareEmpty('Analysis · building curated graph…');
            await renderMergedWithProgress(ANALYSIS_POOL, 'analysis', 'Analysis');
            restoreGraphChrome();
        } catch (err) {
            console.error('Analysis merge failed', err);
            resetToCompareUi();
            showLoadError('analysis', err);
        } finally {
            btn.disabled = false;
        }
    }

    function handleBangButtonClick() {
        const btn = document.getElementById('big-bang-btn');

        if (ANALYSIS_MODE) {
            resetToCompareUi();
            return;
        }

        if (UNIVERSE_MODE) {
            universeExitClicks += 1;
            if (universeExitTimer) clearTimeout(universeExitTimer);
            if (universeExitClicks >= 3) {
                universeExitClicks = 0;
                activateAnalysis();
                return;
            }
            universeExitTimer = setTimeout(() => {
                universeExitTimer = null;
                if (universeExitClicks === 1) resetToCompareUi();
                universeExitClicks = 0;
            }, BANG_EXIT_DBLCLICK_MS);
            return;
        }

        if (BIG_BANG_MODE) {
            if (bangExitClickTimer) {
                clearTimeout(bangExitClickTimer);
                bangExitClickTimer = null;
                activateUniverse();
                return;
            }
            bangExitClickTimer = setTimeout(() => {
                bangExitClickTimer = null;
                resetToCompareUi();
            }, BANG_EXIT_DBLCLICK_MS);
            return;
        }

        enterBigBang();
    }

    function activateBigBang() {
        handleBangButtonClick();
    }

    function restoreGraphChrome() {
        const container = document.getElementById('graph-container');
        if (!container.querySelector('#graph-svg')) {
            container.innerHTML =
                '<svg id="graph-svg"></svg>' +
                '<div class="graph-hint">Scroll to zoom &middot; Drag nodes to rearrange &middot; Hover edges for labels</div>' +
                '<div class="edge-tooltip" id="edge-tooltip"></div>';
        }
    }

    // Allow renderGraph to accept either a JSON-LD doc or a pre-merged flat array.
    function renderGraphFromFlat(flatNodes) {
        // Preserve case lineage when Single-mode filters rebuild from flat nodes.
        annotateFlatNodesWithCase(flatNodes, CURRENT_CASE_ID);
        CURRENT_FLAT_NODES = Array.isArray(flatNodes) ? flatNodes : null;
        renderGraph({ __preMerged: flatNodes });
    }

    function setLookupStatus(msg) {
        const el = document.getElementById('lookup-status');
        if (el) el.textContent = msg || '';
    }

    function sparqlEscape(s) {
        return String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }

    function resolveClassIri(value) {
        if (!value) return null;
        if (/^https?:\/\//i.test(value) || value.startsWith('urn:')) return value;
        // Prefer legal-outcomes module for known sentencing/distribution classes.
        const LEGAL = new Set([
            'CSAM_Distribution', 'SentencingPhase', 'SentencingHearing', 'CriminalSentence',
            'PrisonSentence', 'ProbationSentence', 'PreTrialPhase', 'TrialPhase',
            'MandatoryMinimumSentencing', 'LifeImprisonmentSentence'
        ]);
        if (LEGAL.has(value)) {
            return 'https://cacontology.projectvic.org/legal-outcomes#' + value;
        }
        return 'https://cacontology.projectvic.org#' + value;
    }

    function buildOntologyLookupQuery(opts) {
        const classIri = opts.classIri ? resolveClassIri(opts.classIri) : null;
        const parts = [
            'PREFIX cac: <https://cacontology.projectvic.org#>',
            'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>',
            'PREFIX dcterms: <http://purl.org/dc/terms/>',
            'SELECT DISTINCT ?caseId WHERE {',
            '  ?inv a cac:CACInvestigation ; dcterms:identifier ?caseId .'
        ];
        if (classIri) {
            parts.push('  ?node a <' + classIri + '> .');
            parts.push('  { ?inv ?p1 ?node } UNION { ?node ?p2 ?inv } UNION {');
            parts.push('    ?inv ?p3 ?mid . ?mid ?p4 ?node');
            parts.push('  } .');
        }
        if (opts.platform) {
            parts.push('  ?plat rdfs:label ?platLabel .');
            parts.push('  FILTER(CONTAINS(LCASE(STR(?platLabel)), "' + sparqlEscape(opts.platform.toLowerCase()) + '"))');
            parts.push('  { ?inv ?rp ?plat } UNION { ?ev ?rp2 ?plat . ?inv ?rs ?ev } .');
        }
        if (opts.agency) {
            parts.push('  ?agency rdfs:label ?agencyLabel .');
            parts.push('  FILTER(CONTAINS(LCASE(STR(?agencyLabel)), "' + sparqlEscape(opts.agency.toLowerCase()) + '"))');
            parts.push('  { ?inv ?ra ?agency } UNION { ?x ?ra2 ?agency . ?inv ?rx ?x } .');
        }
        parts.push('}');
        parts.push('LIMIT 80');
        return parts.join('\n');
    }

    async function runSparqlSelect(query) {
        const resp = await fetch(SPARQL_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/sparql-query',
                'Accept': 'application/sparql-results+json'
            },
            body: query
        });
        if (!resp.ok) {
            const text = await resp.text().catch(() => '');
            throw new Error('SPARQL HTTP ' + resp.status + (text ? ': ' + text.slice(0, 160) : ''));
        }
        return resp.json();
    }

    const SPARQL_PREFIX = [
        'PREFIX cac: <https://cacontology.projectvic.org#>',
        'PREFIX cac-multi: <https://cacontology.projectvic.org/multi-jurisdiction#>',
        'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>',
        ''
    ].join('\n');

    const SPARQL_EXAMPLES = {
        platforms: SPARQL_PREFIX + [
            'SELECT ?platform ?label (COUNT(DISTINCT ?case) AS ?cases)',
            'WHERE {',
            '  ?event cac:usesChannel ?platform .',
            '  ?platform rdfs:label ?label .',
            '  ?case a cac:CACInvestigation ; cac:hasStep ?event .',
            '}',
            'GROUP BY ?platform ?label',
            'ORDER BY DESC(?cases)',
            'LIMIT 8'
        ].join('\n'),
        investigations: SPARQL_PREFIX + [
            'SELECT (COUNT(DISTINCT ?inv) AS ?n)',
            'WHERE {',
            '  GRAPH ?g {',
            '    ?inv a cac:CACInvestigation .',
            '  }',
            '  FILTER(STRSTARTS(STR(?g), "https://caselinker.up.railway.app/resource/case/"))',
            '}'
        ].join('\n'),
        agencies: SPARQL_PREFIX + [
            'SELECT ?agency ?label (COUNT(DISTINCT ?case) AS ?cases)',
            'WHERE {',
            '  ?case a cac:CACInvestigation ; cac-multi:involvesAgency ?agency .',
            '  ?agency rdfs:label ?label .',
            '}',
            'GROUP BY ?agency ?label',
            'ORDER BY DESC(?cases)',
            'LIMIT 8'
        ].join('\n'),
        ask: SPARQL_PREFIX + 'ASK { ?s a cac:CACInvestigation }'
    };

    const SPARQL_LLM_PLACEHOLDER =
        'Ask in plain English, then press Generate.\n' +
        'Example: Which platforms appear in the most cases?';

    function looksLikeSparql(text) {
        return /^(PREFIX|BASE|SELECT|ASK|CONSTRUCT|DESCRIBE)\b/i.test((text || '').trim());
    }

    function setSparqlStatus(msg, isError) {
        const el = document.getElementById('sparql-status');
        if (!el) return;
        el.textContent = msg || '';
        el.classList.toggle('error', !!isError);
    }

    function sparqlCellValue(binding) {
        if (!binding) return '';
        if (binding.type === 'uri') {
            const v = binding.value || '';
            return localName(v) || v;
        }
        return binding.value != null ? String(binding.value) : '';
    }

    function renderSparqlResults(payload) {
        const box = document.getElementById('sparql-results');
        if (!box) return 0;
        box.innerHTML = '';
        if (payload && typeof payload.boolean === 'boolean') {
            box.innerHTML = '<div class="sparql-boolean">' +
                (payload.boolean ? 'true' : 'false') + '</div>';
            return 1;
        }
        const head = (payload && payload.head && payload.head.vars) || [];
        const rows = (payload && payload.results && payload.results.bindings) || [];
        if (!head.length) {
            box.textContent = 'No variables in result.';
            return 0;
        }
        const table = document.createElement('table');
        const thead = document.createElement('thead');
        const hr = document.createElement('tr');
        head.forEach(v => {
            const th = document.createElement('th');
            th.textContent = v;
            hr.appendChild(th);
        });
        thead.appendChild(hr);
        table.appendChild(thead);
        const tbody = document.createElement('tbody');
        rows.forEach(row => {
            const tr = document.createElement('tr');
            head.forEach(v => {
                const td = document.createElement('td');
                const full = row[v] && row[v].value != null ? String(row[v].value) : '';
                td.textContent = sparqlCellValue(row[v]);
                if (full && td.textContent !== full) td.title = full;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        box.appendChild(table);
        return rows.length;
    }

    async function runSparqlPanelQuery() {
        const ta = document.getElementById('sparql-query');
        const runBtn = document.getElementById('sparql-run');
        const query = ((ta && ta.value) || '').trim();
        if (!query) {
            setSparqlStatus('Enter a SELECT or ASK query.', true);
            return;
        }
        if (runBtn) runBtn.disabled = true;
        setSparqlStatus('Running…');
        const t0 = performance.now();
        try {
            const payload = await runSparqlSelect(query);
            const n = renderSparqlResults(payload);
            const ms = Math.round(performance.now() - t0);
            if (payload && typeof payload.boolean === 'boolean') {
                setSparqlStatus('ASK · ' + ms + ' ms');
            } else {
                setSparqlStatus(n + ' row' + (n === 1 ? '' : 's') + ' · ' + ms + ' ms');
            }
        } catch (err) {
            const box = document.getElementById('sparql-results');
            if (box) box.innerHTML = '';
            setSparqlStatus(err && err.message ? err.message : String(err), true);
        } finally {
            if (runBtn) runBtn.disabled = false;
        }
    }

    async function generateSparqlFromNl() {
        const ta = document.getElementById('sparql-query');
        const runBtn = document.getElementById('sparql-run');
        const question = ((ta && ta.value) || '').trim();
        if (!question) {
            setSparqlStatus('Describe what you want to query in plain English.', true);
            return;
        }
        if (runBtn) runBtn.disabled = true;
        setSparqlStatus('Generating SPARQL via Groq…');
        const box = document.getElementById('sparql-results');
        if (box) box.innerHTML = '';
        try {
            const resp = await fetch('/api/sparql/from-nl', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ question: question })
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                const detail = (data && data.detail) ? data.detail : ('HTTP ' + resp.status);
                throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
            }
            const sparql = (data && data.sparql) || '';
            if (!sparql.trim()) throw new Error('No SPARQL returned.');
            ta.value = sparql;
            ta.classList.remove('sparql-nl-mode');
            ta.spellcheck = false;
            const label = document.getElementById('sparql-query-label');
            if (label) label.textContent = 'Query';
            if (runBtn) runBtn.textContent = 'Run';
            setSparqlStatus(
                'SPARQL ready' +
                (data.kind ? ' (' + data.kind + ')' : '') +
                ' · press Run to execute'
            );
        } catch (err) {
            setSparqlStatus(err && err.message ? err.message : String(err), true);
        } finally {
            if (runBtn) runBtn.disabled = false;
        }
    }

    function wireSparqlUi() {
        const example = document.getElementById('sparql-example');
        const ta = document.getElementById('sparql-query');
        const runBtn = document.getElementById('sparql-run');
        const label = document.getElementById('sparql-query-label');
        if (!ta || !runBtn) return;

        const epLabel = document.getElementById('sparql-endpoint-label');
        if (epLabel) {
            epLabel.textContent = SPARQL_URL.indexOf('http') === 0
                ? 'caselinker.up.railway.app/sparql'
                : '/sparql';
        }

        function isLlmMode() {
            return example && example.value === 'llm';
        }

        function syncSparqlModeUi() {
            if (isLlmMode() && !looksLikeSparql(ta.value)) {
                ta.classList.add('sparql-nl-mode');
                ta.spellcheck = true;
                if (label) label.textContent = 'Question';
                runBtn.textContent = 'Generate';
            } else {
                ta.classList.remove('sparql-nl-mode');
                ta.spellcheck = false;
                if (label) label.textContent = 'Query';
                runBtn.textContent = 'Run';
            }
        }

        function loadExample() {
            const key = (example && example.value) || 'platforms';
            if (key === 'llm') {
                ta.value = '';
                ta.placeholder = SPARQL_LLM_PLACEHOLDER;
                setSparqlStatus('LLM mode: write a question, Generate → SPARQL, Run again to execute.');
            } else {
                ta.placeholder = '';
                ta.value = SPARQL_EXAMPLES[key] || SPARQL_EXAMPLES.platforms;
                setSparqlStatus('');
            }
            const box = document.getElementById('sparql-results');
            if (box) box.innerHTML = '';
            syncSparqlModeUi();
        }

        async function onSparqlRun() {
            if (isLlmMode() && !looksLikeSparql(ta.value)) {
                await generateSparqlFromNl();
                syncSparqlModeUi();
                return;
            }
            await runSparqlPanelQuery();
        }

        loadExample();
        if (example) example.addEventListener('change', loadExample);
        ta.addEventListener('input', () => {
            if (isLlmMode()) syncSparqlModeUi();
        });
        runBtn.addEventListener('click', () => { onSparqlRun(); });
        ta.addEventListener('keydown', (ev) => {
            if ((ev.metaKey || ev.ctrlKey) && ev.key === 'Enter') {
                ev.preventDefault();
                onSparqlRun();
            }
        });
    }

    async function runOntologyLookup() {
        const classIri = (document.getElementById('lookup-class') || {}).value || '';
        const className = classIri ? localName(classIri) : '';
        const platform = ((document.getElementById('lookup-platform') || {}).value || '').trim();
        const agency = ((document.getElementById('lookup-agency') || {}).value || '').trim();
        if (!className && !platform && !agency) {
            setLookupStatus('Pick a CAC class and/or enter platform or agency text.');
            return;
        }
        setLookupStatus('Searching mapped corpus…');
        const runBtn = document.getElementById('lookup-run');
        if (runBtn) runBtn.disabled = true;
        try {
            // Prefer the existing lookup API (pool-scoped). Platform/agency filter
            // case features server-side — do not join into one substring ``q``.
            const params = new URLSearchParams({ pool: 'universe', limit: '80' });
            if (className) params.set('class_name', className);
            if (platform) params.set('platform', platform);
            if (agency) params.set('agency', agency);
            let ids = [];
            let usedSparql = false;
            try {
                const resp = await fetch('/api/ontology/lookup?' + params.toString(), { cache: 'no-store' });
                if (resp.ok) {
                    const payload = await resp.json();
                    if (Array.isArray(payload.class_facets)) {
                        enrichLookupClassOptions(payload.class_facets);
                    }
                    ids = (payload.cases || []).map(c => c.case_id).filter(Boolean);
                    LOOKUP_CASE_IDS = ids;
                    // Keep catalog entries so Load can fetch paths from the API response.
                    (payload.cases || []).forEach(c => {
                        if (!COMPARE_POOL.some(x => x.case_id === c.case_id)) {
                            COMPARE_POOL.push(c);
                        }
                    });
                    setLookupStatus(
                        (payload.matched_case_count || ids.length) +
                        ' matches' +
                        (ids.length ? ' · ' + ids.length + ' listed' : '')
                    );
                } else {
                    throw new Error('HTTP ' + resp.status);
                }
            } catch (apiErr) {
                // Fall back to live SPARQL over the full Oxigraph corpus.
                usedSparql = true;
                setLookupStatus('API unavailable — trying SPARQL…');
                const payload = await runSparqlSelect(buildOntologyLookupQuery({
                    classIri: classIri || null,
                    platform: platform || null,
                    agency: agency || null
                }));
                const bindings = (payload.results && payload.results.bindings) || [];
                ids = bindings.map(b => b.caseId && b.caseId.value).filter(Boolean);
                LOOKUP_CASE_IDS = ids;
                setLookupStatus(ids.length
                    ? ids.length + ' SPARQL matches'
                    : 'No SPARQL matches.');
            }
            renderLookupResults(LOOKUP_CASE_IDS);
            if (!LOOKUP_CASE_IDS.length && !usedSparql) {
                setLookupStatus('No matches in universe pool.');
            }
        } catch (err) {
            console.error(err);
            setLookupStatus(err && err.message ? err.message : String(err));
            LOOKUP_CASE_IDS = [];
            renderLookupResults([]);
        } finally {
            if (runBtn) runBtn.disabled = false;
        }
    }

    function enrichLookupClassOptions(facets) {
        const select = document.getElementById('lookup-class');
        if (!select || !Array.isArray(facets) || !facets.length) return;
        const current = select.value;
        const known = new Set(Array.from(select.options).map(o => localName(o.value || o.textContent)));
        // API returns up to ~150 corpus class facets; do not truncate further here.
        facets.forEach(f => {
            const name = f.name || f;
            if (!name || known.has(name)) return;
            known.add(name);
            const opt = document.createElement('option');
            // Prefer CAC hash IRI when it looks like a top-level class; else bare local name for lookup API.
            opt.value = name;
            opt.textContent = name + (f.count != null ? ' (' + f.count + ')' : '');
            select.appendChild(opt);
        });
        select.value = current;
    }

    function isCaseOpenedOnCanvas(caseId) {
        if (!caseId) return false;
        if (CORPUS_SOURCE === 'pacer') {
            return PACER_LOADED.some(x => x.id === caseId);
        }
        if (MODE === 'compare') return SELECTED_CASES.has(caseId);
        return CURRENT_CASE_ID === caseId;
    }

    function styleOpenButton(btn, caseId) {
        if (!btn) return;
        const opened = isCaseOpenedOnCanvas(caseId);
        btn.textContent = opened ? 'Opened' : 'Open';
        btn.classList.toggle('opened', opened);
        btn.dataset.caseId = caseId;
    }

    function syncOpenButtons() {
        document.querySelectorAll('#lookup-results button[data-case-id], #pacer-results button[data-case-id]').forEach(btn => {
            styleOpenButton(btn, btn.dataset.caseId);
        });
    }

    function showCanvasIdleForCorpus() {
        if (CORPUS_SOURCE === 'pacer') {
            const titleEl = document.getElementById('case-title');
            if (titleEl) titleEl.textContent = 'PACER · CASE/UCO/CAC knowledge graphs';
            showCompareEmpty('Search Find cases, then Open or Load on graph.');
            return;
        }
        showPressReleaseIdle();
    }

    async function unopenLookupCase(caseId) {
        if (!caseId) return;
        if (MODE === 'compare') {
            SELECTED_CASES.delete(caseId);
            syncChipState();
            if (SELECTED_CASES.size === 0) {
                CURRENT_CASE_ID = null;
                CURRENT_FLAT_NODES = null;
                showCanvasIdleForCorpus();
            } else {
                await refreshCompareView();
            }
        } else if (CURRENT_CASE_ID === caseId) {
            CURRENT_CASE_ID = null;
            CURRENT_FLAT_NODES = null;
            SELECTED_CASES.clear();
            syncChipState();
            showCanvasIdleForCorpus();
        }
        setLookupStatus('Closed ' + caseId + '.');
        syncOpenButtons();
    }

    function unopenPacerCase(caseId) {
        if (!caseId) return;
        PACER_LOADED = PACER_LOADED.filter(x => x.id !== caseId);
        const status = document.getElementById('pacer-status');
        if (!PACER_LOADED.length) {
            CURRENT_FLAT_NODES = null;
            showCanvasIdleForCorpus();
            if (status) status.textContent = 'Closed ' + caseId + '.';
        } else {
            const flat = renderPacerLoaded(PACER_LOADED);
            if (status) status.textContent = 'Closed ' + caseId + ' · ' + PACER_LOADED.length + ' still open · ' + flat.length + ' nodes';
        }
        syncOpenButtons();
    }

    function toggleLookupCase(caseId) {
        if (isCaseOpenedOnCanvas(caseId)) unopenLookupCase(caseId);
        else loadLookupCases([caseId]);
    }

    function togglePacerCase(path, caseId) {
        if (isCaseOpenedOnCanvas(caseId)) unopenPacerCase(caseId);
        else openPacerPaths([path]);
    }

    function renderLookupResults(ids) {
        const ul = document.getElementById('lookup-results');
        if (!ul) return;
        ul.innerHTML = '';
        ids.slice(0, 40).forEach(id => {
            const li = document.createElement('li');
            const span = document.createElement('span');
            span.textContent = id;
            const btn = document.createElement('button');
            btn.type = 'button';
            styleOpenButton(btn, id);
            btn.addEventListener('click', () => toggleLookupCase(id));
            li.appendChild(span);
            li.appendChild(btn);
            ul.appendChild(li);
        });
    }

    function caseEntryFromId(caseId) {
        const known = COMPARE_POOL.concat(BIG_BANG_POOL, UNIVERSE_POOL, ANALYSIS_POOL)
            .find(c => c.case_id === caseId);
        if (known) return known;
        return {
            case_id: caseId,
            path: '/ontology/graph_output/universe/' + encodeURIComponent(caseId) + '.jsonld'
        };
    }

    async function loadLookupCases(ids) {
        const list = (ids && ids.length) ? ids : LOOKUP_CASE_IDS;
        if (!list.length) {
            setLookupStatus('Run a search first.');
            return;
        }
        CORPUS_SOURCE = 'cases';
        syncCorpusSourceUi();
        const capped = list.slice(0, MAX_COMPARE_CASES);
        setLookupStatus('Loading ' + capped.length + ' graphs…');
        BIG_BANG_MODE = false;
        UNIVERSE_MODE = false;
        ANALYSIS_MODE = false;
        const entries = capped.map(caseEntryFromId);
        rememberSessionCases(entries);

        // Open one at a time in Single.
        if (capped.length === 1 && MODE === 'single') {
            SELECTED_CASES.clear();
            syncChipState();
            try {
                await loadAndRenderSingle(entries[0]);
                setLookupStatus('Loaded ' + capped[0] + '.');
            } catch (err) {
                console.error(err);
                setLookupStatus(err && err.message ? err.message : String(err));
            }
            syncOpenButtons();
            return;
        }

        // Compare: Open adds one (or Load on graph adds all) into the selection.
        MODE = 'compare';
        try { sessionStorage.setItem(LS_MODE_KEY, MODE); } catch (_) { /* ignore */ }
        if (capped.length === 1) {
            SELECTED_CASES.add(capped[0]);
        } else {
            SELECTED_CASES = new Set(capped);
        }
        syncChipState();
        try {
            await refreshCompareView();
            setLookupStatus(
                capped.length === 1
                    ? 'Opened ' + capped[0] + ' in compare (' + SELECTED_CASES.size + ' selected).'
                    : 'Loaded ' + capped.length + ' cases.'
            );
        } catch (err) {
            console.error(err);
            setLookupStatus(err && err.message ? err.message : String(err));
        }
        syncOpenButtons();
    }

    function applyCanvasFilter() {
        if (!CURRENT_FLAT_NODES || !CURRENT_FLAT_NODES.length) {
            setLookupStatus('Load a graph before filtering the canvas.');
            return;
        }
        const spine = (document.getElementById('filter-spine') || {}).value || '';
        const typeQ = ((document.getElementById('filter-type') || {}).value || '').trim().toLowerCase();
        const sharedOnly = !!(document.getElementById('filter-shared') || {}).checked;

        const filtered = CURRENT_FLAT_NODES.filter(n => {
            const modelSpine = inferSpineBranch(n);
            if (spine && modelSpine !== spine) return false;
            if (sharedOnly && !n._isShared) return false;
            if (typeQ) {
                const types = Array.isArray(n['@type']) ? n['@type'] : (n['@type'] ? [n['@type']] : []);
                const hay = types.map(localName).join(' ').toLowerCase() + ' ' + nodeLabel(n).toLowerCase();
                if (!hay.includes(typeQ)) return false;
            }
            return true;
        });

        // Keep edges only among surviving nodes by rebuilding from the filtered set.
        const titleEl = document.getElementById('case-title');
        const prev = titleEl ? titleEl.textContent : '';
        renderGraph({ __preMerged: filtered });
        if (titleEl) {
            titleEl.textContent = prev + ' · filtered ' + filtered.length + '/' + CURRENT_FLAT_NODES.length;
        }
    }

    function clearCanvasFilter() {
        const spine = document.getElementById('filter-spine');
        const typeEl = document.getElementById('filter-type');
        const shared = document.getElementById('filter-shared');
        if (spine) spine.value = '';
        if (typeEl) typeEl.value = '';
        if (shared) shared.checked = false;
        if (CURRENT_FLAT_NODES) renderGraphFromFlat(CURRENT_FLAT_NODES);
    }

    function syncCorpusSourceUi() {
        document.querySelectorAll('#corpus-source-row .facet-chip').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.corpus === CORPUS_SOURCE);
        });
        const caseSec = document.getElementById('lookup-case-section');
        const pacerSec = document.getElementById('pacer-section');
        const bangBtn = document.getElementById('big-bang-btn');
        if (caseSec) caseSec.hidden = CORPUS_SOURCE !== 'cases';
        if (pacerSec) pacerSec.hidden = CORPUS_SOURCE !== 'pacer';
        if (bangBtn) bangBtn.style.display = CORPUS_SOURCE === 'pacer' ? 'none' : '';
        const sel = document.getElementById('case-selector');
        if (sel) sel.hidden = CORPUS_SOURCE === 'pacer' || SESSION_CASES.length === 0;
    }

    async function loadPacerCatalog() {
        const status = document.getElementById('pacer-status');
        if (status) status.textContent = 'Loading PACER catalog…';
        const resp = await fetch(API_PACER_URL, { cache: 'default' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const payload = await resp.json();
        PACER_CATALOG = Array.isArray(payload.investigations) ? payload.investigations : [];

        const classSelect = document.getElementById('pacer-class');
        if (classSelect) {
            const current = classSelect.value;
            const preferred = [
                'CACInvestigation', 'Investigation', 'CSAMIncident', 'OnlineGrooming',
                'CriminalCharge', 'FederalCharge', 'InvestigativeAction', 'CriminalProceeding',
                'Organization', 'Message', 'ChildVictim'
            ];
            const facets = Array.isArray(payload.class_facets) ? payload.class_facets : [];
            const names = new Set(facets.map(f => f.name));
            preferred.forEach(n => names.add(n));
            classSelect.innerHTML = '<option value="">Any</option>' +
                [...names].sort().map(n => '<option value="' + escapeHtml(n) + '">' + escapeHtml(n) + '</option>').join('');
            if (current) classSelect.value = current;
        }

        runPacerLookup();
    }

    function runPacerLookup() {
        const className = ((document.getElementById('pacer-class') || {}).value || '').trim();
        const platform = ((document.getElementById('pacer-platform') || {}).value || '').trim().toLowerCase();
        const agency = ((document.getElementById('pacer-agency') || {}).value || '').trim().toLowerCase();
        const status = document.getElementById('pacer-status');

        PACER_MATCHES = PACER_CATALOG.filter(item => {
            if (className) {
                const classes = item.classes || [];
                if (!classes.some(c => c.toLowerCase() === className.toLowerCase())) return false;
            }
            const hay = (item.search_text || '') + ' ' + (item.agencies || []).join(' ').toLowerCase();
            if (platform && !hay.includes(platform)) return false;
            if (agency && !hay.includes(agency)) return false;
            return true;
        });

        renderPacerResults(PACER_MATCHES);
        if (status) {
            status.textContent = PACER_MATCHES.length
                ? PACER_MATCHES.length + ' match' + (PACER_MATCHES.length === 1 ? '' : 'es')
                : 'No matches';
        }
    }

    function renderPacerResults(items) {
        const ul = document.getElementById('pacer-results');
        if (!ul) return;
        ul.innerHTML = '';
        items.slice(0, 40).forEach(item => {
            const li = document.createElement('li');
            const span = document.createElement('span');
            span.textContent = item.id;
            const btn = document.createElement('button');
            btn.type = 'button';
            styleOpenButton(btn, item.id);
            btn.addEventListener('click', () => togglePacerCase(item.path, item.id));
            li.appendChild(span);
            li.appendChild(btn);
            ul.appendChild(li);
        });
    }

    /** Flatten compact CASE-UCO @graph JSON-LD (PACER) into the same shape as CAC graphs. */
    function flattenCompactJsonLd(doc) {
        const graph = Array.isArray(doc)
            ? doc
            : (doc && Array.isArray(doc['@graph']) ? doc['@graph'] : []);
        return graph.filter(n => n && n['@id']).map(n => {
            const copy = Object.assign({}, n);
            copy._isNlp = false;
            copy._cases = copy._cases || [];
            return copy;
        });
    }

    async function fetchPacerFlat(path) {
        const resp = await fetch(path, { cache: 'default' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status + ' for ' + path);
        const doc = await resp.json();
        const id = path.split('/').pop().replace(/-investigation\.jsonld$/i, '') || path;
        return { id, path, flat: flattenCompactJsonLd(doc) };
    }

    function renderPacerLoaded(entries) {
        const store = createFlatStore();
        entries.forEach(({ id, flat }) => {
            mergeOneCaseIntoStore(store, id, [{ '@id': 'urn:pacer:' + id, '@graph': flat }]);
        });
        const flat = flatStoreToArray(store);
        const titleEl = document.getElementById('case-title');
        if (titleEl) {
            if (entries.length === 1) {
                titleEl.textContent = 'PACER · ' + entries[0].id + ' · ' + flat.length + ' nodes';
            } else {
                titleEl.textContent = 'PACER · ' + entries.length + ' graphs · ' + flat.length + ' nodes';
            }
        }
        renderGraphFromFlat(flat);
        return flat;
    }

    async function openPacerPaths(paths) {
        const status = document.getElementById('pacer-status');
        let list = (paths || []).filter(Boolean);
        if (!list.length) {
            if (status) status.textContent = 'Select a case.';
            return;
        }
        if (MODE === 'single') list = list.slice(0, 1);
        if (status) status.textContent = 'Loading ' + list.length + '…';
        try {
            const fetched = await Promise.all(list.map(fetchPacerFlat));
            if (MODE === 'single') {
                PACER_LOADED = fetched;
            } else {
                fetched.forEach(f => {
                    const ix = PACER_LOADED.findIndex(x => x.id === f.id);
                    if (ix >= 0) PACER_LOADED[ix] = f;
                    else PACER_LOADED.push(f);
                });
            }
            const flat = renderPacerLoaded(PACER_LOADED);
            if (status) {
                status.textContent = MODE === 'compare' && list.length === 1
                    ? 'Opened ' + fetched[0].id + ' in compare (' + PACER_LOADED.length + ' loaded).'
                    : 'Loaded ' + PACER_LOADED.length + ' · ' + flat.length + ' nodes';
            }
            syncOpenButtons();
        } catch (err) {
            console.error(err);
            if (status) status.textContent = err && err.message ? err.message : String(err);
        }
    }

    async function loadSelectedPacer() {
        const selected = PACER_MATCHES.map(i => i.path);
        if (!selected.length) {
            const status = document.getElementById('pacer-status');
            if (status) status.textContent = 'Run a search first.';
            return;
        }
        if (MODE === 'single' && selected.length > 1) {
            MODE = 'compare';
            try { sessionStorage.setItem(LS_MODE_KEY, MODE); } catch (_) { /* ignore */ }
            syncChipState();
        }
        // Load on graph replaces the canvas with the full match set (or one in Single).
        PACER_LOADED = [];
        let paths = selected;
        if (MODE === 'single') paths = selected.slice(0, 1);
        await openPacerPaths(paths);
    }

    function wireOntologyUi() {
        const run = document.getElementById('lookup-run');
        const load = document.getElementById('lookup-load');
        const apply = document.getElementById('filter-apply');
        const clear = document.getElementById('filter-clear');
        const pacerLoad = document.getElementById('pacer-load');
        const pacerSearch = document.getElementById('pacer-search');
        if (run) run.addEventListener('click', () => runOntologyLookup());
        if (load) load.addEventListener('click', () => loadLookupCases());
        if (apply) apply.addEventListener('click', () => applyCanvasFilter());
        if (clear) clear.addEventListener('click', () => clearCanvasFilter());
        if (pacerLoad) pacerLoad.addEventListener('click', () => loadSelectedPacer());
        if (pacerSearch) pacerSearch.addEventListener('click', () => runPacerLookup());

        document.getElementById('corpus-source-row')?.addEventListener('click', async (ev) => {
            const chip = ev.target.closest('.facet-chip');
            if (!chip) return;
            CORPUS_SOURCE = chip.dataset.corpus || 'cases';
            syncCorpusSourceUi();
            if (CORPUS_SOURCE === 'pacer') {
                try {
                    if (!PACER_CATALOG.length) await loadPacerCatalog();
                    document.getElementById('case-title').textContent =
                        'PACER · CASE/UCO/CAC knowledge graphs';
                } catch (err) {
                    document.getElementById('pacer-status').textContent =
                        err && err.message ? err.message : String(err);
                }
            } else if (SESSION_CASES.length) {
                if (MODE === 'compare') refreshCompareView();
                else if (CURRENT_CASE_ID) {
                    const entry = SESSION_CASES.find(c => c.case_id === CURRENT_CASE_ID) || SESSION_CASES[0];
                    if (entry) loadAndRenderSingle(entry);
                } else {
                    showPressReleaseIdle();
                }
            } else {
                showPressReleaseIdle();
            }
        });

        ['lookup-platform', 'lookup-agency', 'filter-type'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('keydown', (ev) => {
                if (ev.key !== 'Enter') return;
                if (id.startsWith('lookup')) runOntologyLookup();
                else applyCanvasFilter();
            });
        });
        ['pacer-platform', 'pacer-agency', 'pacer-class'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener(id === 'pacer-class' ? 'change' : 'keydown', (ev) => {
                if (id !== 'pacer-class' && ev.key !== 'Enter') return;
                runPacerLookup();
            });
        });
    }

    function showCompareEmpty(msg) {
        const container = document.getElementById('graph-container');
        container.innerHTML =
            '<div class="empty-state">' + escapeHtml(msg) + '</div>';
    }

    function showEmptyState() {
        const container = document.getElementById('graph-container');
        container.innerHTML =
            '<div class="empty-state">' +
              'No cases have been expressed as knowledge graphs yet.<br>' +
              'Run <code>python ontology/features_to_cac.py &lt;case_id&gt;</code> ' +
              'to generate graphs, then refresh this page.' +
            '</div>';
        document.getElementById('case-title').textContent = 'No graphs available';
    }

    function showLoadError(caseId, err) {
        const container = document.getElementById('graph-container');
        container.innerHTML =
            '<div class="empty-state">' +
              'Failed to load <code>' + escapeHtml(caseId) + '</code>:<br>' +
              escapeHtml(err && err.message ? err.message : String(err)) +
            '</div>';
    }

    // Double-click Compare: select / clear entire stratified 200 pool.
    function toggleSelectAll() {
        if (BIG_BANG_MODE || UNIVERSE_MODE || ANALYSIS_MODE) return;
        if (MODE !== 'compare') {
            MODE = 'compare';
            try { sessionStorage.setItem(LS_MODE_KEY, MODE); } catch (_) { /* ignore */ }
        }
        const poolIds = SESSION_CASES.map(c => c.case_id);
        if (poolIds.length === 0) return;
        if (SELECTED_CASES.size >= poolIds.length) {
            SELECTED_CASES.clear();
        } else {
            SELECTED_CASES = new Set(poolIds);
        }
        syncChipState();
        refreshCompareView();
    }

    function showPressReleaseIdle() {
        renderCaseSelector(SESSION_CASES);
        const titleEl = document.getElementById('case-title');
        if (titleEl) {
            titleEl.textContent = 'Press release · CASE/UCO/CAC knowledge graphs';
        }
        if (!SESSION_CASES.length) {
            showCompareEmpty(
                'Search Find cases, then Open or Load on graph. ' +
                'Use Compare to load and select multiple cases.'
            );
        }
    }

    async function fetchCompareCatalog() {
        const resp = await fetch(API_CASES_URL + '?pool=compare', { cache: 'default' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.json();
    }

    // ---------- Boot ----------
    async function boot() {
        buildLegend();
        wireCaseSelectorOnce();
        wireOntologyUi();
        wireSparqlUi();
        syncCorpusSourceUi();
        fetch('/api/ontology/lookup?pool=compare&limit=1')
            .then(resp => resp.ok ? resp.json() : null)
            .then(payload => {
                if (payload && payload.class_facets) enrichLookupClassOptions(payload.class_facets);
            })
            .catch(() => { /* graph remains usable */ });
        const bangBtn = document.getElementById('big-bang-btn');
        if (bangBtn) {
            bangBtn.addEventListener('click', () => activateBigBang());
        }

        try {
            const savedMode = sessionStorage.getItem(LS_MODE_KEY);
            if (savedMode === 'compare' || savedMode === 'single') MODE = savedMode;
        } catch (_) { /* ignore */ }
        syncChipState();

        const cachedCatalog = loadCachedCatalog();
        if (cachedCatalog) {
            applyCatalogPayload(cachedCatalog);
            DEFAULT_COMPARE_POOL = COMPARE_POOL.slice();
        }
        showPressReleaseIdle();

        try {
            const payload = await fetchCompareCatalog();
            applyCatalogPayload(payload);
            DEFAULT_COMPARE_POOL = COMPARE_POOL.slice();
            saveCachedCatalog(payload);
            if (CORPUS_SOURCE === 'cases' && !SESSION_CASES.length && !CURRENT_FLAT_NODES) {
                showPressReleaseIdle();
            }
        } catch (err) {
            console.error('Failed to fetch case list', err);
            if (!cachedCatalog) {
                document.getElementById('case-title').textContent =
                    'Could not reach ' + API_CASES_URL;
                showEmptyState();
            }
        }
    }

    boot();
    