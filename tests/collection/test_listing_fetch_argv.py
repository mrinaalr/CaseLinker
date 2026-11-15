"""argv for the URL-path listing harvest. No network."""

from pathlib import Path

from caselinker_mcp.collector_tools import listing_fetch_argv


def test_html_listing_uses_url_flag():
    cmd = listing_fetch_argv(
        "https://www.afp.gov.au/news-centre",
        Path("out.txt"),
        path_prefix="/news-centre/media-release/",
    )
    assert "--url" in cmd
    assert "--google-cse-search-page" not in cmd
    assert "--same-host" in cmd
    assert cmd[cmd.index("--path-prefix") + 1] == "/news-centre/media-release/"


def test_page_template_replaces_single_url():
    cmd = listing_fetch_argv(
        "",
        Path("out.txt"),
        url_template="https://www.afp.gov.au/search?page={page}",
        page_range="0:1",
    )
    assert "--url" not in cmd
    assert cmd[cmd.index("--url-template") + 1].endswith("page={page}")
    assert cmd[cmd.index("--page-range") + 1] == "0:1"


def test_google_cse_skips_same_host_and_passes_filters():
    cmd = listing_fetch_argv(
        "https://mypolice.qld.gov.au/?s=child+exploitation",
        Path("out.txt"),
        google_cse=True,
        cse_max_results=12,
        path_prefix="/news/",
        require_any="/news/20",
        exclude="/category/",
        same_host=True,
    )
    assert "--google-cse-search-page" in cmd
    assert "--same-host" not in cmd
    assert cmd[cmd.index("--cse-max-results") + 1] == "12"
    assert "/category/" in cmd
    assert "/news/20" in cmd
