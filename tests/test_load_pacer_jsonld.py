"""IRI encoding and hexBinary casing for PACER JSON-LD → N-Quads."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from load_pacer_jsonld import (  # noqa: E402
    classify,
    graph_iri,
    restore_hex,
    to_nquads,
)


def test_graph_iri_percent_encodes_spaces_and_keeps_slashes():
    assert graph_iri("BULK_FOLDER/pacer -- ncmec_2023_224 -- indictment.jsonld") == (
        "urn:pacer:kg:BULK_FOLDER/pacer%20--%20ncmec_2023_224%20--%20indictment.jsonld"
    )
    assert graph_iri("PRODUCTION/ai/PACER -- production -- docket -- Texas.jsonld") == (
        "urn:pacer:kg:PRODUCTION/ai/PACER%20--%20production%20--%20docket%20--%20Texas.jsonld"
    )


def test_graph_iri_does_not_leave_raw_spaces():
    iri = graph_iri("BULK_FOLDER/outside/pacer -- crypto -- Plea Agreement.jsonld")
    assert " " not in iri
    assert "%20" in iri
    assert iri.startswith("urn:pacer:kg:")


def test_restore_hex_puts_back_uppercase_after_rdflib_fold():
    original = "DEADBEEFCAFE"
    lowered = (
        f'<urn:uuid:probe> <https://ontology.unifiedcyberontology.org/uco/types/hashValue> '
        f'"{original.lower()}"^^<http://www.w3.org/2001/XMLSchema#hexBinary> .'
    )
    restored = restore_hex(lowered, [original])
    assert f'"{original}"^^<http://www.w3.org/2001/XMLSchema#hexBinary>' in restored
    assert original.lower() not in restored


def test_to_nquads_preserves_source_hex_casing(tmp_path: Path):
    digest = "A1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4E5F60718293A4B5C6D7E8F90"
    fixture = {
        "@context": {
            "uco-types": "https://ontology.unifiedcyberontology.org/uco/types/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
        },
        "@graph": [
            {
                "@id": "urn:uuid:hash-probe",
                "uco-types:hashValue": {
                    "@type": "xsd:hexBinary",
                    "@value": digest,
                },
            }
        ],
    }
    path = tmp_path / "pacer -- probe -- hash.jsonld"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    rel = "BULK_FOLDER/pacer -- probe -- hash.jsonld"
    nq, triples, lower_left = to_nquads(path, rel)
    assert triples == 1
    assert lower_left == 0
    assert f'"{digest}"^^<http://www.w3.org/2001/XMLSchema#hexBinary>' in nq
    assert digest.lower() not in nq
    assert graph_iri(rel) in nq
    assert nq.strip().endswith(f"<{graph_iri(rel)}> .")


def test_classify_skips_bare_annotations_and_extracted_content():
    assert classify(Path("BULK_FOLDER/annotations.jsonld")) is None
    assert classify(Path("BULK_FOLDER/extracted-content.json")) is None
    assert classify(Path("pacer -- x -- indictment.extracted-content.json")) is None
    assert classify(Path("BULK_FOLDER/ncmec_2023_224-investigation.jsonld")) == "investigation"
    assert classify(Path("pacer -- ncmec_2023_224 -- indictment.annotations.jsonld")) == "annotation"
    assert classify(Path("pacer -- ncmec_2023_224 -- indictment.jsonld")) == "document"
