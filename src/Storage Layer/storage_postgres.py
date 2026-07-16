"""
PostgreSQL Storage Layer

Purpose: Store cases and relationships with fast retrieval and lookup capabilities.
PostgreSQL version - uses psycopg2 for production-ready database.

Design Ideas from Architecture:
- Case Database (PostgreSQL): keep it simple, store case data tables, ideally similar close together
- Store case entities in "rawish" format (preserve original structure + normalized fields)
- Graph Database: Store case and relationships with weighted edges based on similarity strength
- Efficient traversal for link analysis
- Quick relationship queries (e.g., "show all cases connected to case X")
"""

import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from case_storage_utils import hydrate_case_text_from_raw_data, slim_extracted_features_for_storage

# Connection pool (reuse connections for better performance)
_pool: Optional[SimpleConnectionPool] = None


def get_pool():
    """Get or create connection pool"""
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        # Create connection pool
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url
        )
    return _pool


def get_connection():
    """Get connection from pool"""
    pool = get_pool()
    return pool.getconn()


def return_connection(conn):
    """Return connection to pool"""
    pool = get_pool()
    pool.putconn(conn)


class CaseStorage:
    """
    PostgreSQL Case Database Storage
    
    Stores processed case data in "rawish" format - preserves original structure 
    along with normalized fields. Designed for quick retrieval and lookups.
    Similar cases stored close together for efficient access.
    """
    
    def __init__(self, db_path: str = None, encryption_key: Optional[str] = None):
        """
        Initialize PostgreSQL storage.
        
        Args:
            db_path: Ignored (uses DATABASE_URL from environment)
            encryption_key: Ignored (PostgreSQL handles encryption via SSL)
        """
        # Verify DATABASE_URL is set
        if not os.getenv("DATABASE_URL"):
            raise ValueError("DATABASE_URL environment variable must be set for PostgreSQL storage")
        
        self.init_database()
    
    def init_database(self):
        """
        Initialize database tables.
        Creates tables for storing case data in rawish format.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            # Create tables (PostgreSQL syntax).
            # cases.raw_data: ingestion batch (includes case_text).
            # cases.extracted_features: structured fields only — see case_storage_utils.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    source TEXT,
                    source_url TEXT,
                    date_start TEXT,
                    date_end TEXT,
                    victim_count INTEGER,
                    perpetrator_count INTEGER,
                    relationship_to_victim TEXT,
                    platforms_used TEXT,
                    severity_indicators TEXT,
                    case_topics TEXT,
                    tags TEXT,
                    notes TEXT,
                    raw_data TEXT,
                    extracted_features TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON cases(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_date_start ON cases(date_start)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_case_topics ON cases(case_topics)')
            # Backward-compatible migration for pre-existing PostgreSQL databases.
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name='cases' AND column_name='source_url'
                    ) THEN
                        ALTER TABLE cases ADD COLUMN source_url TEXT;
                    END IF;
                END $$;
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS victim_demographics (
                    case_id TEXT PRIMARY KEY,
                    age_range TEXT,
                    region TEXT,
                    anonymized_id TEXT,
                    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS perpetrator_demographics (
                    case_id TEXT PRIMARY KEY,
                    age_range TEXT,
                    region TEXT,
                    anonymized_id TEXT,
                    previous_conviction TEXT,
                    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prosecution_outcomes (
                    case_id TEXT PRIMARY KEY,
                    status TEXT,
                    charges TEXT,
                    sentences TEXT,
                    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
                )
            ''')
            
            # Legacy table kept for migrations/clear scripts. Full analysis blobs are no
            # longer written here (too large for Postgres). Cluster cache lives in
            # cluster_groups_slim only.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS precomputed_clusters (
                    id SERIAL PRIMARY KEY,
                    cluster_data TEXT,
                    case_count INTEGER,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(case_count)
                )
            ''')
            # Slim cluster groups (metadata + case IDs only) — durable /api/cluster-groups cache
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cluster_groups_slim (
                    case_count INTEGER PRIMARY KEY,
                    data TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS technology_revolver_slim (
                    case_count INTEGER PRIMARY KEY,
                    data TEXT NOT NULL
                )
            ''')
            # Slim automated analysis (groups as IDs, top triaged, insights) — durable cache
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS automated_analysis_slim (
                    case_count INTEGER PRIMARY KEY,
                    data TEXT NOT NULL
                )
            ''')
            conn.commit()
        finally:
            cursor.close()
            return_connection(conn)
    
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
            conn = get_connection()
            cursor = conn.cursor()
            
            date_range = case.get('date_range', {})
            date_start = date_range.get('start') if isinstance(date_range, dict) else None
            date_end = date_range.get('end') if isinstance(date_range, dict) else None
            
            # Check if case already exists to preserve created_at timestamp and prevent conflicts
            case_id = case.get('id')
            cursor.execute('SELECT created_at, raw_data FROM cases WHERE id = %s', (case_id,))
            existing_case = cursor.fetchone()
            
            # Use consistent ISO format for timestamps
            current_time = datetime.now().isoformat()
            
            if existing_case:
                existing_created_at, existing_raw_data_json = existing_case
                
                # Check if this is from a different source file (conflict detection)
                new_source_file = None
                if isinstance(case.get('raw_data'), dict):
                    new_source_file = case.get('raw_data', {}).get('source_file')
                elif isinstance(case.get('raw_data'), str):
                    try:
                        new_source_file = json.loads(case.get('raw_data', '{}')).get('source_file')
                    except:
                        pass
                
                existing_source_file = None
                if existing_raw_data_json:
                    try:
                        existing_raw_data = json.loads(existing_raw_data_json)
                        existing_source_file = existing_raw_data.get('source_file')
                    except:
                        pass
                
                # If source files differ, this is a conflict - don't overwrite
                if new_source_file and existing_source_file and new_source_file != existing_source_file:
                    print(f"⚠️  Warning: Case ID conflict detected for {case_id}")
                    print(f"   Existing case from: {existing_source_file}")
                    print(f"   New case from: {new_source_file}")
                    print(f"   Skipping new case to prevent data loss")
                    cursor.close()
                    return_connection(conn)
                    return False
                
                # Case exists from same source: preserve original created_at, update updated_at
                created_at = existing_created_at
                updated_at = current_time
            else:
                # New case: use created_at from case dict if provided, otherwise use current time
                created_at = case.get('created_at') or current_time
                updated_at = case.get('updated_at') or created_at
            
            # PostgreSQL: Use INSERT ... ON CONFLICT DO UPDATE instead of INSERT OR REPLACE
            cursor.execute('''
                INSERT INTO cases (
                    id, source, source_url, date_start, date_end, victim_count, perpetrator_count,
                    relationship_to_victim, platforms_used,
                    severity_indicators, case_topics, tags, notes,
                    raw_data, extracted_features, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    source = EXCLUDED.source,
                    source_url = EXCLUDED.source_url,
                    date_start = EXCLUDED.date_start,
                    date_end = EXCLUDED.date_end,
                    victim_count = EXCLUDED.victim_count,
                    perpetrator_count = EXCLUDED.perpetrator_count,
                    relationship_to_victim = EXCLUDED.relationship_to_victim,
                    platforms_used = EXCLUDED.platforms_used,
                    severity_indicators = EXCLUDED.severity_indicators,
                    case_topics = EXCLUDED.case_topics,
                    tags = EXCLUDED.tags,
                    notes = EXCLUDED.notes,
                    raw_data = EXCLUDED.raw_data,
                    extracted_features = EXCLUDED.extracted_features,
                    updated_at = EXCLUDED.updated_at
            ''', (
                case_id,
                case.get('source', 'unknown'),
                case.get('source_url') or (case.get('raw_data', {}) if isinstance(case.get('raw_data'), dict) else {}).get('source_url'),
                date_start,
                date_end,
                case.get('victim_count'),
                None,  # perpetrator_count (deprecated)
                case.get('relationship_to_victim'),
                json.dumps(case.get('platforms_used', [])),
                json.dumps(case.get('severity_indicators', [])),
                json.dumps(case.get('case_topics', [])),
                json.dumps(case.get('tags', [])),
                case.get('notes'),
                json.dumps(case.get('raw_data', {})),
                json.dumps(slim_extracted_features_for_storage(case)),
                created_at,
                updated_at
            ))
            
            case_demo = case.get('case_demographics') or case.get('victim_demographics')
            if case_demo and isinstance(case_demo, dict):
                age_range_str = None
                if case_demo.get('age_range'):
                    age_range_str = json.dumps(case_demo.get('age_range'))
                elif case_demo.get('ages'):
                    ages = case_demo.get('ages', [])
                    if ages:
                        age_range_str = json.dumps({'min': min(ages), 'max': max(ages)})
                
                cursor.execute('''
                    INSERT INTO victim_demographics 
                    (case_id, age_range, region, anonymized_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (case_id) DO UPDATE SET
                        age_range = EXCLUDED.age_range,
                        region = EXCLUDED.region,
                        anonymized_id = EXCLUDED.anonymized_id
                ''', (
                    case.get('id'),
                    age_range_str,
                    case_demo.get('region'),
                    None,
                ))
            
            # Store perpetrator demographics
            perp_age = case.get('perpetrator_age')
            perp_registered = case.get('perpetrator_registered_sex_offender', False)
            perp_demo = case.get('perpetrator_demographics')
            
            if perp_age is not None or perp_registered or perp_demo:
                age_range_str = None
                if perp_age is not None:
                    age_range_str = json.dumps({'min': perp_age, 'max': perp_age})
                elif perp_demo and isinstance(perp_demo, dict) and perp_demo.get('age'):
                    age = perp_demo.get('age')
                    age_range_str = json.dumps({'min': age, 'max': age})
                
                prev_conviction = case.get('previous_conviction') or (perp_demo.get('previous_conviction') if isinstance(perp_demo, dict) else None)
                
                cursor.execute('''
                    INSERT INTO perpetrator_demographics 
                    (case_id, age_range, region, anonymized_id, previous_conviction)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (case_id) DO UPDATE SET
                        age_range = EXCLUDED.age_range,
                        region = EXCLUDED.region,
                        anonymized_id = EXCLUDED.anonymized_id,
                        previous_conviction = EXCLUDED.previous_conviction
                ''', (
                    case.get('id'),
                    age_range_str,
                    None,
                    None,
                    json.dumps(prev_conviction) if prev_conviction else None,
                ))
            
            prosecution = case.get('prosecution_outcome')
            if prosecution and isinstance(prosecution, dict):
                status = prosecution.get('booking_status') or prosecution.get('status')
                charges = prosecution.get('charges', [])
                charges_str = json.dumps(charges)
                
                sentences = prosecution.get('sentences', [])
                if isinstance(sentences, str):
                    sentences = [sentences] if sentences.strip() else []
                cursor.execute('''
                    INSERT INTO prosecution_outcomes 
                    (case_id, status, charges, sentences)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (case_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        charges = EXCLUDED.charges,
                        sentences = EXCLUDED.sentences
                ''', (
                    case.get('id'),
                    status,
                    charges_str,
                    json.dumps(sentences if isinstance(sentences, list) else []),
                ))
            
            conn.commit()
            cursor.close()
            return_connection(conn)
            return True
            
        except Exception as e:
            print(f"Error storing case: {e}")
            import traceback
            traceback.print_exc()
            if 'conn' in locals():
                cursor.close()
                return_connection(conn)
            return False
    
    def store_cases(self, cases: List[Dict[str, Any]]) -> int:
        """Store multiple cases in the database."""
        stored_count = 0
        for case in cases:
            if self.store_case(case):
                stored_count += 1
        return stored_count
    
    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single case by ID."""
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute('SELECT * FROM cases WHERE id = %s', (case_id,))
            row = cursor.fetchone()
            
            if not row:
                cursor.close()
                return_connection(conn)
                return None
            
            case_dict = dict(row)
            
            # Parse JSON fields
            for json_field in ['platforms_used', 'severity_indicators',
                             'case_topics', 'tags', 'raw_data', 'extracted_features']:
                if case_dict.get(json_field):
                    try:
                        case_dict[json_field] = json.loads(case_dict[json_field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            if not case_dict.get('source_url'):
                rd = case_dict.get('raw_data')
                if isinstance(rd, dict):
                    rd_url = rd.get('source_url')
                    if isinstance(rd_url, str) and rd_url.strip():
                        case_dict['source_url'] = rd_url.strip()
            
            # Get related data
            cursor.execute('SELECT * FROM victim_demographics WHERE case_id = %s', (case_id,))
            victim_rows = cursor.fetchall()
            if victim_rows:
                case_dict['victim_demographics'] = [dict(row) for row in victim_rows]
            else:
                case_dict['victim_demographics'] = []
            
            cursor.execute('SELECT * FROM perpetrator_demographics WHERE case_id = %s', (case_id,))
            perp_rows = cursor.fetchall()
            if perp_rows:
                case_dict['perpetrator_demographics'] = [dict(row) for row in perp_rows]
            else:
                case_dict['perpetrator_demographics'] = []
            
            cursor.execute('SELECT * FROM prosecution_outcomes WHERE case_id = %s', (case_id,))
            prosecution_rows = cursor.fetchall()
            if prosecution_rows:
                prosecution_cols = [desc[0] for desc in cursor.description]
                case_dict['prosecution_outcomes'] = [dict(row) for row in prosecution_rows]
            else:
                case_dict['prosecution_outcomes'] = []
            
            # Reconstruct date_range
            case_dict['date_range'] = {
                'start': case_dict.get('date_start'),
                'end': case_dict.get('date_end')
            }
            
            # Merge extracted_features back into case_dict
            extracted_features = case_dict.get('extracted_features', {})
            if isinstance(extracted_features, dict):
                for key in ['perpetrator_age', 'perpetrator_gender', 'perpetrator_registered_sex_offender',
                           'press_digest_pollution', 'multi_defendant_operation',
                           'agencies_involved', 'organizations', 'locations', 'investigation_type', 'investigation_types', 'evidence_volume',
                           'prosecution_outcome', 'case_demographics', 'victim_demographics', 'relationship_to_victim',
                           'severity_phrases', 'perpetrator_admissions', 'perpetrator_admission_themes',
                           'case_text', 'comparison_values',
                           'investigation_technology', 'anonymization_network', 'p2p_clients', 'offense_technology']:
                    if key in extracted_features:
                        case_dict[key] = extracted_features[key]
            
            # Merge prosecution_outcome from prosecution_outcomes table
            if not case_dict.get('prosecution_outcome') and case_dict.get('prosecution_outcomes'):
                prosecution_rows = case_dict.get('prosecution_outcomes', [])
                if prosecution_rows and len(prosecution_rows) > 0:
                    prosecution = prosecution_rows[0]
                    _sent = prosecution.get('sentences')
                    try:
                        _sent_list = json.loads(_sent) if _sent else []
                    except (json.JSONDecodeError, TypeError):
                        _sent_list = []
                    case_dict['prosecution_outcome'] = {
                        'booking_status': prosecution.get('status'),
                        'charges': json.loads(prosecution.get('charges', '[]')) if prosecution.get('charges') else [],
                        'jail': None,
                        'sentences': _sent_list if isinstance(_sent_list, list) else [],
                    }
            
            hydrate_case_text_from_raw_data(case_dict)
            
            cursor.close()
            return_connection(conn)
            return case_dict
            
        except Exception as e:
            print(f"Error retrieving case: {e}")
            if 'conn' in locals():
                cursor.close()
                return_connection(conn)
            return None
    
    def get_case_count(self) -> int:
        """
        Get total number of cases in database (fast query).
        
        Returns:
            Number of cases
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM cases')
            count = cursor.fetchone()[0]
            cursor.close()
            return_connection(conn)
            return count
        except Exception as e:
            print(f"Error getting case count: {e}")
            return 0
    
    def get_all_cases(self, include_raw_data: bool = True) -> List[Dict[str, Any]]:
        """Retrieve all cases from the database."""
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Single query to get all cases
            if include_raw_data:
                cursor.execute('''
                    SELECT id, source, date_start, date_end, victim_count, perpetrator_count,
                           source_url,
                           relationship_to_victim, platforms_used,
                           severity_indicators, case_topics, tags, notes,
                           raw_data, extracted_features, created_at, updated_at
                    FROM cases
                    ORDER BY date_start, id
                ''')
            else:
                cursor.execute('''
                    SELECT id, source, date_start, date_end, victim_count, perpetrator_count,
                           source_url,
                           relationship_to_victim, platforms_used,
                           severity_indicators, case_topics, tags, notes,
                           '' as raw_data, extracted_features, created_at, updated_at
                    FROM cases
                    ORDER BY date_start, id
                ''')
            
            rows = cursor.fetchall()
            case_ids = [row['id'] for row in rows]
            
            if not case_ids:
                cursor.close()
                return_connection(conn)
                return []
            
            # Bulk fetch related data
            placeholders = ','.join(['%s'] * len(case_ids))
            
            cursor.execute(f'SELECT * FROM victim_demographics WHERE case_id IN ({placeholders})', case_ids)
            victim_data = {}
            for row in cursor.fetchall():
                case_id = row['case_id']
                if case_id not in victim_data:
                    victim_data[case_id] = []
                victim_data[case_id].append(dict(row))
            
            cursor.execute(f'SELECT * FROM perpetrator_demographics WHERE case_id IN ({placeholders})', case_ids)
            perp_data = {}
            for row in cursor.fetchall():
                case_id = row['case_id']
                if case_id not in perp_data:
                    perp_data[case_id] = []
                perp_data[case_id].append(dict(row))
            
            cursor.execute(f'SELECT * FROM prosecution_outcomes WHERE case_id IN ({placeholders})', case_ids)
            prosecution_data = {}
            for row in cursor.fetchall():
                case_id = row['case_id']
                if case_id not in prosecution_data:
                    prosecution_data[case_id] = []
                prosecution_data[case_id].append(dict(row))
            
            cursor.close()
            return_connection(conn)
            
            # Build case dictionaries
            cases = []
            for row in rows:
                case_dict = dict(row)
                
                # Parse JSON fields
                for json_field in ['platforms_used', 'severity_indicators', 'case_topics', 'tags',
                                 'raw_data', 'extracted_features']:
                    if case_dict.get(json_field):
                        if json_field == 'raw_data' and case_dict[json_field] == '':
                            case_dict[json_field] = None
                            continue
                        try:
                            case_dict[json_field] = json.loads(case_dict[json_field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                
                # Merge extracted_features
                extracted_features = case_dict.get('extracted_features', {})
                if isinstance(extracted_features, dict):
                    for key in ['perpetrator_age', 'perpetrator_registered_sex_offender',
                               'press_digest_pollution', 'multi_defendant_operation',
                               'agencies_involved', 'organizations', 'locations', 'investigation_type', 'investigation_types', 'evidence_volume',
                               'prosecution_outcome', 'case_demographics', 'victim_demographics', 'relationship_to_victim',
                               'severity_phrases', 'perpetrator_admissions', 'perpetrator_admission_themes',
                           'case_text', 'comparison_values',
                               'investigation_technology', 'anonymization_network', 'p2p_clients', 'offense_technology']:
                        if key in extracted_features:
                            case_dict[key] = extracted_features[key]
                
                if include_raw_data:
                    hydrate_case_text_from_raw_data(case_dict)
                else:
                    case_dict.pop('raw_data', None)
                    case_dict.pop('case_text', None)
                
                # Add date_range
                if case_dict.get('date_start') or case_dict.get('date_end'):
                    case_dict['date_range'] = {
                        'start': case_dict.get('date_start'),
                        'end': case_dict.get('date_end')
                    }
                
                # Add related data
                case_id = case_dict['id']
                case_dict['victim_demographics'] = victim_data.get(case_id, [])
                case_dict['perpetrator_demographics'] = perp_data.get(case_id, [])
                case_dict['prosecution_outcome'] = prosecution_data.get(case_id, [{}])[0] if prosecution_data.get(case_id) else {}
                
                cases.append(case_dict)
            
            return cases
            
        except Exception as e:
            print(f"❌ Error retrieving all cases: {e}")
            import traceback
            traceback.print_exc()
            if 'conn' in locals():
                cursor.close()
                return_connection(conn)
            return []

    def get_cases_by_ids(self, case_ids: List[str], include_raw_data: bool = False) -> List[Dict[str, Any]]:
        """Load specific cases by id (same shape as get_all_cases for matching flags). Preserves input id order."""
        if not case_ids:
            return []
        seen = set()
        ordered_unique: List[str] = []
        for cid in case_ids:
            if cid and isinstance(cid, str) and cid not in seen:
                seen.add(cid)
                ordered_unique.append(cid)
        if not ordered_unique:
            return []
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            placeholders = ",".join(["%s"] * len(ordered_unique))
            if include_raw_data:
                cursor.execute(
                    f"""
                    SELECT id, source, date_start, date_end, victim_count, perpetrator_count,
                           source_url,
                           relationship_to_victim, platforms_used,
                           severity_indicators, case_topics, tags, notes,
                           raw_data, extracted_features, created_at, updated_at
                    FROM cases WHERE id IN ({placeholders})
                    """,
                    ordered_unique,
                )
            else:
                cursor.execute(
                    f"""
                    SELECT id, source, date_start, date_end, victim_count, perpetrator_count,
                           source_url,
                           relationship_to_victim, platforms_used,
                           severity_indicators, case_topics, tags, notes,
                           '' as raw_data, extracted_features, created_at, updated_at
                    FROM cases WHERE id IN ({placeholders})
                    """,
                    ordered_unique,
                )
            rows = list(cursor.fetchall())
            if not rows:
                cursor.close()
                return_connection(conn)
                return []
            found_ids = [row["id"] for row in rows]
            ph2 = ",".join(["%s"] * len(found_ids))
            cursor.execute(
                f"SELECT * FROM victim_demographics WHERE case_id IN ({ph2})", found_ids
            )
            victim_data: Dict[str, List] = {}
            for row in cursor.fetchall():
                case_id = row["case_id"]
                victim_data.setdefault(case_id, []).append(dict(row))
            cursor.execute(
                f"SELECT * FROM perpetrator_demographics WHERE case_id IN ({ph2})", found_ids
            )
            perp_data: Dict[str, List] = {}
            for row in cursor.fetchall():
                case_id = row["case_id"]
                perp_data.setdefault(case_id, []).append(dict(row))
            cursor.execute(
                f"SELECT * FROM prosecution_outcomes WHERE case_id IN ({ph2})", found_ids
            )
            prosecution_data: Dict[str, List] = {}
            for row in cursor.fetchall():
                case_id = row["case_id"]
                prosecution_data.setdefault(case_id, []).append(dict(row))
            cursor.close()
            return_connection(conn)
            cases: List[Dict[str, Any]] = []
            for row in rows:
                case_dict = dict(row)
                for json_field in [
                    "platforms_used",
                    "severity_indicators",
                    "case_topics",
                    "tags",
                    "raw_data",
                    "extracted_features",
                ]:
                    if case_dict.get(json_field):
                        if json_field == "raw_data" and case_dict[json_field] == "":
                            case_dict[json_field] = None
                            continue
                        try:
                            case_dict[json_field] = json.loads(case_dict[json_field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                extracted_features = case_dict.get("extracted_features", {})
                if isinstance(extracted_features, dict):
                    for key in [
                        "perpetrator_age",
                        "perpetrator_gender",
                        "perpetrator_registered_sex_offender",
                        "press_digest_pollution",
                        "multi_defendant_operation",
                        "agencies_involved",
                        "organizations",
                        "locations",
                        "investigation_type",
                        "investigation_types",
                        "evidence_volume",
                        "prosecution_outcome",
                        "case_demographics",
                        "victim_demographics",
                        "relationship_to_victim",
                        "severity_phrases",
                        "perpetrator_admissions",
                        "perpetrator_admission_themes",
                        "case_text",
                        "comparison_values",
                        "investigation_technology",
                        "anonymization_network",
                        "p2p_clients",
                        "offense_technology",
                    ]:
                        if key in extracted_features:
                            case_dict[key] = extracted_features[key]
                if include_raw_data:
                    hydrate_case_text_from_raw_data(case_dict)
                else:
                    case_dict.pop("raw_data", None)
                    case_dict.pop("case_text", None)
                if case_dict.get("date_start") or case_dict.get("date_end"):
                    case_dict["date_range"] = {
                        "start": case_dict.get("date_start"),
                        "end": case_dict.get("date_end"),
                    }
                cid = case_dict["id"]
                case_dict["victim_demographics"] = victim_data.get(cid, [])
                case_dict["perpetrator_demographics"] = perp_data.get(cid, [])
                case_dict["prosecution_outcome"] = (
                    prosecution_data.get(cid, [{}])[0] if prosecution_data.get(cid) else {}
                )
                cases.append(case_dict)
            id_to_case = {c["id"]: c for c in cases}
            return [id_to_case[i] for i in ordered_unique if i in id_to_case]
        except Exception as e:
            print(f"❌ Error get_cases_by_ids: {e}")
            if "conn" in locals():
                try:
                    cursor.close()
                    return_connection(conn)
                except Exception:
                    pass
            return []

    def get_cases_slim_chunk(self, offset: int, limit: int) -> List[Dict[str, Any]]:
        """Page through cases without raw_data (same dict shape as get_all_cases(include_raw_data=False))."""
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 500))
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT id, source, date_start, date_end, victim_count, perpetrator_count,
                       source_url,
                       relationship_to_victim, platforms_used,
                       severity_indicators, case_topics, tags, notes,
                       '' as raw_data, extracted_features, created_at, updated_at
                FROM cases
                ORDER BY date_start NULLS LAST, id
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            rows = list(cursor.fetchall())
            if not rows:
                cursor.close()
                return_connection(conn)
                return []
            case_ids = [row["id"] for row in rows]
            placeholders = ",".join(["%s"] * len(case_ids))
            cursor.execute(
                f"SELECT * FROM victim_demographics WHERE case_id IN ({placeholders})", case_ids
            )
            victim_data: Dict[str, List] = {}
            for row in cursor.fetchall():
                cid = row["case_id"]
                victim_data.setdefault(cid, []).append(dict(row))
            cursor.execute(
                f"SELECT * FROM perpetrator_demographics WHERE case_id IN ({placeholders})", case_ids
            )
            perp_data: Dict[str, List] = {}
            for row in cursor.fetchall():
                cid = row["case_id"]
                perp_data.setdefault(cid, []).append(dict(row))
            cursor.execute(
                f"SELECT * FROM prosecution_outcomes WHERE case_id IN ({placeholders})", case_ids
            )
            prosecution_data: Dict[str, List] = {}
            for row in cursor.fetchall():
                cid = row["case_id"]
                prosecution_data.setdefault(cid, []).append(dict(row))
            cursor.close()
            return_connection(conn)
            cases: List[Dict[str, Any]] = []
            for row in rows:
                case_dict = dict(row)
                for json_field in [
                    "platforms_used",
                    "severity_indicators",
                    "case_topics",
                    "tags",
                    "raw_data",
                    "extracted_features",
                ]:
                    if case_dict.get(json_field):
                        if json_field == "raw_data" and case_dict[json_field] == "":
                            case_dict[json_field] = None
                            continue
                        try:
                            case_dict[json_field] = json.loads(case_dict[json_field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                extracted_features = case_dict.get("extracted_features", {})
                if isinstance(extracted_features, dict):
                    for key in [
                        "perpetrator_age",
                        "perpetrator_gender",
                        "perpetrator_registered_sex_offender",
                        "press_digest_pollution",
                        "multi_defendant_operation",
                        "agencies_involved",
                        "organizations",
                        "locations",
                        "investigation_type",
                        "investigation_types",
                        "evidence_volume",
                        "prosecution_outcome",
                        "case_demographics",
                        "victim_demographics",
                        "relationship_to_victim",
                        "severity_phrases",
                        "perpetrator_admissions",
                        "perpetrator_admission_themes",
                        "case_text",
                        "comparison_values",
                        "investigation_technology",
                        "anonymization_network",
                        "p2p_clients",
                        "offense_technology",
                    ]:
                        if key in extracted_features:
                            case_dict[key] = extracted_features[key]
                case_dict.pop("raw_data", None)
                case_dict.pop("case_text", None)
                if case_dict.get("date_start") or case_dict.get("date_end"):
                    case_dict["date_range"] = {
                        "start": case_dict.get("date_start"),
                        "end": case_dict.get("date_end"),
                    }
                cid = case_dict["id"]
                case_dict["victim_demographics"] = victim_data.get(cid, [])
                case_dict["perpetrator_demographics"] = perp_data.get(cid, [])
                case_dict["prosecution_outcome"] = (
                    prosecution_data.get(cid, [{}])[0] if prosecution_data.get(cid) else {}
                )
                cases.append(case_dict)
            return cases
        except Exception as e:
            print(f"❌ Error get_cases_slim_chunk: {e}")
            if "conn" in locals():
                try:
                    cursor.close()
                    return_connection(conn)
                except Exception:
                    pass
            return []
    
    def search_cases(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search cases based on criteria."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if query.get('source'):
                conditions.append('source = %s')
                params.append(query['source'])
            
            if query.get('date_start'):
                conditions.append('date_start >= %s')
                params.append(query['date_start'])
            
            if query.get('date_end'):
                conditions.append('date_start <= %s')
                params.append(query['date_end'])
            
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            
            cursor.execute(f'SELECT id FROM cases WHERE {where_clause} ORDER BY date_start', params)
            case_ids = [row[0] for row in cursor.fetchall()]
            
            cursor.close()
            return_connection(conn)
            
            cases = []
            for case_id in case_ids:
                case = self.get_case(case_id)
                if case:
                    cases.append(case)
            
            return cases
            
        except Exception as e:
            print(f"Error searching cases: {e}")
            if 'conn' in locals():
                cursor.close()
                return_connection(conn)
            return []
    
    def _slim_case_groups(self, case_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strip cases to ID strings only for fast transfer."""
        if not case_groups:
            return []
        result = []
        for group in case_groups:
            slim = {k: v for k, v in group.items() if k not in ('cases', 'internal_groups')}
            cases = group.get('cases', [])
            slim['cases'] = [c.get('id') if isinstance(c, dict) else c for c in cases if (c.get('id') if isinstance(c, dict) else c)]
            internal = group.get('internal_groups', [])
            slim['internal_groups'] = [{'cases': [c.get('id') if isinstance(c, dict) else c for c in ig.get('cases', []) if (c.get('id') if isinstance(c, dict) else c)], 'size': ig.get('size', 0)} for ig in internal]
            result.append(slim)
        return result

    def store_cluster_groups_slim(self, case_groups: List[Dict[str, Any]], case_count: int) -> bool:
        """Store slimmed cluster groups (IDs only) for fast /api/cluster-groups fetches."""
        slim = self._slim_case_groups(case_groups)
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO cluster_groups_slim (case_count, data)
                VALUES (%s, %s)
                ON CONFLICT (case_count) DO UPDATE SET data = EXCLUDED.data
            ''', (case_count, json.dumps(slim)))
            conn.commit()
            cursor.close()
            return_connection(conn)
            return True
        except Exception as e:
            print(f"Error storing cluster groups slim: {e}")
            if 'conn' in locals():
                cursor.close()
                return_connection(conn)
            return False

    def get_cluster_groups_slim(self, case_count: int) -> Optional[List[Dict[str, Any]]]:
        """Fetch slimmed cluster groups - small payload, fast."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT data FROM cluster_groups_slim WHERE case_count = %s', (case_count,))
            row = cursor.fetchone()
            cursor.close()
            return_connection(conn)
            if row:
                try:
                    import orjson
                    return orjson.loads(row[0])
                except ImportError:
                    return json.loads(row[0])
            return None
        except Exception as e:
            if 'conn' in locals():
                cursor.close()
                return_connection(conn)
            return None

    def store_technology_revolver_slim(self, payload: Dict[str, Any], case_count: int) -> bool:
        """Persist technology revolver JSON for fast GET when case_count matches."""
        storable = {k: v for k, v in payload.items() if k not in ("cached", "source")}
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO technology_revolver_slim (case_count, data)
                VALUES (%s, %s)
                ON CONFLICT (case_count) DO UPDATE SET data = EXCLUDED.data
                """,
                (case_count, json.dumps(storable)),
            )
            conn.commit()
            cursor.close()
            return_connection(conn)
            return True
        except Exception as e:
            print(f"Error storing technology_revolver_slim: {e}")
            if "conn" in locals():
                cursor.close()
                return_connection(conn)
            return False

    def get_technology_revolver_slim(self, case_count: int) -> Optional[Dict[str, Any]]:
        """Load persisted technology revolver payload if row exists for this case count."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM technology_revolver_slim WHERE case_count = %s",
                (case_count,),
            )
            row = cursor.fetchone()
            cursor.close()
            return_connection(conn)
            if not row:
                return None
            try:
                import orjson

                data = orjson.loads(row[0])
            except ImportError:
                data = json.loads(row[0])
            if isinstance(data, dict) and "chambers" in data:
                return data
            return None
        except Exception as e:
            if "conn" in locals():
                cursor.close()
                return_connection(conn)
            return None

    def store_automated_analysis_slim(self, analysis: Dict[str, Any], case_count: int) -> bool:
        """Persist slim automated-analysis payload (IDs-only groups + top triaged + insights)."""
        if not isinstance(analysis, dict):
            return False
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO automated_analysis_slim (case_count, data)
                VALUES (%s, %s)
                ON CONFLICT (case_count) DO UPDATE SET data = EXCLUDED.data
                """,
                (case_count, json.dumps(analysis)),
            )
            conn.commit()
            cursor.close()
            return_connection(conn)
            return True
        except Exception as e:
            print(f"Error storing automated_analysis_slim: {e}")
            if "conn" in locals():
                cursor.close()
                return_connection(conn)
            return False

    def get_automated_analysis_slim(self, case_count: int) -> Optional[Dict[str, Any]]:
        """Load persisted slim automated analysis if row exists for this case count."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM automated_analysis_slim WHERE case_count = %s",
                (case_count,),
            )
            row = cursor.fetchone()
            cursor.close()
            return_connection(conn)
            if not row:
                return None
            try:
                import orjson

                data = orjson.loads(row[0])
            except ImportError:
                data = json.loads(row[0])
            return data if isinstance(data, dict) else None
        except Exception as e:
            if "conn" in locals():
                cursor.close()
                return_connection(conn)
            return None

    def store_precomputed_clusters(self, cluster_data: Dict[str, Any], case_count: int) -> bool:
        """
        Persist slim cluster groups only (IDs + group metadata).

        Never writes the full per-case analysis blob — that exceeds Postgres's
        ~1GB single-field limit at corpus scale. Full analysis is persisted in
        automated_analysis_slim and Redis-cached for /api/automated-analysis.
        """
        case_groups: List[Dict[str, Any]] = []
        if isinstance(cluster_data, dict):
            raw = cluster_data.get("case_groups") or []
            if isinstance(raw, list):
                case_groups = raw

        # Drop any legacy full-blob row so stale huge values cannot be re-read.
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM precomputed_clusters WHERE case_count = %s",
                (case_count,),
            )
            conn.commit()
            cursor.close()
            return_connection(conn)
        except Exception as e:
            print(f"Warning clearing legacy precomputed_clusters row: {e}")
            if "conn" in locals():
                try:
                    cursor.close()
                    return_connection(conn)
                except Exception:
                    pass

        ok = self.store_cluster_groups_slim(case_groups, case_count)
        if not ok:
            print("Error storing precomputed clusters: slim write failed")
        return ok

    def clear_precomputed_clusters(self):
        """Clear legacy full-blob table and slim analysis/cluster caches."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM precomputed_clusters")
            cursor.execute("DELETE FROM cluster_groups_slim")
            cursor.execute("DELETE FROM automated_analysis_slim")
            conn.commit()
            cursor.close()
            return_connection(conn)
            return True
        except Exception as e:
            print(f"Error clearing precomputed clusters: {e}")
            if "conn" in locals():
                cursor.close()
                return_connection(conn)
            return False
