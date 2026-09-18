"""Unit tests for WordPress REST URL rewriting in fetch_source_urls."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "collector" / "fetch_source_urls.py"
    spec = importlib.util.spec_from_file_location("fetch_source_urls", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_wp_rest_public_url_rewrites_host_and_keeps_news_path():
    mod = _load()
    url = mod.wp_rest_public_url(
        "https://wp.kentuckystatepolice.ky.gov/news/example-post/",
        "example-post",
        public_host="www.kentuckystatepolice.ky.gov",
        path_prefix="/news/",
    )
    assert url == "https://www.kentuckystatepolice.ky.gov/news/example-post/"


def test_wp_rest_public_url_builds_from_slug_when_path_missing():
    mod = _load()
    url = mod.wp_rest_public_url(
        "https://wp.example.gov/",
        "my-slug",
        public_host="www.example.gov",
        path_prefix="/news/",
    )
    assert url == "https://www.example.gov/news/my-slug/"
