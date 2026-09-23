# Press-release collector suite

This directory turns **any public press release** (a URL list or a DOJ News API harvest) into a structured **PDF** for CaseLinker. ICAC/CAC filters are optional gates, not the engine. This file is onboarding; extractors and DOJ API quirks are `PRESS_RELEASE_COLLECTION.md`.

## The pipeline, in one picture

```mermaid
flowchart LR
    A["Listing / search page<br/>(any agency newsroom)"] -->|"fetch_source_urls.py"| B["sources/urls.txt"]
    API["DOJ News API<br/>(no URL list yet)"] -->|"harvest_doj_press.py<br/>title terms + filters"| F["*_resolved.json<br/>mode: resolved"]
    B -->|"resolve_press_urls.py"| C{"justice.gov?"}
    C -->|"yes"| D["DOJ API slug match"]
    C -->|"no"| E["mode: scrape"]
    D --> F
    E --> F
    F -->|"build_press_pdf.py --doj-file"| G["merged PDF"]
    B -.->|"build_press_pdf.py --url-file<br/>(no justice.gov)"| G
    G --> H["filter / novelty"]
    H --> I["verify_cac.py<br/>ICAC topics only"]
    I --> J["ingest"]
```

The suite is **press-release → PDF**, not ICAC-only. Topic filters (`verify_cac.py`, PSC body regex, “child sexual” listing queries) are **optional gates** for the ICAC corpus. `build_press_pdf.py` will turn any public article URL - or any DOJ API resolved record - into the same `Title / Publication date / Source: https:// / body` layout.

Two things to notice:

1. **Discovery and PDF conversion are separate.** Empty/wrong inputs produce empty/wrong PDFs. HTML listings go through `fetch_source_urls.py`. DOJ **discovery** (you do not already have URLs) goes through `harvest_doj_press.py`. DOJ **resolution** of URLs you already have goes through `resolve_press_urls.py`.
2. **`resolve_press_urls.py` is a router, not a search harvester.** It looks up known `justice.gov` URLs in the API (max 6 pages / 300 hits per query). It will not page 14k “child pornography” titles. Use `harvest_doj_press.py` for that. Skip `resolve_press_urls.py` entirely when the url-file has no `justice.gov` links.

## Suite map

| File | Role |
|---|---|
| `build_press_pdf.py` | **The core engine.** Any press-release URL, or a `--doj-file` resolved record → one ReportLab page → merged PDF. Host extractors, Jina fallback, native `.pdf` via pdfplumber. Topic-agnostic. |
| `harvest_doj_press.py` | **DOJ API discovery.** Pages `parameters[title]` (newest first), optional body regex, optional CAC gate, stage collapse, novelty vs existing DOJ PDFs. Emits `--doj-file` JSON. Defaults are Project Safe Childhood; same script does fentanyl/fraud/etc. with flags. |
| `resolve_press_urls.py` | **DOJ API URL resolver.** You already have `justice.gov` URLs. Looks each one up (slug match, 6 pages max). Passes non-DOJ URLs through as `mode: scrape`. |
| `fetch_source_urls.py` | **Listing harvester.** HTML pages, Squarespace, Google CSE, search.usa.gov, WordPress REST (`--wordpress-rest`), optional `--via-jina`. Not the DOJ API. |
| `filter_merged_pdf.py` | Post-hoc noise filter from the per-URL `tmp/` cache. |
| `remove_pdf_pages_by_text.py` | Drop merged-PDF pages by regex / exact-text dedupe / page list. |
| `check_expand_novelty.py` | Dedup vs an existing merged PDF before append. |
| `sources/urls.txt` | Active URL list for `resolve_press_urls.py` / `build_press_pdf.py --url-file`. |
| `PRESS_RELEASE_COLLECTION.md` | Agent guide: extractors, DOJ API quirks, discovery vs resolve, troubleshooting. |

## Install

```bash
pip install requests beautifulsoup4 reportlab pypdf pdfplumber
```

## Quickstart

### You already have a list of article URLs

If none of them are `justice.gov`:

```bash
cd collector
python3 build_press_pdf.py --url-file sources/urls.txt \
  --out-dir ../.. --out-name MY_SOURCE_All.pdf --jina-fallback
```

If the list might include `justice.gov` URLs (DOJ press releases, USAO releases), route through `resolve_press_urls.py` first - this avoids the Akamai bot-wall entirely by using the DOJ API instead of scraping:

```bash
cd collector
python3 resolve_press_urls.py --url-file sources/urls.txt --out sources/urls_resolved.json
python3 build_press_pdf.py --doj-file sources/urls_resolved.json \
  --out-dir ../.. --out-name MIXED_BATCH_All.pdf
```

### You only have a listing/search page - no article URLs yet

Harvest first, then run either quickstart above on the resulting file:

```bash
cd collector
python3 fetch_source_urls.py \
  --url 'https://www.example.gov/search?q=trafficking' \
  --same-host --path-prefix /news/ \
  --require-any trafficking \
  --exclude /search --exclude /tag/ --exclude /feed/ \
  -o sources/example_trafficking_urls.txt

# WordPress REST (public HTML is an empty Next.js shell; KY SP pattern):
python3 fetch_source_urls.py \
  --wordpress-rest 'https://wp.kentuckystatepolice.ky.gov/wp-json/wp/v2/posts' \
  --wp-search 'child sexual' \
  --wp-public-host www.kentuckystatepolice.ky.gov \
  --wp-path-prefix /news/ \
  -o sources/ky_sp_urls.txt

python3 build_press_pdf.py --url-file sources/example_trafficking_urls.txt \
  --out-dir ../.. --out-name EXAMPLE_TRAFFICKING_All.pdf --jina-fallback
```

Smoke-test with `--limit 3` before running a full list. See `PRESS_RELEASE_COLLECTION.md` → "Canonical workflow" for the full step-by-step (verify one article in a browser, harvest hygiene, one-URL extractor probe) before scraping hundreds of URLs.

Australia (URL path, no DOJ API). Two CSEA newsrooms the suite already harvests:

```bash
# Australian Federal Police — HTML search, one release per result, paginated
python3 fetch_source_urls.py \
  --url-template 'https://www.afp.gov.au/search?keys=child+exploitation&content_type_id=1&page={page}' \
  --page-range 0:1 --same-host --path-prefix /news-centre/media-release/ \
  -o sources/afp_csea_urls.txt

# Queensland Police — the search page is a Google CSE widget, not article HTML
python3 fetch_source_urls.py \
  --google-cse-search-page 'https://mypolice.qld.gov.au/?s=child+exploitation' \
  --path-prefix /news/ --require-any child --exclude /category/ \
  --cse-max-results 12 \
  -o sources/qps_csea_urls.txt
```

Europol articles are a JavaScript shell. The body is in `window.SERVER_DATA`, which `build_press_pdf.py` reads from the HTML response:

```bash
python3 build_press_pdf.py --url-file ../collector_output/europol/europol_csea_ops_urls.txt \
  --out-dir .. --out-name EUROPOL_CSEA_All.pdf
```

UK National Crime Agency case stories (search harvest, twelve prosecutions):

```bash
python3 build_press_pdf.py --url-file ../collector_output/nca/nca_csea_urls.txt \
  --out-dir .. --out-name NCA_CSEA_All.pdf
```

Local MCP: `fetch_press_listing_urls` takes `url_template` + `page_range`, or `google_cse=true`. That tool is local-only. It writes a url-file. It does not ingest.

### You want DOJ cases by topic (no URL list yet)

Do **not** crawl `justice.gov/psc/press-room` (page>0 is HTTP 403). Do **not** call `resolve_press_urls.py` with an empty url-file. Page the public News API, then `--doj-file`:

```bash
cd collector

# Next 2,000+ Project Safe Childhood records (newest-first; skip URLs already in DOJ_*.pdf):
python3 harvest_doj_press.py --max-keep 0 --baseline-pdf ../../DOJ_SAFE_CHILDHOOD.pdf
python3 build_press_pdf.py --doj-file sources/doj_psc_resolved_novel.json \
  --out-dir ../.. --out-name DOJ_SAFE_CHILDHOOD_MORE.pdf

# Any other DOJ topic - same tools, CAC gate off:
python3 harvest_doj_press.py --slug doj_fentanyl --skip-cac \
  --require 'fentanyl' --title-term fentanyl --title-term 'fentanyl analogue' \
  --max-keep 2200
python3 build_press_pdf.py --doj-file sources/doj_fentanyl_resolved_novel.json \
  --out-dir ../.. --out-name DOJ_FENTANYL_All.pdf
```

