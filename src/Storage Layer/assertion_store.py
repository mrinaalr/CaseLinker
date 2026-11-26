"""
Field assertion storage for CaseLinker 3.0 (SQLite and Postgres).

- field_assertions: one row per method claim (method, version, family, role, span).
  Append-only: never updated or deleted (triggers enforce it where the host allows).
- field_resolutions: one row per (run, case, field, rule_set_version) resolution,
  with the winning assertion ids. Re-resolution appends; the latest row wins.
- review_queue: open items for needs_review / contested / partial resolutions.

Same placement as provenance.py: tables are created by CaseStorage.init_database().
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

REVIEW_STATUSES = ("needs_review", "disagreement", "partial")


def _ph(dialect: str) -> str:
    return "?" if dialect == "sqlite" else "%s"


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def apply_assertion_schema(cursor: Any, dialect: str = "sqlite") -> None:
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect == "sqlite" else "BIGSERIAL PRIMARY KEY"
    # SQLite stores CURRENT_TIMESTAMP into TEXT. Postgres will not: the default
    # is timestamptz, and CREATE TABLE fails without the cast.
    now = "CURRENT_TIMESTAMP" if dialect == "sqlite" else "(CURRENT_TIMESTAMP::text)"
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS field_assertions (
            id {pk},
            run_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            field TEXT NOT NULL,
            method TEXT NOT NULL,
            method_version TEXT,
            family TEXT NOT NULL,
            value_json TEXT NOT NULL,
            role TEXT,
            span_start INTEGER,
            span_end INTEGER,
            span_text TEXT,
            span_ok INTEGER NOT NULL,
            confidence REAL,
            extras_json TEXT,
            created_at TEXT NOT NULL DEFAULT {now}
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS field_resolutions (
            id {pk},
            run_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            field TEXT NOT NULL,
            rule_set_version TEXT NOT NULL,
            status TEXT NOT NULL,
            rule_id TEXT,
            final_json TEXT,
            winning_assertion_ids TEXT,
            disagreement_json TEXT,
            created_at TEXT NOT NULL DEFAULT {now}
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS review_queue (
            id {pk},
            run_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            field TEXT NOT NULL,
            rule_set_version TEXT NOT NULL,
            reason TEXT NOT NULL,
            detail_json TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT {now}
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_field_assertions_case ON field_assertions (case_id, field)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_field_resolutions_case ON field_resolutions (case_id, field)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_field_resolutions_status ON field_resolutions (field, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_queue_open ON review_queue (status, field)")
    if dialect == "sqlite":
        for op in ("UPDATE", "DELETE"):
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS field_assertions_append_only_{op.lower()}
                BEFORE {op} ON field_assertions
                BEGIN
                    SELECT RAISE(ABORT, 'field_assertions rows are append-only');
                END
                """
            )
    else:
        # caselinker_append_only() is created by apply_postgres_provenance_schema.
        cursor.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'field_assertions_append_only_update') THEN
                    CREATE TRIGGER field_assertions_append_only_update BEFORE UPDATE ON field_assertions
                    FOR EACH ROW EXECUTE PROCEDURE caselinker_append_only();
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'field_assertions_append_only_delete') THEN
                    CREATE TRIGGER field_assertions_append_only_delete BEFORE DELETE ON field_assertions
                    FOR EACH ROW EXECUTE PROCEDURE caselinker_append_only();
                END IF;
            END $$;
            """
        )


def _insert_returning_id(cursor: Any, sql: str, params: Sequence[Any], dialect: str) -> int:
    if dialect == "sqlite":
        cursor.execute(sql, params)
        return cursor.lastrowid
    cursor.execute(sql + " RETURNING id", params)
    row = cursor.fetchone()
    return row[0] if not isinstance(row, dict) else row["id"]


def write_case_assertions(
    cursor: Any,
    *,
    case_id: str,
    run_id: Optional[str],
    assertions: List[Dict[str, Any]],
    resolutions: Dict[str, Dict[str, Any]],
    dialect: str = "sqlite",
) -> Dict[int, int]:
    """
    Insert one case's assertions, resolutions, and review items. Winning ids
    computed before storage (negative ``seq`` placeholders) are mapped to row ids.
    Returns {seq: row id}.
    """
    ph = _ph(dialect)
    run_id = run_id or "unrecorded"
    seq_to_id: Dict[int, int] = {}
    for a in assertions:
        row_id = _insert_returning_id(
            cursor,
            f"""INSERT INTO field_assertions (run_id, case_id, field, method, method_version, family,
                value_json, role, span_start, span_end, span_text, span_ok, confidence, extras_json)
                VALUES ({", ".join([ph] * 14)})""",
            (
                run_id, case_id, a["field"], a["method"], a.get("method_version"), a.get("family") or a["method"],
                _dumps(a.get("value")), a.get("role"), a.get("span_start"), a.get("span_end"), a.get("span_text"),
                int(bool(a.get("span_ok"))), a.get("confidence"), _dumps(a.get("extras") or {}),
            ),
            dialect,
        )
        if a.get("seq") is not None:
            seq_to_id[a["seq"]] = row_id
    write_resolutions(cursor, case_id=case_id, run_id=run_id, resolutions=resolutions,
                      id_map=seq_to_id, dialect=dialect)
    return seq_to_id


def _review_mention_key(item: Dict[str, Any]) -> str:
    """An open mention. A later pass of the same span and value is the same queue row."""
    if isinstance(item, dict) and (item.get("span") is not None or "value" in item):
        return _dumps({"span": item.get("span"), "value": item.get("value")})
    return _dumps(item)


def _open_review_mentions(cursor: Any, case_id: str, field: str, dialect: str) -> set:
    ph = _ph(dialect)
    cursor.execute(
        f"SELECT detail_json FROM review_queue WHERE case_id = {ph} AND field = {ph} AND status = 'open'",
        (case_id, field),
    )
    keys = set()
    for row in cursor.fetchall():
        raw = row["detail_json"] if isinstance(row, dict) else row[0]
        try:
            item = json.loads(raw or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            keys.add(_review_mention_key(item))
    return keys


def _close_stale_review_mentions(
    cursor: Any,
    *,
    case_id: str,
    field: str,
    keep_keys: set,
    dialect: str,
) -> None:
    """Close open queue rows whose mention is no longer in this resolution's review list."""
    ph = _ph(dialect)
    cursor.execute(
        f"SELECT id, detail_json FROM review_queue WHERE case_id = {ph} AND field = {ph} AND status = 'open'",
        (case_id, field),
    )
    for row in cursor.fetchall():
        row_id = row["id"] if isinstance(row, dict) else row[0]
        raw = row["detail_json"] if isinstance(row, dict) else row[1]
        try:
            item = json.loads(raw or "{}")
        except json.JSONDecodeError:
            item = {}
        key = _review_mention_key(item) if isinstance(item, dict) else _dumps(item)
        if key in keep_keys:
            continue
        cursor.execute(
            f"UPDATE review_queue SET status = 'closed' WHERE id = {ph}",
            (row_id,),
        )


