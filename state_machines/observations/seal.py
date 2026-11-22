"""Seal the held-out cases and the gold-sample frame before any tuning.

    python -m state_machines.observations.seal --config CONFIG --out DIR

The config committed in the repo is blank: no corpus ids, no excluded ids, no
seed and no sizes. Those values are filled in the config before the command is
run. It reads ids only. It does not open page text, and it refuses to write
into ``state_machines/data``, ``local`` or ``caselinker_oxigraph``.

The draw is deterministic. Eligible ids are the corpus minus the exclusion list,
sorted, then sampled with ``random.Random`` at the given seed. Held-out cases are
drawn first. The gold-sample frame is drawn from what remains, so the two sets
are disjoint. An excluded id is not eligible and cannot be drawn. The same
inputs, including the code version, produce the same file bytes.

The SHA-256 is of the canonical manifest with the hash field left out. That
digest is then stored on the manifest. ``development_load`` and
``extraction_debug`` refuse any sealed id unless ``--final-evaluation`` is
passed with that digest. Scoring checks the digest before it computes anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

SEAL_VERSION = "seal-1.0"
HASH_FIELD = "sha256"
_FORBIDDEN = ("caselinker_oxigraph",)


def refuse_store(path: Path) -> None:
    """Refuse a path inside the committed release, the local store, or Oxigraph."""
    parts = set(Path(path).resolve().parts)
    if {"state_machines", "data"} <= parts or "local" in parts or any(name in parts for name in _FORBIDDEN):
        raise SystemExit(f"refusing to read or write {path}: that store is not for this command")


def canonical_bytes(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_sha256(body: dict) -> str:
    """Hash of the manifest with the hash field omitted."""
    payload = {k: body[k] for k in body if k != HASH_FIELD}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def verify_manifest(manifest: dict) -> str:
    """The stored digest, or a refusal when it is not the hash of the body."""
    digest = manifest_sha256(manifest)
    if digest != manifest.get(HASH_FIELD):
        raise SystemExit("sealed manifest hash does not match its contents")
    return digest


def load_config(path: Path) -> dict:
    """The seal config. A blank committed config is refused, so it cannot seal anything."""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in ("seed", "held_out_size", "gold_frame_size") if cfg.get(key) is None]
    if missing or not cfg.get("corpus_ids"):
        detail = ", ".join(missing) if missing else "corpus_ids"
        raise SystemExit(f"seal config is blank ({detail}); fill the seed, the sizes and the corpus ids before sealing")
    if not isinstance(cfg["seed"], int) or isinstance(cfg["seed"], bool):
        raise SystemExit("seed must be an integer")
    for key in ("held_out_size", "gold_frame_size"):
        if not isinstance(cfg[key], int) or isinstance(cfg[key], bool) or cfg[key] < 0:
            raise SystemExit(f"{key} must be a non-negative integer")
    return cfg


def code_version(repo: Optional[Path] = None) -> str:
    root = repo or Path(__file__).resolve().parents[2]
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def seal(corpus_ids: Sequence[str], *, exclusion_ids: Sequence[str], seed: int,
         held_out_size: int, gold_frame_size: int, code_version: str) -> dict:
    """The sealed manifest. Excluded ids are removed before either draw."""
    corpus = list(corpus_ids)
    excluded = sorted(set(exclusion_ids))
    banned = set(excluded)
    eligible = sorted(set(corpus) - banned)
    if held_out_size + gold_frame_size > len(eligible):
        raise SystemExit(
            f"asked for {held_out_size + gold_frame_size} cases from {len(eligible)} eligible "
            f"({len(banned & set(corpus))} excluded); excluded ids are not drawn")
    rng = random.Random(seed)
    held = sorted(rng.sample(eligible, held_out_size))
    remaining = [case_id for case_id in eligible if case_id not in set(held)]
    frame = sorted(rng.sample(remaining, gold_frame_size))
    if banned & set(held) or banned & set(frame):
        raise SystemExit("excluded ids were drawn")
    body = {
        "seal_version": SEAL_VERSION,
        "seed": seed,
        "sizes": {"held_out": held_out_size, "gold_frame": gold_frame_size},
        "population": {
            "corpus": len(corpus),
            "excluded": len(banned & set(corpus)),
            "eligible": len(eligible),
            "held_out": len(held),
            "gold_frame": len(frame),
            "development": len(eligible) - len(held) - len(frame),
        },
        "exclusion_ids": excluded,
        "held_out_ids": held,
        "gold_frame_ids": frame,
        "code_version": code_version,
        "python": sys.version.split()[0],
    }
    body[HASH_FIELD] = manifest_sha256(body)
    return body


def sealed_ids(manifest: dict) -> set:
    return set(manifest.get("held_out_ids") or []) | set(manifest.get("gold_frame_ids") or [])


def guard_development(case_ids: Sequence[str], manifest: dict, *, final_evaluation: bool = False,
                      manifest_hash: Optional[str] = None) -> list:
    """Refuse sealed case ids unless this is the final evaluation and the hash matches.

    The manifest hash is checked first, so a tampered file is rejected before any
    id is used. Development and tuning call this with ``final_evaluation`` false.
    """
    digest = verify_manifest(manifest)
    if final_evaluation and manifest_hash != digest:
        raise SystemExit("final evaluation requires the sealed manifest hash")
    hit = sorted(set(case_ids) & sealed_ids(manifest))
    if hit and not final_evaluation:
        raise SystemExit("refusing sealed case ids on a development path: " + ", ".join(hit))
    return list(case_ids)


def development_load(case_ids: Sequence[str], manifest: dict, *, final_evaluation: bool = False,
                     manifest_hash: Optional[str] = None) -> list:
    """The development and tuning entry point. Sealed ids stay out."""
    return guard_development(case_ids, manifest, final_evaluation=final_evaluation, manifest_hash=manifest_hash)


def extraction_debug(case_ids: Sequence[str], manifest: dict, *, final_evaluation: bool = False,
                     manifest_hash: Optional[str] = None) -> list:
    """The extraction-debug entry point. Same refusal as development."""
    return guard_development(case_ids, manifest, final_evaluation=final_evaluation, manifest_hash=manifest_hash)


def write_manifest(manifest: dict, out_dir: Path) -> Path:
    refuse_store(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sealed_manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--code-version", default="", help="defaults to git rev-parse HEAD")
    args = ap.parse_args(argv)
    refuse_store(args.config)
    refuse_store(args.out)
    cfg = load_config(args.config)
    version = args.code_version or code_version()
    manifest = seal(cfg["corpus_ids"], exclusion_ids=cfg.get("exclusion_ids") or [], seed=cfg["seed"],
                    held_out_size=cfg["held_out_size"], gold_frame_size=cfg["gold_frame_size"],
                    code_version=version)
    path = write_manifest(manifest, args.out)
    print(path)
    print(manifest[HASH_FIELD])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