`--max-keep` (default 2200) stops after that many **kept** records, newest first. The 2022-2026 PSC pull used that cap. **Another 2,000+ PSC records** means `--max-keep 0` (or a higher cap) with `DOJ_SAFE_CHILDHOOD.pdf` as `--baseline-pdf` so already-ingested URLs are marked not-novel. Feed only `*_resolved_novel.json` to `build_press_pdf.py`.

Title `"Project Safe Childhood"` is only ~87 API hits (mostly rollups). Real PSC signal is the body footer. `parameters[topic]`, `body`, and `component` are **ignored** by the API - title substring only. Probe counts with `pagesize=1` before a long page.

## Why DOJ (`justice.gov`) is different

`www.justice.gov/usao-*/pr/*` sits behind an Akamai Bot Manager JS interstitial (host-wide). Direct `requests`/`curl` gets a ~2.4KB challenge shell. Do not solve it. Use the public API (`/api/v1/press_releases.json`, no key, 4 req/s):

| You have | Tool |
|---|---|
| Topic / title phrasing, no URLs | `harvest_doj_press.py` → `--doj-file` |
| A list of `justice.gov` URLs | `resolve_press_urls.py` → `--doj-file` |
| Only non-DOJ URLs | `build_press_pdf.py --url-file` |

`resolve_press_urls.py` matches URL slugs (title search alone is too fuzzy - DOJ republishes the same matter under slightly different titles). Full quirks: `PRESS_RELEASE_COLLECTION.md`.

## Output & caching

- `build_press_pdf.py` writes one PDF per URL under `{out-dir}/tmp/{index:04d}_{sha256(url)[:16]}.pdf`, then merges them into `{out-dir}/{out-name}`.
- Cache is keyed by URL hash, not position - safe to re-run with a different url-file without stale slot collisions. Re-running an unchanged URL prints `[cached]` and skips the fetch.
- To force a re-scrape (e.g. after fixing an extractor), delete the relevant `tmp/NNNN_{hash}.pdf` or the whole `tmp/` directory.
- Both `build_press_pdf.py` output PDFs and any `sources/*.json` intermediate files are covered by the repo's blanket `.gitignore` rules (`*.pdf`, `*.json`) - nothing generated by this suite needs to be committed by hand.

## Can CaseLinker take a new source

Yes. New sources use the same collector suite; no additional tooling is required.

1. **Listing / search page** - `fetch_source_urls.py` (HTML, Squarespace, CSE, usa.gov, WordPress REST, optional `--via-jina`). Prefer a public API when one exists (check `/api`, `/jsonapi`, Drupal meta) before scraping HTML.
2. **justice.gov only** - do not crawl live HTML (Akamai). Discover with `harvest_doj_press.py`, or resolve known URLs with `resolve_press_urls.py`.
3. **Build** - `build_press_pdf.py` (`--url-file` or `--doj-file` / `--resolved-file`).
4. **Quality** - novelty vs an existing merged PDF (`check_expand_novelty.py`); for ICAC/CAC topics, `scripts/verify/verify_cac.py --all-failures --default-fail-csv` before ingest. Other topics: `--skip-cac` on harvest; still drop grants/rollups and novelty-check.
5. **Ingest** - `src/main.py` when the PDF is clean.

Hard hosts (login, CAPTCHA, JS bot-wall with no API) are stop-and-ask. See **When to stop and ask a human** below.

## After the merge: quality gates

**ICAC / CAC topics** (what enters the public corpus, analysis surfaces, and database): `check_expand_novelty.py` then `scripts/verify/verify_cac.py --all-failures --default-fail-csv`. Do not ingest until failures are removed.

**Any other topic** (DOJ drugs, elder fraud, mixed USAO, …): the collector suite is domain-agnostic. Use `harvest_doj_press.py --skip-cac`, skip `verify_cac.py`, still drop grants/rollups/speeches, collapse arrest vs sentencing when the same matter appears twice, and novelty-check against existing merged PDFs. `build_press_pdf.py` does not care what the crime is. Those PDFs stay local research artifacts unless a separate ingest policy is decided; the shipped CaseLinker release and live DB are ICAC/CAC-scoped.

## When to stop and ask a human

- A site requires login, CAPTCHA, or a paid API.
- Releases only exist on Facebook/PDF email blasts with no stable URL list.
- robots.txt or legal terms block automated access at the scale you need.
- The bot-wall in front of a host would require solving a JS challenge, not just changing headers - that's a "stop and ask," not a "try harder," the same call already made for `justice.gov`.
