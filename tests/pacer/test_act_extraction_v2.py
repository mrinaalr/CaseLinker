"""Act extraction v2. Synthetic sentences only. Every new flag is off unless a test sets it."""
from __future__ import annotations

import json

import pytest

from state_machines.coding import coreference as CF
from state_machines.coding import disagreement as D
from state_machines.coding import frames as FR
from state_machines.coding import preflight as PF
from state_machines.coding import propose_verify as PV
from state_machines.coding import quote_check as Q
from state_machines.coding import sections as S
from state_machines.coding.pipeline import main as pipeline_main
from state_machines.coding.workflow import COLLECTED_AS
from state_machines.evidence import evidence as E
from state_machines.graphs.release import DATA, build


def _off(monkeypatch):
    for name in ("CASELINKER_SECTION_FILTER", "CASELINKER_SECTION_MODEL", "CASELINKER_COREFERENCE",
                 "CASELINKER_COREFERENCE_MODEL", "CASELINKER_ADJACENT_LEVEL", "CASELINKER_EXTRACTOR",
                 "CASELINKER_ACT_POLICY"):
        monkeypatch.delenv(name, raising=False)


# --- section classification -----------------------------------------------------------------


@pytest.mark.parametrize("text,role", [
    ("STATEMENT OF OFFENSE. The conduct is set out below for the court.", "statement_of_offense"),
    ("FACTUAL BASIS. The defendant met the child on a messaging application.", "factual_basis"),
    ("The defendant admits the conduct charged in Count One of the information.", "plea_admissions"),
    ("THE GRAND JURY CHARGES that the defendant did knowingly transport the files.", "charging_allegations"),
    ("I know from my training and experience that the service stores messages on its servers.", "affiant_background"),
    ("Tor is a network that routes packets through relays so the destination cannot see the sender.", "technology_explainer"),
    ("1. Tor is a browser that routes traffic through a series of relays.", "technology_explainer"),
    ("The government must prove each element of the offense beyond a reasonable doubt.", "legal_standard"),
    ("The court should impose a sentence within the guideline range under 3553(a).", "sentencing_argument"),
])
def test_section_rules_label_each_role(text, role):
    assert S.classify(text)["role"] == role


def test_section_label_is_stored_on_the_passage():
    labeled = S.label_passage({"passage_id": "p1"}, "PLEA AGREEMENT. The defendant admits the conduct as charged.")
    assert labeled["section_role"] == "plea_admissions"
    assert labeled["section_rule"] and "passage_id" in labeled


def test_section_model_is_off_unless_asked(monkeypatch):
    _off(monkeypatch)
    calls = []

    def complete(text):
        calls.append(text)
        return "sentencing_argument"

    plain = "The filing continues with ordinary narrative about a meeting downtown yesterday afternoon."
    assert S.classify(plain, model=complete)["role"] == "unclassified"
    assert calls == []
    monkeypatch.setenv("CASELINKER_SECTION_MODEL", "1")
    assert S.classify(plain, model=complete)["role"] == "sentencing_argument"
    assert calls == [plain]
    assert S.classify(plain, model=lambda _t: "not-a-role")["rule"] == "model_rejected"
    # a rule hit does not call the model
    calls.clear()
    assert S.classify("Tor is a network that routes packets through relays.", model=complete)["role"] == "technology_explainer"
    assert calls == []


def test_tor_explainer_yields_no_act_and_no_means(monkeypatch):
    _off(monkeypatch)
    text = ("Tor is a network that routes packets through relays. "
            "The defendant initiated contact with Minor Victim 1 through the Kitebox application.")
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    open_path = S.passage_products(text)
    assert open_path["section"]["role"] == "technology_explainer"
    assert open_path["acts"] and open_path["means"]
    monkeypatch.setenv("CASELINKER_SECTION_FILTER", "1")
    blocked = S.passage_products(text)
    assert blocked["acts"] == [] and blocked["means"] == []
    affiant = "I know from my training and experience that the defendant initiated contact with Minor Victim 1 through Kitebox."
    assert S.passage_products(affiant)["acts"] == [] and S.passage_products(affiant)["means"] == []


