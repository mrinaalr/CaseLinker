"""
Clustering & Analysis Layer

Purpose: Compare cases, detect clusters, identify trends, and select cases to display together.

Design Ideas from Architecture:
- Case Comparison: Compare cases against each other, calculate similarity scores using assigned values,
  identify potential links and relationships, support multiple compare metrics
- Clustering: Group cases based on shared characteristics, multi-dimensional clustering 
  (by platform, method, victim, perpetrator, region, time, etc.)
- Link Detection: Entity matching (same perpetrators, victims, platforms across cases),
  Pattern-based linking (deeper patterns in cases)
- Trend Detection: Analyze evolution of exploitation methods over time, recurring case topics
- Case Selection: Select cases to display together based on clustering, filter and group cases 
  for visualization, support user-defined grouping criteria
"""

from typing import List, Dict, Any, Tuple, Optional, Set
import math
from collections import defaultdict, Counter
from datetime import datetime


def compare_cases(case1: Dict[str, Any], case2: Dict[str, Any], 
                 metrics: Optional[List[str]] = None) -> float:
    """
    Compare two cases and return similarity score.
    Supports multiple compare metrics as specified in architecture.
    
    Args:
        case1: First case dictionary
        case2: Second case dictionary
        metrics: Optional list of metrics to use ('platforms', 'methods', 'demographics', 'time', 'all')
        
    Returns:
        Similarity score (0.0 to 1.0)
    """
    if metrics is None:
        metrics = ['all']
    
    similarity_scores = []
    
    if 'all' in metrics or 'platforms' in metrics:
        platforms1 = set(case1.get('platforms_used', []))
        platforms2 = set(case2.get('platforms_used', []))
        if platforms1 or platforms2:
            platform_sim = len(platforms1 & platforms2) / len(platforms1 | platforms2) if (platforms1 | platforms2) else 0.0
            similarity_scores.append(platform_sim * 0.3)
    
    if 'all' in metrics or 'methods' in metrics:
        tech1 = set(case1.get('technologies', []))
        tech2 = set(case2.get('technologies', []))
        if tech1 or tech2:
            tech_sim = len(tech1 & tech2) / len(tech1 | tech2) if (tech1 | tech2) else 0.0
            similarity_scores.append(tech_sim * 0.2)
        
        comm1 = set(case1.get('communication_methods', []))
        comm2 = set(case2.get('communication_methods', []))
        if comm1 or comm2:
            comm_sim = len(comm1 & comm2) / len(comm1 | comm2) if (comm1 | comm2) else 0.0
            similarity_scores.append(comm_sim * 0.15)
    
    if 'all' in metrics or 'demographics' in metrics:
        victim1 = case1.get('victim_demographics', {})
        victim2 = case2.get('victim_demographics', {})
        if victim1 and victim2:
            demo_sim = 0.0
            if victim1.get('age_range') == victim2.get('age_range'):
                demo_sim += 0.5
            if victim1.get('region') == victim2.get('region'):
                demo_sim += 0.5
            similarity_scores.append(demo_sim * 0.15)
        
        perp1 = case1.get('perpetrator_demographics', {})
        perp2 = case2.get('perpetrator_demographics', {})
        if perp1 and perp2:
            perp_sim = 0.0
            if perp1.get('age_range') == perp2.get('age_range'):
                perp_sim += 0.3
            if perp1.get('region') == perp2.get('region'):
                perp_sim += 0.3
            if perp1.get('anonymized_id') == perp2.get('anonymized_id') and perp1.get('anonymized_id'):
                perp_sim += 0.4
            similarity_scores.append(perp_sim * 0.1)
    
    if 'all' in metrics or 'time' in metrics:
        date1 = case1.get('date_range', {})
        date2 = case2.get('date_range', {})
        if date1 and date2:
            time_sim = calculate_time_similarity(date1, date2)
            similarity_scores.append(time_sim * 0.1)
    
    return sum(similarity_scores) if similarity_scores else 0.0


def calculate_time_similarity(date1: Dict[str, Any], date2: Dict[str, Any]) -> float:
    """
    Calculate time-based similarity between two date ranges.
    
    Args:
        date1: First date range dictionary
        date2: Second date range dictionary
        
    Returns:
        Similarity score (0.0 to 1.0)
    """
    try:
        start1 = date1.get('start')
        start2 = date2.get('start')
        
        if start1 and start2:
            d1 = datetime.fromisoformat(start1) if isinstance(start1, str) else start1
            d2 = datetime.fromisoformat(start2) if isinstance(start2, str) else start2
            
            days_diff = abs((d1 - d2).days)
            
            if days_diff <= 365:
                return 1.0 - (days_diff / 365.0)
            else:
                return max(0.0, 1.0 - (days_diff / 1825.0))
    except:
        pass
    
    return 0.0


