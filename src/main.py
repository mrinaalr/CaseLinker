"""
CaseLinker - main code
Simple pipeline: ingest -> process -> analyze -> store -> visualize
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

src_path = Path(__file__).parent
sys.path.insert(0, str(src_path / "Ingestion Layer"))
sys.path.insert(0, str(src_path / "Processing Layer"))
sys.path.insert(0, str(src_path / "Storage Layer"))
sys.path.insert(0, str(src_path / "Clustering & Analysis Layer"))
sys.path.insert(0, str(src_path / "Visualization Layer"))

from processing import process_cases
import difflib
import os
import re

# Use PostgreSQL if DATABASE_URL is set, otherwise use SQLite
if os.getenv("DATABASE_URL"):
    try:
        from storage_postgres import CaseStorage
        print("✅ Using PostgreSQL database for storage")
    except ImportError:
        print("⚠️  PostgreSQL storage not available, falling back to SQLite")
        from storage import CaseStorage
else:
    from storage import CaseStorage
    print("✅ Using SQLite database for storage")


def main():
    print("CaseLinker - Starting up...")
    print("\n✓ All layers loaded successfully!")
    
    print("\n" + "="*60)
    print("CaseLinker Pipeline: Ingest → Process → Store → Output")
    print("="*60)
    print("\nEnter PDF file path(s) - separate multiple files with spaces")
    print("Or press Enter to use default test file")
    print("Default: 2014 Cases and Arrests – AZICAC.ORG.pdf")
    
    try:
        if len(sys.argv) > 1:
            # Multiple files provided as command line arguments
            file_paths = sys.argv[1:]
            print(f"\nUsing {len(file_paths)} provided file(s):")
            for fp in file_paths:
                print(f"  - {fp}")
        else:
            user_input = input("\nPDF file path(s): ").strip()
            
            if not user_input:
                file_paths = ["2014 Cases and Arrests – AZICAC.ORG.pdf"]
                print(f"Using default: {file_paths[0]}")
            else:
                # Split by spaces to handle multiple files
                file_paths = user_input.split()
                print(f"\nProcessing {len(file_paths)} file(s)...")
        
        print("\n" + "="*60)
        print("Step 1: Ingesting PDF(s)...")
        print("="*60)
        from ingestion import ingest_multiple_pdfs
        
        if len(file_paths) == 1:
            # Single file - route through ingestion helper so source_url fallback is applied.
            from ingestion import ingest_file
            df = ingest_file(file_paths[0], file_type='pdf')
            text = str(df.iloc[0].get('extracted_text', '') or '')
            source = str(df.iloc[0].get('source', 'unknown') or 'unknown')
            source_url = df.iloc[0].get('source_url')
            print(f"✓ Extracted {len(text):,} characters from {file_paths[0]}")
            print(f"✓ Detected source: {source}")
            if source_url:
                print(f"✓ Source URL: {source_url}")
        else:
            # Multiple files
            df = ingest_multiple_pdfs(file_paths)
            print(f"\n✓ Successfully ingested {len(df)} PDF file(s)")
        
        print("\n" + "="*60)
        print("Step 2: Processing cases (batch, extract features, merge ml and pattern approaches)...")
        print("="*60)
        cases = process_cases(df)
        print(f"✓ Found {len(cases)} cases across all PDFs")
        
        print("\n" + "="*60)
        print("Step 3: Storing cases in database...")
        print("="*60)
        db_path = get_database_path()
        stored_count = store_cases(cases, db_path)
        print(f"✓ Stored {stored_count}/{len(cases)} cases in database")
        
        print("\n" + "="*60)
        print("Step 4: Summary")
        print("="*60)
        all_stored_cases = get_all_stored_cases(db_path)
        print(f"✓ Total cases in database: {len(all_stored_cases)}")
        
        # Show breakdown by source
        sources = {}
        for case in all_stored_cases:
            source = case.get('source', 'Unknown')
            sources[source] = sources.get(source, 0) + 1
        
        print("\nCases by source:")
        for source, count in sorted(sources.items()):
            print(f"  - {source}: {count} cases")
        
        # Pre-compute clusters after storing cases
        print("\n" + "="*60)
        print("Step 5: Pre-computing clusters...")
        print("="*60)
        try:
            from analysis import run_automated_analysis
            cluster_data = run_automated_analysis(all_stored_cases)
            if db_path:
                storage = CaseStorage(db_path)  # SQLite
            else:
                storage = CaseStorage()  # PostgreSQL
            stored = storage.store_precomputed_clusters(cluster_data, len(all_stored_cases))
            if stored:
                print(f"✓ Pre-computed clusters stored ({len(all_stored_cases)} cases)")
            else:
                print(f"❌ Failed to store pre-computed clusters ({len(all_stored_cases)} cases)")
        except Exception as e:
            print(f"⚠️  Warning: Could not pre-compute clusters: {e}")
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()    



def get_database_path() -> Optional[str]:
    """
    Get database path from config or use default.
    Returns None if using PostgreSQL (DATABASE_URL set).
    
    Returns:
        Path to database file (SQLite) or None (PostgreSQL)
    """
    if os.getenv("DATABASE_URL"):
        return None  # PostgreSQL doesn't use file path
    try:
        from config import DATABASE_PATH
        return DATABASE_PATH
    except ImportError:
        return "caselinker.db"


def store_cases(cases: List[Dict[str, Any]], db_path: Optional[str]) -> int:
    """
    Store cases in the database.
    
    This abstracts storage operations to maintain layer boundaries.
    The main orchestration layer doesn't need to know about storage
    implementation details.
    
    Args:
        cases: List of case dictionaries to store
        db_path: Path to database file (SQLite) or None (PostgreSQL)
        
    Returns:
        Number of successfully stored cases
    """
    if db_path:
        storage = CaseStorage(db_path)  # SQLite
    else:
        storage = CaseStorage()  # PostgreSQL (uses DATABASE_URL)

    # Novelty filter (DOJ / NCMEC de-dupe before insert): off by default — uncomment to restore.
    cases_to_store = cases
    # cases_to_store = _filter_incoming_cases_by_novelty(cases, storage)

    stored_count = 0
    for case in cases_to_store:
        if storage.store_case(case):
            stored_count += 1
    return stored_count


def _normalize_text_for_exact_match(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def _get_case_text(case: Dict[str, Any]) -> str:
    t = case.get("case_text")
    if not t and isinstance(case.get("raw_data"), dict):
        t = case.get("raw_data", {}).get("case_text")
    return t if isinstance(t, str) else ""


def _ncmec_novelty_corpus_year(case: Dict[str, Any]) -> Optional[int]:
    """2022–2024 NCMEC media / state PDFs only; other years pass through without this filter."""
    if str(case.get("source", "")).upper() != "NCMEC":
        return None
    sf = ""
    if isinstance(case.get("raw_data"), dict):
        sf = str(case.get("raw_data", {}).get("source_file") or "")
    if not sf:
        sf = str(case.get("source_file") or "")
    for y in (2024, 2023, 2022):
        if str(y) in sf:
            return y
    cid = str(case.get("id") or "")
    m = re.search(r"_(202[234])_\d{3}", cid, re.I)
    if m:
        return int(m.group(1))
    return None


def _is_ncmec_novelty_target(case: Dict[str, Any]) -> bool:
    return _ncmec_novelty_corpus_year(case) is not None


def _norm_text_duplicate_ratio(
    norm_candidate: str, pool_norm_texts: List[str], threshold: float
) -> bool:
    """True if normalized candidate is >= ``threshold`` similar to any pooled normalized text (difflib)."""
    if not norm_candidate:
        return False
    ln = len(norm_candidate)
    for other in pool_norm_texts:
        if not other:
            continue
        lo = len(other)
        if min(ln, lo) / max(ln, lo, 1) < 0.97:
            continue
        sm = difflib.SequenceMatcher(None, norm_candidate, other)
        if sm.quick_ratio() < threshold:
            continue
        if sm.ratio() >= threshold:
            return True
    return False


def _filter_incoming_cases_by_novelty(
    incoming_cases: List[Dict[str, Any]],
    storage: "CaseStorage",
    *,
    doj_similarity_threshold: float = 0.98,
    ncmec_norm_ratio_threshold: float = 0.99,
) -> List[Dict[str, Any]]:
    """
    Ordered novelty gate before insert:

    - **DOJ CEOS / DOJ ARCHIVES**: skip empty text; skip if normalized ``case_text`` already seen (DB or earlier
      in this batch); skip if ``calculate_case_similarity`` vs any case in the pool (DB + kept so
      far) is >= ``doj_similarity_threshold``.

    - **NCMEC (2022–2024 only)**: skip empty normalized text; skip exact normalized duplicate; skip
      if difflib ratio on **normalized** text vs pool is >= ``ncmec_norm_ratio_threshold``.
      Does **not** use ``calculate_case_similarity`` (NCMEC prose is structurally similar).

    - **All other sources**: pass through, but each kept row is added to the pool so later DOJ/NCMEC
      rows can match against them.
    """
    if not incoming_cases:
        return incoming_cases

    try:
        from analysis import calculate_case_similarity
    except Exception:
        calculate_case_similarity = None

    DOJ_SOURCES = {"DOJ CEOS", "DOJ ARCHIVES"}

    pool: List[Dict[str, Any]] = list(storage.get_all_cases(include_raw_data=True))
    norm_seen: set[str] = set()
    pool_norm_texts: List[str] = []
    for ex in pool:
        nt = _normalize_text_for_exact_match(_get_case_text(ex))
        if nt:
            norm_seen.add(nt)
            pool_norm_texts.append(nt)

    out: List[Dict[str, Any]] = []
    dropped_doj_empty = dropped_doj_exact = dropped_doj_sim = 0
    dropped_ncmec_empty = dropped_ncmec_exact = dropped_ncmec_near = 0

    for c in incoming_cases:
        src_u = str(c.get("source", "")).upper()
        text = _get_case_text(c)
        ntext = _normalize_text_for_exact_match(text)

        if src_u in DOJ_SOURCES:
            if not ntext:
                dropped_doj_empty += 1
                continue
            if ntext in norm_seen:
                dropped_doj_exact += 1
                continue
            if calculate_case_similarity is not None:
                max_sim = 0.0
                for ex in pool:
                    try:
                        sim = float(calculate_case_similarity(c, ex))
                    except Exception:
                        sim = 0.0
                    max_sim = max(max_sim, sim)
                    if max_sim >= doj_similarity_threshold:
                        break
                if max_sim >= doj_similarity_threshold:
                    dropped_doj_sim += 1
                    continue
            out.append(c)
            norm_seen.add(ntext)
            pool_norm_texts.append(ntext)
            pool.append(c)
            continue

        if _is_ncmec_novelty_target(c):
            if not ntext:
                dropped_ncmec_empty += 1
                continue
            if ntext in norm_seen:
                dropped_ncmec_exact += 1
                continue
            if _norm_text_duplicate_ratio(ntext, pool_norm_texts, ncmec_norm_ratio_threshold):
                dropped_ncmec_near += 1
                continue
            out.append(c)
            norm_seen.add(ntext)
            pool_norm_texts.append(ntext)
            pool.append(c)
            continue

        out.append(c)
        if ntext:
            norm_seen.add(ntext)
            pool_norm_texts.append(ntext)
        pool.append(c)

    if dropped_doj_empty or dropped_doj_exact or dropped_doj_sim:
        n_doj = sum(
            1 for x in incoming_cases if str(x.get("source", "")).upper() in DOJ_SOURCES
        )
        kept_doj = sum(1 for x in out if str(x.get("source", "")).upper() in DOJ_SOURCES)
        print(
            f"✓ DOJ novelty filter: kept {kept_doj}/{n_doj} "
            f"(dropped empty={dropped_doj_empty}, exact={dropped_doj_exact}, "
            f"similar={dropped_doj_sim}, threshold={doj_similarity_threshold:.2f})"
        )
    if dropped_ncmec_empty or dropped_ncmec_exact or dropped_ncmec_near:
        n_nc = sum(1 for x in incoming_cases if _is_ncmec_novelty_target(x))
        kept_nc = sum(1 for x in out if _is_ncmec_novelty_target(x))
        print(
            f"✓ NCMEC (2022–2024) novelty filter: kept {kept_nc}/{n_nc} "
            f"(dropped empty={dropped_ncmec_empty}, exact={dropped_ncmec_exact}, "
            f"norm-difflib>={ncmec_norm_ratio_threshold:.2f}={dropped_ncmec_near})"
        )

    return out


def get_all_stored_cases(db_path: Optional[str]) -> List[Dict[str, Any]]:
    """
    Retrieve all cases from the database.
    
    Args:
        db_path: Path to database file (SQLite) or None (PostgreSQL)
        
    Returns:
        List of all case dictionaries
    """
    if db_path:
        storage = CaseStorage(db_path)  # SQLite
    else:
        storage = CaseStorage()  # PostgreSQL (uses DATABASE_URL)
    return storage.get_all_cases()



if __name__ == "__main__":
    main()
