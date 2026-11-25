"""Case-level harms and the two affordance × harm tables for one press corpus.

Reads caselinker.db (read-only). Does not write the database, the snapshot, or
the public AfH outputs other than the three JSON files below.

strict: the harm cue is in a sentence that names the platform.
broad: the case-level harm set, on the same stated-tier mentions.
"""
from __future__ import annotations

import importlib.util
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import pipeline as pl
from .labels import correct_platform_labels, year_corrections
from .snapshot import REPO, RESEARCH

_LAUNCH = importlib.util.spec_from_file_location(
    "launch_years", REPO / "ontology" / "platform_affordance_evidence" / "launch_years.py")
_launch_years = importlib.util.module_from_spec(_LAUNCH)
_LAUNCH.loader.exec_module(_launch_years)

OUT = RESEARCH / "outputs"
H1 = "h1_contact_sexual_abuse"
H2 = "h2_depicted_in_abuse_imagery"
H3 = "h3_imagery_circulated"
H5 = "h5_commercial_sexual_exploitation"
# Input identity of this run (numbers/afh_inputs.py RUN_INPUTS.json), set by numbers/run_afh.py. Only a
# run on the frozen AfH 2.0 inputs may say paper_numbers: true; anything else, including a run that
# did not say what it read, says false.
INPUTS: Optional[dict] = None


def _paper_numbers() -> bool:
    return bool(INPUTS and INPUTS.get("afh_2_0_snapshot") is True)


def _snapshot_label():
    if not INPUTS:
        return "unknown: run outside numbers/run_all.sh, inputs not identified"
    return {k: INPUTS.get(k) for k in ("afh_2_0_snapshot", "db_sha256", "db_cases", "pacer_release", "pacer_sha256")}
TEST_CLASSES = ("Anonymity", "Ephemerality", "ContactDiscovery", "UnmonitoredCommunication",
                "DistributionInfrastructure")
GENERATIONS = _launch_years.GENERATIONS
PUBLICATION_ERAS = ("<=2016", "2017-2019", "2020-2022", "2023-2026")
N_MIN = 30
K_PRESENT = 3
SAMPLE_SEED = 20261124
SAMPLE_N = 30
# The gap this replaced could cross a period. Counted only so the change is measurable.
_OLD_LIVE = re.compile(
    r"\b(?:(?:webcam|video\s*(?:chat|call)s?|livestreams?|live\s*streams?)(?:\W+\w+){0,16}\W+"
    r"(?:perform\w*\s+(?:sex|sexual)|performing\s+sexual|sex\s+acts?|masturbat\w*|sexually\s+explicit)"
    r"|(?:perform\w*\s+(?:sex|sexual)|performing\s+sexual|sex\s+acts?|masturbat\w*|sexually\s+explicit)"
    r"(?:\W+\w+){0,16}\W+(?:webcam|video\s*(?:chat|call)s?|livestreams?|live\s*streams?))\b",
    re.I,
)


def _year(raw: dict) -> Optional[int]:
    year = raw.get("year")
    if year in (None, ""):
        return None
    try:
        return int(year)
    except (TypeError, ValueError):
        return None


def _h5_removed(text: str, topics: set, harm: dict) -> bool:
    """Trafficking case whose every commercial-sex cue match contains restitution."""
    if "trafficking" not in topics or not harm.get("_cue_reject"):
        return False
    matches = list(harm["_cue"].finditer(text))
    if not matches:
        return False
    return not any(not harm["_cue_reject"].search(m.group(0)) for m in matches)


