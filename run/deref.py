"""Turn a w3id CaseLinker IRI into a description a browser or a client can read.

The w3id redirect is a 303 that keeps the path. This module builds the
SPARQL that reads the description from Oxigraph and renders HTML, Turtle,
or JSON-LD. Vocabulary terms are the ontology document, not a case graph.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

import rdflib
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

REPO = Path(__file__).resolve().parent.parent
PROVENANCE_TTL = REPO / "ontology" / "caselinker-provenance.ttl"
W3ID = "https://w3id.org/caselinker/"
RESOURCE_BASE = W3ID + "resource/"
PROVENANCE_IRI = W3ID + "ns/provenance"
CAC_HOST = "cacontology.projectvic.org"
_PATH = re.compile(r"[A-Za-z0-9_./-]+")


def resource_iri(path: str) -> str:
    """Rebuild the w3id IRI for a path under /resource/."""
    cleaned = unquote(path or "").strip("/")
    if not cleaned or ".." in cleaned.split("/") or not _PATH.fullmatch(cleaned):
        raise ValueError(cleaned or path)
    return RESOURCE_BASE + cleaned


def construct_query(iri: str) -> str:
    """A case or provenance IRI is a named graph. Anything else is a node."""
    if re.fullmatch(rf"{re.escape(RESOURCE_BASE)}case/[^/]+(/provenance)?", iri):
        return f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{iri}> {{ ?s ?p ?o }} }}"
    return (
        f"CONSTRUCT {{ <{iri}> ?p ?o }} WHERE {{ GRAPH ?g {{ <{iri}> ?p ?o }} }}"
    )


def is_hub_resource(iri: str) -> bool:
    """Agency, platform, and location IRIs are hubs — cases link out to them."""
    return bool(
        re.match(
            rf"^{re.escape(RESOURCE_BASE)}(agency|platform|location)/[^/]+$",
            iri.rstrip("/"),
        )
    )


def referencing_cases_query(iri: str, *, limit: int = 500) -> str:
    """Named graphs (press-release cases) that mention this hub IRI."""
    lim = max(1, min(int(limit), 2000))
    return (
        "SELECT DISTINCT ?g WHERE {\n"
        f"  GRAPH ?g {{ ?s ?p <{iri}> }}\n"
        "  FILTER(STRSTARTS(STR(?g), "
        f'"{RESOURCE_BASE}case/") && !STRENDS(STR(?g), "/provenance"))\n'
        "}\n"
        "ORDER BY ?g\n"
        f"LIMIT {lim}"
    )


def parse_sparql_json_bindings(payload: str) -> list:
    """Pull ?g / ?case URI values from a SPARQL JSON results document."""
    import json

    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return []
    out = []
    for row in data.get("results", {}).get("bindings", []):
        for key in ("g", "case", "s"):
            cell = row.get(key) or {}
            if cell.get("type") == "uri" and cell.get("value"):
                out.append(str(cell["value"]))
                break
    return out


def preferred_media(accept: Optional[str], *, vocabulary: bool = False) -> str:
    """HTML for a browser. Turtle or JSON-LD when the client asks for them."""
    header = accept or "text/html"
    scores = {"text/html": 0.0, "text/turtle": 0.0, "application/ld+json": 0.0}
    saw_html = False
    for raw in header.split(","):
        part = raw.strip()
        if not part:
            continue
        bits = [b.strip() for b in part.split(";")]
        media = bits[0].lower()
        q = 1.0
        for bit in bits[1:]:
            if bit.startswith("q="):
                try:
                    q = float(bit[2:])
                except ValueError:
                    q = 0.0
        if media in ("text/html", "application/xhtml+xml"):
            scores["text/html"] = max(scores["text/html"], q)
            saw_html = True
        elif media == "text/turtle":
            scores["text/turtle"] = max(scores["text/turtle"], q)
        elif media == "application/ld+json":
            scores["application/ld+json"] = max(scores["application/ld+json"], q)
        elif media == "*/*":
            scores["text/html"] = max(scores["text/html"], q)
            saw_html = True
    if vocabulary:
        scores["application/ld+json"] = 0.0
    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return "text/html" if saw_html or vocabulary else "text/turtle"
    return best


def parse_turtle(text: str) -> Graph:
    graph = Graph()
    if text and text.strip():
        graph.parse(data=text, format="turtle")
    return graph


def serialize_graph(graph: Graph, media: str) -> str:
    if media == "application/ld+json":
        return graph.serialize(format="json-ld")
    if media == "text/turtle":
        return graph.serialize(format="turtle")
    return render_html(graph, focus=None)


def render_html(
    graph: Graph,
    focus: Optional[str] = None,
    *,
    referencing_cases: Optional[list] = None,
) -> str:
    """A page of labels and links. Every CAC class links to its own IRI."""
    subjects = []
    focus_ref = URIRef(focus) if focus else None
    if focus_ref is not None and any(graph.triples((focus_ref, None, None))):
        subjects.append(focus_ref)
    for subject in graph.subjects():
        if isinstance(subject, URIRef) and subject not in subjects:
            subjects.append(subject)
    if focus and "/provenance" in focus:
        subjects = sorted(subjects, key=_provenance_section_key)
    blocks = []
    title = _page_title(graph, focus)
    for subject in subjects:
        rows = []
        for pred, obj in graph.predicate_objects(subject):
            rows.append(
                "<tr><th>"
                + html.escape(_short(pred))
                + "</th><td>"
                + _render_object(obj, graph)
                + "</td></tr>"
            )
        heading = _label(graph, subject) or _short(subject)
        blocks.append(
            f"<section><h2>{html.escape(heading)}</h2>"
            f"<p><a href=\"{html.escape(str(subject))}\">{html.escape(str(subject))}</a></p>"
            f"<table>{''.join(rows)}</table></section>"
        )
    if referencing_cases is not None and focus and is_hub_resource(focus):
        blocks.append(_render_referencing_cases(referencing_cases))
    body = "".join(blocks) or "<p>No description is stored for this IRI.</p>"
    explore_href = "/explore" + (f"?iri={quote(focus, safe='')}" if focus else "")
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font:16px/1.45 Georgia,serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1c1917}"
        "a{color:#1d4e89}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;"
        "border-top:1px solid #e7e5e4;padding:.4rem .6rem}th{width:12rem;font-weight:600}"
        "ul.refs{padding-left:1.2rem}ul.refs li{margin:.25rem 0}p.nav{font:13px/1.4 -apple-system,Helvetica,Arial,sans-serif;color:#78716c}</style>"
        f"</head><body><p class=\"nav\"><a href=\"/\">CaseLinker</a> &middot; "
        f"<a href=\"{html.escape(explore_href)}\">open in Explore</a></p>"
        f"<h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def _render_referencing_cases(case_iris: list) -> str:
    """HTML section listing case graphs that mention the hub."""
    if not case_iris:
        return (
            "<section><h2>Cases referencing this</h2>"
            "<p>No press-release case graphs mention this resource.</p></section>"
        )
    items = []
    for iri in case_iris:
        case_id = iri.rstrip("/").rsplit("/", 1)[-1]
        local = "/resource/" + iri[len(RESOURCE_BASE) :] if iri.startswith(RESOURCE_BASE) else iri
        items.append(
            f'<li><a href="{html.escape(local)}">{html.escape(case_id)}</a></li>'
        )
    return (
        "<section><h2>Cases referencing this</h2>"
        f"<p>{len(case_iris)} case{'s' if len(case_iris) != 1 else ''}</p>"
        f'<ul class="refs">{"".join(items)}</ul></section>'
    )


def provenance_graph() -> Graph:
    graph = Graph()
    graph.parse(PROVENANCE_TTL, format="turtle")
    return graph


def _page_title(graph: Graph, focus: Optional[str]) -> str:
    """Stable page titles: case id, or Provenance · case_id — not the first labeled node."""
    if not focus:
        return "CaseLinker"
    focus = focus.rstrip("/")
    if focus.endswith("/provenance") and "/resource/case/" in focus:
        case_id = focus.rsplit("/provenance", 1)[0].rsplit("/", 1)[-1]
        return f"Provenance · {case_id}"
    if re.fullmatch(rf"{re.escape(RESOURCE_BASE)}case/[^/]+", focus):
        return focus.rsplit("/", 1)[-1]
    focus_ref = URIRef(focus)
    return _label(graph, focus_ref) or _short(focus_ref)


def _provenance_section_key(subject: URIRef):
    """Assertion, then its passage + selectors; other nodes after the assertion blocks."""
    text = str(subject)
    marker = "/assertion/"
    if marker not in text:
        return (1, text)
    rest = text.split(marker, 1)[1]
    parts = rest.split("/")
    try:
        index = int(parts[0])
    except ValueError:
        return (1, text)
    kind = parts[1] if len(parts) > 1 else ""
    # assertion → passage (target IRI) → position → quote
    order = {"": 0, "target": 1, "position": 2, "quote": 3}
    return (0, index, order.get(kind, 9), text)


def _label(graph: Graph, subject) -> str:
    value = graph.value(subject, RDFS.label)
    return str(value) if value else ""


def _short(term) -> str:
    text = str(term)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    return text.rstrip("/").rsplit("/", 1)[-1]


def _render_object(obj, graph: Optional[Graph] = None) -> str:
    if isinstance(obj, URIRef):
        target = str(obj)
        label = _label(graph, obj) if graph is not None else ""
        shown = html.escape(label or _short(obj))
        if CAC_HOST in target:
            return f'<a href="{html.escape(target)}">{shown}</a>'
        if target.startswith(RESOURCE_BASE):
            local = "/resource/" + target[len(RESOURCE_BASE):]
            return f'<a href="{html.escape(local)}">{shown}</a>'
        if target.startswith(W3ID):
            return f'<a href="{html.escape(target)}">{shown}</a>'
        return f'<a href="{html.escape(target)}">{shown}</a>'
    if obj == RDF.type:
        return html.escape(str(obj))
    return html.escape(str(obj))
