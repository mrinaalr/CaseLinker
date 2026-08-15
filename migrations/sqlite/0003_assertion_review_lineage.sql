PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assertion_review_inputs (
    assertion_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    decision_id TEXT NOT NULL,
    PRIMARY KEY (assertion_id, ordinal),
    UNIQUE (assertion_id, decision_id),
    FOREIGN KEY (assertion_id) REFERENCES assertions(assertion_id) ON DELETE RESTRICT,
    FOREIGN KEY (decision_id) REFERENCES review_decisions(decision_id) ON DELETE RESTRICT,
    CHECK (ordinal >= 0)
);

CREATE INDEX IF NOT EXISTS idx_assertion_review_inputs_decision
ON assertion_review_inputs (decision_id, assertion_id);

CREATE TRIGGER IF NOT EXISTS assertion_review_inputs_validate_target
BEFORE INSERT ON assertion_review_inputs
BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM review_decisions review
        JOIN assertion_inputs input
          ON input.assertion_id = NEW.assertion_id
         AND input.input_assertion_id = review.assertion_id
        WHERE review.decision_id = NEW.decision_id
    ) THEN RAISE(ABORT, 'review decision must govern an input assertion') END;
END;

CREATE TRIGGER IF NOT EXISTS assertion_review_inputs_immutable_update
BEFORE UPDATE ON assertion_review_inputs
BEGIN
    SELECT RAISE(ABORT, 'assertion_review_inputs rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS assertion_review_inputs_immutable_delete
BEFORE DELETE ON assertion_review_inputs
BEGIN
    SELECT RAISE(ABORT, 'assertion_review_inputs rows are immutable');
END;
