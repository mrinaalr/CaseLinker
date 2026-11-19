"""
Processing Layer
Extracts features, assigns comparison values, and fills case schema

This layer contains:
- Pattern Processing Layer: Regex and pattern-based extraction
- ML Processing Layer: ML/NLP enhancements (experimental)
"""

# Import from Pattern Processing Layer (handles spaces in directory name)
import importlib.util
import sys
from pathlib import Path

_pattern_layer_path = Path(__file__).parent / "Pattern Processing Layer" / "__init__.py"
if _pattern_layer_path.exists():
    # The layer's modules import their siblings by name (ai_extraction_patterns,
    # agency_label_normalize, ...), so both folders go on the path.
    for _dir in (Path(__file__).parent, _pattern_layer_path.parent):
        if str(_dir) not in sys.path:
            sys.path.append(str(_dir))
    # Load it as a package so its relative imports (.pattern_processing) resolve.
    spec = importlib.util.spec_from_file_location(
        "pattern_processing_layer",
        _pattern_layer_path,
        submodule_search_locations=[str(_pattern_layer_path.parent)],
    )
    pattern_module = importlib.util.module_from_spec(spec)
    sys.modules["pattern_processing_layer"] = pattern_module
    spec.loader.exec_module(pattern_module)
    
    # Import all exports
    case_batching = pattern_module.case_batching
    process_cases = pattern_module.process_cases
    extract_features = pattern_module.extract_features
    assign_comparison_values = pattern_module.assign_comparison_values
    extract_date_range = pattern_module.extract_date_range
    extract_victim_count = pattern_module.extract_victim_count
    extract_case_demographics = pattern_module.extract_case_demographics
    extract_perpetrator_demographics = pattern_module.extract_perpetrator_demographics
    extract_relationship = pattern_module.extract_relationship
    extract_previous_conviction = pattern_module.extract_previous_conviction
    extract_platforms = pattern_module.extract_platforms
    extract_evidence_volume = pattern_module.extract_evidence_volume
    extract_investigation_info = pattern_module.extract_investigation_info
    extract_prosecution_outcome = pattern_module.extract_prosecution_outcome
    extract_severity = pattern_module.extract_severity
    extract_topics = pattern_module.extract_topics
    extract_severity_phrases = pattern_module.extract_severity_phrases
    extract_perpetrator_admissions = pattern_module.extract_perpetrator_admissions
    perpetrator_admission_themes = pattern_module.perpetrator_admission_themes
    
    # Import MergeProcessing (intersection class)
    _merge_path = Path(__file__).parent / "merge_processing.py"
    _merge_spec = importlib.util.spec_from_file_location("merge_processing_module", _merge_path)
    merge_module = importlib.util.module_from_spec(_merge_spec)
    _merge_spec.loader.exec_module(merge_module)
    
    MergeProcessing = merge_module.MergeProcessing
    merge_processing = merge_module.merge_processing
else:
    raise ImportError("Pattern Processing Layer not found")


__all__ = [
    'case_batching',
    'process_cases',
    'extract_features',
    'assign_comparison_values',
    'extract_date_range',
    'extract_victim_count',
    'extract_case_demographics',
    'extract_perpetrator_demographics',
    'extract_relationship',
    'extract_previous_conviction',
    'extract_platforms',
    'extract_evidence_volume',
    'extract_investigation_info',
    'extract_prosecution_outcome',
    'extract_severity',
    'extract_topics',
    'extract_severity_phrases',
    'extract_perpetrator_admissions',
    'perpetrator_admission_themes',
    'MergeProcessing',
    'merge_processing',
]
