"""Evidence-bound extraction of explicitly attributed reported legal events."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
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

REPORTED_SUBJECT_PREDICATE: Final = "caselinker:reportedSubjectOf"
REPORTED_EVENT_TYPE_PREDICATE: Final = "caselinker:reportedLegalEventType"
REPORTED_EVENT_DATE_PREDICATE: Final = "caselinker:reportedEventDate"

_RULE_VERSION: Final = "1.0.0"
_LEXICAL_WORD_RE: Final = re.compile(r"[^\W_]+", re.UNICODE)
_MONTHS: Final = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
_DATE_TEXT: Final = (
    rf"(?:{_MONTHS})[ \t]+[0-9]{{1,2}},[ \t]+[0-9]{{4}}|[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}"
)
_PREFIX_DATE_RE: Final = re.compile(
    rf"\bOn[ \t]+(?P<date>{_DATE_TEXT})[ \t]*,[ \t]*$",
    re.IGNORECASE,
)
_SUFFIX_DATE_RE: Final = re.compile(
    rf"^[ \t]+on[ \t]+(?P<date>{_DATE_TEXT})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AttributedSubject:
    """Opaque party identity plus explicit public-text aliases for attribution."""

    subject_id: str
    aliases: tuple[str, ...]

    def __post_init__(self) -> None:
        if OPAQUE_ID_PATTERN.fullmatch(self.subject_id) is None:
            raise ValueError("subject_id must be an opaque identifier")
        if not self.aliases or len(self.aliases) > 16:
            raise ValueError("aliases must contain between 1 and 16 explicit names")
        folded: set[str] = set()
        for alias in self.aliases:
            if (
                not alias
                or alias != alias.strip()
                or len(alias) > 128
                or any(ord(character) < 32 or ord(character) == 127 for character in alias)
            ):
                raise ValueError("aliases must be trimmed text of at most 128 characters")
            if len(_LEXICAL_WORD_RE.findall(alias)) < 2:
                raise ValueError("each alias must contain at least two lexical words")
            normalized = alias.casefold()
            if normalized in folded:
                raise ValueError("aliases must be unique under case folding")
            folded.add(normalized)


@dataclass(frozen=True, slots=True)
class _EventRule:
    rule_id: str
    event_type_id: str
    target_expression: str
    actor_expression: str | None


_RULES: Final = (
    _EventRule(
        "legal_event.arrest",
        "legal_event_arrest",
        r"(?:was|has[ \t]+been|had[ \t]+been)[ \t]+"
        r"(?:(?:also|later|previously|subsequently)[ \t]+)?arrested\b",
        r"(?:police|authorities|agents|deputies|detectives|officers|investigators)"
        r"[ \t]+(?:have[ \t]+|had[ \t]+)?arrested\b",
    ),
    _EventRule(
        "legal_event.charge",
        "legal_event_charge",
        r"(?:was|has[ \t]+been|had[ \t]+been)[ \t]+"
        r"(?:(?:also|later|previously|subsequently)[ \t]+)?charged\b",
        r"(?:prosecutors|authorities)[ \t]+(?:have[ \t]+|had[ \t]+)?charged\b",
    ),
    _EventRule(
        "legal_event.indictment",
        "legal_event_indictment",
        r"(?:was|has[ \t]+been|had[ \t]+been)[ \t]+"
        r"(?:(?:also|later|previously|subsequently)[ \t]+)?indicted\b",
        r"(?:a|the)[ \t]+grand[ \t]+jury[ \t]+(?:has[ \t]+|had[ \t]+)?indicted\b",
    ),
    _EventRule(
        "legal_event.guilty_plea",
        "legal_event_guilty_plea",
        r"(?:has[ \t]+|had[ \t]+)?(?:pleaded|pled)[ \t]+guilty\b",
        None,
    ),
    _EventRule(
        "legal_event.conviction",
        "legal_event_conviction",
        r"(?:was|has[ \t]+been|had[ \t]+been)[ \t]+"
        r"(?:(?:also|later|previously|subsequently)[ \t]+)?convicted\b",
        r"(?:a|the)[ \t]+jury[ \t]+(?:has[ \t]+|had[ \t]+)?convicted\b",
    ),
    _EventRule(
        "legal_event.sentencing",
        "legal_event_sentencing",
        r"(?:was|has[ \t]+been|had[ \t]+been)[ \t]+"
        r"(?:(?:also|later|previously|subsequently)[ \t]+)?sentenced\b",
        r"(?:a|the)[ \t]+court[ \t]+(?:has[ \t]+|had[ \t]+)?sentenced\b",
    ),
)


@dataclass(frozen=True, slots=True)
class _EventCandidate:
    start_char: int
    end_char: int
    rule: _EventRule
    rule_variant: str
    date_value: date | None
    date_start_char: int | None
    date_end_char: int | None


@dataclass(frozen=True, slots=True)
class _DateBinding:
    value: date | None
    start_char: int
    end_char: int


def _alias_expression(subject: AttributedSubject) -> str:
    alternatives = sorted(subject.aliases, key=lambda alias: (-len(alias), alias.casefold()))
    return r"(?<!\w)(?:" + "|".join(re.escape(alias) for alias in alternatives) + r")(?!\w)"


def _parse_date(value: str, *, not_after: date) -> date | None:
    try:
        parsed = (
            date.fromisoformat(value)
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
            else datetime.strptime(value, "%B %d, %Y").date()
        )
    except ValueError:
        return None
    if parsed.year < 1900 or parsed > not_after:
        return None
    return parsed


def _bound_date(
    normalized_text: str,
    *,
    event_start: int,
    event_end: int,
    not_after: date,
) -> _DateBinding | None:
    prefix_start = max(0, event_start - 64)
    prefix = normalized_text[prefix_start:event_start]
    prefix_match = _PREFIX_DATE_RE.search(prefix)
    if prefix_match is not None:
        raw = prefix_match.group("date")
        parsed = _parse_date(raw, not_after=not_after)
        start = prefix_start + prefix_match.start("date")
        return _DateBinding(parsed, start, start + len(raw))

    suffix = normalized_text[event_end : event_end + 64]
    suffix_match = _SUFFIX_DATE_RE.search(suffix)
    if suffix_match is not None:
        raw = suffix_match.group("date")
        parsed = _parse_date(raw, not_after=not_after)
        start = event_end + suffix_match.start("date")
        return _DateBinding(parsed, start, start + len(raw))
    return None


def _event_candidates(
    normalized_text: str,
    *,
    subject: AttributedSubject,
    not_after: date,
) -> tuple[_EventCandidate, ...]:
    alias = _alias_expression(subject)
    candidates: list[_EventCandidate] = []
    for rule in _RULES:
        expressions = [
            (
                "target",
                rf"{alias}(?:,[ \t]+[0-9]{{1,3}},?)?[ \t]+{rule.target_expression}",
            )
        ]
        if rule.actor_expression is not None:
            expressions.append(("actor", rf"(?<!\w){rule.actor_expression}[ \t]+{alias}"))
        for variant, expression in expressions:
            for match in re.finditer(expression, normalized_text, re.IGNORECASE):
                bound = _bound_date(
                    normalized_text,
                    event_start=match.start(),
                    event_end=match.end(),
                    not_after=not_after,
                )
                if bound is not None and bound.value is None:
                    continue
                candidates.append(
                    _EventCandidate(
                        start_char=match.start(),
                        end_char=match.end(),
                        rule=rule,
                        rule_variant=variant,
                        date_value=bound.value if bound else None,
                        date_start_char=bound.start_char if bound else None,
                        date_end_char=bound.end_char if bound else None,
                    )
                )

    candidates.sort(
        key=lambda candidate: (
            candidate.start_char,
            candidate.end_char,
            candidate.rule.rule_id,
            candidate.rule_variant,
        )
    )
    deduplicated: list[_EventCandidate] = []
    seen: set[tuple[int, int, str]] = set()
    for candidate in candidates:
        identity = (candidate.start_char, candidate.end_char, candidate.rule.event_type_id)
        if identity not in seen:
            seen.add(identity)
            deduplicated.append(candidate)
    return tuple(deduplicated)


def _digest_id(prefix: str, identity: dict[str, object]) -> str:
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_id(
    *,
    subject_id: str,
    document_version_id: str,
    candidate: _EventCandidate,
) -> str:
    return _digest_id(
        "event_",
        {
            "document_version_id": document_version_id,
            "end_char": candidate.end_char,
            "event_type": candidate.rule.event_type_id,
            "rule_id": candidate.rule.rule_id,
            "rule_variant": candidate.rule_variant,
            "rule_version": _RULE_VERSION,
            "start_char": candidate.start_char,
            "subject_id": subject_id,
        },
    )


def _assertion(
    *,
    assertion_role: str,
    subject_id: str,
    predicate: str,
    value: AssertionValue,
    evidence: tuple[EvidenceReference, ...],
    event_id: str,
    candidate: _EventCandidate,
    run: ExtractionRun,
) -> Assertion:
    assertion_id = _digest_id(
        "asrt_",
        {
            "assertion_role": assertion_role,
            "event_id": event_id,
            "predicate": predicate,
            "rule_id": candidate.rule.rule_id,
            "rule_version": _RULE_VERSION,
            "run_id": run.run_id,
            "subject_id": subject_id,
            "value_kind": value.kind.value,
            "value": value.value,
        },
    )
    return Assertion(
        assertion_id=assertion_id,
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        state=AssertionState.EXTRACTED,
        polarity=Polarity.AFFIRMED,
        valid_from=None,
        valid_to=None,
        method=AssertionMethod(
            family=MethodFamily.DETERMINISTIC_PATTERN,
            name=f"{candidate.rule.rule_id}.{candidate.rule_variant}",
            version=_RULE_VERSION,
            run_id=run.run_id,
            code_revision=run.code_revision,
        ),
        confidence=Confidence(ConfidenceDimension.EXTRACTION, None, None),
        evidence=evidence,
        input_assertion_ids=(),
        supersedes_assertion_id=None,
        created_at=run.created_at,
    )


class LegalEventExtractor:
    """Emit unreviewed candidates only for events explicitly tied to a known party."""

    def extract(
        self,
        *,
        subject: AttributedSubject,
        document_version: SourceDocumentVersion,
        normalized_text: str,
        run: ExtractionRun,
    ) -> tuple[Assertion, ...]:
        text_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        if document_version.normalized_text_sha256 is None:
            raise ValueError("document version does not identify normalized text")
        if document_version.normalized_text_sha256 != text_sha256:
            raise ValueError("normalized text does not match the document version")

        assertions: list[Assertion] = []
        for candidate in _event_candidates(
            normalized_text,
            subject=subject,
            not_after=run.created_at.date(),
        ):
            event_id = _event_id(
                subject_id=subject.subject_id,
                document_version_id=document_version.version_id,
                candidate=candidate,
            )
            event_evidence = EvidenceReference.from_text(
                document_version_id=document_version.version_id,
                normalized_text=normalized_text,
                start_char=candidate.start_char,
                end_char=candidate.end_char,
            )
            assertions.append(
                _assertion(
                    assertion_role="reported_subject",
                    subject_id=subject.subject_id,
                    predicate=REPORTED_SUBJECT_PREDICATE,
                    value=AssertionValue(ValueKind.ENTITY, event_id),
                    evidence=(event_evidence,),
                    event_id=event_id,
                    candidate=candidate,
                    run=run,
                )
            )
            assertions.append(
                _assertion(
                    assertion_role="event_type",
                    subject_id=event_id,
                    predicate=REPORTED_EVENT_TYPE_PREDICATE,
                    value=AssertionValue(ValueKind.ENTITY, candidate.rule.event_type_id),
                    evidence=(event_evidence,),
                    event_id=event_id,
                    candidate=candidate,
                    run=run,
                )
            )
            if candidate.date_value is not None:
                assert candidate.date_start_char is not None
                assert candidate.date_end_char is not None
                date_evidence = EvidenceReference.from_text(
                    document_version_id=document_version.version_id,
                    normalized_text=normalized_text,
                    start_char=candidate.date_start_char,
                    end_char=candidate.date_end_char,
                )
                assertions.append(
                    _assertion(
                        assertion_role="event_date",
                        subject_id=event_id,
                        predicate=REPORTED_EVENT_DATE_PREDICATE,
                        value=AssertionValue(ValueKind.DATE, candidate.date_value.isoformat()),
                        evidence=(event_evidence, date_evidence),
                        event_id=event_id,
                        candidate=candidate,
                        run=run,
                    )
                )
        return tuple(assertions)
