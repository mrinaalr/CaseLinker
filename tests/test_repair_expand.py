"""Repair and expand tools: what they report, and that a proposal cannot reach the code that grades it.

Every person in this file is made up. The corpus is a temporary sqlite file built here.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from assertion_store import write_case_assertions
from caselinker_mcp import repair_expand as R
from storage import CaseStorage

A = R._pipeline().assertions_module

TIP = "Detectives followed up on a CyberTip and contacted Corin Ashcombe, 34, at his workplace."
DECOY = "Officer used screen name Jake, a 14-year-old from Boise, during the chat. Reese Thistlewood, 41, was arrested."
PAID = "Rowan Brambleton, 52, was sentenced to 8 years in prison and ordered to pay $4,000 in restitution."
CASES = {"tip_case": TIP, "decoy_case": DECOY, "paid_case": PAID}

SCREEN_RULE = {
    "id": "screen_name_age", "field": "age", "role": "decoy",
    "regex": r"screen name\W+(?:\w+\W+){0,6}?(\d{1,2})-year-old",
    "positives": ["used screen name Jake, a 14-year-old from Boise"], "negatives": ["a 14-year-old victim"],
}
TIP_RULE = {
    "id": "followed_up_tip", "field": "investigation_type", "role": "case_action",
    "regex": r"followed\s+up\s+on\s+an?\s+(Cyber\s*Tip)",
    "positives": ["detectives followed up on a CyberTip"], "negatives": ["report a CyberTip online"],
}


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "corpus.db"
    storage = CaseStorage(str(path))
    for cid, text in CASES.items():
        assert storage.store_case({"id": cid, "source": "TEST", "raw_data": {"source_file": "t.pdf",
                                                                              "case_text": text, "case_id": cid}})
    con = sqlite3.connect(path)
    for cid, text in CASES.items():
        assertions = A.collect_assertions(text, case_id=cid, use_spacy=False, overrides={})
        write_case_assertions(con.cursor(), case_id=cid, run_id=f"run-{cid}", assertions=assertions,
                              resolutions=A.resolve(assertions, text=text), dialect="sqlite")
    con.commit()
    con.close()
    monkeypatch.setenv("CASELINKER_DB", str(path))
    return path


@pytest.fixture
def ext_dir(tmp_path: Path, monkeypatch) -> Path:
    folder = tmp_path / "extensions"
    folder.mkdir()
    monkeypatch.setattr(R, "EXTENSIONS_DIR", folder)
    return folder


def _extension(folder: Path, name: str, body: str) -> None:
    (folder / name).mkdir()
    (folder / name / "extension.py").write_text(textwrap.dedent(body), encoding="utf-8")


# --- the trace hook ------------------------------------------------------------

def test_trace_observes_without_changing_the_assertions():
    plain = A.collect_assertions(DECOY, use_spacy=False, overrides={})
    trace = []
    traced = A.collect_assertions(DECOY, use_spacy=False, overrides={}, trace=trace)
    assert json.dumps(plain, sort_keys=True, default=str) == json.dumps(traced, sort_keys=True, default=str)
    assert {t["detector"] for t in trace} >= {"press_age", "press_victim_gate"}
    assert len(trace) >= len(traced)  # dropped candidates are traced too


# --- describe_pipeline -----------------------------------------------------------

def test_describe_lists_detectors_with_their_source_and_the_reserved_decisions(corpus):
    out = R.describe_pipeline()
    by_name = {d["name"]: d for d in out["detectors"]}
    assert by_name["press_cybertip"]["kinds"] == ["press_release"]
    assert by_name["press_cybertip"]["defined_in"].startswith("src/Processing Layer/field_assertions/assertions.py:")
    assert [f["field"] for f in out["fields"]] == ["age", "sentence", "investigation_type", "cybertip_reporter", "date"]
    reserved = {r["decision"] for r in out["reserved_for_maintainer"]}
    assert "a new document kind" in reserved and "ontology mapping and pinned versions" in reserved
    assert out["corpus"]["cases"] == 3 and "victim_count" in out["corpus"]["domain_columns"]
    assert out["write"] is False


def test_describe_says_when_there_is_no_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("CASELINKER_DB", str(tmp_path / "absent.db"))
    assert R.describe_pipeline()["corpus"]["available"] is False


# --- diagnose_case -------------------------------------------------------------

def test_diagnose_shows_the_unscoped_tip_with_a_masked_excerpt(corpus):
    out = R.diagnose_case("tip_case", "investigation_type")
    field = out["fields"]["investigation_type"]
    assert field["stored"]["status"] == "needs_review" and field["replay"]["status"] == "needs_review"
    [cand] = field["candidates"]
    assert cand["detector"] == "press_cybertip" and cand["role"] == "unscoped" and cand["in_store"]
    assert "followed up on a CyberTip" in cand["excerpt"]
    assert "Ashcombe" not in json.dumps(out)
    assert field["changed_if_reextracted"] is False


def test_diagnose_lists_rows_todays_readers_no_longer_raise(corpus):
    con = sqlite3.connect(corpus)  # a row an older reader stored: rows are append-only, so add one
    write_case_assertions(con.cursor(), case_id="paid_case", run_id="run-paid_case", resolutions={}, dialect="sqlite",
                          assertions=[{"field": "age", "method": "regex", "value": 8, "role": "victim", "span_start": 64,
                                       "span_end": 65, "span_ok": 1, "confidence": 0.9, "extras": {}}])
    con.commit()
    con.close()
    out = R.diagnose_case("paid_case", "age")
    assert any(row["why"] == "today's readers do not raise it" for row in out["fields"]["age"]["stored_only"])


def test_diagnose_rejects_unknown_cases_and_fields(corpus):
    assert "error" in R.diagnose_case("no_such_case")
    assert "error" in R.diagnose_case("tip_case", "victim_name")


# --- extensions: the child runs them, the parent grades --------------------------

def test_an_extension_that_patches_the_gate_is_still_graded_by_the_parent(ext_dir):
    _extension(ext_dir, "tamper", '''
        import span_gate
        span_gate.age_support = lambda *a, **k: (True, "patched")
        span_gate.money_value = lambda token: 1e9
        print("noise on stdout")
        FIELDS = {"paid": "money"}

        def detect_tamper(ctx):
            boise = ctx.text.index("Boise")
            dollars = ctx.text.index("$4,000")
            return [
                {"field": "age", "role": "victim", "value": 9, "span_start": boise, "span_end": boise + 5, "confidence": 1.0},
                {"field": "paid", "role": "ordered", "value": 999, "span_start": dollars, "span_end": dollars + 6, "confidence": 0.9},
            ]
    ''')
    out = R.rehearse_extension("tamper", [{"case_id": "c", "text": DECOY + " " + PAID}])
    assert out["errors"] == []
    assert [(a["field"], a["value"]) for a in out["kept"]] == [("paid", 4000.0)]  # the span's amount, not 999 or 1e9
    assert sum(out["dropped"].values()) == 1  # the age on "Boise"


def test_a_hanging_extension_is_stopped(ext_dir):
    _extension(ext_dir, "hangs", '''
        def detect_forever(ctx):
            while True:
                pass
    ''')
    out = R.rehearse_extension("hangs", [{"case_id": "c", "text": TIP}], timeout=5)
    assert out["kept"] == [] and "timed out" in out["errors"][0]


def test_an_extension_error_is_reported_by_type_only(ext_dir):
    _extension(ext_dir, "raises", '''
        def detect_boom(ctx):
            raise ValueError(ctx.text)
    ''')
    out = R.rehearse_extension("raises", [{"case_id": "c", "text": TIP}])
    assert out["errors"] == ["raises.detect_boom: ValueError on c"]
    assert "Ashcombe" not in json.dumps(out)


def test_a_literal_span_on_a_person_is_dropped_and_no_literal_text_is_returned(ext_dir):
    _extension(ext_dir, "literal", '''
        FIELDS = {"employer": "literal"}

        def detect_employer(ctx):
            name = ctx.text.index("Corin")
            work = ctx.text.index("workplace")
            return [{"field": "employer", "role": "stated", "span_start": name, "span_end": name + 14, "confidence": 0.9},
                    {"field": "employer", "role": "stated", "span_start": work, "span_end": work + 9, "confidence": 0.9}]
    ''')
    out = R.rehearse_extension("literal", [{"case_id": "c", "text": TIP}])
    assert out["dropped"] == {"span_names_a_person": 1}
    assert [a["value"] for a in out["kept"]] == [None]


@pytest.mark.parametrize("body, reason", [
    ('FIELDS = {"age": "number"}\ndef detect_x(ctx):\n    return []\n', "already gated"),
    ('DOCUMENT_KINDS = ("tweet",)\ndef detect_x(ctx):\n    return []\n', "unknown document kinds"),
    ('FIELDS = {"x": "anything"}\ndef detect_x(ctx):\n    return []\n', "must name one of"),
    ('FIELDS = dict(x="money")\ndef detect_x(ctx):\n    return []\n', "must be literals"),
    ('X = 1\n', "no detect_"),
])
def test_manifests_that_would_widen_the_core_are_refused(ext_dir, body, reason):
    _extension(ext_dir, "bad_manifest", body)
    assert reason in R.read_manifest("bad_manifest")["error"]


def test_the_shipped_restitution_extension_reads_amounts():
    out = R.rehearse_extension("restitution", [{"case_id": "c", "text": PAID}])
    assert [(a["value"], a["role"]) for a in out["kept"]] == [(4000.0, "ordered")]


# --- scaffold_extension ----------------------------------------------------------

def test_scaffold_dry_run_writes_nothing_and_a_real_one_fails_its_own_test(ext_dir):
    dry = R.scaffold_extension("tip_wording", "investigation_type", role="case_action")
    assert dry["write"] is False and not (ext_dir / "tip_wording").exists()
    made = R.scaffold_extension("tip_wording", "investigation_type", role="case_action", dry_run=False)
    assert made["created"] == ["extensions/tip_wording/extension.py", "extensions/tip_wording/test_extension.py"]
    assert R.read_manifest("tip_wording")["detectors"] == ["detect_investigation_type"]
    proc = subprocess.run([sys.executable, "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())",
                           str(ext_dir / "tip_wording" / "test_extension.py")], capture_output=True)
    assert proc.returncode == 0
    body = (ext_dir / "tip_wording" / "test_extension.py").read_text()
    assert 'assert SAMPLE and EXPECTED_SPANS' in body  # fails until written
    assert "already exists" in R.scaffold_extension("tip_wording", "investigation_type")["error"]


@pytest.mark.parametrize("kwargs, reason", [
    ({"field": "cybertip_reporter"}, "read by its own detector"),
    ({"field": "restitution"}, "value_type must be one of"),
    ({"field": "age", "doc_kind": "tweet"}, "maintainer's decision"),
])
def test_scaffold_refuses_what_is_not_an_extension(ext_dir, kwargs, reason):
    assert reason in R.scaffold_extension("refused", **kwargs)["error"]


# --- run_gate --------------------------------------------------------------------

def test_a_rule_lists_the_cases_it_changes(corpus):
    out = R.run_gate(rule=SCREEN_RULE, checks=["integrity"])
    impact = out["impact"]
    assert impact["cases_matched"] == 1 and impact["cases_changed"] == 1
    assert impact["changes"][0]["case_id"] == "decoy_case"
    assert out["checks"]["proposal"]["approved_entry"]["regex"] == SCREEN_RULE["regex"]
    assert out["write"] is False and A.compiled_rules.APPROVED == []


def test_a_rule_in_the_same_family_as_a_contrary_reader_moves_nothing(corpus):
    """The press detector already calls this tip unscoped; a surface rule saying case_action is a family self-contradiction."""
    impact = R.run_gate(rule=TIP_RULE, checks=["integrity"])["impact"]
    assert impact["cases_matched"] == 1 and impact["cases_changed"] == 0


@pytest.mark.parametrize("rule, reason", [
    ({**SCREEN_RULE, "regex": r"(\d+)"}, "must leave alone"),
    ({**SCREEN_RULE, "positives": ["nothing here"]}, "missed a confirmed quote"),
    ({**SCREEN_RULE, "field": "date"}, "field must be one of"),
    ({**SCREEN_RULE, "document_kinds": ["tweet"]}, "document_kinds"),
])
def test_bad_rules_fail_the_gate_without_running(corpus, rule, reason):
    out = R.run_gate(rule=rule, checks=["integrity"])
    assert out["passed"] is False and reason in out["checks"]["proposal"]["reason"]
    assert "impact" not in out


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel in (*R.GRADER, *R.TEST_TIER, "src/x.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("line one\nline two\n")
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root,
                                    check=True, capture_output=True)
    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "base")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def test_integrity_flags_an_edited_grader_and_a_weakened_test_but_not_an_added_one(tmp_path):
    root = _repo(tmp_path)
    assert R._integrity(root)["ok"] is True
    (root / R.TEST_TIER[0]).write_text("line one\nline two\nline three\n")
    assert R._integrity(root)["ok"] is True  # adding a test is fine
    (root / R.TEST_TIER[0]).write_text("line one\n")
    weakened = R._integrity(root)
    assert weakened["ok"] is False and weakened["tests_rewritten"][0]["file"] == R.TEST_TIER[0]
    (root / R.TEST_TIER[0]).write_text("line one\nline two\n")
    (root / R.GRADER[0]).write_text("def run_gate(**k):\n    return {'passed': True}\n")
    edited = R._integrity(root)
    assert edited["ok"] is False and edited["grader_changed"] == [R.GRADER[0]]


# --- the MCP surface -------------------------------------------------------------

def test_the_tools_are_registered_on_local_mcp(corpus):
    from caselinker_mcp import server

    fn = getattr(server.describe_pipeline, "fn", server.describe_pipeline)
    out = asyncio.run(fn())
    assert out["tool_kind"] == "READ" and out["corpus"]["cases"] == 3
    for name in ("diagnose_case", "profile_new_source", "scaffold_extension", "run_gate"):
        assert callable(getattr(server, name))
