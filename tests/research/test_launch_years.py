"""The launch-year table covers the capability registry and does not feed the pipeline."""
from __future__ import annotations

from pathlib import Path

from ontology.platform_affordance_evidence.launch_years import (
    by_generation, generation, load, unknowns,
)
from state_machines.trajectories.affordances import load as load_registry

ROOT = Path(__file__).resolve().parents[2]
YEAR_MIN, YEAR_MAX = 1960, 2026


def test_every_registry_platform_appears_once():
    registry = {entry["name"] for entry in load_registry()["platforms"].values()}
    rows = load()
    ids = [row["platform_id"] for row in rows]
    assert len(ids) == len(set(ids)) == len(registry)
    assert set(ids) == registry


def test_years_are_sane_and_sourced():
    for row in load():
        year = row["launch_year"]
        if year is None:
            assert row["source_url"] == ""
            assert row["note"]
            continue
        assert isinstance(year, int)
        assert YEAR_MIN <= year <= YEAR_MAX
        assert row["source_url"].startswith("http")


def test_messenger_dates_from_the_2011_app_and_the_rule_stays_short():
    row = next(item for item in load() if item["platform_id"] == "Facebook Messenger")
    assert row["launch_year"] == 2011
    assert "9 August 2011" in row["note"]
    text = (ROOT / "ontology/platform_affordance_evidence/LAUNCH_YEARS.md").read_text(encoding="utf-8")
    assert "launch_year = year of first public release, including public beta or early access." in text
    assert "same service continued" not in text


def test_generation_boundaries():
    assert generation(2003) == "<=2003"
    assert generation(2004) == "2004-2010"
    assert generation(2010) == "2004-2010"
    assert generation(2011) == "2011-2016"
    assert generation(2016) == "2011-2016"
    assert generation(2017) == ">=2017"
    assert generation(None) is None
    # The same boundaries, taken from rows whose sources state those years.
    stated = {row["platform_id"]: row["launch_year"] for row in load()}
    assert generation(stated["Steam"]) == "<=2003"
    assert generation(stated["Facebook"]) == "2004-2010"
    assert generation(stated["Instagram"]) == "2004-2010"
    assert generation(stated["Twitch"]) == "2011-2016"
    assert generation(stated["TikTok"]) == "2011-2016"
    assert generation(stated["Fortnite"]) == ">=2017"


def test_unknowns_are_excluded_and_listed():
    rows = load()
    missing = unknowns(rows)
    assert missing == ["Gen AI", "IMVU", "Skout", "Webcam platform", "Wickr"]
    grouped = by_generation(rows)
    listed = {pid for ids in grouped.values() for pid in ids}
    assert set(missing).isdisjoint(listed)
    assert len(listed) + len(missing) == len(rows)


def test_the_pipeline_does_not_read_the_table():
    for relative in (
        "state_machines/trajectories/affordances.py",
        "state_machines/trajectories/derive.py",
        "state_machines/graphs/release.py",
        "state_machines/observations/observe.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "platform_launch_years" not in text
        assert "launch_years" not in text
