"""Precision-first extraction of explicit platform mentions.

This module intentionally does not claim that a platform was used, caused harm,
or was material to an investigation. It emits review candidates for the narrower
claim that a normalized public document explicitly names a platform.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Final

from caselinker.assertions.models import (
    OPAQUE_ID_PATTERN,
    Assertion,
    AssertionMethod,
    AssertionState,
    AssertionValue,
    Confidence,
    ConfidenceDimension,
    EvidenceReference,
    MethodFamily,
    Polarity,
    ValueKind,
)
from caselinker.documents.models import SourceDocumentVersion
from caselinker.extraction.models import ExtractionRun

PLATFORM_MENTION_PREDICATE: Final = "caselinker:platformMentioned"


@dataclass(frozen=True, slots=True)
class _PlatformRule:
    rule_id: str
    version: str
    entity_id: str
    pattern: re.Pattern[str]


def _rule(rule_id: str, entity_id: str, expression: str) -> _PlatformRule:
    return _PlatformRule(
        rule_id=rule_id,
        version="1.0.0",
        entity_id=entity_id,
        pattern=re.compile(expression, re.IGNORECASE),
    )


# Specific forms precede their containing brands. Generic terms such as "chat",
# "online", and bare "X" are excluded because they are not precise identifiers.
_RULES: Final = (
    _rule(
        "platform.facebook_messenger",
        "platform_facebook_messenger",
        r"\b(?:Facebook|FB)\s+Messenger\b",
    ),
    _rule("platform.youtube_live", "platform_youtube_live", r"\bYouTube\s+Live\b"),
    _rule("platform.facebook", "platform_facebook", r"\bFacebook\b"),
    _rule("platform.instagram", "platform_instagram", r"\bInstagram\b"),
    _rule("platform.snapchat", "platform_snapchat", r"\bSnapchat\b"),
    _rule("platform.tiktok", "platform_tiktok", r"\bTikTok\b"),
    _rule(
        "platform.twitter",
        "platform_twitter_x",
        r"\bTwitter\b|(?<![A-Za-z0-9_])(?:twitter\.com|x\.com)(?![A-Za-z0-9_])",
    ),
    _rule("platform.whatsapp", "platform_whatsapp", r"\bWhatsApp\b"),
    _rule("platform.telegram", "platform_telegram", r"\bTelegram\b"),
    _rule("platform.discord", "platform_discord", r"\bDiscord\b"),
    _rule("platform.youtube", "platform_youtube", r"\bYouTube\b"),
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    start_char: int
    end_char: int
    rule_index: int
    rule: _PlatformRule


def _non_overlapping_candidates(normalized_text: str) -> tuple[_Candidate, ...]:
    candidates = [
        _Candidate(match.start(), match.end(), rule_index, rule)
        for rule_index, rule in enumerate(_RULES)
        for match in rule.pattern.finditer(normalized_text)
    ]
    candidates.sort(
        key=lambda candidate: (
            candidate.start_char,
            -(candidate.end_char - candidate.start_char),
            candidate.rule_index,
        )
    )

    selected: list[_Candidate] = []
    for candidate in candidates:
        if selected and candidate.start_char < selected[-1].end_char:
            continue
        selected.append(candidate)
    selected.sort(key=lambda candidate: (candidate.start_char, candidate.end_char))
    return tuple(selected)


def _assertion_id(
    *,
    subject_id: str,
    document_version_id: str,
    candidate: _Candidate,
    run_id: str,
) -> str:
    identity = {
        "document_version_id": document_version_id,
        "end_char": candidate.end_char,
        "predicate": PLATFORM_MENTION_PREDICATE,
        "rule_id": candidate.rule.rule_id,
        "rule_version": candidate.rule.version,
        "run_id": run_id,
        "start_char": candidate.start_char,
        "subject_id": subject_id,
        "value": candidate.rule.entity_id,
    }
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "asrt_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PlatformMentionExtractor:
    """Emit exact-span, unreviewed candidates for allowlisted platform names."""

    def extract(
        self,
        *,
        subject_id: str,
        document_version: SourceDocumentVersion,
        normalized_text: str,
        run: ExtractionRun,
    ) -> tuple[Assertion, ...]:
        if OPAQUE_ID_PATTERN.fullmatch(subject_id) is None:
            raise ValueError("subject_id must be an opaque identifier")
        text_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        if document_version.normalized_text_sha256 is None:
            raise ValueError("document version does not identify normalized text")
        if document_version.normalized_text_sha256 != text_sha256:
            raise ValueError("normalized text does not match the document version")

        assertions = []
        for candidate in _non_overlapping_candidates(normalized_text):
            rule = candidate.rule
            assertions.append(
                Assertion(
                    assertion_id=_assertion_id(
                        subject_id=subject_id,
                        document_version_id=document_version.version_id,
                        candidate=candidate,
                        run_id=run.run_id,
                    ),
                    subject_id=subject_id,
                    predicate=PLATFORM_MENTION_PREDICATE,
                    value=AssertionValue(ValueKind.ENTITY, rule.entity_id),
                    state=AssertionState.EXTRACTED,
                    polarity=Polarity.AFFIRMED,
                    valid_from=None,
                    valid_to=None,
                    method=AssertionMethod(
                        family=MethodFamily.DETERMINISTIC_PATTERN,
                        name=rule.rule_id,
                        version=rule.version,
                        run_id=run.run_id,
                        code_revision=run.code_revision,
                    ),
                    confidence=Confidence(
                        dimension=ConfidenceDimension.EXTRACTION,
                        score_millionths=None,
                        calibration_id=None,
                    ),
                    evidence=(
                        EvidenceReference.from_text(
                            document_version_id=document_version.version_id,
                            normalized_text=normalized_text,
                            start_char=candidate.start_char,
                            end_char=candidate.end_char,
                        ),
                    ),
                    input_assertion_ids=(),
                    supersedes_assertion_id=None,
                    created_at=run.created_at,
                )
            )
        return tuple(assertions)
