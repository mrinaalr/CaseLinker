"""
Visualization Layer

Purpose: Present case data, clusters, and trends in an interactive, tasteful, and informative way.

Design Ideas from Architecture:
Most important part of project:
- Filtering: analyze all cases based on what interests you
- Clustering: visually grouping similar cases (or even filtered content like platforms)
- Interactive components (think HCI and data visualization class)
- Interactive dashboards
- Graphs (!!)
- Filtering
- Expandable case/data views
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime


def create_graph(cases: List[Dict[str, Any]], 
                relationships: List[Tuple[str, str, float]]) -> Dict[str, Any]:
    """
    Create graph visualization of case relationships.
    Interactive graph showing connections between cases.
    
    Args:
        cases: List of cases to visualize
        relationships: List of (case_id1, case_id2, similarity_score) tuples
        
    Returns:
        Graph data structure for visualization (nodes and edges)
    """
    nodes = []
    edges = []
    
    for case in cases:
        node = {
            'id': case.get('id'),
            'label': f"Case {case.get('id', 'Unknown')}",
            'source': case.get('source', 'unknown'),
            'platforms': case.get('platforms_used', []),
            'topics': case.get('case_topics', []),
            'date': case.get('date_range', {}).get('start'),
            'properties': {
                'victim_count': case.get('victim_count'),
                'perpetrator_count': case.get('perpetrator_count'),
            }
        }
        nodes.append(node)
    
    for source_id, target_id, weight in relationships:
        edge = {
            'source': source_id,
            'target': target_id,
            'weight': weight,
            'value': weight,
            'label': f"{weight:.2f}"
        }
        edges.append(edge)
    
    return {
        'nodes': nodes,
        'edges': edges,
        'metadata': {
            'node_count': len(nodes),
            'edge_count': len(edges),
            'avg_weight': sum(e['weight'] for e in edges) / len(edges) if edges else 0.0
        }
    }


def create_cluster_visualization(clusters: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Visualize case clusters.
    Visually grouping similar cases as specified in architecture.
    
    Args:
        clusters: List of clusters (each cluster is a list of cases)
        
    Returns:
        Visualization data for clusters
    """
    cluster_data = []
    
    for idx, cluster in enumerate(clusters):
        cluster_info = {
            'cluster_id': idx,
            'size': len(cluster),
            'cases': [case.get('id') for case in cluster],
            'common_platforms': [],
            'common_topics': [],
            'date_range': {},
            'sources': list(set(case.get('source', 'unknown') for case in cluster))
        }
        
        all_platforms = []
        for case in cluster:
            all_platforms.extend(case.get('platforms_used', []))
        platform_counts = Counter(all_platforms)
        cluster_info['common_platforms'] = [p for p, c in platform_counts.most_common(5)]
        
        all_topics = []
        for case in cluster:
            all_topics.extend(case.get('case_topics', []))
        topic_counts = Counter(all_topics)
        cluster_info['common_topics'] = [t for t, c in topic_counts.most_common(5)]
        
        dates = []
        for case in cluster:
            date_range = case.get('date_range', {})
            if isinstance(date_range, dict):
                date_start = date_range.get('start')
                if date_start:
                    dates.append(date_start)
        
        if dates:
            try:
                date_objs = [datetime.fromisoformat(d) if isinstance(d, str) else d for d in dates]
                cluster_info['date_range'] = {
                    'start': min(date_objs).isoformat(),
                    'end': max(date_objs).isoformat()
                }
            except:
                pass
        
        cluster_data.append(cluster_info)
    
    return {
        'clusters': cluster_data,
        'metadata': {
            'total_clusters': len(clusters),
            'total_cases': sum(len(c) for c in clusters),
            'avg_cluster_size': sum(len(c) for c in clusters) / len(clusters) if clusters else 0
        }
    }


