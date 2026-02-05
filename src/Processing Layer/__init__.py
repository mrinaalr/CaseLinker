"""
Processing Layer
Extracts features, assigns comparison values, and fills case schema
"""

from .processing import (
    process_cases,
    extract_features,
    assign_comparison_values,
    extract_date_range,
    extract_victim_count,
    extract_victim_demographics,
    extract_perpetrator_count,
    extract_perpetrator_demographics,
    extract_relationship,
    extract_previous_conviction,
    extract_platforms,
    extract_technologies,
    extract_communication_methods,
    extract_investigation_methods,
    extract_prosecution_outcome,
    extract_severity,
    extract_topics,
)

__all__ = [
    'process_cases',
    'extract_features',
    'assign_comparison_values',
    'extract_date_range',
    'extract_victim_count',
    'extract_victim_demographics',
    'extract_perpetrator_count',
    'extract_perpetrator_demographics',
    'extract_relationship',
    'extract_previous_conviction',
    'extract_platforms',
    'extract_technologies',
    'extract_communication_methods',
    'extract_investigation_methods',
    'extract_prosecution_outcome',
    'extract_severity',
    'extract_topics',
]