def classify_release(text: str, topics: Iterable[str], investigation_types, age: Any, codebook: pl.Codebook) -> dict:
    topics = set(topics or [])
    roles = pl.settled_age_roles(age if isinstance(age, dict) else {})
    pre = pl.case_harm_set(text, topics, codebook)
    final, _cleared = pl.apply_case_harm_gates(pre, topics, investigation_types, roles)
    signal = pl.h1_form(text, topics, codebook.harms[H1])
    likeness = any(pl._guarded_hit(s, codebook.harms[H2]) for s in pl._sentences(text))
    ai = "ai_csam" in topics and not likeness and H1 not in pre and H2 not in pre
    attempted = (not final) and bool(pl.ENTICEMENT.search(text)) and signal is None
    strict = pl.undercover_no_real_minor(investigation_types, roles)
    return {
        "pre": pre,
        "final": final,
        "form": signal if H1 in final else None,
        "signal": signal,
        "ai": ai,
        "attempted": attempted,
        "strict": strict,
        "sting_empty": bool(strict and not final),
        "sting_h2_h3": bool(strict and (H2 in final or H3 in final)),
    }


# Affordance x harm rows count a class only while the platform's registry window for it is open
# (since..ended), the same rule as recurrence (_on_at). False reproduces the unclosed tables.
CLOSE_AT_END = True

# Cases left out of a run, for sensitivity analysis only (numbers/year_sensitivity.py). Empty for AfH 2.0.
EXCLUDE_CASES: frozenset = frozenset()


def _default_on(info: pl.PlatformInfo, codebook: pl.Codebook, year: Optional[int]) -> List[str]:
    if year is None:
        return []
    out = []
    for cname, spec in codebook.classes.items():
        if CLOSE_AT_END:
            if _on_at(info, spec["capability"], year):
                out.append(cname)
            continue
        since = info.capabilities.get(spec["capability"])
        if since is None or year < since:
            continue
        if info.default_on.get(spec["capability"], False):
            out.append(cname)
    return out


def _on_at(info: pl.PlatformInfo, key: str, year: Optional[int]) -> bool:
    """The class is default_on and its registry window covers the publication year."""
    if year is None or not info.default_on.get(key):
        return False
    cap = info.cap_meta.get(key) or {}
    since = cap.get("since", info.capabilities.get(key))
    if since is None or year < since:
        return False
    ended = cap.get("ended")
    return ended is None or year <= ended


def _publication_era(year: Optional[int]) -> Optional[str]:
    """Publication-year bin. Years after 2026 are outside the table."""
    if year is None:
        return None
    if year <= 2016:
        return "<=2016"
    if year <= 2019:
        return "2017-2019"
    if year <= 2022:
        return "2020-2022"
    if year <= 2026:
        return "2023-2026"
    return None


def _recurs(counts: Dict[str, Dict[str, set]], coded: Dict[str, set], cname: str,
            bins: tuple = GENERATIONS) -> bool:
    """Present in at least two qualifying bins, and in every qualifying bin after the first."""
    qualifying = [g for g in bins if len(coded[g]) >= N_MIN]
    present = [g for g in qualifying if len(counts[cname][g]) >= K_PRESENT]
    if len(present) < 2:
        return False
    first = bins.index(present[0])
    return all(g in present for g in qualifying if bins.index(g) > first)


def _era_cell(cases: set, platforms: Dict[str, set], qualifies: bool) -> dict:
    """Case count, presence, contributing platforms, and the top platform's share of the cases."""
    n = len(cases)
    ranked = sorted(platforms, key=lambda name: (-len(platforms[name]), name))
    top = ranked[0] if ranked else None
    top_n = len(platforms[top]) if top else 0
    return {
        "cases": n,
        "present": qualifies and n >= K_PRESENT,
        "platforms": len(platforms),
        "top_platform": top,
        "top_platform_cases": top_n,
        "top_platform_share": round(top_n / n, 3) if top and n else None,
    }


def _mask_excerpt(text: str, spans) -> str:
    sys.path.insert(0, str(REPO / "src" / "Processing Layer" / "field_assertions"))
    from people_mask import mask_person_names, person_surnames, public_text, spans_for
    features = {"person_spans": spans} if spans else {}
    masked = public_text(text or "", spans_for(features, text or ""))
    masked = mask_person_names(masked, surnames=person_surnames(text or ""))[0]
    return " ".join(masked.split())[:300]


def _table(counts: Dict[str, Dict[str, set]], harms: List[str]) -> dict:
    return {c: {h: len(counts[c][h]) for h in harms} for c in pl.CLASSES}