def create_timeline_visualization(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create timeline visualization of cases over time.
    
    Args:
        cases: List of cases with date information
        
    Returns:
        Timeline data for visualization
    """
    timeline_events = []
    
    for case in cases:
        date_range = case.get('date_range', {})
        if isinstance(date_range, dict):
            date_start = date_range.get('start')
            date_end = date_range.get('end') or date_start
            
            if date_start:
                event = {
                    'case_id': case.get('id'),
                    'start': date_start,
                    'end': date_end,
                    'source': case.get('source', 'unknown'),
                    'platforms': case.get('platforms_used', []),
                    'topics': case.get('case_topics', []),
                    'label': f"Case {case.get('id', 'Unknown')}"
                }
                timeline_events.append(event)
    
    time_periods = defaultdict(list)
    for event in timeline_events:
        try:
            date_obj = datetime.fromisoformat(event['start']) if isinstance(event['start'], str) else event['start']
            year = date_obj.year
            time_periods[year].append(event)
        except:
            pass
    
    return {
        'events': timeline_events,
        'time_periods': dict(time_periods),
        'metadata': {
            'total_events': len(timeline_events),
            'date_range': {
                'start': min(e['start'] for e in timeline_events) if timeline_events else None,
                'end': max(e['end'] for e in timeline_events) if timeline_events else None
            }
        }
    }


def create_statistical_charts(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate statistical charts and visualizations.
    
    Args:
        cases: List of cases
        
    Returns:
        Dictionary with chart data (platform usage, technology trends, etc.)
    """
    charts = {}
    
    all_platforms = []
    for case in cases:
        all_platforms.extend(case.get('platforms_used', []))
    platform_counts = Counter(all_platforms)
    charts['platform_usage'] = {
        'labels': [p for p, c in platform_counts.most_common(10)],
        'values': [c for p, c in platform_counts.most_common(10)],
        'total': len(all_platforms)
    }
    
    all_technologies = []
    for case in cases:
        all_technologies.extend(case.get('technologies', []))
    tech_counts = Counter(all_technologies)
    charts['technology_usage'] = {
        'labels': [t for t, c in tech_counts.most_common(10)],
        'values': [c for t, c in tech_counts.most_common(10)],
        'total': len(all_technologies)
    }
    
    sources = [case.get('source', 'unknown') for case in cases]
    source_counts = Counter(sources)
    charts['source_distribution'] = {
        'labels': list(source_counts.keys()),
        'values': list(source_counts.values()),
        'total': len(cases)
    }
    
    all_topics = []
    for case in cases:
        all_topics.extend(case.get('case_topics', []))
    topic_counts = Counter(all_topics)
    charts['topic_distribution'] = {
        'labels': [t for t, c in topic_counts.most_common(10)],
        'values': [c for t, c in topic_counts.most_common(10)],
        'total': len(all_topics)
    }
    
    victim_counts = [case.get('victim_count') for case in cases if case.get('victim_count')]
    perp_counts = [case.get('perpetrator_count') for case in cases if case.get('perpetrator_count')]
    
    charts['victim_statistics'] = {
        'total_cases_with_victims': len(victim_counts),
        'total_victims': sum(victim_counts),
        'avg_victims_per_case': sum(victim_counts) / len(victim_counts) if victim_counts else 0
    }
    
    charts['perpetrator_statistics'] = {
        'total_cases_with_perpetrators': len(perp_counts),
        'total_perpetrators': sum(perp_counts),
        'avg_perpetrators_per_case': sum(perp_counts) / len(perp_counts) if perp_counts else 0
    }
    
    return charts


def create_geographic_visualization(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create geographic distribution visualization (anonymized).
    
    Args:
        cases: List of cases with region/location data
        
    Returns:
        Geographic visualization data
    """
    regions = defaultdict(int)
    
    for case in cases:
        victim_demo = case.get('victim_demographics', {})
        victim_region = victim_demo.get('region')
        if victim_region:
            regions[victim_region] += 1
        
        perp_demo = case.get('perpetrator_demographics', {})
        perp_region = perp_demo.get('region')
        if perp_region:
            regions[perp_region] += 1
    
    return {
        'regions': dict(regions),
        'metadata': {
            'total_regions': len(regions),
            'total_cases': len(cases)
        }
    }


def create_case_detail_view(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create expandable case detail view.
    Interactive component for viewing detailed case information.
    
    Args:
        case: Case dictionary
        
    Returns:
        Formatted case detail data for display
    """
    detail_view = {
        'id': case.get('id'),
        'source': case.get('source', 'unknown'),
        'date_range': case.get('date_range', {}),
        'summary': {
            'victim_count': case.get('victim_count'),
            'perpetrator_count': case.get('perpetrator_count'),
            'relationship': case.get('relationship_to_victim'),
        },
        'victim_demographics': case.get('victim_demographics', {}),
        'perpetrator_demographics': case.get('perpetrator_demographics', {}),
        'technology': {
            'platforms': case.get('platforms_used', []),
            'technologies': case.get('technologies', []),
            'communication_methods': case.get('communication_methods', []),
        },
        'investigation': {
            'methods_and_teams': case.get('investigation_methods_and_teams', []),
            'prosecution_outcome': case.get('prosecution_outcome', {}),
        },
        'classification': {
            'severity_indicators': case.get('severity_indicators', []),
            'case_topics': case.get('case_topics', []),
            'tags': case.get('tags', []),
        },
        'metadata': {
            'notes': case.get('notes'),
            'created_at': case.get('created_at'),
            'updated_at': case.get('updated_at'),
        },
        'raw_data': case.get('raw_data', {}),  # Expandable section
        'extracted_features': case.get('extracted_features', {}),  # Expandable section
    }
    
    return detail_view


def filter_cases(all_cases: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Filter cases based on criteria.
    Analyze all cases based on what interests you - core filtering functionality.
    
    Args:
        all_cases: List of all cases
        filters: Dictionary with filter criteria:
            - date_range: {start, end}
            - source: source name
            - platform: platform name(s)
            - topics: topic name(s)
            - region: region name
            - severity: severity indicators
            - victim_count: min/max victim count
            - perpetrator_count: min/max perpetrator count
            
    Returns:
        Filtered list of cases
    """
    filtered = all_cases.copy()
    
    if 'source' in filters:
        filtered = [c for c in filtered if c.get('source') == filters['source']]
    
    if 'date_range' in filters:
        filter_date = filters['date_range']
        date_filtered = []
        for case in filtered:
            case_date = case.get('date_range', {})
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
                                continue
                        if filter_end:
                            filter_end_dt = datetime.fromisoformat(filter_end) if isinstance(filter_end, str) else filter_end
                            if case_dt > filter_end_dt:
                                continue
                        date_filtered.append(case)
                    except:
                        pass
        filtered = date_filtered
    
    if 'platform' in filters or 'platforms' in filters:
        platforms_filter = filters.get('platforms', filters.get('platform', []))
        if not isinstance(platforms_filter, list):
            platforms_filter = [platforms_filter]
        platforms_set = set(platforms_filter)
        filtered = [c for c in filtered 
                   if set(c.get('platforms_used', [])) & platforms_set]
    
    if 'topic' in filters or 'topics' in filters:
        topics_filter = filters.get('topics', filters.get('topic', []))
        if not isinstance(topics_filter, list):
            topics_filter = [topics_filter]
        topics_set = set(topics_filter)
        filtered = [c for c in filtered 
                   if set(c.get('case_topics', [])) & topics_set]
    
    if 'region' in filters:
        region_filter = filters['region']
        region_filtered = []
        for case in filtered:
            victim_demo = case.get('victim_demographics', {})
            perp_demo = case.get('perpetrator_demographics', {})
            if (victim_demo.get('region') == region_filter or 
                perp_demo.get('region') == region_filter):
                region_filtered.append(case)
        filtered = region_filtered
    
    if 'severity' in filters:
        severity_filter = filters['severity']
        if not isinstance(severity_filter, list):
            severity_filter = [severity_filter]
        severity_set = set(severity_filter)
        filtered = [c for c in filtered 
                   if set(c.get('severity_indicators', [])) & severity_set]
    
    if 'victim_count' in filters:
        vc_filter = filters['victim_count']
        if isinstance(vc_filter, dict):
            min_vc = vc_filter.get('min')
            max_vc = vc_filter.get('max')
            filtered = [c for c in filtered 
                       if c.get('victim_count') is not None and
                       (min_vc is None or c.get('victim_count') >= min_vc) and
                       (max_vc is None or c.get('victim_count') <= max_vc)]
    
    if 'perpetrator_count' in filters:
        pc_filter = filters['perpetrator_count']
        if isinstance(pc_filter, dict):
            min_pc = pc_filter.get('min')
            max_pc = pc_filter.get('max')
            filtered = [c for c in filtered 
                       if c.get('perpetrator_count') is not None and
                       (min_pc is None or c.get('perpetrator_count') >= min_pc) and
                       (max_pc is None or c.get('perpetrator_count') <= max_pc)]
    
    return filtered


def create_dashboard(cases: List[Dict[str, Any]], 
                    clusters: Optional[List[List[Dict[str, Any]]]] = None, 
                    trends: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create interactive dashboard with multiple visualizations.
    Main dashboard combining all visualization components.
    
    Args:
        cases: List of cases
        clusters: Optional list of case clusters
        trends: Optional trend analysis data
        
    Returns:
        Dashboard data structure with all visualizations
    """
    dashboard = {
        'overview': {
            'total_cases': len(cases),
            'sources': list(set(c.get('source', 'unknown') for c in cases)),
            'date_range': get_date_range(cases),
        },
        'statistical_charts': create_statistical_charts(cases),
        'geographic_data': create_geographic_visualization(cases),
        'timeline': create_timeline_visualization(cases),
    }
    
    if clusters:
        dashboard['clusters'] = create_cluster_visualization(clusters)
    
    if trends:
        dashboard['trends'] = trends
    
    dashboard['graph'] = {
        'nodes': [{'id': c.get('id'), 'label': f"Case {c.get('id')}"} for c in cases],
        'edges': [],  # Would be populated from relationships
    }
    
    return dashboard


def get_date_range(cases: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """
    Get overall date range from cases.
    
    Args:
        cases: List of cases
        
    Returns:
        Date range dictionary or None
    """
    dates = []
    for case in cases:
        date_range = case.get('date_range', {})
        if isinstance(date_range, dict):
            date_start = date_range.get('start')
            if date_start:
                dates.append(date_start)
    
    if dates:
        try:
            date_objs = [datetime.fromisoformat(d) if isinstance(d, str) else d for d in dates]
            return {
                'start': min(date_objs).isoformat(),
                'end': max(date_objs).isoformat()
            }
        except:
            pass
    
    return None
