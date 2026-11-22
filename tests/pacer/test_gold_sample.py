"""Seal and gold-sample tooling. Synthetic ids and sentences only."""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from state_machines.observations import gold_sample as G
from state_machines.observations import seal as S
from state_machines.observations.seal import SEAL_VERSION
from state_machines.observations.validation import wilson

CONFIG = Path(__file__).resolve().parents[2] / "state_machines" / "observations" / "seal_config.json"


def _seal(corpus, exclusion, seed=1, held=2, frame=2, version="test-commit"):
    return S.seal(corpus, exclusion_ids=exclusion, seed=seed, held_out_size=held,
                  gold_frame_size=frame, code_version=version)


def test_blank_config_is_refused():
    with pytest.raises(SystemExit, match="blank"):
        S.load_config(CONFIG)


def test_seal_is_deterministic_and_never_draws_an_excluded_id(tmp_path):
    corpus = ["pilot_a", "pilot_b", "case_01", "case_02", "case_03", "case_04", "case_05"]
    exclusion = ["pilot_a", "pilot_b"]
    first = _seal(list(reversed(corpus)), exclusion)
    second = _seal(corpus, exclusion)
    assert first == second
    assert first["seal_version"] == SEAL_VERSION
    assert S.manifest_sha256(first) == first["sha256"]
    assert set(first["held_out_ids"]).isdisjoint(exclusion)
    assert set(first["gold_frame_ids"]).isdisjoint(exclusion)
    assert set(first["held_out_ids"]).isdisjoint(first["gold_frame_ids"])
    assert first["population"]["excluded"] == 2
    assert first["population"]["eligible"] == 5
    left = S.write_manifest(first, tmp_path / "a").read_bytes()
    right = S.write_manifest(second, tmp_path / "b").read_bytes()
    assert left == right
    with pytest.raises(SystemExit, match="eligible"):
        _seal(corpus, exclusion, held=4, frame=2)


def test_development_refuses_sealed_ids_and_a_bad_hash():
    manifest = _seal(["case_01", "case_02", "case_03", "case_04"], [], held=1, frame=1)
    sealed = manifest["held_out_ids"][0]
    dev = next(case for case in ("case_01", "case_02", "case_03", "case_04")
               if case not in S.sealed_ids(manifest))
    with pytest.raises(SystemExit, match="development"):
        S.development_load([sealed], manifest)
    with pytest.raises(SystemExit, match="development"):
        S.extraction_debug([sealed, dev], manifest)
    assert S.development_load([dev], manifest) == [dev]
    with pytest.raises(SystemExit, match="hash"):
        S.development_load([sealed], manifest, final_evaluation=True, manifest_hash="0" * 64)
    tampered = dict(manifest, seed=manifest["seed"] + 1)
    with pytest.raises(SystemExit, match="does not match"):
        S.verify_manifest(tampered)
    assert S.development_load([sealed], manifest, final_evaluation=True, manifest_hash=manifest["sha256"]) == [sealed]


def test_benchmark_score_refuses_a_sealed_benchmark_case(tmp_path):
    from state_machines.benchmark.score import main as score_main

    manifest = _seal(["synth_001", "synth_002", "synth_003", "synth_004"], [], held=1, frame=1)
    path = S.write_manifest(manifest, tmp_path)
    with pytest.raises(SystemExit, match="development"):
        score_main([str(tmp_path / "coded"), "--sealed-manifest", str(path)])
    with pytest.raises(SystemExit, match="final evaluation"):
        score_main([str(tmp_path / "coded"), "--sealed-manifest", str(path),
                    "--final-evaluation", "--manifest-hash", "0" * 64])


def _population(frame_ids):
    rows = []
    for case_id in frame_ids:
        for stratum, sentence in (
            ("published_acts", "The defendant initiated contact with Minor Victim 1."),
            ("means_rule_no_act", "The record names a messaging application and states no act."),
            ("other", "The hearing was continued to the following week."),
        ):
            rows.append({
                "unit_id": f"{case_id}:{stratum}",
                "case_id": case_id,
                "stratum": stratum,
                "sentence": sentence,
                "context_before": [f"before {i} {case_id}" for i in range(5)],
                "context_after": [f"after {i} {case_id}" for i in range(5)],
                "machine": {"act": "INITIATE_CONTACT" if stratum == "published_acts" else None,
                            "means_tie": stratum == "published_acts", "level_c": False},
                "uncertainty": 0.1,
            })
    return rows


