"""
Storage Layer

Purpose: Store cases and relationships with fast retrieval and lookup capabilities.

Design Ideas from Architecture:
- Case Database (PostgreSQL/MySQL): keep it simple, store case data tables, ideally similar close together
- Store case entities in "rawish" format (preserve original structure + normalized fields)
- Graph Database: Store case and relationships with weighted edges based on similarity strength
- Efficient traversal for link analysis
- Quick relationship queries (e.g., "show all cases connected to case X")
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


class CaseStorage:
    """
    Case Database Storage
    
    Stores processed case data in "rawish" format - preserves original structure 
    along with normalized fields. Designed for quick retrieval and lookups.
    Similar cases stored close together for efficient access.
    """
    
    def __init__(self, db_path: str = "caselinker.db"):
        """
        Initialize case storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """
        Initialize database tables.
        Creates tables for storing case data in rawish format.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                source TEXT,
                date_start TEXT,
                date_end TEXT,
                victim_count INTEGER,
                perpetrator_count INTEGER,
                relationship_to_victim TEXT,
                platforms_used TEXT,  -- JSON array
                technologies TEXT,    -- JSON array
                communication_methods TEXT,  -- JSON array
                investigation_methods TEXT,   -- JSON array
                severity_indicators TEXT,     -- JSON array
                case_topics TEXT,             -- JSON array
                tags TEXT,                    -- JSON array
                notes TEXT,
                raw_data TEXT,                -- JSON - original case data
                extracted_features TEXT,      -- JSON - structured features
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON cases(source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date_start ON cases(date_start)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_case_topics ON cases(case_topics)')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS victim_demographics (
                case_id TEXT,
                age_range TEXT,
                region TEXT,
                anonymized_id TEXT,
                FOREIGN KEY (case_id) REFERENCES cases(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS perpetrator_demographics (
                case_id TEXT,
                age_range TEXT,
                region TEXT,
                anonymized_id TEXT,
                previous_conviction TEXT,  -- JSON
                FOREIGN KEY (case_id) REFERENCES cases(id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prosecution_outcomes (
                case_id TEXT,
                status TEXT,
                charges TEXT,      -- JSON array
                sentences TEXT,    -- JSON array
                FOREIGN KEY (case_id) REFERENCES cases(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def store_case(self, case: Dict[str, Any]) -> bool:
        """
        Store a single case in the database.
        Preserves raw data while storing normalized fields.
        
        Args:
            case: Case dictionary from processing layer
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            date_range = case.get('date_range', {})
            date_start = date_range.get('start') if isinstance(date_range, dict) else None
            date_end = date_range.get('end') if isinstance(date_range, dict) else None
            
            cursor.execute('''
                INSERT OR REPLACE INTO cases (
                    id, source, date_start, date_end, victim_count, perpetrator_count,
                    relationship_to_victim, platforms_used, technologies, communication_methods,
                    investigation_methods, severity_indicators, case_topics, tags, notes,
                    raw_data, extracted_features, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                case.get('id'),
                case.get('source', 'unknown'),
                date_start,
                date_end,
                case.get('victim_count'),
                case.get('perpetrator_count'),
                case.get('relationship_to_victim'),
                json.dumps(case.get('platforms_used', [])),
                json.dumps(case.get('technologies', [])),
                json.dumps(case.get('communication_methods', [])),
                json.dumps(case.get('investigation_methods_and_teams', [])),
                json.dumps(case.get('severity_indicators', [])),
                json.dumps(case.get('case_topics', [])),
                json.dumps(case.get('tags', [])),
                case.get('notes'),
                json.dumps(case.get('raw_data', {})),
                json.dumps(case.get('extracted_features', {})),
                datetime.now().isoformat()
            ))
            
            victim_demo = case.get('victim_demographics')
            if victim_demo:
                cursor.execute('''
                    INSERT OR REPLACE INTO victim_demographics 
                    (case_id, age_range, region, anonymized_id)
                    VALUES (?, ?, ?, ?)
                ''', (
                    case.get('id'),
                    victim_demo.get('age_range'),
                    victim_demo.get('region'),
                    victim_demo.get('anonymized_id')
                ))
            
            perp_demo = case.get('perpetrator_demographics')
            if perp_demo:
                cursor.execute('''
                    INSERT OR REPLACE INTO perpetrator_demographics 
                    (case_id, age_range, region, anonymized_id, previous_conviction)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    case.get('id'),
                    perp_demo.get('age_range'),
                    perp_demo.get('region'),
                    perp_demo.get('anonymized_id'),
                    json.dumps(case.get('previous_conviction', {}))
                ))
            
            prosecution = case.get('prosecution_outcome')
            if prosecution:
                cursor.execute('''
                    INSERT OR REPLACE INTO prosecution_outcomes 
                    (case_id, status, charges, sentences)
                    VALUES (?, ?, ?, ?)
                ''', (
                    case.get('id'),
                    prosecution.get('status'),
                    json.dumps(prosecution.get('charges', [])),
                    json.dumps(prosecution.get('sentences', []))
                ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error storing case: {e}")
            return False
    
    def store_cases(self, cases: List[Dict[str, Any]]) -> bool:
        """
        Store multiple cases in the database.
        
        Args:
            cases: List of case dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        success_count = 0
        for case in cases:
            if self.store_case(case):
                success_count += 1
        
        return success_count == len(cases)
    
    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a case by ID.
        
        Args:
            case_id: Unique case identifier
            
        Returns:
            Case dictionary or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM cases WHERE id = ?', (case_id,))
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return None
            
            case = dict(row)
            
            for json_field in ['platforms_used', 'technologies', 'communication_methods',
                             'investigation_methods', 'severity_indicators', 'case_topics',
                             'tags', 'raw_data', 'extracted_features']:
                if case.get(json_field):
                    case[json_field] = json.loads(case[json_field])
            
            cursor.execute('SELECT * FROM victim_demographics WHERE case_id = ?', (case_id,))
            victim_row = cursor.fetchone()
            if victim_row:
                case['victim_demographics'] = dict(victim_row)
            
            cursor.execute('SELECT * FROM perpetrator_demographics WHERE case_id = ?', (case_id,))
            perp_row = cursor.fetchone()
            if perp_row:
                perp_dict = dict(perp_row)
                if perp_dict.get('previous_conviction'):
                    perp_dict['previous_conviction'] = json.loads(perp_dict['previous_conviction'])
                case['perpetrator_demographics'] = perp_dict
            
            cursor.execute('SELECT * FROM prosecution_outcomes WHERE case_id = ?', (case_id,))
            pros_row = cursor.fetchone()
            if pros_row:
                pros_dict = dict(pros_row)
                if pros_dict.get('charges'):
                    pros_dict['charges'] = json.loads(pros_dict['charges'])
                if pros_dict.get('sentences'):
                    pros_dict['sentences'] = json.loads(pros_dict['sentences'])
                case['prosecution_outcome'] = pros_dict
            
            conn.close()
            return case
        except Exception as e:
            print(f"Error retrieving case: {e}")
            return None
    
    def get_all_cases(self) -> List[Dict[str, Any]]:
        """
        Retrieve all cases from the database.
        
        Returns:
            List of all case dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM cases')
            case_ids = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
            return [self.get_case(cid) for cid in case_ids if self.get_case(cid)]
        except Exception as e:
            print(f"Error retrieving all cases: {e}")
            return []
    
    def search_cases(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search cases based on filter criteria.
        Fast lookup using indexed fields.
        
        Args:
            filters: Dictionary with search criteria (source, date_range, platforms, etc.)
            
        Returns:
            List of matching case dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = "SELECT id FROM cases WHERE 1=1"
            params = []
            
            if 'source' in filters:
                query += " AND source = ?"
                params.append(filters['source'])
            
            if 'date_start' in filters:
                query += " AND date_start >= ?"
                params.append(filters['date_start'])
            
            if 'date_end' in filters:
                query += " AND date_end <= ?"
                params.append(filters['date_end'])
            
            if 'platforms' in filters:
                platform_filter = " OR ".join(["platforms_used LIKE ?" for _ in filters['platforms']])
                query += f" AND ({platform_filter})"
                params.extend([f"%{p}%" for p in filters['platforms']])
            
            cursor.execute(query, params)
            case_ids = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
            return [self.get_case(cid) for cid in case_ids if self.get_case(cid)]
        except Exception as e:
            print(f"Error searching cases: {e}")
            return []


class GraphStorage:
    """
    Graph Database Storage
    
    Stores case relationships with weighted edges based on similarity strength.
    Designed for efficient traversal and link analysis.
    Quick relationship queries (e.g., "show all cases connected to case X").
    """
    
    def __init__(self, db_path: str = "caselinker_graph.db"):
        """
        Initialize graph storage.
        
        Args:
            db_path: Path to graph database file
        """
        self.db_path = db_path
        self.init_graph_database()
    
    def init_graph_database(self):
        """
        Initialize graph database tables.
        Stores nodes (cases) and edges (relationships) with weights.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                case_id TEXT PRIMARY KEY,
                properties TEXT  -- JSON for additional node properties
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_case_id TEXT,
                target_case_id TEXT,
                weight REAL,  -- Similarity score (0.0 to 1.0)
                relationship_type TEXT,  -- e.g., 'similar', 'linked', 'cluster'
                properties TEXT,  -- JSON for additional edge properties
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_case_id) REFERENCES nodes(case_id),
                FOREIGN KEY (target_case_id) REFERENCES nodes(case_id),
                UNIQUE(source_case_id, target_case_id)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON edges(source_case_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_target ON edges(target_case_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_weight ON edges(weight)')
        
        conn.commit()
        conn.close()
    
    def add_case_node(self, case_id: str, properties: Optional[Dict[str, Any]] = None):
        """
        Add a case node to the graph.
        
        Args:
            case_id: Unique case identifier
            properties: Optional additional node properties
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO nodes (case_id, properties)
            VALUES (?, ?)
        ''', (case_id, json.dumps(properties or {})))
        
        conn.commit()
        conn.close()
    
    def add_relationship(self, source_case_id: str, target_case_id: str, 
                        weight: float, relationship_type: str = 'similar',
                        properties: Optional[Dict[str, Any]] = None):
        """
        Add a weighted relationship between two cases.
        
        Args:
            source_case_id: Source case ID
            target_case_id: Target case ID
            weight: Similarity score (0.0 to 1.0)
            relationship_type: Type of relationship
            properties: Optional additional edge properties
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO edges 
            (source_case_id, target_case_id, weight, relationship_type, properties)
            VALUES (?, ?, ?, ?, ?)
        ''', (source_case_id, target_case_id, weight, relationship_type, 
              json.dumps(properties or {})))
        
        conn.commit()
        conn.close()
    
    def get_connected_cases(self, case_id: str, min_weight: float = 0.0) -> List[Tuple[str, float]]:
        """
        Get all cases connected to a given case.
        Quick relationship query as specified in architecture.
        
        Args:
            case_id: Case ID to find connections for
            min_weight: Minimum similarity weight threshold
            
        Returns:
            List of (connected_case_id, weight) tuples
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT target_case_id, weight FROM edges
            WHERE source_case_id = ? AND weight >= ?
            UNION
            SELECT source_case_id, weight FROM edges
            WHERE target_case_id = ? AND weight >= ?
            ORDER BY weight DESC
        ''', (case_id, min_weight, case_id, min_weight))
        
        results = cursor.fetchall()
        conn.close()
        
        return [(row[0], row[1]) for row in results]
    
    def get_all_relationships(self, min_weight: float = 0.0) -> List[Tuple[str, str, float]]:
        """
        Get all relationships in the graph.
        
        Args:
            min_weight: Minimum similarity weight threshold
            
        Returns:
            List of (source_case_id, target_case_id, weight) tuples
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT source_case_id, target_case_id, weight FROM edges
            WHERE weight >= ?
            ORDER BY weight DESC
        ''', (min_weight,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [(row[0], row[1], row[2]) for row in results]
