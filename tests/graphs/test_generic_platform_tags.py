"""Generic tags stay in the graph and stay out of the named-platform channel."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from rdflib import RDF

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))
_spec = importlib.util.spec_from_file_location(
    "features_to_cac", ROOT / "ontology" / "pipeline" / "features_to_cac.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

_analysis_spec = importlib.util.spec_from_file_location(
    "cluster_analysis",
    ROOT / "src" / "Clustering & Analysis Layer" / "analysis.py",
)
analysis = importlib.util.module_from_spec(_analysis_spec)
_analysis_spec.loader.exec_module(analysis)

CASE = {
    "id": "fixture_generic_001",
    "source": "TEST",
    "date_start": "2024-06-01",
    "date_end": "2024-06-01",
    "platforms_used": ["Snapchat", "social media", "online", "internet", "chat"],
    "case_topics": ["possession"],
    "investigation_type": "unknown",
}
TAGS = ("online", "internet", "social-media", "chat")


def _graph():
    cg, warnings = mod.CaseToCAC().map_case(CASE)
    g = cg.get_context(mod.GRAPH_DETERMINISTIC)
    return g, warnings


def test_generic_tags_are_not_the_event_channel():
    g, warnings = _graph()
    assert not any("unmapped label 'internet'" in w for w in warnings)
    snap = mod.BASE["platform/snapchat"]
    assert (snap, RDF.type, mod.CAC_PLATFORMS.MessagingService) in g
    assert (None, mod.CAC.usesChannel, snap) in g
    inv = mod.BASE["case/fixture_generic_001"]
    named_classes = {
        mod.CAC_PLATFORMS.SocialMediaPlatform,
        mod.CAC_PLATFORMS.MessagingService,
        mod.CAC_PLATFORMS.AnonymousChatPlatform,
    }
    for slug in TAGS:
        uri = mod.BASE[f"platform/{slug}"]
        types = set(g.objects(uri, RDF.type))
        assert mod.CAC_CORE.DigitalSystemEntity in types
        assert types.isdisjoint(named_classes), (slug, types)
        assert {str(o) for o in g.objects(uri, mod.CAC_PLATFORMS.platformType)} == {"generic-tag"}
        assert (None, mod.CAC.usesChannel, uri) not in g
        assert (inv, mod.UCO_CORE.object, uri) in g


def test_cluster_rankings_keep_tags_beside_named_platforms():
    cases = [
        {"id": "a", "platforms_used": ["online", "internet", "Snapchat"]},
        {"id": "b", "platforms_used": ["social media", "chat", "Snapchat", "Kik"]},
    ]
    stats = analysis.analyze_group_characteristics(cases)["statistics"]
    assert stats["top_platforms"] == {"Snapchat": 2, "Kik": 1}
    assert stats["top_generic_tags"]["online"] == 1
    assert set(stats["top_generic_tags"]) == {"online", "internet", "social media", "chat"}
    insights = analysis.generate_automated_insights(cases)["insights"]
    titles = [i["title"] for i in insights if i["type"] == "platform_analysis"]
    assert titles == ["Most Common Platform"]
    assert "Snapchat" in insights[0]["description"]
    assert "online" not in insights[0]["description"]


def test_online_only_cluster_names_top_platform() -> None:
    """The online-only description reads (platform, count) pairs, not dict keys."""
    cases = [
        {
            "id": f"fixture_online_{i:03d}",
            "source": "TEST",
            "date_start": "2024-06-01",
            "date_end": "2024-06-01",
            "platforms_used": ["Snapchat"],
            "case_topics": ["online_only", "possession"],
            "investigation_type": "unknown",
        }
        for i in range(3)
    ]
    groups = analysis.group_similar_cases(cases, similarity_threshold=0.45)
    online = next(g for g in groups if g["group_id"] == "online_only_cluster")
    assert "Most common named platform: Snapchat (3/3 cases)" in online["description"]
