from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.quality.check_repository import (
    Finding,
    check_paths,
    is_authored_text,
    main,
    tracked_paths,
    validate_python,
    validate_text,
)


def test_validate_text_accepts_utf8() -> None:
    text = "evidence \N{EN DASH} lineage\n"

    assert validate_text(Path("example.md"), text.encode()) == []


def test_validate_text_rejects_invalid_utf8() -> None:
    findings = validate_text(Path("claims.py"), b'"2002\xe2\xff\xff2026"')

    assert len(findings) == 1
    assert findings[0].check == "utf8"


def test_validate_text_rejects_merge_markers() -> None:
    findings = validate_text(Path("module.py"), b"<<<<<<< ours\n=======\n>>>>>>> theirs\n")

    assert [finding.check for finding in findings] == [
        "merge-marker",
        "merge-marker",
        "merge-marker",
    ]


def test_validate_text_rejects_replacement_and_nul_characters() -> None:
    findings = validate_text(Path("damaged.md"), "damaged \ufffd\x00".encode())

    assert [finding.check for finding in findings] == ["utf8", "text"]


def test_validate_python_reports_syntax_error() -> None:
    findings = validate_python(Path("broken.py"), "def unfinished(\n")

    assert len(findings) == 1
    assert findings[0].check == "python-compile"
    assert "line 1" in findings[0].detail


def test_validate_python_does_not_execute_source() -> None:
    findings = validate_python(Path("safe.py"), "raise RuntimeError('must not execute')\n")

    assert findings == []


def test_validate_python_reports_value_error() -> None:
    findings = validate_python(Path("nul.py"), "value = '\x00'")

    assert len(findings) == 1
    assert findings[0].check == "python-compile"
    assert "null bytes" in findings[0].detail


def test_finding_renders_relative_and_external_paths(tmp_path: Path) -> None:
    internal = Finding(tmp_path / "inside.py", "test", "detail")
    external = Finding(Path("/outside.py"), "test", "detail")

    assert internal.render(tmp_path) == "inside.py: test: detail"
    assert external.render(tmp_path) == "/outside.py: test: detail"


def test_authored_text_filter_excludes_artifacts(tmp_path: Path) -> None:
    authored = tmp_path / "docs" / "design.md"
    migration = tmp_path / "migrations" / "0001.sql"
    rdf_shape = tmp_path / "schemas" / "profile.ttl"
    named_text = tmp_path / "LICENSE"
    generated = tmp_path / "ontology" / "graph_output" / "case.json"
    binary = tmp_path / "image.png"

    assert is_authored_text(authored, tmp_path)
    assert is_authored_text(migration, tmp_path)
    assert is_authored_text(rdf_shape, tmp_path)
    assert is_authored_text(named_text, tmp_path)
    assert not is_authored_text(generated, tmp_path)
    assert not is_authored_text(binary, tmp_path)


def test_check_paths_validates_text_and_python(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    bad = tmp_path / "bad.py"
    ignored = tmp_path / "ontology" / "graph_output" / "bad.py"
    good.write_text("answer = 42\n")
    bad.write_text("def broken(\n")
    ignored.parent.mkdir(parents=True)
    ignored.write_text("def ignored(\n")

    findings = check_paths(tmp_path, [good, bad, ignored])

    assert len(findings) == 1
    assert findings[0].path == bad
    assert findings[0].check == "python-compile"


def test_check_paths_does_not_decode_invalid_python_twice(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.py"
    invalid.write_bytes(b"value = '\xff'\n")

    findings = check_paths(tmp_path, [invalid])

    assert [finding.check for finding in findings] == ["utf8"]


def test_tracked_paths_includes_cached_and_untracked_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    cached = tmp_path / "cached.py"
    untracked = tmp_path / "untracked.md"
    ignored = tmp_path / "ignored.log"
    cached.write_text("cached = True\n")
    untracked.write_text("# Draft\n")
    ignored.write_text("ignored\n")
    (tmp_path / ".gitignore").write_text("*.log\n")
    subprocess.run(["git", "add", "cached.py", ".gitignore"], cwd=tmp_path, check=True)

    result = [path.relative_to(tmp_path).as_posix() for path in tracked_paths(tmp_path)]

    assert result == [".gitignore", "cached.py", "untracked.md"]


def test_main_reports_missing_explicit_path(tmp_path: Path, capsys: object) -> None:
    result = main(["missing.py"], root=tmp_path)

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert result == 2
    assert "file does not exist" in captured.err


def test_main_reports_findings(tmp_path: Path, capsys: object) -> None:
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(\n")

    result = main(["invalid.py"], root=tmp_path)

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert result == 1
    assert "repository check failed with 1 finding" in captured.err


def test_main_passes_explicit_path(tmp_path: Path, capsys: object) -> None:
    valid = tmp_path / "valid.py"
    valid.write_text("valid = True\n")

    result = main(["valid.py"], root=tmp_path)

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert result == 0
    assert "repository check passed for 1 tracked file" in captured.out
