"""Unit tests for NL → SPARQL extraction helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "run"))

from sparql_proxy import extract_sparql_from_llm_text, prepare_sparql_query  # noqa: E402


class TestExtractSparql(unittest.TestCase):
    def test_strips_fence_and_prose(self):
        raw = (
            "Sure, here you go:\n"
            "```sparql\n"
            "PREFIX cac: <https://cacontology.projectvic.org#>\n"
            "ASK { ?s a cac:CACInvestigation }\n"
            "```\n"
            "Hope that helps."
        )
        out = extract_sparql_from_llm_text(raw)
        self.assertIn("ASK", out)
        self.assertNotIn("```", out)
        self.assertNotIn("Hope", out)

    def test_keeps_blank_line_between_prefix_and_select(self):
        raw = (
            "PREFIX cac: <https://cacontology.projectvic.org#>\n"
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
            "\n"
            "SELECT ?platform ?label (COUNT(DISTINCT ?case) AS ?caseCount)\n"
            "WHERE {\n"
            "  ?case a cac:CACInvestigation .\n"
            "}\n"
            "LIMIT 5"
        )
        out = extract_sparql_from_llm_text(raw)
        self.assertIn("SELECT", out)
        prepared = prepare_sparql_query(out)
        self.assertEqual(prepared.kind, "SelectQuery")

    def test_prepare_accepts_extracted(self):
        q = extract_sparql_from_llm_text(
            "PREFIX cac: <https://cacontology.projectvic.org#>\n"
            "SELECT ?s WHERE { ?s a cac:CACInvestigation } LIMIT 5"
        )
        prepared = prepare_sparql_query(q)
        self.assertEqual(prepared.kind, "SelectQuery")


if __name__ == "__main__":
    unittest.main()
