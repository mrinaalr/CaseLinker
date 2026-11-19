"""
Pattern Processing Layer

Purpose: Regex and pattern-based feature extraction from case text.
This is the core processing layer that extracts structured features
using regex patterns and rule-based matching.

This layer handles:
- Case batching (splitting cases by month patterns)
- Feature extraction (demographics, platforms, severity, etc.)
- Comparison value assignment for similarity calculation
"""

from .pattern_processing import (
    case_batching,
    process_cases,
    extract_features,
    assign_comparison_values,
    extract_date_range,
    extract_victim_count,
    extract_case_demographics,
    extract_perpetrator_demographics,
    extract_relationship,
    extract_previous_conviction,
    extract_platforms,
    extract_evidence_volume,
    extract_investigation_info,
    extract_prosecution_outcome,
    extract_severity,
    extract_topics,
    extract_severity_phrases,
    clean_urls_from_text,  # Backward compatibility (aliased to clean_artifacts_from_text)
    clean_artifacts_from_text,
)
from .perpetrator_admissions import (
    extract_perpetrator_admissions,
    perpetrator_admission_themes,
)

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
    'clean_urls_from_text',  # Backward compatibility
    'clean_artifacts_from_text',
]