def _empty_counts(harms: List[str]) -> Dict[str, Dict[str, set]]:
    return {c: {h: set() for h in harms} for c in pl.CLASSES}


def build(db_path: Path, log=print) -> dict:
    codebook = pl.Codebook.load()
    registry = pl.platform_registry()
    pe = pl.evidence_module()
    launch = {r["platform_id"]: r["launch_year"] for r in _launch_years.load()}
    class_key = {name: spec["capability"] for name, spec in codebook.classes.items()}
    harms = list(codebook.harms)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    ages = {}
    for cid, blob in conn.execute("SELECT case_id, final_json FROM field_resolutions WHERE field='age' ORDER BY id"):
        parsed = json.loads(blob) if blob else {}
        ages[cid] = parsed if isinstance(parsed, dict) else {}
    rows = []
    fixes = year_corrections(conn)
    for cid, topics, feats, raw, plats in conn.execute(
        "SELECT id, case_topics, extracted_features, raw_data, platforms_used FROM cases ORDER BY id"
    ):
        if cid in EXCLUDE_CASES:
            continue                                     # sensitivity runs only; empty for AfH 2.0
        raw_obj = json.loads(raw or "{}")
        feat = json.loads(feats or "{}")
        types = feat.get("investigation_types") or []
        rows.append({
            "id": cid,
            "topics": json.loads(topics or "[]"),
            "types": types if isinstance(types, list) else [types],
            "text": pe.repair_line_wraps(raw_obj.get("case_text") or ""),
            "raw_text": raw_obj.get("case_text") or "",
            "year": fixes[cid]["corrected"] if cid in fixes else _year(raw_obj),
            "platforms": correct_platform_labels(json.loads(plats or "[]"), raw_obj.get("case_text") or ""),
            "spans": feat.get("person_spans") or None,
        })
    conn.close()

    classified = []
    formless = []
    live_new = live_old = h5_removed = 0
    for row in rows:
        got = classify_release(row["text"], row["topics"], row["types"], ages.get(row["id"]), codebook)
        if H1 in got["final"] and got["form"] is None:
            formless.append(row["id"])
        if pl._live_hit(row["text"], codebook.harms[H1]):
            live_new += 1
        if _OLD_LIVE.search(row["text"]):
            live_old += 1
        if _h5_removed(row["text"], set(row["topics"]), codebook.harms[H5]):
            h5_removed += 1
        classified.append(got)
    if formless:
        raise SystemExit(f"h1 with no form: {len(formless)} {formless[:8]}")

    ai_ids, attempted_ids, sting_ids, kept_sting_ids, other_sting_ids = [], [], [], [], []
    base, uncovered = [], []
    form_counts = {"in_person": 0, "online": 0, "both": 0, "none": 0}
    cases = []
    for row, got in zip(rows, classified):
        cid = row["id"]
        final = got["final"]
        if got["ai"]:
            ai_ids.append(cid)
        if got["attempted"]:
            attempted_ids.append(cid)
        if got["sting_empty"]:
            sting_ids.append(cid)
        elif got["sting_h2_h3"]:
            kept_sting_ids.append(cid)
        elif got["strict"]:
            other_sting_ids.append(cid)
        out = pl.outside_uncovered_base(
            final, ai_no_identifiable_child=got["ai"], attempted_contact=got["attempted"],
            strict_sting=got["strict"])
        if not out:
            base.append(cid)
            if not final:
                uncovered.append(cid)
        form_counts[got["form"] or "none"] += 1
        cases.append({"id": cid, "harms": sorted(final), "h1_form": got["form"]})

    strict_counts = _empty_counts(harms)
    broad_counts = _empty_counts(harms)
    stated_cases, stated_with_affordance = set(), set()
    stated_mentions = stated_affordance_mentions = 0
    coded = {g: set() for g in GENERATIONS}
    class_cases = {c: {g: set() for g in GENERATIONS} for c in list(codebook.classes)}
    era_coded = {g: set() for g in PUBLICATION_ERAS}
    era_cases = {c: {g: set() for g in PUBLICATION_ERAS} for c in list(codebook.classes)}
    era_platforms = {c: {g: defaultdict(set) for g in PUBLICATION_ERAS} for c in list(codebook.classes)}
    era_after_2026 = set()
    for row, got in zip(rows, classified):
        labels = [p for p in row["platforms"] if pl.platform_info(p, registry).status != "excluded"]
        if not labels:
            continue
        published = pe.process_case(row["id"], labels, row["raw_text"])
        tiers = pe.linewrap_tiers(row["id"], labels, row["raw_text"], published["records"])
        offense = pe.offense_lines(row["text"])[0]
        final = got["final"]
        for rec in published["records"]:
            platform = rec["platform"]
            if tiers.get(platform) != "stated":
                continue
            stated_mentions += 1
            stated_cases.add(row["id"])
            info = pl.platform_info(platform, registry)
            gen = _launch_years.generation(launch[platform]) if platform in launch else None
            if gen is not None:
                ons = [c for c in TEST_CLASSES if _on_at(info, class_key[c], row["year"])]
                if ons:
                    coded[gen].add(row["id"])
                for c in ons:
                    class_cases[c][gen].add(row["id"])
                if _on_at(info, class_key["GenerativeSynthesis"], row["year"]):
                    class_cases["GenerativeSynthesis"][gen].add(row["id"])
            era = _publication_era(row["year"])
            if row["year"] is not None and row["year"] > 2026 and any(
                    _on_at(info, class_key[c], row["year"]) for c in TEST_CLASSES):
                era_after_2026.add(row["id"])
            if era is not None:
                era_ons = [c for c in TEST_CLASSES if _on_at(info, class_key[c], row["year"])]
                if era_ons:
                    era_coded[era].add(row["id"])
                for c in era_ons:
                    era_cases[c][era].add(row["id"])
                    era_platforms[c][era][platform].add(row["id"])
                if _on_at(info, class_key["GenerativeSynthesis"], row["year"]):
                    era_cases["GenerativeSynthesis"][era].add(row["id"])
                    era_platforms["GenerativeSynthesis"][era][platform].add(row["id"])
            affordances = _default_on(info, codebook, row["year"])
            if not affordances:
                continue
            stated_affordance_mentions += 1
            stated_with_affordance.add(row["id"])
            sentences = pe.sentences_with_platform(offense, platform)
            directs = {h for h in final if pl.harm_direct_hit(sentences, codebook.harms[h])}
            for cname in affordances:
                for h in final:
                    broad_counts[cname][h].add(row["id"])
                for h in directs:
                    strict_counts[cname][h].add(row["id"])

    excluded = set(ai_ids) | set(attempted_ids) | set(sting_ids)
    overlap = {
        "ai_no_identifiable_child & attempted_contact": sorted(set(ai_ids) & set(attempted_ids)),
        "ai_no_identifiable_child & sting_no_minor": sorted(set(ai_ids) & set(sting_ids)),
        "attempted_contact & sting_no_minor": sorted(set(attempted_ids) & set(sting_ids)),
        "all_three": sorted(set(ai_ids) & set(attempted_ids) & set(sting_ids)),
    }
    header = {
        "built": True,
        "paper_numbers": _paper_numbers(),
        "snapshot": _snapshot_label(),
        "source_db": db_path.name,
        "codebook": codebook.version,
        "codebook_sha256": pl.config_sha("codebook.yaml"),
        "registry": pl.load_yaml("platforms.yaml")["version"],
        "case_count": len(rows),
        "text": "line-repaired release text",
        "uncovered_share": {
            "numerator": len(uncovered),
            "denominator": len(base),
            "share": round(len(uncovered) / len(base), 4) if base else None,
            "rule": ("Empty harm set among cases in none of ai_no_identifiable_child, "
                     "attempted_contact, and sting_no_minor, over that same set."),
        },
        "h1_form_counts": form_counts,
        "live_conduct_cases": live_new,
        "live_conduct_cases_previous_gap": live_old,
        "h5_marks_removed": h5_removed,
        "stings_keeping_h2_or_h3": {
            "count": len(kept_sting_ids),
            "rule": "Strict sting whose harm set still contains h2 or h3. Stays in the uncovered-share base.",
            "case_ids": kept_sting_ids,
        },
        "stings_with_another_harm": {
            "count": len(other_sting_ids),
            "rule": "Strict sting whose remaining harm is neither h2 nor h3. Stays in the base.",
            "case_ids": other_sting_ids,
        },
    }
    groups = {
        "ai_no_identifiable_child": {
            "rule": "Topic ai_csam, no h2 likeness mark, and no h1 or h2. Offense topics stay. No harm code. Out of the uncovered share.",
            "count": len(ai_ids),
            "case_ids": ai_ids,
        },
        "attempted_contact": {
            "rule": ("Matched only by the removed meet / travel-to-meet / arrange-to-meet cues, "
                     "and the harm set is empty. Out of the uncovered share."),
            "count": len(attempted_ids),
            "case_ids": attempted_ids,
        },
        "sting_no_minor": {
            "rule": ("Undercover, at least one settled age role, and every settled role is decoy or claimed, "
                     "with an empty harm set after h1 and h4 are cleared. Out of the uncovered share."),
            "count": len(sting_ids),
            "case_ids": sting_ids,
        },
    }
    doc = {
        **header,
        **groups,
        "excluded_groups": {
            "sizes": {
                "ai_no_identifiable_child": len(ai_ids),
                "attempted_contact": len(attempted_ids),
                "sting_no_minor": len(sting_ids),
            },
            "overlap": {name: {"count": len(ids), "case_ids": ids} for name, ids in overlap.items()},
            "union": len(excluded),
        },
        "cases": cases,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "case_harms.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    common = {
        "built": True,
        "paper_numbers": _paper_numbers(),
        "snapshot": _snapshot_label(),
        "codebook": codebook.version,
        "registry": pl.load_yaml("platforms.yaml")["version"],
        "stated_tier": "primary tier after line-wrap repair; inferred and named_only mentions are omitted",
        "affordance": ("registry default_on and its window (since..ended) open in the publication year" if CLOSE_AT_END
                       else "registry default_on and already available in the publication year (rows not closed at ended)"),
        "platforms": "status is not excluded",
        "stated_mentions": stated_mentions,
        "stated_cases": len(stated_cases),
        "stated_mentions_with_default_on": stated_affordance_mentions,
        "stated_cases_with_default_on": len(stated_with_affordance),
        "rows": list(pl.CLASSES),
        "columns": harms,
    }
    strict_doc = {
        **common,
        "table": "strict",
        "link": "the harm cue is in a sentence naming that platform, and the harm is in the case set",
        "counts": _table(strict_counts, harms),
    }
    broad_doc = {
        **common,
        "table": "broad",
        "link": "the case-level harm set, including a cue or topic elsewhere in the release",
        "counts": _table(broad_counts, harms),
    }
    (OUT / "affordance_harm_strict.json").write_text(
        json.dumps(strict_doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "affordance_harm_broad.json").write_text(
        json.dumps(broad_doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    qualifying = [g for g in GENERATIONS if len(coded[g]) >= N_MIN]
    era_qualifying = [g for g in PUBLICATION_ERAS if len(era_coded[g]) >= N_MIN]
    recurrence = {
        "built": True,
        "paper_numbers": _paper_numbers(),
        "snapshot": _snapshot_label(),
        "registry": pl.load_yaml("platforms.yaml")["version"],
        "recurrence by launch cohort": {
            "table": "recurrence by launch cohort",
            "rule": {
                "n_min": N_MIN,
                "k": K_PRESENT,
                "generation": "platform launch year",
                "bins": list(GENERATIONS),
                "qualifies": "at least n_min distinct stated-tier cases, pooled across the five tested classes, on a platform in that launch generation where one of those classes is default_on at the publication date",
                "present": "a qualifying generation in which at least k distinct cases carry a stated-tier record of a platform where the class is default_on at the publication date",
                "recurs": "present in at least two qualifying generations and in every qualifying generation after the first",
                "window": "since through ended, inclusive; an open ended year does not close",
            },
            "generations": {
                g: {"coded_cases": len(coded[g]), "qualifies": g in qualifying} for g in GENERATIONS
            },
            "classes": {
                c: {
                    "recurs": _recurs(class_cases, coded, c),
                    "generations": {
                        g: {
                            "stated_tier_default_on_cases": len(class_cases[c][g]),
                            "present": g in qualifying and len(class_cases[c][g]) >= K_PRESENT,
                        } for g in GENERATIONS
                    },
                } for c in TEST_CLASSES
            },
            "generative_synthesis": {
                "in_test": False,
                "generations": {g: len(class_cases["GenerativeSynthesis"][g]) for g in GENERATIONS},
            },
        },
        "persistence by publication era": {
            "table": "persistence by publication era",
            "bins": list(PUBLICATION_ERAS),
            "cases_after_2026": len(era_after_2026),
            "rule": {
                "n_min": N_MIN,
                "k": K_PRESENT,
                "era": "case publication year",
                "qualifies": "at least n_min distinct stated-tier cases in that publication era, pooled across the five tested classes, where one of those classes is default_on at the publication date",
                "present": "a qualifying era in which at least k distinct cases carry a stated-tier record of a platform where the class is default_on at the publication date",
                "persists": "present in at least two qualifying eras and in every qualifying era after the first",
                "window": "since through ended, inclusive; an open ended year does not close",
            },
            "eras": {
                g: {"coded_cases": len(era_coded[g]), "qualifies": g in era_qualifying} for g in PUBLICATION_ERAS
            },
            "classes": {
                c: {
                    "persists": _recurs(era_cases, era_coded, c, PUBLICATION_ERAS),
                    "eras": {
                        g: _era_cell(era_cases[c][g], era_platforms[c][g], g in era_qualifying)
                        for g in PUBLICATION_ERAS
                    },
                } for c in TEST_CLASSES
            },
            "generative_synthesis": {
                "in_test": False,
                "eras": {
                    g: {k: v for k, v in _era_cell(
                        era_cases["GenerativeSynthesis"][g], era_platforms["GenerativeSynthesis"][g], False
                    ).items() if k != "present"}
                    for g in PUBLICATION_ERAS
                },
            },
        },
    }
    (OUT / "recurrence_by_generation.json").write_text(
        json.dumps(recurrence, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    rng = random.Random(SAMPLE_SEED)
    picked = rng.sample(base, SAMPLE_N)
    by_id = {row["id"]: (row, got) for row, got in zip(rows, classified)}
    sample = []
    for cid in picked:
        row, got = by_id[cid]
        sample.append({
            "id": cid,
            "harms": sorted(got["final"]),
            "h1_form": got["form"],
            "excerpt": _mask_excerpt(row["raw_text"], row["spans"]),
        })
    summary = {
        "cases": len(rows),
        "live_conduct_cases": live_new,
        "live_conduct_cases_previous_gap": live_old,
        "h5_marks_removed": h5_removed,
        "uncovered": f"{len(uncovered)}/{len(base)}",
        "ai_no_identifiable_child": len(ai_ids),
        "attempted_contact": len(attempted_ids),
        "sting_no_minor": len(sting_ids),
        "stings_keeping_h2_or_h3": len(kept_sting_ids),
        "stings_with_another_harm": len(other_sting_ids),
        "h1_form_counts": form_counts,
        "excluded_overlap": {name: len(ids) for name, ids in overlap.items()},
        "excluded_union": len(excluded),
        "stated_cases_with_default_on": len(stated_with_affordance),
        "recurrence": recurrence,
        "sample": sample,
    }
    log(json.dumps({k: v for k, v in summary.items() if k != "sample"}, indent=1))
    return summary


def main() -> None:
    db = Path(REPO / "caselinker.db")
    if not db.is_file():
        raise SystemExit(f"missing {db}")
    build(db)


if __name__ == "__main__":
    main()