def test_sampler_draws_only_the_sealed_frame_and_hides_machine_labels(tmp_path):
    manifest = _seal(["case_01", "case_02", "case_03", "case_04", "pilot_a"], ["pilot_a"], held=1, frame=2)
    population = _population(manifest["gold_frame_ids"])
    config = {"seed": 3, "strata": {"published_acts": {"n": 1}, "means_rule_no_act": {"n": 1}, "other": {"n": 2}}}
    sample = G.draw_sample(population, config, sealed=manifest)
    assert {row["case_id"] for row in sample["rows"]} <= set(manifest["gold_frame_ids"])
    assert all(row["stratum_population"] >= row["stratum_drawn"] for row in sample["rows"])
    noisy = [dict(row, uncertainty=0.99) for row in population]
    again = G.draw_sample(noisy, config, sealed=manifest)
    assert [row["unit_id"] for row in sample["rows"]] == [row["unit_id"] for row in again["rows"]]
    digest = G.draw_sha256(sample)
    assert G.draw_sha256(again) == digest
    sheet = G.grading_sheet(sample)
    assert "machine" not in json.dumps(sheet) and "stratum" not in json.dumps(sheet)
    assert all(len(unit["context_before"]) == 2 and len(unit["context_after"]) == 2 for unit in sheet["units"])
    key = G.key_file(sample)
    assert all("machine" in unit for unit in key["units"])
    written = G.write_draw(sample, tmp_path / "draw")
    assert (tmp_path / "draw" / "draw.sha256").read_text(encoding="utf-8").strip() == written["sha256"] == digest
    outside = _population(["not_in_frame"])
    with pytest.raises(SystemExit, match="sealed frame"):
        G.draw_sample(outside, config, sealed=manifest)
    forced = dict(manifest)
    forced["gold_frame_ids"] = sorted(set(manifest["gold_frame_ids"]) | {"pilot_a"})
    forced["sha256"] = S.manifest_sha256(forced)
    with pytest.raises(SystemExit, match="excluded"):
        G.draw_sample(_population(["pilot_a"]), config, sealed=forced)


def test_weights_recover_a_known_recall():
    """Unequal sampling rates. Unweighted recall follows the over-sampled stratum. Weighted recall does not.

    Wide stratum: N=100, n=10, weight 10. One sampled gold positive, and the machine hit it.
    Tight stratum: N=10, n=10, weight 1. Nine sampled gold positives, and the machine missed all nine.
    Unweighted recall is 1/10. Weighted recall is 10 / (10 + 9) = 10/19.
    """
    rows = [_scored("wide", 100, 10, "CONTACT", "CONTACT", case_id="wide", unit_id="w0")]
    rows += [_scored("tight", 10, 10, "OTHER", "CONTACT", case_id="tight", unit_id=f"t{i}") for i in range(9)]
    assert G.unweighted_recall(rows, "act") == pytest.approx(0.1)
    assert G.ipw_recall(rows, "act") == pytest.approx(10 / 19)


def test_cohen_kappa_matches_a_hand_computation():
    """Ten items, three labels, one disagreement. Kappa is (0.9 - 0.36) / 0.64 = 0.84375.

    left  A A A A A B B B C C
    right A A A A B B B B C C
    Observed agreement is 9/10. Chance is (5*4 + 3*4 + 2*2) / 100 = 0.36.
    """
    left = ["A", "A", "A", "A", "A", "B", "B", "B", "C", "C"]
    right = ["A", "A", "A", "A", "B", "B", "B", "B", "C", "C"]
    assert len(left) >= 10
    assert G.cohen_kappa(left, right) == pytest.approx(0.84375)
    assert G.cohen_kappa(["A"] * 10, ["A"] * 10) is None


def test_equal_rates_recover_the_population_totals():
    """The mean Horvitz-Thompson totals, over every stratified sample, are the population totals."""
    def stratum():
        return [{"gold": True, "hit": True}, {"gold": True, "hit": False}, {"gold": False, "hit": False}]

    samples = []
    for left in itertools.combinations(stratum(), 2):
        for right in itertools.combinations(stratum(), 2):
            rows = []
            for unit in (*left, *right):
                rows.append({"stratum_population": 3, "stratum_drawn": 2, **unit})
            samples.append(rows)
    mean_hits = sum(G.ipw_total(rows, lambda row: row["gold"] and row["hit"]) for rows in samples) / len(samples)
    mean_gold = sum(G.ipw_total(rows, lambda row: row["gold"]) for rows in samples) / len(samples)
    assert mean_hits == pytest.approx(2.0)
    assert mean_gold == pytest.approx(4.0)
    assert mean_hits / mean_gold == pytest.approx(0.5)