def test_section_filter_defaults_off(monkeypatch):
    _off(monkeypatch)
    assert S.section_filter_enabled() is False
    assert S.blocks_offender_products("technology_explainer") is False


# --- coreference and the adjacent-sentence level --------------------------------------------


def test_they_includes_smith_and_affiant_i_is_not_the_defendant(monkeypatch):
    _off(monkeypatch)
    monkeypatch.setenv("CASELINKER_COREFERENCE", "1")
    actors = CF.make_inventory(defendant="Smith", victims=("Minor Victim 1",))
    text = "Smith created an account on Kitebox and they communicated via an encrypted channel."
    mentions = CF.resolve_mentions(text, actors)
    they = next(m for m in mentions if m["text"].lower() == "they")
    defendant = next(a for a in actors if "Smith" in a.names)
    assert defendant.actor_id in they["actor_ids"]
    assert "Smith" not in json.dumps({k: v for k, v in they.items() if k != "text"})
    affidavit = "I reviewed the account Smith used on the listed service."
    affiant = CF.resolve_mentions(affidavit, actors, voice="affiant")
    i_mention = next(m for m in affiant if m["text"] == "I")
    assert i_mention["actor_ids"] == ["affiant"]
    assert "defendant" not in i_mention["actor_ids"]


def test_coreference_off_resolves_nothing_and_model_ids_stay_on_the_list(monkeypatch):
    _off(monkeypatch)
    actors = CF.make_inventory(defendant="Smith")
    text = "Smith created an account and they communicated via an encrypted channel."
    calls = []

    def complete(sentence, ids):
        calls.append(ids)
        return [{"text": "they", "start": sentence.index("they"), "end": sentence.index("they") + 4,
                 "actor_id": "not-on-the-list", "confidence": 0.99},
                {"text": "Smith", "start": 0, "end": 5, "actor_id": "defendant", "confidence": 0.6}]

    assert CF.resolve_mentions(text, actors, complete=complete) == []
    assert calls == []
    monkeypatch.setenv("CASELINKER_COREFERENCE_MODEL", "1")
    kept = CF.resolve_mentions(text, actors, complete=complete)
    assert calls and all(m["actor_ids"] == ["defendant"] for m in kept)
    assert all("not-on-the-list" not in m["actor_ids"] for m in kept)


def test_resolved_they_is_an_offender_for_the_subject_test(monkeypatch):
    _off(monkeypatch)
    from state_machines.observations.observe import _means

    actors = CF.make_inventory(defendant="Smith")
    sentence = "Smith opened an account on Kitebox and they communicated via an encrypted channel."
    observation = {"feature_term": "encrypted"}
    assert _means("feature", sentence, observation) is None
    assert CF.means_with_resolved_subject("feature", sentence, observation, actors) is None
    monkeypatch.setenv("CASELINKER_COREFERENCE", "1")
    hit = CF.means_with_resolved_subject("feature", sentence, observation, actors)
    assert hit is not None and hit[0] == "Supports_Action"


