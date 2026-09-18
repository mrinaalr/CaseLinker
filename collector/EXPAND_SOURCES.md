# ICAC / CAC source expansion queue

**Pipeline** (you provide the search/listing URL; agent runs the rest):

1. **Harvest** - `fetch_source_urls.py`, site API, or Jina (SPA sites). Query must be **`child sexual`** (not bare `child`).
2. **Dedupe** - drop URLs already in the merged `*_ICAC_All.pdf` (and obvious noise: grants, bills, DEI, index pages).
3. **Novelty gate** - `python3 collector/check_expand_novelty.py --batch-pdf … --baseline *.pre_expand.bak --new-urls-file …` (must PASS before append). Uses **raw PDF URLs** (authoritative) plus body fingerprint vs baseline.
4. **Scrape** - `scrape_pdf.py --url-file …` → `batch.pdf`
5. **Append** - merge into repo-root `*_ICAC_All.pdf` (backup `*.pre_expand.bak` first).
6. **Re-check** - `check_expand_novelty.py --pdf … --baseline *.pre_expand.bak` (no double-dip in merged file).
7. **CAC verify (required)** - every batched case in the final merged PDF must pass `verify_cac.py`. **Print and save ALL failures** (not just a sample). Do not ingest until failures are removed or justified.
8. **Recommend** - next source from the table below.

### Step 7 - CAC verify on final PDF (all failures)

After append, run (repo root):

```bash
python3 scripts/verify/verify_cac.py \
  --pdf SCAG_ICAC_All.pdf \
  --source "SCAG ICAC" \
  --all-failures \
  --default-fail-csv
```

- **`--all-failures`** - prints **every** non-CAC case to the terminal in a numbered block (`case_id`, URL, preview).
- **`--default-fail-csv`** - writes a full machine-readable list to  
  `collector/state/<pdf_stem>_cac_failures.csv` (one row per failure).
- Exit code **1** if any case fails → treat as blocking until you review the CSV.
- Optional: `--json collector/state/<stem>_cac_verify.json` for automation.

Same pattern for each expanded source, e.g. Kentucky:

```bash
python3 scripts/verify/verify_cac.py \
  --pdf KYSP_ICAC_All.pdf \
  --source "KY SP" \
  --all-failures \
  --default-fail-csv
```

**What to do with failures:** grants, bills, fugitive manhunts, election/DEI press, etc. → delete those pages from the merged PDF (or exclude URL and re-merge). Borderline CAC wording may pass on manual read even if regex misses - note in CSV, don’t auto-delete.

**Already expanded (re-verify anytime):**

| PDF | Source key | Failures CSV (after `--default-fail-csv`) |
|-----|------------|-------------------------------------------|
| `SCAG_ICAC_All.pdf` | `SCAG ICAC` | `collector/state/scag_icac_all_cac_failures.csv` |
| `KYSP_ICAC_All.pdf` | `KY SP` | `collector/state/kysp_icac_all_cac_failures.csv` |

---

## Top priority (ICAC-only harvest → broaden with child sexual)

