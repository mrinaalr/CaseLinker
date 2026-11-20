"""robots.txt refuses AI-training crawlers and nobody else."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def _robots():
    spec = importlib.util.spec_from_file_location("caselinker_run_main_robots", ROOT / "run" / "main.py")
    mod = sys.modules.get("caselinker_run_main_robots")
    if mod is None:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["caselinker_run_main_robots"] = mod
        spec.loader.exec_module(mod)
    return TestClient(mod.app).get("/robots.txt").text


def _groups(text):
    """{user-agent: [rules]} as a crawler reads them: consecutive User-agent lines share the rules after them."""
    groups, agents, rules = {}, [], []
    for line in text.splitlines() + [""]:
        key, _, val = line.partition(":")
        if key.strip().lower() == "user-agent":
            if rules:
                agents, rules = [], []
            agents.append(val.strip())
        elif line.strip():
            rules.append(line.strip())
            for a in agents:
                groups[a] = rules
    return groups


def test_training_crawlers_are_refused_the_whole_site():
    g = _groups(_robots())
    for ua in ("GPTBot", "ClaudeBot", "CCBot", "Google-Extended", "Reflectionbot"):
        assert g[ua] == ["Disallow: /"], ua


def test_everyone_else_keeps_the_site_and_only_loses_expensive_routes():
    g = _groups(_robots())
    for ua in ("ChatGPT-User", "Claude-User", "Perplexity-User", "Googlebot", "bingbot"):
        assert ua not in g   # user-triggered agents and search engines fall under the * group
    assert g["*"] == ["Allow: /", "Disallow: /api/", "Disallow: /ontology/", "Disallow: /sparql"]
