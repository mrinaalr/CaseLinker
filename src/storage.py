"""
Storage Layer
"""

import sqlite3
from pathlib import Path


class CaseStorage:
    """
    Simple storage implementation.
    Stores processed case data (Dictionary format from processing layer).
    """
    
    def __init__(self, db_path: str = "caselinker.db"):
        """
        Initialize storage.
        
        Args:
            db_path: Path to database file
        """
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database"""