def test_score_checks_the_manifest_hash_and_reports_agreement():
    manifest = _seal(["case_01", "case_02", "case_03", "case_04"], [], held=1, frame=2)
    population = _population(manifest["gold_frame_ids"])
    config = {"seed": 1, "strata": {"published_acts": {"n": len(manifest["gold_frame_ids"])},
                                    "means_rule_no_act": {"n": 1}, "other": {"n": 1}}}
    sample = G.draw_sample(population, config, sealed=manifest)
    key = G.key_file(sample)
    graded = {"units": []}
    for unit in key["units"]:
        gold_act = unit["machine"]["act"]
        graded["units"].append({
            "unit_id": unit["unit_id"],
            "gold": {"act": gold_act, "means_tie": unit["machine"]["means_tie"], "level_c": False},
            "coders": {
                "h1": {"act": gold_act, "means_tie": unit["machine"]["means_tie"], "level_c": False},
                "h2": {"act": gold_act, "means_tie": unit["machine"]["means_tie"], "level_c": False},
            },
        })
    result = G.score_drawn(graded, key, sample, sealed=manifest, replicates=40, seed=0)
    assert result["manifest_sha256"] == manifest["sha256"]
    assert result["precision"]["act"]["precision"] == 1
    assert "gold_positives_by_stratum" in result["recall"]["act"]
    assert "warnings" in result["recall"]["act"]
    assert result["krippendorff_alpha"]["act"]["alpha"] == 1
    assert result["design_based"]["ready_for"] == ["DSL"]
    assert result["design_based"]["population_by_stratum"]["published_acts"] == len(manifest["gold_frame_ids"])
    assert all(row["sampling_weight"] == pytest.approx(1 / row["inclusion_probability"])
               for row in result["design_based"]["rows"])
    bad = dict(manifest, sha256="ab" * 32)
    with pytest.raises(SystemExit, match="does not match"):
        G.score(graded, key, sealed=bad)
    assert G.krippendorff_alpha([["a", "b"]]) == pytest.approx(0.0)


def _scored(stratum, population, drawn, machine, gold, case_id=None, unit_id="u"):
    return {
        "case_id": stratum if case_id is None else case_id,
        "unit_id": unit_id,
        "stratum": stratum,
        "stratum_population": population,
        "stratum_drawn": drawn,
        "machine": {"act": machine, "means_tie": False, "level_c": False},
        "gold": {"act": gold, "means_tie": False, "level_c": False},
    }


def test_weighted_precision_matches_a_hand_computation():
    """Two strata at different rates. Unweighted precision is 1/2; the weighted value is 10/12."""
    rows = [
        _scored("wide", 100, 10, "CONTACT", "CONTACT"),
        _scored("tight", 20, 10, "CONTACT", "OTHER"),
    ]
    assert G.unweighted_precision(rows, "act") == pytest.approx(0.5)
    # w_wide = 100/10 = 10, TP=1, FP=0; w_tight = 20/10 = 2, TP=0, FP=1.
    # 10*1 / (10*1 + 2*1) = 10/12.
    assert G.ipw_precision(rows, "act") == pytest.approx(10 / 12)
    block = G.precision_unit(rows, "act")
    assert block["precision"] == pytest.approx(10 / 12)
    assert block["by_stratum"]["wide"]["wilson_95"] == wilson(1, 1)
    assert block["by_stratum"]["tight"]["wilson_95"] == wilson(0, 1)


def test_cluster_bootstrap_keeps_a_case_whole_and_is_wider_than_rows():
    """Two cases, very different sizes, labels constant inside a case. Resampling rows looks precise; resampling cases does not."""
    import random
    rows = [_scored("s", 32, 32, "CONTACT", "CONTACT", case_id="big", unit_id=f"b{i}") for i in range(30)]
    rows += [_scored("s", 32, 32, "CONTACT", "OTHER", case_id="small", unit_id=f"s{i}") for i in range(2)]
    full = {}
    for row in rows:
        full.setdefault(row["case_id"], []).append(row["unit_id"])

    def row_resample(rng):
        return [rows[rng.randrange(len(rows))] for _ in rows]

    def width(draw):
        rng = random.Random(0)
        stats = sorted(G.ipw_precision(draw(rng), "act") for _ in range(300))
        return stats[int(0.975 * (len(stats) - 1))] - stats[int(0.025 * (len(stats) - 1))]

    assert width(lambda rng: G.cluster_resample(rows, rng)) > width(row_resample)
    rng = random.Random(1)
    for _ in range(40):
        sample = G.cluster_resample(rows, rng)
        seen = {}
        for row in sample:
            seen.setdefault(row["case_id"], []).append(row["unit_id"])
        for case, ids in seen.items():
            copies = len(ids) // len(full[case])
            assert copies >= 1 and ids == full[case] * copies


