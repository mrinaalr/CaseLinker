/* CaseLinker — shared shell: nav, fetch helpers, SPARQL runner, dereferencing.
   Pages include:  <div id="cl-nav" data-active="ask"></div>
   and this script (defer). Everything is exposed on window.CL. */
(function () {
  'use strict';

  var PROD = 'https://caselinker.up.railway.app';
  var W3ID = 'https://w3id.org/caselinker/resource/';

  var NAV = [
    { id: 'analysis',  href: '/analysis',       label: 'Analysis' },
    { id: 'graph',     href: '/patterns',       label: 'Graph' },
    { id: 'explore',   href: '/explore',        label: 'Explore' },
    { id: 'lifecycle', href: '/lifecycle',      label: 'State machines' },
    { id: 'platforms', href: '/visualization',  label: 'Affordances' },
    { id: 'search',    href: '/search',         label: 'Search' },
    { sep: true },
    { id: 'audit',     href: '/audit',          label: 'Audit' },
    { id: 'sources',   href: '/sources',        label: 'Sources' },
    { id: 'hood',      href: '/under-the-hood', label: 'Under the hood' }
  ];

  var MARK = '<svg class="cl-brand__mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<circle cx="9" cy="12" r="5.5" stroke="currentColor" stroke-width="1.6"/>' +
    '<circle cx="15" cy="12" r="5.5" stroke="currentColor" stroke-width="1.6"/>' +
    '</svg>';

  var GH = '<svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>';

  function renderNav() {
    var host = document.getElementById('cl-nav');
    if (!host) return;
    var active = host.getAttribute('data-active') || ''; if (active === 'ask') active = 'analysis';
    var links = NAV.map(function (n) {
      if (n.sep) return '<span class="sep" aria-hidden="true"></span>';
      var cur = n.id === active ? ' aria-current="page"' : '';
      return '<a href="' + n.href + '"' + cur + '>' + n.label + '</a>';
    }).join('');
    host.className = 'cl-nav';
    host.innerHTML =
      '<div class="cl-nav__inner">' +
        '<a class="cl-brand" href="/"><span class="cl-brand__case">Case</span><span class="cl-brand__linker">Linker</span></a>' +
        '<nav class="cl-nav__links" aria-label="Primary">' + links + '</nav>' +
        '<span class="cl-nav__spacer"></span>' +
        '<div class="cl-nav__right"><a href="/docs" title="OpenAPI">API</a><a href="https://github.com/mrinaalr/CaseLinker/blob/main/ontology/docs/SPARQL.md" rel="noopener" title="SPARQL guide">SPARQL</a><a class="cl-nav__gh" href="https://github.com/mrinaalr/CaseLinker" rel="noopener" title="GitHub" aria-label="GitHub">' + GH + '</a></div>' +
      '</div>';
  }

  /* ---------- tiny DOM helper ---------- */
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === 'class') node.className = v;
      else if (k === 'html') node.innerHTML = v;
      else if (k === 'text') node.textContent = v;
      else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), v);
      else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
      else node.setAttribute(k, v === true ? '' : v);
    });
    (Array.isArray(children) ? children : children == null ? [] : [children]).forEach(function (c) {
      if (c == null || c === false) return;
      node.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    });
    return node;
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function fmt(n) { return (n == null || isNaN(n)) ? '—' : Number(n).toLocaleString('en-US'); }

  var toastEl;
  function toast(msg, ms) {
    if (!toastEl) { toastEl = el('div', { class: 'cl-toast', role: 'status' }); document.body.appendChild(toastEl); }
    toastEl.textContent = msg; toastEl.classList.add('is-on');
    clearTimeout(toastEl._t); toastEl._t = setTimeout(function () { toastEl.classList.remove('is-on'); }, ms || 1800);
  }
  function copy(text, label) {
    return navigator.clipboard.writeText(text).then(function () { toast(label || 'Copied'); }, function () { toast('Copy failed'); });
  }

  /* ---------- fetch ---------- */
  function apiFetch(url, init) {
    return (window.caselinkerFetch || fetch)(url, init);
  }
  function json(url, init) {
    return apiFetch(url, init).then(function (r) {
      if (!r.ok) { var e = new Error('HTTP ' + r.status + ' ' + url); e.status = r.status; e.response = r; throw e; }
      return r.json();
    });
  }
  function isLocal() {
    var h = location.hostname; return h === 'localhost' || h === '127.0.0.1' || h === '[::1]';
  }

  /* ---------- SPARQL (local store first, live store when local has none) ---------- */
  var graphBase = null; // '' = same origin, PROD = live
  function sparqlOnce(base, query, accept) {
    return fetch(base + '/sparql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/sparql-query', 'Accept': accept || 'application/sparql-results+json' },
      body: query
    });
  }
  function sparql(query, opts) {
    opts = opts || {};
    var accept = opts.accept || 'application/sparql-results+json';
    var bases = graphBase === null ? ['', PROD] : [graphBase];
    var attempt = function (i) {
      if (i >= bases.length) return Promise.reject(new Error('No SPARQL store reachable.'));
      return sparqlOnce(bases[i], query, accept).then(function (r) {
        if ((r.status === 503 || r.status === 502) && i + 1 < bases.length && bases[i] === '') return attempt(i + 1);
        if (!r.ok) return r.text().then(function (t) { var e = new Error(t || ('HTTP ' + r.status)); e.status = r.status; throw e; });
        graphBase = bases[i];
        if (accept.indexOf('json') === -1) return r.text();
        return r.json().then(function (d) {
          if (d && d.status === 'waking' && d.retry && !opts._retried) {
            var wait = Math.min(8, Number(d.retry_after_seconds) || 3) * 1000;
            return new Promise(function (res) { setTimeout(res, wait); }).then(function () { return sparql(query, Object.assign({}, opts, { _retried: true })); });
          }
          return d;
        });
      }, function (err) {
        if (i + 1 < bases.length && bases[i] === '') return attempt(i + 1);
        throw err;
      });
    };
    return attempt(0);
  }
  function sparqlStoreLabel() { return graphBase === PROD ? 'live store (caselinker.up.railway.app)' : graphBase === '' ? 'this server' : 'store'; }

  /* ---------- Dereference a w3id resource as JSON-LD ---------- */
  function derefPath(path) {
    var p = String(path || '').replace(/^\/+/, '');
    var bases = graphBase === null ? ['', PROD] : [graphBase];
    var attempt = function (i) {
      if (i >= bases.length) return Promise.reject(new Error('No store reachable.'));
      return fetch(bases[i] + '/resource/' + p, { headers: { Accept: 'application/ld+json' } }).then(function (r) {
        if ((r.status === 503 || r.status === 502) && i + 1 < bases.length && bases[i] === '') return attempt(i + 1);
        if (r.status === 404) { var e = new Error('No description is stored for this IRI.'); e.status = 404; throw e; }
        if (!r.ok) { var e2 = new Error('HTTP ' + r.status); e2.status = r.status; throw e2; }
        graphBase = bases[i];
        return r.json();
      }, function (err) { if (i + 1 < bases.length && bases[i] === '') return attempt(i + 1); throw err; });
    };
    return attempt(0);
  }
  function iriToPath(iri) {
    if (!iri) return '';
    if (iri.indexOf(W3ID) === 0) return iri.slice(W3ID.length);
    var m = /\/resource\/(.+)$/.exec(iri); return m ? m[1] : iri;
  }
  function caseIdFromIri(iri) {
    var m = /\/resource\/case\/([^\/]+)/.exec(iri || ''); return m ? m[1] : null;
  }

  /* ---------- Case id suggestions ---------- */
  function suggestCases(q, limit) {
    var u = '/api/ontology/lookup?pool=full&q=' + encodeURIComponent(q || '') + '&limit=' + (limit || 12);
    return json(u).then(function (d) { return (d.cases || []).map(function (c) { return c.case_id; }); }).catch(function () { return []; });
  }
  function attachSuggest(input, onPick) {
    var box = el('div', { class: 'cl-suggest', role: 'listbox' });
    input.parentNode.style.position = 'relative';
    input.parentNode.appendChild(box);
    var t, items = [], idx = -1;
    function close() { box.innerHTML = ''; box.style.display = 'none'; items = []; idx = -1; }
    function render() {
      box.innerHTML = '';
      items.forEach(function (id, i) {
        box.appendChild(el('div', { class: 'cl-suggest__item' + (i === idx ? ' is-active' : ''), role: 'option', onmousedown: function (e) { e.preventDefault(); input.value = id; close(); onPick(id); } }, id));
      });
      box.style.display = items.length ? 'block' : 'none';
    }
    input.addEventListener('input', function () {
      clearTimeout(t); var q = input.value.trim();
      if (q.length < 2) return close();
      t = setTimeout(function () { suggestCases(q).then(function (ids) { items = ids; idx = -1; render(); }); }, 160);
    });
    input.addEventListener('keydown', function (e) {
      if (!items.length) return;
      if (e.key === 'ArrowDown') { idx = Math.min(items.length - 1, idx + 1); render(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { idx = Math.max(0, idx - 1); render(); e.preventDefault(); }
      else if (e.key === 'Enter' && idx >= 0) { input.value = items[idx]; close(); onPick(items[idx]); e.preventDefault(); }
      else if (e.key === 'Escape') close();
    });
    input.addEventListener('blur', function () { setTimeout(close, 120); });
  }

  var style = document.createElement('style');
  style.textContent = '.cl-suggest{display:none;position:absolute;left:0;right:0;top:calc(100% + 4px);background:var(--surface);border:1px solid var(--line-2);border-radius:8px;box-shadow:var(--shadow-2);z-index:40;max-height:260px;overflow:auto;padding:4px}' +
    '.cl-suggest__item{padding:7px 10px;font-family:var(--mono);font-size:12.5px;border-radius:5px;cursor:pointer}.cl-suggest__item:hover,.cl-suggest__item.is-active{background:var(--surface-2)}';
  document.head.appendChild(style);

  /* ---------- Narrative with highlighted passages ----------
     spans: [{ quote, start, end, id, label }]. Offsets are hints; the quote is
     located in the served text (nearest occurrence to the stated offset) so a
     re-masked or re-fetched narrative still highlights the right passage. */
  var textCache = {};
  function caseText(id) {
    if (textCache[id]) return textCache[id];
    textCache[id] = json('/api/cases/' + encodeURIComponent(id)).then(function (c) {
      // Localhost and trusted keys get raw_data.case_text; public callers get case_text_redacted (people masked).
      var t = (c.raw_data && c.raw_data.case_text) || c.case_text || c.case_text_redacted || '';
      return { id: id, text: String(t), source: c.source || '', url: c.source_url || '' };
    });
    return textCache[id];
  }
  function locate(text, span) {
    var q = span.quote == null ? '' : String(span.quote);
    var s = Number(span.start), e = Number(span.end);
    if (q && !isNaN(s) && text.slice(s, s + q.length) === q) return { start: s, end: s + q.length, exact: true };
    if (q) {
      var best = -1, i = text.indexOf(q);
      while (i >= 0) { if (best < 0 || Math.abs(i - s) < Math.abs(best - s)) best = i; i = text.indexOf(q, i + 1); }
      if (best >= 0) return { start: best, end: best + q.length, exact: false };
      var lower = text.toLowerCase(), ql = q.toLowerCase().replace(/\s+/g, ' ');
      var j = lower.replace(/\s+/g, ' ').indexOf(ql);
      if (j >= 0 && lower.length === text.length) return { start: j, end: j + ql.length, exact: false };
    }
    if (!isNaN(s) && !isNaN(e) && e > s && e <= text.length) return { start: s, end: e, exact: false, offsetOnly: true };
    return null;
  }
  function narrativeHtml(text, spans) {
    var marks = [];
    (spans || []).forEach(function (sp, i) {
      var loc = locate(text, sp); if (!loc) return;
      marks.push({ start: loc.start, end: loc.end, id: sp.id || ('sp' + i), label: sp.label || '', exact: loc.exact });
    });
    marks.sort(function (a, b) { return a.start - b.start || a.end - b.end; });
    var out = '', pos = 0, missed = (spans || []).length - marks.length;
    marks.forEach(function (m) {
      if (m.start < pos) return; // overlapping: keep the first
      out += esc(text.slice(pos, m.start));
      out += '<mark class="cl-mark" id="mk-' + esc(m.id) + '" data-span="' + esc(m.id) + '"' + (m.label ? ' title="' + esc(m.label) + '"' : '') + (m.exact ? '' : ' data-moved="1"') + '>' + esc(text.slice(m.start, m.end)) + '</mark>';
      pos = m.end;
    });
    out += esc(text.slice(pos));
    return { html: out, found: marks.length, missed: missed };
  }
  function narrativePanel(opts) {
    /* opts: { caseId, spans, title } → element with a header, a scrolling narrative and a jump API */
    var panel = el('section', { class: 'cl-narrative' });
    var head = el('div', { class: 'cl-narrative__head' }, [
      el('div', {}, [el('span', { class: 'cl-label' }, opts.title || 'Source text'), ' ', el('span', { class: 'cl-id' }, opts.caseId)]),
      el('div', { class: 'cl-narrative__meta', html: '<span class="cl-spinner"></span>' })
    ]);
    var body = el('div', { class: 'cl-narrative__body', tabindex: '0' });
    panel.appendChild(head); panel.appendChild(body);
    panel.jump = function (id) {
      var m = body.querySelector('#mk-' + CSS.escape(String(id)));
      Array.prototype.forEach.call(body.querySelectorAll('mark.is-on'), function (x) { x.classList.remove('is-on'); });
      if (!m) { toast('That passage is not in the served text'); return false; }
      m.classList.add('is-on');
      var top = m.offsetTop - body.clientHeight / 2 + m.offsetHeight / 2;
      body.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
      return true;
    };
    caseText(opts.caseId).then(function (c) {
      var r = narrativeHtml(c.text, opts.spans || []);
      body.innerHTML = '<pre class="cl-narrative__text">' + r.html + '</pre>';
      var meta = fmt(c.text.length) + ' chars';
      if (opts.spans && opts.spans.length) meta = r.found + ' of ' + opts.spans.length + ' passages located · ' + meta;
      if (r.missed > 0) meta += ' · ' + r.missed + ' not found in this copy of the text';
      head.querySelector('.cl-narrative__meta').innerHTML = esc(meta) + (c.url ? ' · <a href="' + esc(c.url) + '" rel="noopener" target="_blank">original</a>' : '');
      if (opts.onReady) opts.onReady(panel, r);
    }).catch(function (e) {
      body.innerHTML = '<div class="cl-notice cl-notice--warn">Source text unavailable: ' + esc(e.message) + '</div>';
      head.querySelector('.cl-narrative__meta').textContent = '';
    });
    return panel;
  }

  function qs(name) { return new URLSearchParams(location.search).get(name); }

  window.CL = {
    PROD: PROD, W3ID: W3ID, NAV: NAV,
    el: el, esc: esc, fmt: fmt, toast: toast, copy: copy, qs: qs,
    fetch: apiFetch, json: json, isLocal: isLocal,
    sparql: sparql, storeLabel: sparqlStoreLabel, deref: derefPath, iriToPath: iriToPath, caseIdFromIri: caseIdFromIri,
    suggestCases: suggestCases, attachSuggest: attachSuggest,
    caseText: caseText, narrativeHtml: narrativeHtml, narrativePanel: narrativePanel, locate: locate,
    get graphBase() { return graphBase; }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', renderNav); else renderNav();
})();
