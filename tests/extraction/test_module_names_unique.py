"""No two source folders that go on sys.path define the same module name.

Tests and scripts insert these folders into sys.path in different orders. When two of
them hold a module with the same name, `import <name>` returns whichever folder is
first at that moment, and Python caches that answer for the rest of the process.
`Pattern Processing Layer/processing.py` shadowed the `Processing Layer/processing.py`
wrapper this way: a whole-suite run failed to collect six test files with
"module 'processing' has no attribute 'assertions_module'".
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Folders that code in this repo puts on sys.path.
PATH_DIRS = (
    "src",
    "src/Processing Layer",
    "src/Processing Layer/Pattern Processing Layer",
    "src/Processing Layer/ML Processing Layer",
    "src/Processing Layer/field_assertions",
    "src/Storage Layer",
    "src/Ingestion Layer",
    "src/Clustering & Analysis Layer",
    "src/Visualization Layer",
    "ontology/pipeline",
    "scripts/run",
    "run",
)

ALLOWED = {
    # run/main.py (the API) and src/main.py (the pipeline) are loaded by file path or
    # with only one of the two folders on sys.path.
    "main": {"src", "run"},
    # Processing Layer/assertions.py is a shim that loads field_assertions/assertions.py,
    # so either folder yields the same code.
    "assertions": {"src/Processing Layer", "src/Processing Layer/field_assertions"},
}


def _modules(folder: Path):
    for f in folder.glob("*.py"):
        if f.name != "__init__.py":
            yield f.stem
    for d in folder.iterdir():
        if d.is_dir() and (d / "__init__.py").exists():
            yield d.name


def test_no_module_name_is_defined_in_two_path_folders():
    where = defaultdict(set)
    for rel in PATH_DIRS:
        folder = ROOT / rel
        if folder.is_dir():
            for name in _modules(folder):
                where[name].add(rel)
    clashes = {n: sorted(d) for n, d in where.items() if len(d) > 1 and d != ALLOWED.get(n)}
    assert not clashes, clashes


def test_processing_layer_package_imports():
    import importlib.util
    import sys

    init = ROOT / "src/Processing Layer/__init__.py"
    spec = importlib.util.spec_from_file_location(
        "processing_layer_under_test", init, submodule_search_locations=[str(init.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert mod.extract_features.__module__ == "pattern_processing_layer.pattern_processing"
    assert callable(mod.MergeProcessing)


def test_processing_resolves_to_the_wrapper_even_with_the_pattern_folder_first():
    import importlib.machinery

    order = [str(ROOT / "src/Processing Layer/Pattern Processing Layer"), str(ROOT / "src/Processing Layer")]
    spec = importlib.machinery.PathFinder.find_spec("processing", order)
    assert spec is not None
    assert Path(spec.origin) == ROOT / "src/Processing Layer/processing.py"
