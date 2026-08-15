PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_documents (
    document_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    canonicalization_version TEXT NOT NULL,
    document_type TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    CHECK (document_id GLOB 'doc_[a-z0-9]*'),
    CHECK (length(source_id) BETWEEN 2 AND 128),
    CHECK (length(canonical_url) BETWEEN 8 AND 2048),
    CHECK (length(canonicalization_version) BETWEEN 1 AND 128),
    CHECK (length(document_type) BETWEEN 2 AND 64),
    CHECK (recorded_at GLOB '*Z')
);

CREATE INDEX IF NOT EXISTS idx_source_documents_source_id
ON source_documents (source_id);

CREATE TABLE IF NOT EXISTS source_document_versions (
    version_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    byte_length INTEGER NOT NULL,
    storage_key TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    published_at TEXT,
    recorded_at TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    http_etag TEXT,
    http_last_modified TEXT,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    normalized_text_sha256 TEXT,
    FOREIGN KEY (document_id) REFERENCES source_documents(document_id) ON DELETE RESTRICT,
    CHECK (version_id GLOB 'docv_[a-z0-9]*'),
    CHECK (length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'),
    CHECK (byte_length >= 0),
    CHECK (storage_key = 'sha256/' || substr(content_sha256, 1, 2) || '/' || content_sha256),
    CHECK (retrieved_at GLOB '*Z'),
    CHECK (published_at IS NULL OR published_at GLOB '*Z'),
    CHECK (recorded_at GLOB '*Z'),
    CHECK (http_status = 200),
    CHECK (http_last_modified IS NULL OR http_last_modified GLOB '*Z'),
    CHECK (
        normalized_text_sha256 IS NULL
        OR (
            length(normalized_text_sha256) = 64
            AND normalized_text_sha256 NOT GLOB '*[^0-9a-f]*'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_source_document_versions_document_time
ON source_document_versions (document_id, retrieved_at, version_id);

CREATE INDEX IF NOT EXISTS idx_source_document_versions_content_sha256
ON source_document_versions (content_sha256);

CREATE TRIGGER IF NOT EXISTS source_documents_immutable_update
BEFORE UPDATE ON source_documents
BEGIN
    SELECT RAISE(ABORT, 'source_documents rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS source_documents_immutable_delete
BEFORE DELETE ON source_documents
BEGIN
    SELECT RAISE(ABORT, 'source_documents rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS source_document_versions_immutable_update
BEFORE UPDATE ON source_document_versions
BEGIN
    SELECT RAISE(ABORT, 'source_document_versions rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS source_document_versions_immutable_delete
BEFORE DELETE ON source_document_versions
BEGIN
    SELECT RAISE(ABORT, 'source_document_versions rows are immutable');
END;