def write_resolutions(
    cursor: Any,
    *,
    case_id: str,
    run_id: str,
    resolutions: Dict[str, Dict[str, Any]],
    id_map: Optional[Dict[int, int]] = None,
    dialect: str = "sqlite",
) -> None:
    ph = _ph(dialect)
    for field, res in (resolutions or {}).items():
        winning = [(id_map or {}).get(i, i) for i in res.get("winning_assertion_ids") or []]
        cursor.execute(
            f"""INSERT INTO field_resolutions (run_id, case_id, field, rule_set_version, status, rule_id,
                final_json, winning_assertion_ids, disagreement_json) VALUES ({", ".join([ph] * 9)})""",
            (
                run_id, case_id, field, res["rule_set_version"], res["status"], res.get("rule_id"),
                _dumps(res.get("final_value")), _dumps(sorted(winning)), _dumps(res.get("disagreement") or {}),
            ),
        )
        review_items = res.get("review") or []
        keep_keys = {_review_mention_key(item) for item in review_items}
        open_mentions = _open_review_mentions(cursor, case_id, field, dialect)
        for item in review_items:
            key = _review_mention_key(item)
            if key in open_mentions:
                continue
            cursor.execute(
                f"""INSERT INTO review_queue (run_id, case_id, field, rule_set_version, reason, detail_json)
                    VALUES ({", ".join([ph] * 6)})""",
                (run_id, case_id, field, res["rule_set_version"], item.get("reason", "review"), _dumps(item)),
            )
            open_mentions.add(key)
        _close_stale_review_mentions(
            cursor, case_id=case_id, field=field, keep_keys=keep_keys, dialect=dialect,
        )