def find_similar_cases(target_case: Dict[str, Any], all_cases: List[Dict[str, Any]], 
                      threshold: float = 0.5, metrics: Optional[List[str]] = None) -> List[Tuple[Dict[str, Any], float]]:
    """
    Find cases similar to target case.
    Compare cases against each other in database as specified in architecture.
    
    Args:
        target_case: Case to compare against
        all_cases: List of all cases
        threshold: Minimum similarity score
        metrics: Optional list of metrics to use for comparison
        
    Returns:
        List of (case, similarity_score) tuples, sorted by similarity
    """
    similar_cases = []
    
    for case in all_cases:
        if case.get('id') == target_case.get('id'):
            continue  # Skip self
        
        similarity = compare_cases(target_case, case, metrics)
        if similarity >= threshold:
            similar_cases.append((case, similarity))
    
    similar_cases.sort(key=lambda x: x[1], reverse=True)
    
    return similar_cases


def cluster_cases(cases: List[Dict[str, Any]], threshold: float = 0.5,
                 dimension: Optional[str] = None) -> List[List[Dict[str, Any]]]:
    """
    Cluster cases based on similarity.
    Multi-dimensional clustering as specified in architecture:
    by platform, method, victim, perpetrator, region, time, etc.
    
    Args:
        cases: List of cases to cluster
        threshold: Similarity threshold for clustering
        dimension: Optional dimension to cluster by ('platform', 'method', 'region', 'time', None for all)
        
    Returns:
        List of clusters (each cluster is a list of cases)
    """
    if not cases:
        return []
    
    clusters = []
    assigned = set()
    
    for i, case1 in enumerate(cases):
        if i in assigned:
            continue
        
        cluster = [case1]
        assigned.add(i)
        
        for j, case2 in enumerate(cases[i+1:], start=i+1):
            if j in assigned:
                continue
            
            if dimension == 'platform':
                metrics = ['platforms']
            elif dimension == 'method':
                metrics = ['methods']
            elif dimension == 'region':
                metrics = ['demographics']
            elif dimension == 'time':
                metrics = ['time']
            else:
                metrics = None
            
            similarity = compare_cases(case1, case2, metrics)
            
            if similarity >= threshold:
                cluster.append(case2)
                assigned.add(j)
        
        if cluster:
            clusters.append(cluster)
    
    return clusters


