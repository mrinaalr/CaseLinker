"""Schema 1.x -> 2.0 migration: mechanical where it can be, listed for review where it cannot."""
from __future__ import annotations

import copy

from tests.pacer import fixtures as F
from state_machines.evidence.migrate import migrate
from state_machines.evidence.validate import validate

OLD_REF = {"P1": "D1", "P2": "V1", "P3": "LE1"}


def _as_v1(bundle: dict) -> dict:
    """The fictional case in its schema 1.1 shape (role-coded actors, one time interval)."""
    b = copy.deepcopy(bundle)
    roles = {"P1": "offender", "P2": "victim", "P3": "law_enforcement"}
    b["actors"] = [{"actor_ref": OLD_REF[p["participant_ref"]], "role": roles[p["participant_ref"]],
                    "victim_kind": "minor" if p["participant_ref"] == "P2" else None, "age_band": p.get("age_band")}
                   for p in b.pop("participants")]
    for e in b["events"]:
        e["actor_ref"] = OLD_REF[e.pop("actor")["participant_ref"]]
        e["target_refs"] = [OLD_REF[t["participant_ref"]] for t in e.pop("targets")]
        e["co_actor_refs"] = [OLD_REF[c["participant_ref"]] for c in e.pop("co_actors")]
        a = e["time"]["assertions"]
        e["time"] = ({"earliest": a[0]["earliest"][:7] if a[0]["precision"] == "month" else a[0]["earliest"],
                      "latest": a[0]["latest"][:7] if a[0]["precision"] == "month" else a[0]["latest"],
                      "precision": a[0]["precision"], "basis": a[0]["basis"], "passage_ids": a[0]["passage_ids"]}
                     if a else {"precision": "none", "basis": "none", "passage_ids": []})
        for h in e["harms"]:
            h["victim_ref"] = OLD_REF[h["victim_ref"]]
            h.pop("victim_kind")
    for t in b["tracks"]:
        t["anchor_ref"] = OLD_REF[t["anchor_ref"]]
    b["schema_version"] = "1.1.0"
    return b


def test_migrated_bundle_validates_and_keeps_roles_dates_and_victim_kinds(tmp_path):
    F.write_pages(tmp_path)
    new, review = migrate(_as_v1(F.build()[0]))
    assert [f for f in validate(new, text_root=tmp_path) if f.severity == "error"] == []
    e01 = next(e for e in new["events"] if e["event_id"] == "e01")
    # refs are numbered by old prefix: D1 -> P1, LE1 -> P2, V1 -> P3
    assert e01["actor"] == {"participant_ref": "P1", "role": "offender"}
    assert e01["targets"] == [{"participant_ref": "P3", "role": "victim"}]
    assert e01["time"]["assertions"][0]["earliest"] == "2024-03-01" and e01["time"]["assertions"][0]["latest"] == "2024-03-31"
    assert all(h["victim_kind"] == "minor" for e in new["events"] for h in e["harms"])
    assert all(p["legal_status"] == [] for p in new["participants"])            # never inferred
    assert sum("legal status not recorded" in r for r in review) == 3
    assert new["schema_version"] == "2.0.0"


def test_co_actor_with_an_incompatible_role_is_left_unresolved_not_given_a_role(tmp_path):
    F.write_pages(tmp_path)
    v1 = _as_v1(F.build()[0])
    next(e for e in v1["events"] if e["event_id"] == "e08")["co_actor_refs"] = ["LE1"]
    new, review = migrate(v1)
    e08 = next(e for e in new["events"] if e["event_id"] == "e08")
    assert e08["co_actors"] == [] and all(t["participant_ref"] != "P2" for t in e08["targets"])
    assert e08["unresolved_participants"] == [{"participant_ref": "P2", "passage_ids": ["p08"],
                                               "note": "coded as co-actor LE1 (law_enforcement) of an offender action in schema 1"}]
    assert any("e08" in r and "decide it" in r for r in review)
    findings = validate(new, text_root=tmp_path)
    assert not [f for f in findings if f.severity == "error"]
    assert any(f.code == "T17" and f.severity == "warning" for f in findings)
    from state_machines.evidence.validate import release_errors
    assert any("role is not decided" in p for p in release_errors(new, text_root=tmp_path, allow_unreviewed=True))


def test_schema_2_bundles_pass_through_unchanged():
    b, _ = F.build()
    assert migrate(b) == (b, [])