def test_adjacent_sentence_level_fires_only_on_an_explicit_anaphor(monkeypatch):
    _off(monkeypatch)
    actors = CF.make_inventory(defendant="Smith", platforms=("Kitebox",))
    pair = ["He created an account on Kitebox.", "Through that account, he sent images to Minor Victim 1."]
    assert CF.adjacent_links(pair, actors) == []
    monkeypatch.setenv("CASELINKER_ADJACENT_LEVEL", "1")
    links = CF.adjacent_links(pair, actors)
    assert len(links) == 1 and links[0]["level"] == "adjacent-sentence" and links[0]["anaphor"] == "that account"
    assert CF.adjacent_links(["He created an account on Kitebox.", "Images were stored on a phone in the evidence room."], actors) == []
    # a full noun phrase is not an anaphor, and an anaphor with no antecedent is not a link
    assert CF.adjacent_links(
        ["He created an account on Kitebox.", "The defendant sent images through the Kitebox application yesterday."], actors) == []
    assert CF.adjacent_links(
        ["The folder stayed in the cabinet overnight.", "He sent a message through the application after that."], actors) == []
    level_c = [{"relationship": "Carried_Out_Through", "cue": "through"}]
    split = CF.level_c_only(level_c, links)
    assert split["level_c"][0]["level"] == "C"
    assert split["adjacent_sentence"][0]["level"] == "adjacent-sentence"
    assert all(row["level"] != "adjacent-sentence" for row in split["level_c"])
    with pytest.raises(ValueError, match="never merged"):
        CF.level_c_only([{"level": "adjacent-sentence"}], [])


# --- frames ----------------------------------------------------------------------------------


def _page(sentence: str) -> tuple:
    page = "STATEMENT OF FACTS. " + sentence
    start = page.index(sentence)
    return page, start


def test_frames_are_off_until_selected(monkeypatch):
    _off(monkeypatch)
    page, start = _page("The defendant initiated contact with Minor Victim 1 through the Kitebox application.")
    assert FR.extract_frames(page[start:], page_text=page, sentence_start=start) == []