def _rows(cursor: Any) -> List[Dict[str, Any]]:
    cols = [d[0] for d in cursor.description]
    return [dict(r) if isinstance(r, dict) else dict(zip(cols, r)) for r in cursor.fetchall()]


def latest_run_id(cursor: Any, case_id: str, dialect: str = "sqlite") -> Optional[str]:
    """Current extraction run for a case.

    Non-human assertions win when they exist. A run that stored resolutions
    and no assertions (``rule_id`` ``no_assertions``) is still the current run.
    """
    ph = _ph(dialect)
    cursor.execute(
        f"SELECT run_id FROM field_assertions WHERE case_id = {ph} AND method <> 'human' ORDER BY id DESC LIMIT 1",
        (case_id,),
    )
    row = cursor.fetchone()
    if not row:
        cursor.execute(
            f"SELECT run_id FROM field_resolutions WHERE case_id = {ph} ORDER BY id DESC LIMIT 1",
            (case_id,),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return row[0] if not isinstance(row, dict) else row["run_id"]


def load_assertions(cursor: Any, case_id: str, *, run_id: Optional[str] = None,
                    field: Optional[str] = None, dialect: str = "sqlite") -> List[Dict[str, Any]]:
    """Assertions of the case's current extraction run, as resolution inputs.

    An earlier run on the same case id is ignored, including a human verdict
    stored against a previous article.
    """
    ph = _ph(dialect)
    run_id = run_id or latest_run_id(cursor, case_id, dialect)
    if run_id is None:
        return []
    sql = f"SELECT * FROM field_assertions WHERE case_id = {ph} AND run_id = {ph}"
    params: List[Any] = [case_id, run_id]
    if field:
        sql += f" AND field = {ph}"
        params.append(field)
    cursor.execute(sql + " ORDER BY id", params)
    out = []
    for r in _rows(cursor):
        r["value"] = json.loads(r.pop("value_json"))
        r["extras"] = json.loads(r.pop("extras_json") or "{}")
        out.append(r)
    return out


def latest_resolutions(cursor: Any, case_id: str, *, field: Optional[str] = None,
                       dialect: str = "sqlite") -> Dict[str, Dict[str, Any]]:
    """Last resolution per field inside the case's current extraction run."""
    ph = _ph(dialect)
    run_id = latest_run_id(cursor, case_id, dialect)
    if not run_id:
        return {}
    sql = f"SELECT * FROM field_resolutions WHERE case_id = {ph} AND run_id = {ph}"
    params: List[Any] = [case_id, run_id]
    if field:
        sql += f" AND field = {ph}"
        params.append(field)
    cursor.execute(sql + " ORDER BY id", params)
    out: Dict[str, Dict[str, Any]] = {}
    for r in _rows(cursor):
        out[r["field"]] = {
            "status": r["status"],
            "rule_id": r["rule_id"],
            "rule_set_version": r["rule_set_version"],
            "run_id": r["run_id"],
            "final_value": json.loads(r["final_json"] or "null"),
            "winning_assertion_ids": json.loads(r["winning_assertion_ids"] or "[]"),
            "disagreement": json.loads(r["disagreement_json"] or "{}"),
            "resolved_at": str(r["created_at"]),
        }
    return out


def read_case_assertions(cursor: Any, case_id: str, *, field: Optional[str] = None,
                         dialect: str = "sqlite") -> Dict[str, Any]:
    assertions = load_assertions(cursor, case_id, field=field, dialect=dialect)
    resolutions = latest_resolutions(cursor, case_id, field=field, dialect=dialect)
    keep = ("id", "run_id", "field", "method", "method_version", "family", "value", "role",
            "span_start", "span_end", "span_text", "span_ok", "confidence", "extras")
    run_id = assertions[0]["run_id"] if assertions else None
    if not run_id:
        for res in resolutions.values():
            if res.get("run_id"):
                run_id = res["run_id"]
                break
    return {
        "case_id": case_id,
        "run_id": run_id,
        "assertions": [{k: a.get(k) for k in keep} for a in assertions],
        "resolutions": resolutions,
    }


def _latest_resolution_ids_sql() -> str:
    """Newest resolution row per field, and only inside that case's current run.

    A case id with no row in ``cases`` is omitted, so a deleted id cannot keep
    an open disagreement after its article was removed.
    """
    return """
        SELECT MAX(fr.id) FROM field_resolutions fr
        WHERE fr.run_id = (
            SELECT fa.run_id FROM field_assertions fa
            WHERE fa.case_id = fr.case_id AND fa.method <> 'human'
            ORDER BY fa.id DESC LIMIT 1
        )
        AND fr.case_id IN (SELECT id FROM cases)
        GROUP BY fr.case_id, fr.field
    """


def read_disagreements(cursor: Any, *, field: Optional[str] = None, status: Optional[str] = None,
                       limit: int = 50, offset: int = 0, dialect: str = "sqlite") -> Dict[str, Any]:
    """Latest resolution per (case, field) whose status needs a human, newest first."""
    ph = _ph(dialect)
    statuses = [status] if status else list(REVIEW_STATUSES)
    where = [f"r.status IN ({', '.join([ph] * len(statuses))})"]
    params: List[Any] = list(statuses)
    if field:
        where.append(f"r.field = {ph}")
        params.append(field)
    latest = _latest_resolution_ids_sql()
    cursor.execute(
        f"""SELECT r.case_id, r.field, r.status, r.rule_id, r.rule_set_version, r.final_json, r.disagreement_json
            FROM field_resolutions r WHERE r.id IN ({latest}) AND {' AND '.join(where)}
            ORDER BY r.id DESC LIMIT {ph} OFFSET {ph}""",
        params + [int(limit), int(offset)],
    )
    items = []
    for r in _rows(cursor):
        items.append({
            "case_id": r["case_id"],
            "field": r["field"],
            "status": r["status"],
            "rule_id": r["rule_id"],
            "rule_set_version": r["rule_set_version"],
            "final_value": json.loads(r["final_json"] or "null"),
            "disagreement": json.loads(r["disagreement_json"] or "{}"),
        })
    cursor.execute(
        f"""SELECT r.field, r.status, COUNT(*) FROM field_resolutions r WHERE r.id IN ({latest})
            GROUP BY r.field, r.status"""
    )
    counts: Dict[str, Dict[str, int]] = {}
    for row in cursor.fetchall():
        f, st, n = (row["field"], row["status"], row["count"]) if isinstance(row, dict) else row
        counts.setdefault(f, {})[st] = int(n)
    return {"items": items, "limit": limit, "offset": offset, "status_counts": counts}


def count_assertion_feature_values(cursor: Any, excluded_roles, *, dialect: str = "sqlite") -> Dict[str, int]:
    """Distinct (case, field, value) assertions in each case's current extraction run, per field,
    leaving out the given roles (program boilerplate, not-an-age, statutory thresholds, ...).
    Used by the /api/stats feature count (run/feature_count.py)."""
    roles = sorted(excluded_roles)
    ph = _ph(dialect)
    not_in = f"AND fa.role NOT IN ({', '.join([ph] * len(roles))})" if roles else ""
    cursor.execute(
        f"""
        SELECT t.field, COUNT(*) FROM (
            SELECT DISTINCT fa.case_id, fa.field, fa.value_json
            FROM field_assertions fa
            JOIN cases c ON c.id = fa.case_id AND c.extraction_run_id = fa.run_id
            WHERE fa.value_json IS NOT NULL {not_in}
        ) t
        GROUP BY t.field
        """,
        roles,
    )
    return {field: int(n) for field, n in cursor.fetchall()}