def detect_links(cases: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """
    Detect links between cases using entity matching and pattern-based linking.
    
    Args:
        cases: List of cases to analyze
        
    Returns:
        List of (case_id1, case_id2, link_type) tuples
    """
    links = []
    
    entity_links = entity_matching(cases)
    links.extend(entity_links)
    
    pattern_links = pattern_based_linking(cases)
    links.extend(pattern_links)
    
    return links


def entity_matching(cases: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """
    Entity matching: same perpetrators, victims, platforms across cases.
    
    Args:
        cases: List of cases to analyze
        
    Returns:
        List of (case_id1, case_id2, link_type) tuples
    """
    links = []
    
    perp_map = defaultdict(list)
    for case in cases:
        perp_demo = case.get('perpetrator_demographics', {})
        perp_id = perp_demo.get('anonymized_id')
        if perp_id:
            perp_map[perp_id].append(case.get('id'))
    
    for perp_id, case_ids in perp_map.items():
        if len(case_ids) > 1:
            for i, cid1 in enumerate(case_ids):
                for cid2 in case_ids[i+1:]:
                    links.append((cid1, cid2, 'same_perpetrator'))
    
    platform_map = defaultdict(list)
    for case in cases:
        platforms = case.get('platforms_used', [])
        for platform in platforms:
            platform_map[platform].append(case.get('id'))
    
    for platform, case_ids in platform_map.items():
        if len(case_ids) > 1:
            for i, cid1 in enumerate(case_ids):
                for cid2 in case_ids[i+1:]:
                    links.append((cid1, cid2, 'same_platform'))
    
    return links


def pattern_based_linking(cases: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """
    Pattern-based linking: deeper patterns in cases.
    Identifies cases with similar patterns beyond simple entity matching.
    
    Args:
        cases: List of cases to analyze
        
    Returns:
        List of (case_id1, case_id2, link_type) tuples
    """
    links = []
    
    for i, case1 in enumerate(cases):
        for case2 in cases[i+1:]:
            inv1 = set(case1.get('investigation_methods_and_teams', []))
            inv2 = set(case2.get('investigation_methods_and_teams', []))
            if inv1 and inv2 and len(inv1 & inv2) >= 2:
                links.append((case1.get('id'), case2.get('id'), 'similar_investigation'))
            
            topics1 = set(case1.get('case_topics', []))
            topics2 = set(case2.get('case_topics', []))
            if topics1 and topics2 and len(topics1 & topics2) >= 2:
                links.append((case1.get('id'), case2.get('id'), 'similar_topics'))
    
    return links


def trend_analysis(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect trends in data set of cases over time.
    Analyze evolution of exploitation methods over time and recurring case topics.
    
    Args:
        cases: List of cases
        
    Returns:
        Dictionary with trend information
    """
    trends = {
        'platform_trends': {},
        'technology_trends': {},
        'method_evolution': {},
        'recurring_topics': [],
        'temporal_patterns': {}
    }
    
    time_periods = defaultdict(list)
    for case in cases:
        date_range = case.get('date_range', {})
        date_start = date_range.get('start') if isinstance(date_range, dict) else None
        if date_start:
            try:
                date_obj = datetime.fromisoformat(date_start) if isinstance(date_start, str) else date_start
                year = date_obj.year
                time_periods[year].append(case)
            except:
                pass
    
    for year, year_cases in sorted(time_periods.items()):
        platforms = []
        for case in year_cases:
            platforms.extend(case.get('platforms_used', []))
        platform_counts = Counter(platforms)
        trends['platform_trends'][year] = dict(platform_counts.most_common(5))
    
    for year, year_cases in sorted(time_periods.items()):
        technologies = []
        for case in year_cases:
            technologies.extend(case.get('technologies', []))
        tech_counts = Counter(technologies)
        trends['technology_trends'][year] = dict(tech_counts.most_common(5))
    
    all_topics = []
    for case in cases:
        all_topics.extend(case.get('case_topics', []))
    topic_counts = Counter(all_topics)
    trends['recurring_topics'] = [topic for topic, count in topic_counts.most_common(10)]
    
    return trends


def select_cases_for_display(cases: List[Dict[str, Any]], 
                             grouping_criteria: Optional[Dict[str, Any]] = None) -> List[List[Dict[str, Any]]]:
    """
    Select cases to display together based on clustering.
    Filter and group cases for visualization.
    Support user-defined grouping criteria.
    
    Args:
        cases: List of all cases
        grouping_criteria: Optional dictionary with grouping criteria:
            - 'by': 'cluster', 'platform', 'region', 'time', 'similarity'
            - 'threshold': similarity threshold (if by='similarity' or 'cluster')
            - 'filter': optional filter dictionary
            
    Returns:
        List of case groups (each group is a list of cases to display together)
    """
    if grouping_criteria is None:
        grouping_criteria = {'by': 'cluster', 'threshold': 0.5}
    
    filtered_cases = cases
    if 'filter' in grouping_criteria:
        filters = grouping_criteria['filter']
        filtered_cases = [c for c in cases if matches_filter(c, filters)]
    
    grouping_method = grouping_criteria.get('by', 'cluster')
    
    if grouping_method == 'cluster':
        threshold = grouping_criteria.get('threshold', 0.5)
        return cluster_cases(filtered_cases, threshold)
    
    elif grouping_method == 'platform':
        platform_groups = defaultdict(list)
        for case in filtered_cases:
            platforms = case.get('platforms_used', [])
            if platforms:
                for platform in platforms:
                    platform_groups[platform].append(case)
        return list(platform_groups.values())
    
    elif grouping_method == 'region':
        region_groups = defaultdict(list)
        for case in filtered_cases:
            victim_demo = case.get('victim_demographics', {})
            region = victim_demo.get('region')
            if region:
                region_groups[region].append(case)
        return list(region_groups.values())
    
    elif grouping_method == 'time':
        time_groups = defaultdict(list)
        for case in filtered_cases:
            date_range = case.get('date_range', {})
            date_start = date_range.get('start') if isinstance(date_range, dict) else None
            if date_start:
                try:
                    date_obj = datetime.fromisoformat(date_start) if isinstance(date_start, str) else date_start
                    year = date_obj.year
                    time_groups[year].append(case)
                except:
                    pass
        return list(time_groups.values())
    
    elif grouping_method == 'similarity':
        threshold = grouping_criteria.get('threshold', 0.5)
        return cluster_cases(filtered_cases, threshold)
    
    else:
        return [filtered_cases]


def matches_filter(case: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """
    Check if a case matches the filter criteria.
    
    Args:
        case: Case dictionary
        filters: Filter criteria dictionary
        
    Returns:
        True if case matches filters, False otherwise
    """
    if 'source' in filters and case.get('source') != filters['source']:
        return False
    
    if 'platforms' in filters:
        case_platforms = set(case.get('platforms_used', []))
        filter_platforms = set(filters['platforms'])
        if not (case_platforms & filter_platforms):
            return False
    
    if 'date_range' in filters:
        case_date = case.get('date_range', {})
        filter_date = filters['date_range']
        if isinstance(case_date, dict) and isinstance(filter_date, dict):
            case_start = case_date.get('start')
            filter_start = filter_date.get('start')
            filter_end = filter_date.get('end')
            if case_start:
                try:
                    case_dt = datetime.fromisoformat(case_start) if isinstance(case_start, str) else case_start
                    if filter_start:
                        filter_start_dt = datetime.fromisoformat(filter_start) if isinstance(filter_start, str) else filter_start
                        if case_dt < filter_start_dt:
                            return False
                    if filter_end:
                        filter_end_dt = datetime.fromisoformat(filter_end) if isinstance(filter_end, str) else filter_end
                        if case_dt > filter_end_dt:
                            return False
                except:
                    pass
    
    return True