def test_frames_means_near_far_parenthetical_and_absent(monkeypatch):
    _off(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    near = "The defendant initiated contact with Minor Victim 1 through the Kitebox application."
    far = "The defendant initiated contact with Minor Victim 1 long before the filing ever names Kitebox."
    paren = "The defendant initiated contact with Minor Victim 1 (through the Kitebox application)."
    absent = "The defendant initiated contact with Minor Victim 1 on the telephone that afternoon."
    feature = "The defendant initiated contact with Minor Victim 1 using the disappearing-message feature."
    dated = "On May 2, 2020, the defendant initiated contact with Minor Victim 1 through the Kitebox application."

    def frames_of(sentence):
        page, start = _page(sentence)
        found = FR.extract_frames(sentence, page_text=page, sentence_start=start)
        assert found and all(FR.verify_frame(frame, page) == [] for frame in found)
        return found

    near_frames = frames_of(near)
    assert near_frames[0]["means"]["text"] == "Kitebox" and near_frames[0]["means"]["level"] == "stated-platform"
    assert near_frames[0]["level_c"] is False and "affordances" not in near_frames[0]
    assert "documented_feature_use" not in near_frames[0]
    far_frames = frames_of(far)
    assert far_frames[0]["act"]["code"] == "INITIATE_CONTACT" and far_frames[0]["means"] is None
    paren_frames = frames_of(paren)
    assert paren_frames[0]["means"]["text"] == "Kitebox"
    assert "(" in paren and paren.index("(") < paren.index("Kitebox")
    assert frames_of(absent)[0]["means"] is None
    feature_frames = frames_of(feature)
    assert feature_frames[0]["means"]["level"] == "C" and feature_frames[0]["level_c"] is True
    assert feature_frames[0]["means"]["kind"] == "feature"
    dated_frames = frames_of(dated)
    assert "May 2, 2020" in dated_frames[0]["time"]["text"]
    assert dated_frames[0]["object"]["text"] == "Minor Victim 1"
    assert dated_frames[0]["actor"]["text"].lower() == "the defendant"


def test_span_verifier_rejects_a_paraphrased_span(monkeypatch):
    _off(monkeypatch)
    monkeypatch.setenv("CASELINKER_EXTRACTOR", "frame-1.0")
    sentence = "The defendant initiated contact with Minor Victim 1 through the Kitebox application."
    page, start = _page(sentence)
    frame = FR.extract_frames(sentence, page_text=page, sentence_start=start)[0]
    assert FR.verify_frame(frame, page) == []
    paraphrased = json.loads(json.dumps(frame))
    paraphrased["actor"]["text"] = "the accused party"
    assert any("actor" in problem for problem in FR.verify_frame(paraphrased, page))
    stale = json.loads(json.dumps(frame))
    stale["passage_hash"] = "0" * 64
    assert FR.verify_frame(stale, page) == ["passage hash does not match the page"]


# --- propose-then-verify ---------------------------------------------------------------------


def _proposal(frame_id, code="INITIATE_CONTACT", sentence_id="s1"):
    return {"frame_id": frame_id, "sentence_id": sentence_id, "passage_id": "p1",
            "act": {"code": code, "text": "initiated contact", "start": 0, "end": 17},
            "actor": {"id": "defendant", "text": "the defendant", "start": 0, "end": 13}}


def test_propose_verify_accept_reject_correct_and_recover(monkeypatch):
    _off(monkeypatch)
    proposals = [_proposal("f1"), _proposal("f2", code="DISTRIBUTE_MATERIAL", sentence_id="s2"),
                 _proposal("f3", sentence_id="s3")]
    reviews = [
        {"frame_id": "f1", "decision": "accept"},
        {"frame_id": "f2", "decision": "reject", "reason_code": "not_an_act"},
        {"frame_id": "f3", "decision": "correct", "reason_code": "slot_correction", "slot": "act",
         "corrected": {"code": "SOLICIT_IMAGERY", "text": "asked", "start": 20, "end": 25}},
    ]

    def recover(sentence):
        return [_proposal("recovered", code="STORE_MATERIAL", sentence_id=sentence["sentence_id"])]

    result = PV.propose_verify(
        proposals, reviews,
        missed=({"sentence_id": "s9", "text": "The defendant kept the files in cloud storage on the phone."},
                {"sentence_id": "s3", "text": "already framed"}),
        means_sentence_ids=("s9",),
        recover=recover,
    )
    by_decision = {item["decision"] for item in result["published"]}
    assert by_decision == {"accept", "correct", "recovered"}
    assert all(item["produced_by"] == "propose-verify-1.0" for item in result["published"])
    assert result["rejected"][0]["reason_code"] == "not_an_act"
    assert result["corrected"][0]["act"]["code"] == "SOLICIT_IMAGERY"
    assert [item["sentence_id"] for item in result["recovered"]] == ["s9"]
    assert result["act_policy"] == "propose-verify-1.0"


def test_intersection_outputs_are_unchanged(monkeypatch):
    _off(monkeypatch)
    from state_machines.coding.resolve import resolve
    from tests.pacer.test_resolve import _coders

    a, b = _coders()
    assert PV.resolve_case(a, b) == resolve(a, b)
    assert all("produced_by" not in event for event in resolve(a, b)[0]["events"])
    monkeypatch.setenv("CASELINKER_ACT_POLICY", "propose-verify-1.0")
    produced = PV.resolve_case(a, b)
    assert produced["act_policy"] == "propose-verify-1.0"
    assert all(item["produced_by"] == "propose-verify-1.0" for item in produced["published"])


# --- disagreement export ---------------------------------------------------------------------


def _event(eid, action, role="offender"):
    return {"event_id": eid, "action": action, "actor": {"participant_ref": "P1", "role": role},
            "support": [{"passage_id": "p1", "facet": "action", "status": "DIRECT"}],
            "affordances": [], "harms": []}


def _bundle(events):
    return {"events": events, "passages": [
        {"passage_id": "p1", "doc_id": "sof", "pdf_page": 1, "char_start": 0, "char_end": 48}], "relations": []}


def test_disagreement_sheet_has_blank_human_columns_and_adjudicated_label(tmp_path):
    a = _bundle([_event("e1", "INITIATE_CONTACT"), _event("e2", "DISTRIBUTE_MATERIAL")])
    b = _bundle([_event("e1", "SOLICIT_IMAGERY")])
    rows = D.rows_from_intersection("synth_case", a, b)
    assert rows and all(row["human_decision"] == "" and row["human_reason"] == "" and row["human_adjudicator"] == "" for row in rows)
    assert any(row["coder_a_frame"] and row["coder_b_frame"] for row in rows)
    csv_path, jsonl_path = D.write_sheet(rows, tmp_path / "sheet")
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header.endswith("human_decision,human_reason,human_adjudicator")
    loaded = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert loaded[0]["case_id"] == "synth_case" and loaded[0]["human_decision"] == ""
    proposed = PV.propose_verify([{"frame_id": "f1", "passage_id": "p1", "sentence_start": 0, "sentence_end": 10,
                                   "act": {"code": "INITIATE_CONTACT"}, "actor": {"id": "defendant"}}],
                                 [{"frame_id": "f1", "decision": "reject", "reason_code": "wrong_actor"}])
    assert D.rows_from_propose_verify("synth_case", proposed)[0]["human_decision"] == ""
    adjudicated = [{"review": {"status": "adjudicated"}}]
    assert D.count_label(adjudicated) == "adjudicated"
    with pytest.raises(ValueError, match="never machine"):
        D.count_label(adjudicated, requested="machine")
    assert D.count_label([{"review": {"status": "agreed"}}], requested="machine") == "machine"
    with pytest.raises(SystemExit, match="refusing"):
        D.refuse_store(tmp_path / "state_machines" / "data" / "sheet")


# --- quote check -----------------------------------------------------------------------------


def test_quote_check_passes_and_reports_offset_paraphrase_and_stale_hash():
    page = "The defendant initiated contact with Minor Victim 1 through the Kitebox application."
    digest = E.sha256_text(page)
    pages = {digest: page}
    good = Q.item_from_span(case_id="synth_case", item_id="sentence", page_text=page, char_start=0, char_end=len(page), kind="act")
    assert Q.check_item(good, pages) is None
    slipped = dict(good, item_id="slipped", char_start=0, char_end=3, quote="The defendant")
    assert Q.check_item(slipped, pages)["problem"] == "offset_off"
    paraphrased = dict(good, item_id="paraphrased", quote="the accused contacted the child")
    assert Q.check_item(paraphrased, pages)["problem"] == "paraphrased"
    stale = dict(good, item_id="stale", passage_hash="ab" * 32)
    assert Q.check_item(stale, pages)["problem"] == "stale_hash"
    mismatches = Q.check_items([good, slipped, paraphrased, stale], pages)
    assert {(m["case_id"], m["item_id"]) for m in mismatches} == {
        ("synth_case", "slipped"), ("synth_case", "paraphrased"), ("synth_case", "stale")}


def test_quote_check_command_refuses_a_release_path(tmp_path, capsys):
    page = "The defendant initiated contact with Minor Victim 1 yesterday afternoon."
    records = tmp_path / "records.json"
    pages = tmp_path / "pages.json"
    records.write_text(json.dumps([Q.item_from_span(case_id="synth_case", item_id="a1", page_text=page,
                                                    char_start=0, char_end=len(page))]), encoding="utf-8")
    pages.write_text(json.dumps({E.sha256_text(page): page}), encoding="utf-8")
    assert Q.main([str(records), "--pages", str(pages)]) == 0
    blocked = tmp_path / "state_machines" / "data" / "records.json"
    with pytest.raises(SystemExit, match="refusing"):
        Q.main([str(blocked), "--pages", str(pages)])


# --- case-id preflight -----------------------------------------------------------------------


def _layout(tmp_path, *, text_name, bundle_name, release_name=None, case_id="synth_case"):
    text = tmp_path / "text" / text_name
    text.mkdir(parents=True)
    (text / "sources.json").write_text(json.dumps({"case_id": case_id, "documents": []}), encoding="utf-8")
    out = tmp_path / "out"
    for coder in ("coder_A", "coder_B"):
        folder = out / coder
        folder.mkdir(parents=True)
        (folder / f"{bundle_name}.json").write_text(json.dumps({"case_id": case_id, "events": []}), encoding="utf-8")
    release = None
    if release_name is not None:
        release = tmp_path / "release"
        cases = release / "cases"
        cases.mkdir(parents=True)
        (cases / f"{release_name}.json").write_text(json.dumps({"case_id": case_id}), encoding="utf-8")
    return text.parent, out, release


def test_preflight_matching_ids_pass_and_each_alias_kind_is_reported(tmp_path):
    text_root, out, _release = _layout(tmp_path, text_name="synth_case", bundle_name="synth_case")
    report = PF.preflight(["synth_case"], text_root, out, collected_as={})
    assert report["ok"] and report["aliases"] == []

    text_root, out, _release = _layout(tmp_path / "text_alias", text_name="text_other", bundle_name="synth_case")
    kinds = {row["kind"] for row in PF.preflight(["synth_case"], text_root, out, collected_as={})["aliases"]}
    assert kinds == {"text_dir"}

    text_root, out, _release = _layout(tmp_path / "bundle_alias", text_name="synth_case", bundle_name="bundle_other")
    kinds = {row["kind"] for row in PF.preflight(["synth_case"], text_root, out, collected_as={})["aliases"]}
    assert kinds == {"coder_bundle"}

    text_root, out, _release = _layout(tmp_path / "pdf_alias", text_name="synth_case", bundle_name="synth_case")
    kinds = {row["kind"] for row in PF.preflight(["synth_case"], text_root, out, collected_as={"synth_case": "pdf_other"})["aliases"]}
    assert kinds == {"collected_as"}
    assert PF.preflight(["synth_case"], text_root, out, collected_as={"synth_case": "pdf_other"})["aliases"][0]["other_id"] == "pdf_other"


def test_preflight_reports_the_known_id_alias_pattern(tmp_path):
    case = "ncmec_2025_1026"
    assert COLLECTED_AS[case] == "ncmec_2025_1116"
    text_root, out, release = _layout(tmp_path, text_name="ncmec_2025_1035", bundle_name="ncmec_2025_1035",
                                      release_name=case, case_id=case)
    report = PF.preflight([case], text_root, out, release_root=release, collected_as=COLLECTED_AS)
    found = {row["kind"]: row["other_id"] for row in report["aliases"]}
    assert found["text_dir"] == "ncmec_2025_1035"
    assert found["coder_bundle"] == "ncmec_2025_1035"
    assert found["collected_as"] == "ncmec_2025_1116"
    assert report["ok"] is False


def test_fingerprint_table_reports_a_changed_id_a_missing_id_and_a_shared_fingerprint():
    table = [
        {"case_id": "case_a", "fingerprint": "aa" * 32, "normalization_version": "fp-1"},
        {"case_id": "case_b", "fingerprint": "aa" * 32, "normalization_version": "fp-1"},
        {"case_id": "case_c", "fingerprint": "cc" * 32, "normalization_version": "fp-1"},
        {"case_id": "case_d", "fingerprint": "dd" * 32, "normalization_version": "fp-0"},
    ]
    same = PF.fingerprint_checks(["case_c"], table, collected_fingerprints={"case_c": "cc" * 32}, collected_as={})
    assert same["mismatches"] == [] and same["shared"] == []
    changed = PF.fingerprint_checks(["case_c"], table, collected_fingerprints={"case_c": "ee" * 32}, collected_as={})
    assert changed["mismatches"] == [{
        "case_id": "case_c", "kind": "fingerprint_different",
        "collected_fingerprint": "ee" * 32, "current_fingerprint": "cc" * 32,
    }]
    missing = PF.fingerprint_checks(["case_gone"], table, collected_as={})
    assert missing["mismatches"][0]["kind"] == "fingerprint_none" and missing["mismatches"][0]["case_id"] == "case_gone"
    shared = PF.fingerprint_checks(["case_a", "case_b"], table, collected_as={})
    assert shared["shared"] == [{"fingerprint": "aa" * 32, "case_ids": ["case_a", "case_b"]}]
    other = PF.fingerprint_checks(["case_d"], table, collected_as={})
    assert other["mismatches"][0]["kind"] == "fingerprint_other_version"
    # the id on the PDF is checked as well as the press-release id
    both = PF.fingerprint_checks(["case_a"], table, collected_as={"case_a": "case_b"})
    assert both["shared"][0]["case_ids"] == ["case_a", "case_b"]
    old_pdf = PF.fingerprint_checks(["case_c"], table, collected_as={"case_c": "pdf_old"})
    assert any(row["case_id"] == "pdf_old" and row["kind"] == "fingerprint_none" for row in old_pdf["mismatches"])


def test_fingerprint_preflight_does_not_rewrite_ids(tmp_path):
    text_root, out, _release = _layout(tmp_path, text_name="synth_case", bundle_name="synth_case")
    sources = text_root / "synth_case" / "sources.json"
    bundle = out / "coder_A" / "synth_case.json"
    before = {sources: sources.read_bytes(), bundle: bundle.read_bytes()}
    report = PF.preflight(
        ["synth_case"], text_root, out, collected_as={},
        fingerprint_table=[{"case_id": "synth_case", "fingerprint": "ab" * 32, "normalization_version": "fp-1"}],
        collected_fingerprints={"synth_case": "ff" * 32},
    )
    assert report["ok"] is False
    assert report["fingerprints"]["mismatches"][0]["kind"] == "fingerprint_different"
    assert {path: path.read_bytes() for path in before} == before
    assert sources.name == "sources.json" and bundle.name == "synth_case.json"


def test_collected_as_is_parsed_in_full_and_classified_without_a_shared_prefix():
    from pathlib import Path
    source = Path("state_machines/coding/workflow.py").read_text(encoding="utf-8")
    parsed = PF.parse_collected_as(source)
    assert parsed == COLLECTED_AS
    assert parsed == {
        "ncmec_2022_575": "ncmec_2022_586",
        "ncmec_2023_222": "ncmec_2023_224",
        "ncmec_2025_1026": "ncmec_2025_1116",
        "usss_2021_017": "usss_2021_019",
        "doj_safe_childhood_2023_420": "ncmec_2023_190",
    }
    kinds = {retired: PF.alias_class(retired, surviving) for retired, surviving in parsed.items()}
    assert kinds["ncmec_2022_575"] == "renumbering"
    assert kinds["ncmec_2023_222"] == "renumbering"
    assert kinds["ncmec_2025_1026"] == "renumbering"
    assert kinds["usss_2021_017"] == "renumbering"
    assert kinds["doj_safe_childhood_2023_420"] == "merge/dedup alias"
    # the shared first token is not the source: these are different orgs
    assert PF.alias_class("doj_safe_childhood_2024_001", "doj_ceos_2024_009") == "merge/dedup alias"
    assert PF.org_of("doj_safe_childhood_2024_001") == "doj_safe_childhood"
    assert PF.org_of("doj_ceos_2024_009") == "doj_ceos"


def test_cross_source_alias_checks_the_surviving_id_only():
    retired, surviving = "agency_one_2021_003", "bureau_two_2021_008"
    rows = PF.audit_collected_as(
        {retired: surviving},
        live_cases={surviving, "other_2020_001"},
        fingerprint_ids={surviving},
        bundle_ids={surviving},
    )
    row = rows[0]
    assert row["kind"] == "merge/dedup alias"
    assert row["bundle_resolves_to_surviving"] is True
    assert row["surviving_in_corpus"] is True
    assert row["surviving_has_fingerprint"] is True
    assert row["retired_is_live"] is False
    assert row["ok"] is True
    missed = PF.audit_collected_as(
        {retired: surviving},
        live_cases={retired, surviving},
        fingerprint_ids={surviving},
        bundle_ids={retired},
    )[0]
    assert missed["ok"] is False
    assert missed["retired_is_live"] is True
    assert missed["bundle_resolves_to_surviving"] is False


def test_collected_as_lines_were_added_after_96ffb1a35():
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    for retired in COLLECTED_AS:
        assert PF.fingerprint_lock_relation(repo, retired) == "alias recorded in workflow.py after 96ffb1a35"
    audit = PF.audit_collected_as(COLLECTED_AS, repo=repo)
    assert all(row["id_change_date"] == "not determinable from the code" for row in audit)
    dedup = next(row for row in audit if row["retired_id"] == "doj_safe_childhood_2023_420")
    assert dedup["kind"] == "merge/dedup alias"
    assert dedup["note"] == "deliberate duplicate removal; the kept id is the value"


def test_preflight_command_does_not_read_page_text_or_rewrite_ids(tmp_path, monkeypatch):
    _off(monkeypatch)
    text_root, out, _release = _layout(tmp_path, text_name="synth_case", bundle_name="synth_case")
    page = text_root / "synth_case" / "p0001.txt"
    page.write_text("this page text must not be required", encoding="utf-8")
    sources = text_root / "synth_case" / "sources.json"
    before = {path: path.read_bytes() for path in (sources, page, out / "coder_A" / "synth_case.json", out / "coder_B" / "synth_case.json")}
    code = pipeline_main(["preflight", "synth_case", "--text-root", str(text_root), "--out", str(out)])
    assert code == 0
    assert {path: path.read_bytes() for path in before} == before
    assert sorted(p.name for p in (text_root / "synth_case").iterdir()) == sorted(p.name for p in before if p.parent == text_root / "synth_case")


# --- release guard ---------------------------------------------------------------------------


def test_new_release_refuses_an_empty_registry(tmp_path, monkeypatch):
    monkeypatch.setattr("state_machines.trajectories.affordances.load", lambda paths=None: {"platforms": {}})
    cases = tmp_path / "rel" / "cases"
    cases.mkdir(parents=True)
    (cases / "synth_case.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="capability_registry_loaded"):
        build("rel", data_root=tmp_path, allow_empty_registry=False)
    assert not (tmp_path / "rel" / "graphs").exists()


def test_reading_committed_pacer_v1_does_not_raise():
    manifest = json.loads((DATA / "pacer-v1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["capability_registry_loaded"] is False
    derived = next((DATA / "pacer-v1" / "derived").glob("*.json"))
    json.loads(derived.read_text(encoding="utf-8"))


def test_allow_empty_registry_suppresses_the_refusal(monkeypatch):
    from state_machines.graphs.release import require_loaded_registry

    monkeypatch.setattr("state_machines.trajectories.affordances.load", lambda paths=None: {"platforms": {}})
    assert require_loaded_registry(allow_empty_registry=True) is False
    with pytest.raises(SystemExit, match="capability_registry_loaded"):
        require_loaded_registry(allow_empty_registry=False)


def test_allow_empty_registry_records_the_flag(tmp_path, monkeypatch):
    pytest.importorskip("case_uco")
    from tests.pacer import fixtures as F
    from tests.pacer.test_release import _adjudicated, _release

    monkeypatch.setattr("state_machines.trajectories.affordances.load", lambda paths=None: {"platforms": {}})
    bundle = _adjudicated(F.build()[0])
    root = _release(tmp_path, bundle, release="empty-reg")
    manifest = build("empty-reg", data_root=root, text_root=tmp_path / "text", allow_empty_registry=True)
    assert manifest["capability_registry_loaded"] is False
