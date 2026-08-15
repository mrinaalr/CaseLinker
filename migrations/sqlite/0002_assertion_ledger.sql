PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assertions (
    assertion_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_kind TEXT NOT NULL,
    value_text TEXT NOT NULL,
    state TEXT NOT NULL,
    polarity TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    method_family TEXT NOT NULL,
    method_name TEXT NOT NULL,
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    code_revision TEXT NOT NULL,
    confidence_dimension TEXT,
    confidence_score_millionths INTEGER,
    confidence_calibration_id TEXT,
    supersedes_assertion_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (supersedes_assertion_id) REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
    CHECK (assertion_id GLOB 'asrt_[a-z0-9]*'),
    CHECK (value_kind IN ('entity', 'text', 'integer', 'boolean', 'date', 'iri')),
    CHECK (
        state IN (
            'observed', 'extracted', 'resolved', 'derived',
            'inferred', 'authored', 'contested', 'retracted'
        )
    ),
    CHECK (polarity IN ('affirmed', 'negated', 'uncertain')),
    CHECK (valid_from IS NULL OR valid_from GLOB '????-??-??'),
    CHECK (valid_to IS NULL OR valid_to GLOB '????-??-??'),
    CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from),
    CHECK (
        method_family IN (
            'deterministic_pattern', 'nlp_model', 'manual_observation',
            'resolution_rule', 'computation', 'statistical_model',
            'researcher_authorship'
        )
    ),
    CHECK (
        (confidence_dimension IS NULL AND confidence_score_millionths IS NULL
            AND confidence_calibration_id IS NULL)
        OR
        (confidence_dimension IN ('extraction', 'resolution', 'inference')
            AND (
                (confidence_score_millionths IS NULL AND confidence_calibration_id IS NULL)
                OR
                (confidence_score_millionths BETWEEN 0 AND 1000000
                    AND confidence_calibration_id IS NOT NULL)
            ))
    ),
    CHECK (created_at GLOB '*Z')
);

CREATE INDEX IF NOT EXISTS idx_assertions_subject_predicate
ON assertions (subject_id, predicate, assertion_id);

CREATE INDEX IF NOT EXISTS idx_assertions_state_created
ON assertions (state, created_at, assertion_id);

CREATE TABLE IF NOT EXISTS assertion_evidence (
    assertion_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    document_version_id TEXT NOT NULL,
    basis_sha256 TEXT,
    page_number INTEGER,
    start_char INTEGER,
    end_char INTEGER,
    span_sha256 TEXT,
    unavailable_reason TEXT,
    PRIMARY KEY (assertion_id, ordinal),
    FOREIGN KEY (assertion_id) REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
    FOREIGN KEY (document_version_id)
        REFERENCES source_document_versions(version_id) ON DELETE RESTRICT,
    CHECK (ordinal >= 0),
    CHECK (page_number IS NULL OR page_number >= 1),
    CHECK (basis_sha256 IS NULL OR (
        length(basis_sha256) = 64 AND basis_sha256 NOT GLOB '*[^0-9a-f]*'
    )),
    CHECK (span_sha256 IS NULL OR (
        length(span_sha256) = 64 AND span_sha256 NOT GLOB '*[^0-9a-f]*'
    )),
    CHECK (
        (
            start_char IS NOT NULL AND end_char IS NOT NULL AND span_sha256 IS NOT NULL
            AND basis_sha256 IS NOT NULL AND start_char >= 0 AND end_char > start_char
            AND unavailable_reason IS NULL
        )
        OR
        (
            start_char IS NULL AND end_char IS NULL AND span_sha256 IS NULL
            AND unavailable_reason IN (
                'non_textual_source', 'parser_did_not_preserve_offsets',
                'legacy_unanchored', 'source_version_unavailable'
            )
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_assertion_evidence_document_version
ON assertion_evidence (document_version_id, assertion_id);

CREATE TABLE IF NOT EXISTS assertion_inputs (
    assertion_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    input_assertion_id TEXT NOT NULL,
    PRIMARY KEY (assertion_id, ordinal),
    UNIQUE (assertion_id, input_assertion_id),
    FOREIGN KEY (assertion_id) REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
    FOREIGN KEY (input_assertion_id) REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
    CHECK (ordinal >= 0),
    CHECK (assertion_id <> input_assertion_id)
);

CREATE INDEX IF NOT EXISTS idx_assertion_inputs_input
ON assertion_inputs (input_assertion_id, assertion_id);

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id TEXT PRIMARY KEY,
    assertion_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    rationale TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    supersedes_decision_id TEXT,
    FOREIGN KEY (assertion_id) REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
    FOREIGN KEY (supersedes_decision_id)
        REFERENCES review_decisions(decision_id) ON DELETE RESTRICT,
    CHECK (decision_id GLOB 'rvw_[a-z0-9]*'),
    CHECK (outcome IN ('accepted', 'rejected', 'needs_changes')),
    CHECK (reviewer_role IN ('domain_reviewer', 'corpus_curator', 'policy_reviewer')),
    CHECK (decided_at GLOB '*Z'),
    CHECK (supersedes_decision_id IS NULL OR supersedes_decision_id <> decision_id)
);

CREATE INDEX IF NOT EXISTS idx_review_decisions_assertion_time
ON review_decisions (assertion_id, decided_at, decision_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_decisions_one_root
ON review_decisions (assertion_id)
WHERE supersedes_decision_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_decisions_one_successor
ON review_decisions (supersedes_decision_id)
WHERE supersedes_decision_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS review_decisions_validate_chain
BEFORE INSERT ON review_decisions
WHEN NEW.supersedes_decision_id IS NOT NULL
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM review_decisions previous
        WHERE previous.decision_id = NEW.supersedes_decision_id
          AND previous.assertion_id = NEW.assertion_id
    ) THEN RAISE(ABORT, 'review supersession must remain within one assertion') END;

    SELECT CASE WHEN EXISTS (
        SELECT 1
        FROM review_decisions previous
        WHERE previous.decision_id = NEW.supersedes_decision_id
          AND previous.decided_at >= NEW.decided_at
    ) THEN RAISE(ABORT, 'review decision time must advance monotonically') END;
END;

CREATE TRIGGER IF NOT EXISTS assertions_immutable_update
BEFORE UPDATE ON assertions
BEGIN
    SELECT RAISE(ABORT, 'assertions rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS assertions_immutable_delete
BEFORE DELETE ON assertions
BEGIN
    SELECT RAISE(ABORT, 'assertions rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS assertion_evidence_immutable_update
BEFORE UPDATE ON assertion_evidence
BEGIN
    SELECT RAISE(ABORT, 'assertion_evidence rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS assertion_evidence_immutable_delete
BEFORE DELETE ON assertion_evidence
BEGIN
    SELECT RAISE(ABORT, 'assertion_evidence rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS assertion_inputs_immutable_update
BEFORE UPDATE ON assertion_inputs
BEGIN
    SELECT RAISE(ABORT, 'assertion_inputs rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS assertion_inputs_immutable_delete
BEFORE DELETE ON assertion_inputs
BEGIN
    SELECT RAISE(ABORT, 'assertion_inputs rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_decisions_immutable_update
BEFORE UPDATE ON review_decisions
BEGIN
    SELECT RAISE(ABORT, 'review_decisions rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS review_decisions_immutable_delete
BEFORE DELETE ON review_decisions
BEGIN
    SELECT RAISE(ABORT, 'review_decisions rows are immutable');
END;
