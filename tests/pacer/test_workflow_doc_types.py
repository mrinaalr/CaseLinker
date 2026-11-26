from pathlib import Path

from state_machines.coding.workflow import doc_type_of


def test_utah_statement_in_advance_of_plea_is_a_plea_agreement():
    assert doc_type_of(Path("pacer -- ut_ag_2026_006 -- statement in advance of plea.pdf")) == "plea_agreement"
    assert doc_type_of(Path("pacer -- ut_ag_2026_006 -- indictment.pdf")) == "indictment"


def test_findings_of_fact_keeps_its_type():
    """A trailing comment once swallowed this rule, so findings fell through to 'other'."""
    assert doc_type_of(Path("pacer -- doj_ceos_2025_025 -- findings of fact.pdf")) == "findings_of_fact"


def test_every_released_doc_type_has_a_rule():
    """Each doc_type in pacer-v2 must still be producible: a dropped rule would retype documents on re-coding.
    (Published source_path names are shortened, e.g. 'memorandum opinion and order' -> 'opinion',
    so the types are checked against the rule set, not re-derived from the published names.)"""
    import json
    from state_machines.coding.workflow import DOC_TYPE_WORDS
    root = Path(__file__).resolve().parents[2] / "state_machines" / "data" / "pacer-v2" / "cases"
    released = {d["doc_type"] for p in root.glob("*.json") for d in json.loads(p.read_text())["documents"]}
    assert "findings_of_fact" in released
    assert released - {kind for _, kind in DOC_TYPE_WORDS} == set()
