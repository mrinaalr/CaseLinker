#!/usr/bin/env python3
"""
Clear all data from the PostgreSQL database (every table in the public schema).
WARNING: This deletes ALL rows in ALL tables. Take a snapshot first.
Schemas are kept; the next ingest writes into empty tables.
"""
import os
import sys
from pathlib import Path

# Add paths
src_path = Path(__file__).resolve().parents[2] / "src" / "Storage Layer"
sys.path.insert(0, str(src_path))

from storage_postgres import get_connection, return_connection

def clear_database():
    """Clear all tables in PostgreSQL database"""
    if not os.getenv("DATABASE_URL"):
        print("❌ ERROR: DATABASE_URL environment variable not set")
        print("   Set it to your PostgreSQL connection string")
        return False
    
    print("⚠️  WARNING: This will delete ALL data from the database!")
    
    # Allow skipping confirmation via environment variable or command line arg
    if os.getenv("AUTO_CONFIRM") == "true" or (len(sys.argv) > 1 and sys.argv[1] == "--yes"):
        print("   Auto-confirmed (AUTO_CONFIRM=true or --yes flag)")
    else:
        confirm = input("Type 'DELETE ALL' to confirm: ")
        if confirm != "DELETE ALL":
            print("❌ Cancelled. Database not cleared.")
            return False
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        print("\n🗑️  Clearing database tables...")

        # Every table in the public schema, whatever exists today: a hardcoded list
        # misses tables added later (field_assertions, field_resolutions, fingerprints, ...).
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        tables = [row[0] for row in cursor.fetchall()]
        if not tables:
            print("   (no tables)")
        for table in tables:
            cursor.execute(f'SELECT count(*) FROM "{table}"')
            print(f"   • {table}: {cursor.fetchone()[0]} rows")
        # TRUNCATE (not DELETE): one statement, foreign keys via CASCADE, and the
        # append-only row triggers on field_assertions do not fire on TRUNCATE.
        if tables:
            cursor.execute(
                "TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"
            )
            print(f"   ✓ Truncated {len(tables)} tables")

        conn.commit()
        cursor.close()
        return_connection(conn)
        
        print("\n✅ Database cleared successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error clearing database: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    clear_database()
