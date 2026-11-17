"""
Platform mention noise detection and filtering for the CAC pipeline.

`NoiseFilter` classifies press-release platform mentions as signal, noise,
or ambiguous from local context windows, then decides:

  - map-time: should this platform enter the knowledge graph?
  - corpus-time: should this whole case be excluded?

Currently used at corpus selection time.

CLI:
    python ontology/pipeline/noise_filter.py <case_id> [...]   # dry-run per case
    python ontology/pipeline/noise_filter.py --report          # corpus noise_analysis_report.md
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]


class NoiseFilter:
    """Signal/noise classifier + map/corpus filter rules."""

    GENERIC_SENTINELS = frozenset(
        {
            "online",
            "social media",
            "chat",
            "internet",
            "messaging app",
            "messaging apps",
            "video chat",
            "web",
        }
    )

    SIGNAL_PATTERNS = [
        r"\b(?:groomed|grooming)\b.*\b(?:on|via|through|using)\b",
        r"\b(?:exchanged|sent|shared|posted|uploaded|downloaded)\b.*\b(?:on|via|through|using)\b",
        r"\b(?:communicat(?:ed|ing)|messag(?:ed|ing)|chatted)\b.*\b(?:on|via|through|using)\b",
        r"\b(?:met|contacted|approached)\b.*\b(?:on|via|through|using)\b",
        r"\b(?:used|utilized|accessed)\b.*\b(?:account|profile|app)\b",
        r"\b(?:posed|pretending)\b.*\b(?:as|to be)\b",
        r"\b(?:traded|distributed|possessed|produced)\b.*\b(?:images?|videos?|csam|child porn)\b",
        r"\b(?:cybertip|ncmec tip)\b.*\b(?:from|about|regarding)\b",
        r"\b(?:undercover|sting)\b.*\b(?:on|via|through)\b",
        r"\b(?:kik|snapchat|instagram|discord|facebook|omegle|roblox)\b",
    ]

    NOISE_PATTERNS = [
        r"\b(?:parents?|guardians?)\s+should\b",
        r"\b(?:warning|warns|warned)\b.*\b(?:about|regarding)\b",
        r"\b(?:monitor|supervise)\b.*\b(?:children|kids|accounts?)\b",
        r"\b(?:awareness|educat(?:e|ion|ional))\b",
        r"\b(?:tips?|advice|guidance)\b.*\b(?:for|to)\b.*\b(?:parents?|families)\b",
        r"\b(?:press release|media contact|for more information)\b",
        r"\b(?:commonly used|popular among|often used by teens)\b",
        r"\b(?:be aware|stay safe|online safety)\b",
        r"\b(?:about icac|about ncmec)\b",
    ]

    PLATFORM_ALIASES: Dict[str, List[str]] = {
        "Twitter / X": ["twitter", "x.com", " twitter "],
        "social media": ["social media", "social-media", "social networking"],
        "chat": [" chat ", "chat room", "chatroom", "online chat"],
        "online": [" online ", "on-line", "on the internet", "internet"],
    }

    EDU_KEYWORDS = (
        "warning", "warnings", "warn", "warns", "warned",
        "educate", "education", "educational", "awareness",
        "tips", "advice", "guidance", "be aware",
        "parents should", "monitor your",
        "press release boilerplate", "for more information",
        "media contact", "press contact", "about icac", "about ncmec",
    )

    _LABEL_RANK = {"signal": 2, "ambiguous": 1, "noise": 0}

    def word_window(self, text: str, start: int, end: int, words: int = 60) -> str:
        if not text:
            return ""
        before, after = text[:start], text[end:]
        left = before.split()[-words // 2 :] if before else []
        right = after.split()[: words // 2] if after else []
        return (" ".join(left) + " " + text[start:end] + " " + " ".join(right)).strip()

    def aliases_for(self, platform_label: str) -> List[str]:
        key = platform_label.strip()
        low = key.lower()
        if key in self.PLATFORM_ALIASES:
            return self.PLATFORM_ALIASES[key]
        if low in self.GENERIC_SENTINELS:
            return [low]
        return [low, key]

    def classify_mention(self, window: str, platform_label: str) -> Tuple[str, bool, bool]:
        """Return (label, has_signal_pattern, has_noise_pattern)."""
        w = window.lower()
        sig = any(re.search(p, w, re.I) for p in self.SIGNAL_PATTERNS)
        noi = any(re.search(p, w, re.I) for p in self.NOISE_PATTERNS)
        if sig and not noi:
            return "signal", True, False
        if noi and not sig:
            return "noise", False, True
        if sig and noi:
            return "ambiguous", True, True
        if platform_label.strip().lower() in self.GENERIC_SENTINELS:
            return "ambiguous", False, False
        return "signal", False, False

    def is_platform_signal(self, case_text: str, platform_label: str) -> bool:
        """
        True if the platform mention should be kept in the knowledge graph.

        Specific platforms → keep unless classifier says 'noise'.
        Generic sentinels  → keep only if classifier says 'signal'.
        No case_text       → keep specific, drop generic.
        """
        is_generic = platform_label.strip().lower() in self.GENERIC_SENTINELS
        if not case_text:
            return not is_generic

        text_l = case_text.lower()
        seen_label: Optional[str] = None
        for alias in self.aliases_for(platform_label):
            start = 0
            alias_l = alias.lower()
            while True:
                idx = text_l.find(alias_l, start)
                if idx < 0:
                    break
                window = self.word_window(case_text, idx, idx + len(alias))
                label, _, _ = self.classify_mention(window, platform_label)
                if seen_label is None or self._LABEL_RANK[label] > self._LABEL_RANK[seen_label]:
                    seen_label = label
                start = idx + len(alias)

        if seen_label is None:
            return False
        if is_generic:
            return seen_label == "signal"
        return seen_label != "noise"

    def filter_platforms(
        self, case_text: str, platforms: Iterable[str]
    ) -> Tuple[List[str], List[str]]:
        kept, dropped = [], []
        for p in platforms:
            (kept if self.is_platform_signal(case_text, p) else dropped).append(p)
        return kept, dropped

    def edu_density(self, text: str) -> float:
        if not text:
            return 0.0
        n_words = max(1, len(text.split()))
        text_l = text.lower()
        hits = sum(text_l.count(kw) for kw in self.EDU_KEYWORDS)
        return hits * 200.0 / n_words

    def is_noisy_case(self, case: Dict[str, Any]) -> Tuple[bool, str]:
        """
        True iff the case is advisory/boilerplate-dominated and should be
        excluded from corpus selection (all four rules must hold).
        """
        case_text = self.case_text(case)
        platforms = self.parse_platforms(case)

        rule1 = True
        if platforms:
            for p in platforms:
                if self.is_platform_signal(case_text, p) and p.lower() not in self.GENERIC_SENTINELS:
                    rule1 = False
                    break

        vc = case.get("victim_count")
        try:
            rule2 = vc is None or int(vc) == 0
        except (TypeError, ValueError):
            rule2 = True

        ef = self.extracted_features(case)
        pros = ef.get("prosecution_outcome") or {} if isinstance(ef, dict) else {}
        rule3 = not (
            (isinstance(pros, dict) and pros.get("charges"))
            or (isinstance(pros, dict) and pros.get("booking_status"))
        )

        rule4 = self.edu_density(case_text) > 1.0
        is_noisy = rule1 and rule2 and rule3 and rule4
        density = self.edu_density(case_text)
        if is_noisy:
            reason = (
                f"all_platforms_noise_or_ambiguous=True, victim_count={vc}, "
                f"prosecution_empty=True, edu_density={density:.2f}/200w"
            )
        else:
            reason = f"r1={rule1} r2={rule2} r3={rule3} r4={rule4}; edu_density={density:.2f}"
        return is_noisy, reason

    @staticmethod
    def case_text(case: Dict[str, Any]) -> str:
        for blob_key in ("raw_data", "extracted_features"):
            blob = case.get(blob_key)
            if isinstance(blob, dict):
                for k in ("case_text", "raw_text", "text"):
                    v = blob.get(k)
                    if isinstance(v, str) and v.strip():
                        return v
            if isinstance(blob, str):
                try:
                    d = json.loads(blob)
                except json.JSONDecodeError:
                    continue
                if isinstance(d, dict):
                    for k in ("case_text", "raw_text", "text"):
                        v = d.get(k)
                        if isinstance(v, str) and v.strip():
                            return v
        return ""

    @staticmethod
    def extracted_features(case: Dict[str, Any]) -> Dict[str, Any]:
        ef = case.get("extracted_features")
        if isinstance(ef, dict):
            return ef
        if isinstance(ef, str):
            try:
                return json.loads(ef)
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def parse_platforms(case: Dict[str, Any]) -> List[str]:
        p = case.get("platforms_used") or []
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except json.JSONDecodeError:
                p = []
        return [str(x) for x in p] if isinstance(p, list) else []

    def run_corpus_report(self, db_path: Optional[Path] = None) -> Path:
        """Scan all cases; write ontology/noise_analysis_report.md."""
        db_path = db_path or REPO_ROOT / "caselinker.db"
        conn = sqlite3.connect(str(db_path))
        cols = [c[1] for c in conn.execute("PRAGMA table_info(cases)").fetchall()]
        label_counts: Counter[str] = Counter()
        per_platform: Dict[str, Counter[str]] = defaultdict(Counter)
        n_mentions = 0

        for row in conn.execute("SELECT * FROM cases"):
            case = dict(zip(cols, row))
            text = self.case_text(case)
            if not text:
                continue
            text_l = text.lower()
            for plat in self.parse_platforms(case):
                for alias in self.aliases_for(plat):
                    start = 0
                    while True:
                        idx = text_l.find(alias.lower(), start)
                        if idx < 0:
                            break
                        window = self.word_window(text, idx, idx + len(alias))
                        label, _, _ = self.classify_mention(window, plat)
                        label_counts[label] += 1
                        per_platform[plat.lower()][label] += 1
                        n_mentions += 1
                        start = idx + len(alias)

        report = REPO_ROOT / "ontology" / "noise_analysis_report.md"
        lines = [
            "# Noise analysis report",
            "",
            f"Total mention windows scanned: **{n_mentions}**",
            "",
            "## Overall",
            "",
        ]
        for lab in ("signal", "ambiguous", "noise"):
            c = label_counts[lab]
            pct = (100.0 * c / n_mentions) if n_mentions else 0
            lines.append(f"- **{lab}**: {c} ({pct:.1f}%)")
        lines.extend(["", "## Top platforms by signal rate", ""])
        for plat, ctr in sorted(
            per_platform.items(),
            key=lambda kv: -(kv[1]["signal"] / max(1, sum(kv[1].values()))),
        )[:25]:
            tot = sum(ctr.values())
            lines.append(
                f"- `{plat}`: signal={ctr['signal']} ambiguous={ctr['ambiguous']} "
                f"noise={ctr['noise']} (n={tot})"
            )
        report.write_text("\n".join(lines) + "\n")
        return report


# Default instance + module-level API (features_to_cac, select_100)
_default = NoiseFilter()

GENERIC_SENTINELS = NoiseFilter.GENERIC_SENTINELS


def is_platform_signal(case_text: str, platform_label: str) -> bool:
    return _default.is_platform_signal(case_text, platform_label)


def filter_platforms(case_text: str, platforms: Iterable[str]) -> Tuple[List[str], List[str]]:
    return _default.filter_platforms(case_text, platforms)


def is_noisy_case(case: Dict[str, Any]) -> Tuple[bool, str]:
    return _default.is_noisy_case(case)


def _load_case(cid: str) -> Optional[Dict[str, Any]]:
    db = REPO_ROOT / "caselinker.db"
    conn = sqlite3.connect(str(db))
    cols = [c[1] for c in conn.execute("PRAGMA table_info(cases)").fetchall()]
    row = conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone()
    if not row:
        return None
    return dict(zip(cols, row))


def _dry_run(case_id: str) -> int:
    case = _load_case(case_id)
    if case is None:
        print(f"case {case_id!r} not found")
        return 1
    nf = _default
    text = nf.case_text(case)
    platforms = nf.parse_platforms(case)
    print(
        f"case {case_id} · source={case.get('source')} · "
        f"victim_count={case.get('victim_count')}"
    )
    print(f"  platforms_used   : {platforms}")
    if platforms:
        kept, dropped = nf.filter_platforms(text, platforms)
        print(f"  kept by filter   : {kept}")
        print(f"  dropped by filter: {dropped}")
    noisy, reason = nf.is_noisy_case(case)
    print(f"  is_noisy_case    : {noisy}")
    print(f"  reason           : {reason}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in ("--report", "-r"):
        path = _default.run_corpus_report()
        print(f"Wrote {path.relative_to(REPO_ROOT)}")
        sys.exit(0)
    if len(sys.argv) < 2:
        print("usage: python ontology/pipeline/noise_filter.py <case_id> [...]")
        print("       python ontology/pipeline/noise_filter.py --report")
        sys.exit(2)
    rc = 0
    for cid in sys.argv[1:]:
        rc |= _dry_run(cid)
        print()
    sys.exit(rc)
