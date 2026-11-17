"""SharePoint list JSON and Domino OpenView listing parsers. No network."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[2] / "collector" / "fetch_source_urls.py"
    spec = importlib.util.spec_from_file_location("fetch_source_urls", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_SHAREPOINT_HTML = r"""
var WPQ1ListData = { "Row" : [
{
"ID": "19",
"Title": "Vilas County Man Arrested for Possession of Child Sexual Abuse Material",
"Link": "https:\u002f\u002fwww.wisdoj.gov\u002fPressReleases\u002f3.2.23_Aschbrenner_CSAM.pdf",
"Date": "3\u002f2\u002f2023",
"Year": "2023",
"Topic": "Law Enforcement"
}
]};
"""

_DOMINO_PAGE_1 = """
<html><body>
<a href="/press.nsf/abc/one!OpenDocument">07/10/2026 -: A child exploitation sentence</a>
<a href="/files/report.pdf">annual report</a>
<a href="/search">Search</a>
<a href="/press.nsf/index!OpenView&amp;Start=30">Next</a>
</body></html>
"""

_DOMINO_PAGE_2 = """
<html><body>
<a href="http://www.dia.govt.nz/press.nsf/abc/two!OpenDocument">08/04/2005 -: Jail for a collector</a>
<a href="/press.nsf/abc/one!OpenDocument">duplicate of page 1</a>
<a href="/press.nsf/index!OpenView&amp;Start=30">Next</a>
</body></html>
"""


def test_sharepoint_list_decodes_unicode_escapes():
    mod = _load()
    rows = mod.parse_sharepoint_list_rows(_SHAREPOINT_HTML)
    assert len(rows) == 1
    assert rows[0]["link"] == (
        "https://www.wisdoj.gov/PressReleases/3.2.23_Aschbrenner_CSAM.pdf"
    )
    assert rows[0]["date"] == "3/2/2023"
    urls = mod.sharepoint_list_urls(
        _SHAREPOINT_HTML, "https://www.wisdoj.gov/Pages/AboutUs/press-releases.aspx"
    )
    assert urls == [
        "https://www.wisdoj.gov/PressReleases/3.2.23_Aschbrenner_CSAM.pdf"
    ]


def test_domino_view_follows_next_and_drops_pdf_and_search():
    mod = _load()
    pages = {
        "https://www.dia.govt.nz/press.nsf/index!OpenView&Start=1": _DOMINO_PAGE_1,
        "https://www.dia.govt.nz/press.nsf/index!OpenView&Start=30": _DOMINO_PAGE_2,
    }
    calls = []

    def fetch_html(url):
        calls.append(url)
        return pages.get(url)

    urls = mod.collect_domino_openview_urls(
        "https://www.dia.govt.nz/press.nsf/index!OpenView&Start=1",
        fetch_html=fetch_html,
        delay=0,
        allow_http=True,
    )
    assert calls[0].endswith("Start=1")
    assert any(c.endswith("Start=30") for c in calls)
    assert urls == [
        "https://www.dia.govt.nz/press.nsf/abc/one!OpenDocument",
        "https://www.dia.govt.nz/press.nsf/abc/two!OpenDocument",
    ]
    assert not any(u.lower().endswith(".pdf") or "/search" in u.lower() for u in urls)


def test_dia_lead_date_beats_an_older_date_later_in_the_story():
    path = Path(__file__).resolve().parents[2] / "collector" / "build_press_pdf.py"
    spec = importlib.util.spec_from_file_location("build_press_pdf_dates", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    body = (
        "29/04/2004 Name suppression in this matter ended on June 07, 2003 "
        "after the court sentenced him."
    )
    assert mod._dia_lead_date(body).isoformat() == "2004-04-29"
    assert mod._first_dateline_date_in_text("19 August 2026 he was sentenced.").isoformat() == "2026-08-19"


def test_domino_view_rejects_http_unless_allowed():
    mod = _load()
    html = '<a href="http://www.dia.govt.nz/press.nsf/abc/two!OpenDocument">x</a>'
    urls = mod.collect_domino_openview_urls(
        "https://www.dia.govt.nz/press.nsf/index!OpenView&Start=1",
        fetch_html=lambda url: html,
        allow_http=False,
    )
    assert urls == []


def _load_builder():
    path = Path(__file__).resolve().parents[2] / "collector" / "build_press_pdf.py"
    spec = importlib.util.spec_from_file_location("build_press_pdf_text", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_utf8_meta_is_used_when_the_header_omits_a_charset():
    mod = _load_builder()
    raw = (
        b'<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />'
        + "Affairs\u2019s \u201cdewit\u201d".encode()
    )
    text = mod._decode_http_text(raw, content_type="text/html", encoding="ISO-8859-1")
    assert "Affairs\u2019s" in text
    assert "\u201cdewit\u201d" in text
    assert "\u00e2" not in text


def test_explicit_latin1_charset_is_not_reread_as_utf8():
    mod = _load_builder()
    raw = b'<meta charset="utf-8" />caf\xe9'
    text = mod._decode_http_text(
        raw,
        content_type="text/html; charset=iso-8859-1",
        encoding="ISO-8859-1",
    )
    assert "caf\u00e9" in text
    assert "\ufffd" not in text


def test_latin1_bytes_without_a_charset_stay_latin1():
    mod = _load_builder()
    raw = "caf\u00e9".encode("latin-1")
    text = mod._decode_http_text(raw, content_type="text/html", encoding="ISO-8859-1")
    assert text == "caf\u00e9"


def test_builtin_pdf_font_keeps_quotes_and_folds_macrons():
    mod = _load_builder()
    assert mod._fit_builtin_pdf_font("Affairs\u2019s \u201cdewit\u201d") == "Affairs\u2019s \u201cdewit\u201d"
    assert mod._fit_builtin_pdf_font("\u014cpunake") == "Opunake"
    assert mod._fit_builtin_pdf_font("hello") == "hello"


def test_wi_doj_pdf_uses_the_release_headline_not_the_filename():
    mod = _load_builder()
    eagle = (
        "Josh Kaul P.O. Box 7857 FOR IMMEDIATE RELEASE May 27, 2021 "
        "Vilas County Man Arrested on Child Pornography Charges EAGLE RIVER, Wis. – "
        "The Wisconsin Department of Justice today announced an arrest."
    )
    url = "https://www.wisdoj.gov/PressReleases/5.27.21_Eagle_River_CSAM_0.pdf"
    assert mod._title_for_native_pdf(url, eagle) == (
        "Vilas County Man Arrested on Child Pornography Charges"
    )
    grant = (
        "NEWS FOR IMMEDIATE RELEASE December 6, 2019 "
        "Boscobel Man Charged with Possession of Child Pornography; "
        "Grant County Sheriff's Office Joins ICAC Task Force BOSCOBEL, Wis. – "
        "The task force announced the charges."
    )
    assert "Joins ICAC Task Force" in mod._headline_from_wi_doj_body(grant)
    salem = (
        "NEWS FOR IMMEDIATE RELEASE May 28, 2020 "
        "Salem Man, an Illinois Police Officer, Arrested and "
        "Charged with Possession of Child Pornography SALEM, Wis. – rest"
    )
    assert mod._headline_from_wi_doj_body(salem) == (
        "Salem Man, an Illinois Police Officer, Arrested and "
        "Charged with Possession of Child Pornography"
    )
    other = "https://www.example.gov/PressReleases/5.27.21_Eagle_River_CSAM_0.pdf"
    assert mod._title_for_native_pdf(other, eagle) == "5.27.21 Eagle River Csam 0"
