"""restitution: the detector finds the amounts in a made-up release and the gate keeps them."""

from caselinker_mcp import repair_expand

# A made-up release. Never paste a real release or a real person's name into a test.
SAMPLE = (
    "A man was sentenced to 10 years in prison and ordered to pay $12,500 in restitution. "
    "His co-defendant must pay restitution in the amount of $3,000. "
    "Each count faces up to $250,000 in restitution and fines."
)
EXPECTED_SPANS = [
    [SAMPLE.index("$12,500"), SAMPLE.index("$12,500") + len("$12,500")],
    [SAMPLE.index("$250,000"), SAMPLE.index("$250,000") + len("$250,000")],
    [SAMPLE.index("$3,000"), SAMPLE.index("$3,000") + len("$3,000")],
]


def test_detector_finds_the_value_and_the_gate_keeps_it():
    out = repair_expand.rehearse_extension("restitution", [{"case_id": "sample", "text": SAMPLE}])
    assert out["errors"] == []
    assert [[a["span_start"], a["span_end"]] for a in out["kept"]] == EXPECTED_SPANS
    assert [a["value"] for a in out["kept"]] == [12500.0, 250000.0, 3000.0]
    assert [a["role"] for a in out["kept"]] == ["ordered", "exposure", "ordered"]
