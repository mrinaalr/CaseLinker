"""Analysis-time corrections to stored labels, and text rules the numbers use. The database is never changed.

Facebook inside "Facebook Messenger": the platform matcher tags `Facebook` when a release only
names Facebook Messenger. Such a tag is replaced by `Facebook Messenger` wherever AfH loads platform
labels (snapshot export, harm release, the numbers scripts).
"""
from __future__ import annotations

import re
from typing import List

# Case-insensitive, like the platform matcher that assigned the tag (pattern_processing.py, re.IGNORECASE).
# "Facebook Messenger" may be joined by whitespace, a hyphen or an underscore (URL slugs: facebook-messenger).
STANDALONE_FACEBOOK = re.compile(r"\bFacebook\b(?![\s\-_]*Messenger)(?!['’]s\s+Messenger)", re.I)
MESSENGER = re.compile(r"Facebook[\s\-_]*Messenger", re.I)


def facebook_only_inside_messenger(labels: List[str], text: str) -> bool:
    """The case is tagged Facebook, but the text names Facebook only as part of 'Facebook Messenger'."""
    return ("Facebook" in labels and bool(MESSENGER.search(text or ""))
            and not STANDALONE_FACEBOOK.search(text or ""))


def correct_platform_labels(labels: List[str], text: str) -> List[str]:
    if not facebook_only_inside_messenger(labels, text):
        return list(labels)
    out = [p for p in labels if p != "Facebook"]
    if "Facebook Messenger" not in out:
        out.append("Facebook Messenger")
    return out


# §2252A(g) child exploitation enterprise (affordance family "coordination"). No stored field carries
# the charge, so it is read from the case text. Singular "enterprise" only: the plural appears in
# generic quotes ("those who engage in child exploitation enterprises").
ENTERPRISE_CHARGE = re.compile(r"2252A\s*\(g\)|child exploitation enterprise(?!s)", re.I)


def names_enterprise_charge(text: str) -> bool:
    return bool(ENTERPRISE_CHARGE.search(text or ""))


# Publication year. Ingest took the first date in some releases' text as the publication year (an event or a
# biography date). At load, a stored year is corrected when >= 2 of the record's own publication evidence
# fields agree on another year and none supports the stored one. Publication evidence: the case-id year, the
# year of the compilation file the release was collected from (e.g. "2022 NCMEC.pdf"), and stated
# publication dates. An event date says when something happened, not when the release was published: it
# supports the stored year only when the record states no publication date. The DB is unchanged.
_ID_YEAR = re.compile(r"_((?:19|20)\d{2})_\d+$")
_FILE_YEAR = re.compile(r"\s*((?:19|20)\d{2})\b")


def year_evidence(case_id: str, source_file, dated: dict) -> dict:
    """dated: role -> set of years from the record's date assertions."""
    idm, fm = _ID_YEAR.search(case_id or ""), _FILE_YEAR.match(source_file or "")
    return {"id": int(idm.group(1)) if idm else None, "file": int(fm.group(1)) if fm else None,
            "publication": sorted(dated.get("publication", ())), "event": sorted(dated.get("event", ())),
            "biography": sorted(dated.get("biography", ()))}


def corrected_pub_year(year, ev: dict):
    """(year to use, evidence fields that agree on it) for one record."""
    if year is None:
        return None, []
    pub = set(ev["publication"])
    supports = ev["id"] == year or ev["file"] == year or year in pub or (not pub and year in ev["event"])
    if supports:
        return year, []
    votes = {}
    for y in {ev["id"], ev["file"], *pub} - {None, year}:
        votes[y] = [f for f, ok in (("id", ev["id"] == y), ("file", ev["file"] == y), ("publication", y in pub)) if ok]
    if not votes:
        return year, []
    best = max(len(v) for v in votes.values())
    winners = [y for y, v in votes.items() if len(v) == best]
    if best >= 2 and len(winners) == 1:
        return winners[0], votes[winners[0]]
    return year, []


def dated_assertions(conn) -> dict:
    """case_id -> role -> years of its date assertions (current extraction run only)."""
    out: dict = {}
    for cid, role, value in conn.execute(
            "SELECT fa.case_id, fa.role, fa.value_json FROM field_assertions fa JOIN cases c "
            "ON c.id = fa.case_id AND c.extraction_run_id = fa.run_id WHERE fa.field = 'date'"):
        m = re.match(r'"?((?:19|20)\d{2})', value or "")
        if m:
            out.setdefault(cid, {}).setdefault(role, set()).add(int(m.group(1)))
    return out


def year_corrections(conn) -> dict:
    """case_id -> {stored, corrected, agreeing, evidence} for every record the rule corrects."""
    dated = dated_assertions(conn)
    out = {}
    for cid, year, source_file in conn.execute(
            "SELECT id, CAST(json_extract(raw_data,'$.year') AS INT), json_extract(raw_data,'$.source_file') FROM cases"):
        ev = year_evidence(cid, source_file, dated.get(cid, {}))
        new, agreeing = corrected_pub_year(year, ev)
        if new != year:
            out[cid] = {"stored": year, "corrected": new, "agreeing": agreeing,
                        "evidence": {k: ev[k] for k in ("id", "file", "publication")}}
    return out
