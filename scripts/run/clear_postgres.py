#!/usr/bin/env python3
"""
Clear all data from PostgreSQL database
WARNING: This will delete ALL cases and related data!
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
        
        # Delete in order (respecting foreign keys)
        tables = [
            'technology_revolver_slim',
            'automated_analysis_slim',
            'cluster_groups_slim',
            'precomputed_clusters',
            'prosecution_outcomes',
            'perpetrator_demographics',
            'victim_demographics',
            'cases'
        ]
        
        for table in tables:
            cursor.execute(f'DELETE FROM {table}')
            count = cursor.rowcount
            print(f"   ✓ Cleared {table}: {count} rows")
        
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
