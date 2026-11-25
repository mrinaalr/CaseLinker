"""Case graphs carry the corrected publication year (afhq1.labels.year_corrections), without losing precision."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "caselinker.db"
sys.path.insert(0, str(ROOT / "ontology" / "pipeline"))


@pytest.mark.skipif(not DB.is_file(), reason="caselinker.db is local-only")
def test_graph_dates_follow_the_year_corrections(tmp_path, monkeypatch):
    import graph_generate as gg
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(gg, "_load_dotenv", lambda: None)
    assert gg.main(["--sqlite", "--out", str(tmp_path), "--no-resume", "--no-provenance",
                    "--ids", "ncmec_2022_506", "ncmec_2023_597"]) == 0
    # stored 1992-06 (a biography date): corrected to 2022, known to the year only
    assert '"2022"^^xsd:gYear' in (tmp_path / "ncmec_2022_506.ttl").read_text()
    # stored date already in the corrected year: full precision kept
    assert '"2023-12-06"^^xsd:date' in (tmp_path / "ncmec_2023_597.ttl").read_text()
