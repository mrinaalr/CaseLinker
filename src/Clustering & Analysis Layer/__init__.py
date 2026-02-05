"""
Clustering & Analysis Layer
Compare cases, detect clusters, identify trends, and select cases to display together
"""

from .analysis import (
    compare_cases,
    find_similar_cases,
    cluster_cases,
    trend_analysis,
    detect_links,
    entity_matching,
    pattern_based_linking,
    select_cases_for_display,
)

__all__ = [
    'compare_cases',
    'find_similar_cases',
    'cluster_cases',
    'trend_analysis',
    'detect_links',
    'entity_matching',
    'pattern_based_linking',
    'select_cases_for_display',
]