| Priority | Source key | Merged PDF | Child-sexual search URL | Notes |
|---------:|------------|------------|-------------------------|--------|
| ✅ done | SCAG ICAC | `SCAG_ICAC_All.pdf` | `https://www.scag.gov/search?s=child%20sexual&p={1-50}` | Paginated site search |
| ✅ done | **KY SP** | `KYSP_ICAC_All.pdf` | `https://www.kentuckystatepolice.ky.gov/news?searchTerm=child+sexual` | WP REST harvest - `harvest_ky_child_sexual.py` (+164 new) |
| 1 | ILLINOIS AG | `ILLNOISAG_ICAC_All.pdf` | `https://illinoisattorneygeneral.gov/site-search-page/press-releases/index?q=child+sexual` | |
| 2 | Idaho ICAC | `IDAHO_ICAC_All.pdf` | (newsroom ICAC category + child sexual site search) | |
| ✅ done | NJ AG | `NJOAG_ICAC_All.pdf` | `https://www.njoag.gov/?s=child+sexual` (+ `page/N`) | Jina search harvest; HTML extract + `_trim_njoag_body` (+116 novel) |
| 4 | SVICAC | `SVICAC_ICAC_All.pdf` | Silicon Valley ICAC news index | |
| 5 | SOUTH FLORIDA ICAC | `SOUTHFLORIDA_ICAC_All.pdf` | | |
| 6 | TBI ICAC | `TBI_ICAC_All.pdf` | `https://tbinewsroom.com/?s=child+sexual` | |
| ✅ done | NEWYORK SP | `NYSP_ICAC_All.pdf` | [NY State CSE](https://search.its.ny.gov/search/search.html?q=child+sexual+inurl:troopers.ny.gov&site=default_collection) + [newsroom keyword](https://troopers.ny.gov/nysp-newsroom?keyword=child+sexual) | `harvest_nysp_child_sexual.py` (+138 new) |
| 8 | FRESNO SO | `FRESNOSO_ICAC_All.pdf` | `https://www.fresnosheriff.org/search.html?q=child+sexual` | `--insecure` |
| 9 | LAPD | `LAPD_ICAC_All.pdf` | `https://www.lapdonline.org/?s=child+sexual` | |
| 10 | SJPD | `SJPD_ICAC_All.pdf` | `https://www.sjpd.org/services/automated-services/search?q=child+sexual` | |
| 11 | ANCHORAGE PD | `ANCHORAGEPD_ICAC_All.pdf` | `https://www.anchoragepolice.com/search?q=child+sexual` | Squarespace API in `fetch_source_urls.py` |
| 12 | WCSO | `WCSO_ICAC_All.pdf` | `https://washoesheriff.com/search_results.php?q=child+sexual` | |
| 13 | OSCEOLA SO | `OSCEOLA_ICAC_All.pdf` | `https://www.osceolasheriff.org/?s=child+sexual` | |
| 14 | LVMPD | `LVMPD_ICAC_All.pdf` | `https://www.lvmpd.com/.../search?q=child+sexual` | |
| 15 | SPD | `SPD_ICAC_All.pdf` | `https://spdblotter.seattle.gov/?s=child+sexual` | |
| 16 | SDPD | `SDPD_ICAC_All.pdf` | `https://www.sandiego.gov/search/site?search_api_fulltext=child+sexual` | |
| 17 | CSPD | `CSPD_ICAC_All.pdf` | `https://coloradosprings.gov/search?s=child+sexual` | |
| 18 | PA AG | `PAAG_ICAC_All.pdf` | `https://www.attorneygeneral.gov/taking-action-search-results/?swpquery=child+sexual` | |
| 19 | VT AG | `VTAG_ICAC_All.pdf` | Vermont AG child search | |
| 20 | OHIO AG | `OHIOAG_ICAC_All.pdf` | | |
| 21 | DE AG | `DEAG_ICAC_All.pdf` | | |
| 22 | UT AG | `UTAG_ICAC_All.pdf` | | |
| 23 | WA AG | `WAAG_ICAC_All.pdf` | | |
| 24 | OREGON DOJ | `OREGON_ICAC_All.pdf` | | |
| 25 | FL AG | `FLAG_ICAC_All.pdf` | | |
| 26 | RI AG | `RIAG_ICAC_All.pdf` | | |

DB counts (approx., pre-expansion): see `visualization/query.html` ICAC-search table.

**Next recommended after KY SP:** Illinois AG (265 cases, largest remaining gap).

---

## DOJ (justice.gov) - API source, not a URL-harvest source

`justice.gov` is Akamai-gated (see `PRESS_RELEASE_COLLECTION.md`). Do not use `fetch_source_urls.py` on USAO HTML. Two entry points:

| Job | Entry point | Then |
|-----|-------------|------|
| Discover by title/topic (PSC, drugs, fraud, …) | `harvest_doj_psc.py` | `scrape_pdf.py --doj-file sources/<slug>_resolved_novel.json` |
| You already have `justice.gov` URLs | `scrape_doj.py --url-file …` | `scrape_pdf.py --doj-file …` |

`verify_cac.py` is **ICAC-topic only**. PSC defaults keep it on. `--skip-cac` for drugs / other federal crime types. Novelty vs existing `DOJ_*.pdf` still applies.

| Source key | Endpoint | Notes |
|------------|----------|-------|
| DOJ SAFE CHILDHOOD | `https://www.justice.gov/api/v1/press_releases.json` | First pull: `--max-keep 2200` → 2,192 novel vs CEOS/archives/AI-CSAM. Next batch: `--max-keep 0 --baseline-pdf ../../DOJ_SAFE_CHILDHOOD.pdf`. |
| Any other DOJ topic | same API | `--slug … --skip-cac --title-term … --require …` |

**Recon (title-substring counts)** - probe with `pagesize=1` before paging. Counts move; 2026-07-18 snapshot:

| Category | Term | Count |
|---|---|---:|
| Elder fraud | `"elder fraud"` | 710 |
| | `"elder abuse"` | 175 |
| | `"elderly victims"` | 246 |
| Trafficking | `"trafficking"` (bare) | 20,800 |
| | `"sex trafficking"` | 2,615 |
| | `"human trafficking"` | 485 |
| Racketeering | `"racketeering"` | 2,127 |
| Extortion | `"extortion"` | 962 |
| Child exploitation/CSAM | `"child exploitation"` | 2,547 |
| | `"child pornography"` (legacy statutory term) | 13,997 |
| | `"child sexual abuse material"` (modern term) | 1,123 |

Single-term search **undercounts** (same matter under “fraud” vs “abuse”) and **overcounts** (bare `"trafficking"` is mostly drugs/arms/wildlife). CSAM: legacy title term outnumbers the modern name ~12x. Always page **multiple phrasing variants**, dedupe by API `uuid`. `parameters[topic]`/`body`/`component` are ignored.

`harvest_doj_psc.py` is the batch harvester. `scrape_doj.py` remains URL lookup only (6 pages/query).

---

## Next expansion phase: fetch_source_urls.py as a general URL/record discovery system

**Status: planning / scoping only - nothing below is built.** No API integration beyond DOJ exists yet. This section documents the next phase of work, not current capability.

**Standing first step, not a one-off insight.** The DOJ case revealed a pattern that should now be checked for *every* new agency before writing a scraper for it: does a public API already exist? Many .gov sites (especially Drupal-based ones, which a large share of state AG and federal agency sites are) expose one whether or not it's advertised - check `/api/v1/...`, `/jsonapi/...`, search "`[agency] developer API`", and view-source for Drupal meta tags (`Drupal.settings`, `X-Generator: Drupal`, `/jsonapi` links in `<head>`) before assuming a site needs HTML scraping. Finding an API before building a harvester avoids exactly the class of problem `justice.gov` posed (bot-wall-gated HTML with a perfectly good API sitting behind it, unused).

**`fetch_source_urls.py`'s current scope** is HTML-listing-page harvesting only: plain pagination (`--url-template` + `--page-range`), Squarespace's search API (`--squarespace-search-page`), Google Programmable Search / CSE (`--google-cse-search-page`), and `search.usa.gov` (`--usa-search`). All four output a deduplicated URL list. They do not talk to an agency's own structured data API.

**DOJ discovery is already the sibling:** `harvest_doj_psc.py` queries the News API and emits the resolved-record shape `scrape_pdf.py --doj-file` already accepts. Other agencies still need the same pattern (detect API → normalize to `{title, byline, body, pub_date, agency, source_url}` → `--doj-file`). No changes to `scrape_pdf.py` conversion logic.
