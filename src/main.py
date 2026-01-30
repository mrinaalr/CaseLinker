"""
CaseLinker - main code
Simple pipeline: ingest -> process -> analyze -> store -> visualize
"""

from .ingestion import ingest_file
from .processing import process_cases
from .storage import CaseStorage
from .analysis import cluster_cases, find_similar_cases
import pandas as pd


def main():

    print("CaseLinker - Starting up...")
    
    


if __name__ == "__main__":
    main()
