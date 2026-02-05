"""
CaseLinker - main code
Simple pipeline: ingest -> process -> analyze -> store -> visualize
"""

import sys
from pathlib import Path

src_path = Path(__file__).parent
sys.path.insert(0, str(src_path / "Ingestion Layer"))
sys.path.insert(0, str(src_path / "Processing Layer"))
sys.path.insert(0, str(src_path / "Storage Layer"))
sys.path.insert(0, str(src_path / "Clustering & Analysis Layer"))
sys.path.insert(0, str(src_path / "Visualization Layer"))

from ingestion import ingest_file, extract_pdf_text
from processing import process_cases
from storage import CaseStorage, GraphStorage
from analysis import cluster_cases, find_similar_cases, trend_analysis
from visualization import create_dashboard, filter_cases
import pandas as pd


def main():
    print("CaseLinker - Starting up...")
    print("\n✓ All layers loaded successfully!")
    print("\nLayer Structure:")
    print("  - Ingestion Layer: PDF text extraction, file import, validation")
    print("  - Processing Layer: Feature extraction, case schema filling")
    print("  - Storage Layer: Case database & graph storage")
    print("  - Clustering & Analysis Layer: Case comparison, clustering, trends")
    print("  - Visualization Layer: Interactive dashboards, graphs, filtering")
    print("\nTo use PDF extraction, install: pip install pdfplumber")
    


if __name__ == "__main__":
    main()