def test_a_duplicate_document_drops_every_sentence_and_the_original_keeps_its_own():
    from state_machines.observations.gold_sample import merge_dockets
    rows = [
        {"unit_id": "a1", "case_id": "one", "doc_id": "plea", "document_sha256": "aa",
         "court": "dcd", "docket_number": "1:24-cr-1"},
        {"unit_id": "a2", "case_id": "one", "doc_id": "plea", "document_sha256": "aa",
         "court": "dcd", "docket_number": "1:24-cr-1"},
        {"unit_id": "b1", "case_id": "two", "doc_id": "copy", "document_sha256": "aa",
         "court": "dcd", "docket_number": "1:24-cr-1"},
    ]
    merged = merge_dockets(rows)
    assert [row["unit_id"] for row in merged] == ["a1", "a2"]
    assert {row["case_id"] for row in merged} == {"one"}


def test_the_same_docket_is_one_case_and_a_repeated_document_is_dropped():
    from state_machines.observations.gold_sample import merge_dockets
    rows = [
        {"unit_id": "a", "case_id": "one", "court": "dcd", "docket_number": "1:24-cr-1", "document_sha256": "aa"},
        {"unit_id": "b", "case_id": "two", "court": "dcd", "docket_number": "1:24-cr-1", "document_sha256": "bb"},
        {"unit_id": "c", "case_id": "two", "court": "dcd", "docket_number": "1:24-cr-1", "document_sha256": "aa"},
    ]
    merged = merge_dockets(rows)
    assert [row["unit_id"] for row in merged] == ["a", "b"]
    assert {row["case_id"] for row in merged} == {"one"}


def test_bootstrap_cli_default_is_two_thousand(capsys):
    from state_machines.observations.gold_sample import main
    with pytest.raises(SystemExit) as caught:
        main(["score", "--help"])
    assert caught.value.code == 0
    assert "2000" in (capsys.readouterr().out + capsys.readouterr().err)


def test_bootstrap_default_is_two_thousand():
    import inspect
    from state_machines.observations.gold_sample import score, score_drawn
    assert inspect.signature(score).parameters["replicates"].default == 2000
    assert inspect.signature(score_drawn).parameters["replicates"].default == 2000


def test_bootstrap_draws_a_case_across_strata_or_not_at_all():
    """A case with rows in two strata is taken with all of those rows, or with none."""
    import random
    rows = [
        _scored("wide", 10, 5, "CONTACT", "CONTACT", case_id="both", unit_id="a"),
        _scored("tight", 8, 4, "CONTACT", "OTHER", case_id="both", unit_id="b"),
        _scored("wide", 10, 5, "CONTACT", "CONTACT", case_id="only", unit_id="c"),
    ]
    rng = random.Random(2)
    saw_both = saw_none = False
    for _ in range(40):
        sample = G.cluster_resample(rows, rng)
        ids = [row["unit_id"] for row in sample]
        assert ids.count("a") == ids.count("b")
        for row in sample:
            if row["unit_id"] == "a":
                assert row["stratum"] == "wide" and G._weight(row) == pytest.approx(2)
            if row["unit_id"] == "b":
                assert row["stratum"] == "tight" and G._weight(row) == pytest.approx(2)
        if ids.count("a"):
            saw_both = True
        else:
            saw_none = True
    assert saw_both and saw_none


def test_a_stratum_with_fewer_than_five_gold_positives_warns():
    rows = [_scored("thin", 8, 4, "CONTACT", "CONTACT") for _ in range(4)]
    rows += [_scored("wide", 10, 5, "CONTACT", "CONTACT") for _ in range(5)]
    report = G.recall_report(rows, "act", replicates=20, seed=0)
    assert report["gold_positives_by_stratum"] == {"thin": 4, "wide": 5}
    assert report["warnings"] == ["thin: fewer than 5 gold positives; its bootstrap interval is unreliable"]
    assert report["recall"] == pytest.approx(1.0)
