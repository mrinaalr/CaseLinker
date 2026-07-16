"""
Clustering & Analysis Layer

Simple tag-based case filtering and retrieval.
Automated analysis with case grouping, triage, and insights.
"""

from typing import List, Dict, Any, Tuple, Optional
import json
import re
from collections import Counter, defaultdict
from datetime import datetime


def match_custom_tag(case_text: str, tag: str) -> bool:
    """
    Check if a custom tag matches in case text.
    Uses word boundary matching for better accuracy.
    
    Args:
        case_text: The case text to search in
        tag: The custom tag to search for
        
    Returns:
        True if tag is found in text, False otherwise
    """
    if not case_text or not tag:
        return False
    
    # Normalize to lowercase
    case_text_lower = case_text.lower()
    tag_lower = tag.lower().strip()
    
    # Simple substring match (current behavior)
    # This allows partial matches like "girl" matching "girls" or "girlfriend"
    if tag_lower in case_text_lower:
        return True
    
    # Optional: Word boundary matching for exact word matches
    # Uncomment below for stricter matching (only matches whole words)
    # import re
    # pattern = re.compile(r'\b' + re.escape(tag_lower) + r'\b', re.IGNORECASE)
    # return bool(pattern.search(case_text))
    
    return False


def get_case_text(case: Dict[str, Any]) -> str:
    """
    Extract case text from a case dictionary.
    Handles different data structures.
    
    Args:
        case: Case dictionary
        
    Returns:
        Case text as string, empty string if not found
    """
    # Try raw_data.case_text first
    raw_data = case.get('raw_data', {})
    if isinstance(raw_data, dict):
        case_text = raw_data.get('case_text', '')
        if case_text:
            return case_text
    
    # Try case_text directly
    case_text = case.get('case_text', '')
    if case_text:
        return case_text
    
    return ''


def _case_matches_tag(case: Dict[str, Any], tag: str, category: str) -> bool:
    """
    Check if a case matches a single tag in a category.
    This is the core matching logic used by both return_tagged_cases and tag_threader.
    
    Args:
        case: Case dictionary
        tag: Tag to match
        category: Category of the tag (case_topics, severity_indicators, etc.)
        
    Returns:
        True if case matches the tag, False otherwise
    """
    if category == 'case_topics':
        topics = case.get('case_topics', [])
        # Special handling for "stranger": show all cases NOT family-tagged
        if tag == 'stranger':
            has_family = isinstance(topics, list) and 'family' in topics
            relationship = case.get('relationship_to_victim', '')
            family_relationships = ['father', 'mother', 'parent', 'brother', 'sister', 'sibling', 'uncle', 'aunt', 'cousin', 'teacher', 'coach']
            has_family_rel = relationship and any(fam in relationship.lower() for fam in family_relationships)
            return not has_family and not has_family_rel
        else:
            return isinstance(topics, list) and tag in topics
    
    elif category == 'severity_indicators':
        if tag == 'very_young':
            # Check for very_young or under_12 tags (both indicate very young)
            severity = case.get('severity_indicators', [])
            if isinstance(severity, str):
                try:
                    severity = json.loads(severity)
                except:
                    severity = []
            if not isinstance(severity, list):
                severity = []
            return isinstance(severity, list) and ('very_young' in severity or 'under_12' in severity)
        else:
            severity = case.get('severity_indicators', [])
            return isinstance(severity, list) and tag in severity
    
    elif category == 'platforms_used':
        platforms = case.get('platforms_used', [])
        return isinstance(platforms, list) and any(
            p and p.lower() == tag.lower() for p in platforms
        )
    
    elif category == 'investigation_type':
        types = case.get('investigation_types')
        if isinstance(types, list):
            inv_types = [str(t).strip().lower() for t in types if t is not None and str(t).strip()]
        else:
            inv_type = case.get('investigation_type', '')
            inv_types = [str(inv_type).strip().lower()] if inv_type else []
        return tag.lower() in inv_types
    
    elif category == 'relationship_to_victim':
        relationship = case.get('relationship_to_victim', '')
        # Special handling for "stranger": show all cases NOT family-tagged
        if tag == 'stranger':
            topics = case.get('case_topics', [])
            has_family = isinstance(topics, list) and 'family' in topics
            family_relationships = ['father', 'mother', 'parent', 'brother', 'sister', 'sibling', 'uncle', 'aunt', 'cousin', 'teacher', 'coach']
            has_family_rel = relationship and any(fam in relationship.lower() for fam in family_relationships)
            return not has_family and not has_family_rel
        else:
            return relationship and relationship.lower() == tag.lower()
    
    elif category == 'registered_sex_offender':
        return tag == 'registered_sex_offender' and case.get('perpetrator_registered_sex_offender') is True
    
    elif category == 'organizations':
        # Handle organization tags: ICAC, FBI, Police, Unique
        # Check both top-level and extracted_features (organizations may be in extracted_features)
        agencies = case.get('agencies_involved', [])
        organizations = case.get('organizations', [])
        
        # Always check extracted_features as organizations may not be merged to top level
        extracted_features = case.get('extracted_features', {})
        if isinstance(extracted_features, dict):
            # Get organizations from extracted_features (organizations is NOT merged to top level)
            extracted_orgs = extracted_features.get('organizations', [])
            if isinstance(extracted_orgs, list):
                # Combine with top-level organizations if any
                if isinstance(organizations, list):
                    organizations = list(set(organizations + extracted_orgs))  # Deduplicate
                else:
                    organizations = extracted_orgs
            # Get agencies_involved from extracted_features (fallback if not at top level)
            extracted_agencies = extracted_features.get('agencies_involved', [])
            if isinstance(extracted_agencies, list):
                if not agencies or (isinstance(agencies, list) and len(agencies) == 0):
                    agencies = extracted_agencies
                else:
                    # Combine both sources
                    if isinstance(agencies, list):
                        agencies = list(set(agencies + extracted_agencies))  # Deduplicate
        
        all_orgs = []
        
        # Combine agencies and organizations
        if isinstance(agencies, list):
            all_orgs.extend(agencies)
        if isinstance(organizations, list):
            all_orgs.extend(organizations)
        
        # Normalize all orgs to lowercase for comparison
        all_orgs_lower = [str(org).lower().strip() for org in all_orgs if org]
        case_text = get_case_text(case).lower()
        
        if tag == 'ICAC':
            # Match ICAC, AZICAC, Arizona Internet Crimes Against Children, etc.
            has_icac_org = any(
                'icac' in org_lower or 
                'internet crimes against children' in org_lower or
                'arizona internet crimes' in org_lower
                for org_lower in all_orgs_lower
            )
            has_icac_text = (
                'icac' in case_text or 
                'internet crimes against children' in case_text or
                'arizona internet crimes' in case_text
            )
            return has_icac_org or has_icac_text
        
        elif tag == 'FBI':
            # Match FBI, Federal Bureau of Investigation
            has_fbi_org = any(
                org_lower == 'fbi' or 
                'federal bureau of investigation' in org_lower
                for org_lower in all_orgs_lower
            )
            has_fbi_text = (
                'fbi' in case_text or 
                'federal bureau of investigation' in case_text
            )
            return has_fbi_org or has_fbi_text
        
        elif tag == 'NCMEC':
            # Match NCMEC, National Center for Missing and Exploited Children
            has_ncmec_org = any(
                org_lower == 'ncmec' or 
                'national center for missing and exploited children' in org_lower or
                ('national center for missing' in org_lower and 'exploited children' in org_lower)
                for org_lower in all_orgs_lower
            )
            has_ncmec_text = (
                'ncmec' in case_text or 
                'national center for missing and exploited children' in case_text or
                ('national center for missing' in case_text and 'exploited children' in case_text)
            )
            return has_ncmec_org or has_ncmec_text
        
        elif tag == 'Police':
            # Match any police department
            has_police_org = any(
                'police' in org_lower or 
                'sheriff' in org_lower
                for org_lower in all_orgs_lower
            )
            has_police_text = (
                re.search(r'\bpolice\b', case_text, re.IGNORECASE) is not None or
                re.search(r'\bsheriff', case_text, re.IGNORECASE) is not None
            )
            return has_police_org or has_police_text
        
        elif tag == 'Unique':
            # Cases where at least one organization appears only once across all cases
            # We need to count occurrences across all cases - this requires all_cases context
            # For now, we'll compute this on-demand when needed
            # Note: This is less efficient but works correctly
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                pass
            
            # Get all cases to count org occurrences
            # We'll need to pass all_cases to this function or compute it differently
            # For now, return False and handle it in return_tagged_cases
            return False  # Will be handled specially in return_tagged_cases
    
    elif category == 'custom':
        # Search in case text for custom topics using helper function
        case_text = get_case_text(case)
        return match_custom_tag(case_text, tag)
    
    return False


def return_tagged_cases(all_cases: List[Dict[str, Any]], selected_tags: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Query database and return all cases matching the selected tags.
    
    Args:
        all_cases: List of all cases from database
        selected_tags: List of dictionaries with 'tag' and 'category' keys
            Example: [{'tag': 'production', 'category': 'case_topics'}, {'tag': 'infant', 'category': 'severity_indicators'}]
        
    Returns:
        List of case dictionaries matching ALL selected tags (intersection)
    """
    if not selected_tags:
        return []
    
    # Pre-compute unique organizations if "Unique" tag is selected
    has_unique_tag = any(
        tag_info.get('tag') == 'Unique' and tag_info.get('category') == 'organizations' 
        for tag_info in selected_tags
    )
    
    unique_orgs = set()
    if has_unique_tag:
        # Count occurrences of each organization across all cases
        org_counts = {}
        for case in all_cases:
            agencies = case.get('agencies_involved', [])
            organizations = case.get('organizations', [])
            
            # Always check extracted_features as organizations may not be merged to top level
            extracted_features = case.get('extracted_features', {})
            if isinstance(extracted_features, dict):
                # Get organizations from extracted_features (organizations is NOT merged to top level)
                extracted_orgs = extracted_features.get('organizations', [])
                if isinstance(extracted_orgs, list):
                    if isinstance(organizations, list):
                        organizations = list(set(organizations + extracted_orgs))  # Deduplicate
                    else:
                        organizations = extracted_orgs
                # Get agencies_involved from extracted_features (fallback if not at top level)
                extracted_agencies = extracted_features.get('agencies_involved', [])
                if isinstance(extracted_agencies, list):
                    if not agencies or (isinstance(agencies, list) and len(agencies) == 0):
                        agencies = extracted_agencies
                    else:
                        if isinstance(agencies, list):
                            agencies = list(set(agencies + extracted_agencies))  # Deduplicate
            
            all_orgs = []
            if isinstance(agencies, list):
                all_orgs.extend(agencies)
            if isinstance(organizations, list):
                all_orgs.extend(organizations)
            
            # Track unique orgs per case to avoid double-counting
            seen_in_case = set()
            for org in all_orgs:
                if org and isinstance(org, str):
                    org_lower = org.strip().lower()
                    if org_lower and org_lower not in seen_in_case:
                        seen_in_case.add(org_lower)
                        org_counts[org_lower] = org_counts.get(org_lower, 0) + 1
        
        # Find organizations that appear only once
        unique_orgs = {org_lower for org_lower, count in org_counts.items() if count == 1}
    
    matching_cases = []
    for case in all_cases:
        # Case must match ALL selected tags (intersection logic)
        matches_all = True
        
        for tag_info in selected_tags:
            tag = tag_info['tag']
            category = tag_info['category']
            
            # Special handling for Unique organizations (requires all_cases context)
            if category == 'organizations' and tag == 'Unique':
                agencies = case.get('agencies_involved', [])
                organizations = case.get('organizations', [])
                
                # Always check extracted_features as organizations may not be merged to top level
                extracted_features = case.get('extracted_features', {})
                if isinstance(extracted_features, dict):
                    if not organizations or (isinstance(organizations, list) and len(organizations) == 0):
                        organizations = extracted_features.get('organizations', [])
                    if not agencies or (isinstance(agencies, list) and len(agencies) == 0):
                        agencies = extracted_features.get('agencies_involved', [])
                
                all_orgs = []
                if isinstance(agencies, list):
                    all_orgs.extend(agencies)
                if isinstance(organizations, list):
                    all_orgs.extend(organizations)
                
                # Check if case has at least one unique organization
                has_unique = any(
                    org and isinstance(org, str) and org.strip().lower() in unique_orgs
                    for org in all_orgs
                )
                if not has_unique:
                    matches_all = False
                    break
            else:
                if not _case_matches_tag(case, tag, category):
                    matches_all = False
                    break
        
        if matches_all:
            matching_cases.append(case)
    
    return matching_cases


def tag_threader(all_cases: List[Dict[str, Any]], selected_tags: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Query database for cases matching selected tags and create threaded tag links.
    
    Args:
        all_cases: List of all cases from database
        selected_tags: List of dictionaries with 'tag' and 'category' keys
        
    Returns:
        Dictionary with:
            - 'intersection_cases': List of case IDs matching ALL tags
            - 'tag_results': List of dictionaries with tag counts
    """
    if not selected_tags:
        return {
            'intersection_cases': [],
            'tag_results': []
        }
    
    # Find cases matching ALL selected tags (intersection) - reuse return_tagged_cases
    intersection_cases = return_tagged_cases(all_cases, selected_tags)
    
    # For each tag, find cases matching that specific tag
    tag_results = []
    for tag_info in selected_tags:
        tag = tag_info['tag']
        category = tag_info['category']
        
        matching_case_ids = []
        for case in all_cases:
            if _case_matches_tag(case, tag, category):
                matching_case_ids.append(case.get('id', ''))
        
        tag_results.append({
            'tag': tag,
            'category': category,
            'count': len(matching_case_ids),
            'cases': matching_case_ids
        })
    
    return {
        'intersection_cases': [c.get('id', '') for c in intersection_cases],
        'tag_results': tag_results
    }


def calculate_case_similarity(case1: Dict[str, Any], case2: Dict[str, Any]) -> float:
    """
    Calculate similarity score between two cases using comparison values.
    Returns a score between 0.0 and 1.0.
    """
    comp1 = case1.get('comparison_values', {})
    comp2 = case2.get('comparison_values', {})
    
    if not comp1 or not comp2:
        return 0.0
    
    similarity_score = 0.0
    weight_sum = 0.0
    
    # Platform similarity (weight: 0.15)
    platforms1 = comp1.get('platform_vector') or []
    platforms2 = comp2.get('platform_vector') or []
    platforms1 = set(platforms1) if isinstance(platforms1, (list, tuple, set)) else set()
    platforms2 = set(platforms2) if isinstance(platforms2, (list, tuple, set)) else set()
    if platforms1 or platforms2:
        platform_sim = len(platforms1 & platforms2) / max(len(platforms1 | platforms2), 1)
        similarity_score += platform_sim * 0.15
        weight_sum += 0.15
    
    # Demographic similarity (weight: 0.20)
    demo1 = comp1.get('demographic_vector', {})
    demo2 = comp2.get('demographic_vector', {})
    demo_sim = 0.0
    demo_count = 0
    
    # Victim age range similarity
    age_range1 = demo1.get('case_age_range')
    age_range2 = demo2.get('case_age_range')
    if age_range1 and age_range2:
        overlap = min(age_range1.get('max', 0), age_range2.get('max', 0)) - max(age_range1.get('min', 0), age_range2.get('min', 0))
        range1_size = age_range1.get('max', 0) - age_range1.get('min', 0)
        range2_size = age_range2.get('max', 0) - age_range2.get('min', 0)
        if overlap > 0 and (range1_size + range2_size) > 0:
            demo_sim += overlap / max(range1_size, range2_size)
            demo_count += 1
    
    # Victim count similarity
    vc1 = demo1.get('victim_count')
    vc2 = demo2.get('victim_count')
    if vc1 is not None and vc2 is not None:
        if vc1 == vc2:
            demo_sim += 1.0
        elif max(vc1, vc2) > 0:
            demo_sim += min(vc1, vc2) / max(vc1, vc2)
        demo_count += 1
    
    # Perpetrator age similarity (handles both single and multiple perpetrators)
    pa1 = demo1.get('perpetrator_age')
    pa2 = demo2.get('perpetrator_age')
    
    # Normalize to lists
    if isinstance(pa1, int):
        pa1 = [pa1]
    elif not isinstance(pa1, list):
        pa1 = []
    
    if isinstance(pa2, int):
        pa2 = [pa2]
    elif not isinstance(pa2, list):
        pa2 = []
    
    if pa1 and pa2:
        # Calculate similarity between perpetrator age lists
        # Method 1: Exact matches (same ages)
        set1 = set(pa1)
        set2 = set(pa2)
        if set1 == set2:
            demo_sim += 1.0  # Perfect match
        elif set1 & set2:
            # Some ages match - calculate overlap
            overlap = len(set1 & set2)
            total_unique = len(set1 | set2)
            demo_sim += overlap / total_unique
        else:
            # No exact matches - calculate average age difference
            avg_age1 = sum(pa1) / len(pa1)
            avg_age2 = sum(pa2) / len(pa2)
            age_diff = abs(avg_age1 - avg_age2)
            demo_sim += max(0, 1.0 - age_diff / 20.0)  # Normalize by 20 year difference
        
        # Bonus: Both have multiple perpetrators (gives more weight)
        mp1 = demo1.get('multiple_perpetrators', False)
        mp2 = demo2.get('multiple_perpetrators', False)
        if mp1 and mp2:
            demo_sim += 0.2  # Bonus for both having multiple perpetrators
            demo_count += 1  # Count this as an additional factor
        
        demo_count += 1
    
    # Registered sex offender match
    rso1 = demo1.get('perpetrator_registered', False)
    rso2 = demo2.get('perpetrator_registered', False)
    if rso1 == rso2:
        demo_sim += 1.0
        demo_count += 1
    
    if demo_count > 0:
        similarity_score += (demo_sim / demo_count) * 0.20
        weight_sum += 0.20
    
    # Relationship similarity (weight: 0.10)
    rel1 = comp1.get('relationship_vector') or []
    rel2 = comp2.get('relationship_vector') or []
    rel1 = set(rel1) if isinstance(rel1, (list, tuple, set)) else set()
    rel2 = set(rel2) if isinstance(rel2, (list, tuple, set)) else set()
    if rel1 or rel2:
        rel_sim = 1.0 if rel1 == rel2 else (0.5 if rel1 & rel2 else 0.0)
        similarity_score += rel_sim * 0.10
        weight_sum += 0.10
    
    # Investigation similarity (weight: 0.15)
    inv1 = comp1.get('investigation_vector', {})
    inv2 = comp2.get('investigation_vector', {})
    inv_sim = 0.0
    inv_count = 0
    
    if inv1.get('type') and inv2.get('type'):
        inv_sim += 1.0 if inv1['type'] == inv2['type'] else 0.0
        inv_count += 1
    
    agencies1 = inv1.get('agencies') or []
    agencies2 = inv2.get('agencies') or []
    agencies1 = set(agencies1) if isinstance(agencies1, (list, tuple, set)) else set()
    agencies2 = set(agencies2) if isinstance(agencies2, (list, tuple, set)) else set()
    if agencies1 or agencies2:
        agency_sim = len(agencies1 & agencies2) / max(len(agencies1 | agencies2), 1)
        inv_sim += agency_sim
        inv_count += 1
    
    if inv_count > 0:
        similarity_score += (inv_sim / inv_count) * 0.15
        weight_sum += 0.15
    
    # Topic similarity (weight: 0.25)
    topics1 = comp1.get('topic_vector') or []
    topics2 = comp2.get('topic_vector') or []
    topics1 = set(topics1) if isinstance(topics1, (list, tuple, set)) else set()
    topics2 = set(topics2) if isinstance(topics2, (list, tuple, set)) else set()
    if topics1 or topics2:
        topic_sim = len(topics1 & topics2) / max(len(topics1 | topics2), 1)
        similarity_score += topic_sim * 0.25
        weight_sum += 0.25
    
    # Severity similarity (weight: 0.15)
    severity1 = comp1.get('severity_vector') or []
    severity2 = comp2.get('severity_vector') or []
    severity1 = set(severity1) if isinstance(severity1, (list, tuple, set)) else set()
    severity2 = set(severity2) if isinstance(severity2, (list, tuple, set)) else set()
    if severity1 or severity2:
        severity_sim = len(severity1 & severity2) / max(len(severity1 | severity2), 1)
        similarity_score += severity_sim * 0.15
        weight_sum += 0.15
    
    # Normalize by weight sum
    if weight_sum > 0:
        return similarity_score / weight_sum
    return 0.0


def extract_keywords_semantic(case_text: str, top_n: int = 10) -> List[str]:
    """
    Extract keywords from case text using simple frequency-based approach.
    (Pattern-based keyword extraction - robust and auditable)
    """
    if not case_text:
        return []
    
    # Common stop words to filter
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'his', 'her', 'its', 'our', 'their', 'who', 'what', 'where', 'when', 'why', 'how', 'which', 'whom', 'whose'}
    
    # Extract words (3+ characters, alphanumeric)
    words = [w.lower() for w in case_text.split() if len(w) >= 3 and w.isalnum() and w.lower() not in stop_words]
    
    # Count frequencies
    word_counts = Counter(words)
    
    # Return top N keywords
    return [word for word, count in word_counts.most_common(top_n)]


def analyze_group_characteristics(group_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze common characteristics of a case group.
    Returns dictionary with group name, description, and statistics.
    """
    if not group_cases:
        return {}
    
    # Collect all features from cases in group
    all_platforms = []
    all_topics = []
    all_severity = []
    all_relationships = []
    rso_count = 0
    infant_count = 0
    very_young_count = 0
    hands_on_count = 0
    online_only_count = 0
    possession_count = 0
    production_count = 0
    
    for case in group_cases:
        # Parse JSON strings
        platforms = case.get('platforms_used', [])
        if isinstance(platforms, str):
            try:
                platforms = json.loads(platforms)
            except:
                platforms = []
        if isinstance(platforms, list):
            all_platforms.extend(platforms)
        
        topics = case.get('case_topics', [])
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except:
                topics = []
        if isinstance(topics, list):
            all_topics.extend(topics)
            if 'hands_on' in topics:
                hands_on_count += 1
            if 'online_only' in topics:
                online_only_count += 1
            if 'possession' in topics:
                possession_count += 1
            if 'production' in topics:
                production_count += 1
        
        severity = case.get('severity_indicators', [])
        if isinstance(severity, str):
            try:
                severity = json.loads(severity)
            except:
                severity = []
        if isinstance(severity, list):
            all_severity.extend(severity)
            if 'infant' in severity:
                infant_count += 1
            if 'very_young' in severity:
                very_young_count += 1
        
        relationship = case.get('relationship_to_victim')
        if relationship:
            all_relationships.append(relationship)
        
        if case.get('perpetrator_registered_sex_offender'):
            rso_count += 1
    
    # Calculate percentages
    total = len(group_cases)
    platform_counts = Counter(all_platforms)
    topic_counts = Counter(all_topics)
    severity_counts = Counter(all_severity)
    relationship_counts = Counter(all_relationships)
    
    # Determine group name based on dominant characteristics
    # Use stricter thresholds to ensure groups are actually about the named feature
    group_name = "Case Cluster"
    description_parts = []
    
    # Priority order: Most specific/important features first
    # Use majority (>= 50%) or minimum count (>= 2) for important features
    
    # Hands-on cluster (requires ALL cases)
    if hands_on_count == total:
        group_name = "Hands-On Abuse Cluster"
        description_parts.append(f"All {total} cases involve hands-on contact")
    # Infant cluster (requires majority OR at least 2 cases)
    elif infant_count >= max(2, total * 0.5):
        group_name = "High-Severity Infant Cluster"
        description_parts.append(f"{infant_count}/{total} cases ({infant_count/total*100:.0f}%) involve infant victims")
    # Very young victims (requires majority OR at least 2 cases)
    elif very_young_count >= max(2, total * 0.5):
        group_name = "Very Young Victims Cluster"
        description_parts.append(f"{very_young_count}/{total} cases ({very_young_count/total*100:.0f}%) involve very young victims")
    # Production cluster (requires majority)
    elif production_count >= max(2, total * 0.5):
        group_name = "Production Cluster"
        description_parts.append(f"{production_count}/{total} cases ({production_count/total*100:.0f}%) involve production")
    # Registered sex offender (requires majority OR at least 2 cases)
    elif rso_count >= max(2, total * 0.5):
        group_name = "Registered Sex Offender Cluster"
        description_parts.append(f"{rso_count}/{total} cases ({rso_count/total*100:.0f}%) involve registered sex offenders")
    # Online-only cluster (requires majority)
    elif online_only_count >= max(2, total * 0.5):
        group_name = "Online-Only Cluster"
        description_parts.append(f"{online_only_count}/{total} cases ({online_only_count/total*100:.0f}%) are online-only")
    # Possession cluster (requires majority)
    elif possession_count >= max(2, total * 0.5):
        group_name = "Possession Cluster"
        description_parts.append(f"{possession_count}/{total} cases ({possession_count/total*100:.0f}%) involve possession")
    
    # Add common characteristics
    if platform_counts:
        top_platform = platform_counts.most_common(1)[0]
        if top_platform[1] >= total * 0.3:
            description_parts.append(f"Most common platform: {top_platform[0]} ({top_platform[1]}/{total} cases)")
    
    if topic_counts:
        top_topic = topic_counts.most_common(1)[0]
        if top_topic[1] >= total * 0.3:
            description_parts.append(f"Most common topic: {top_topic[0].replace('_', ' ').title()} ({top_topic[1]}/{total} cases)")
    
    if severity_counts:
        top_severity = severity_counts.most_common(1)[0]
        if top_severity[1] >= total * 0.3:
            description_parts.append(f"Most common severity: {top_severity[0].replace('_', ' ').title()} ({top_severity[1]}/{total} cases)")
    
    return {
        'group_name': group_name,
        'description': ' | '.join(description_parts) if description_parts else f"Cluster of {total} similar cases",
        'statistics': {
            'total_cases': total,
            'hands_on': f"{hands_on_count}/{total} ({hands_on_count/total*100:.1f}%)",
            'online_only': f"{online_only_count}/{total} ({online_only_count/total*100:.1f}%)",
            'possession': f"{possession_count}/{total} ({possession_count/total*100:.1f}%)",
            'production': f"{production_count}/{total} ({production_count/total*100:.1f}%)",
            'infant_victims': f"{infant_count}/{total} ({infant_count/total*100:.1f}%)",
            'very_young_victims': f"{very_young_count}/{total} ({very_young_count/total*100:.1f}%)",
            'registered_sex_offenders': f"{rso_count}/{total} ({rso_count/total*100:.1f}%)",
            'top_platforms': dict(platform_counts.most_common(3)),
            'top_topics': dict(topic_counts.most_common(5)),
            'top_severity': dict(severity_counts.most_common(5)),
        }
    }


def find_physical_abuse_cases(all_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find cases that fit the Physical Abuse Cluster.
    
    Criteria: Cases must have BOTH:
    - physical_abuse in severity_indicators
    - hands_on in case_topics
    
    Args:
        all_cases: List of all case dictionaries
        
    Returns:
        List of cases matching Physical Abuse Cluster criteria
    """
    matching_cases = []
    
    for case in all_cases:
        # Parse JSON strings
        severity = case.get('severity_indicators', [])
        if isinstance(severity, str):
            try:
                severity = json.loads(severity)
            except:
                severity = []
        if not isinstance(severity, list):
            severity = []
        
        topics = case.get('case_topics', [])
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except:
                topics = []
        if not isinstance(topics, list):
            topics = []
        
        # Must have BOTH physical_abuse AND hands_on
        has_physical_abuse = 'physical_abuse' in severity
        has_hands_on = 'hands_on' in topics
        
        if has_physical_abuse and has_hands_on:
            matching_cases.append(case)
    
    return matching_cases


def find_online_only_cases(all_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find cases that fit the Online-Only Cluster.
    
    Criteria: Cases must have:
    - online_only in case_topics
    
    Args:
        all_cases: List of all case dictionaries
        
    Returns:
        List of cases matching Online-Only Cluster criteria
    """
    matching_cases = []
    
    for case in all_cases:
        topics = case.get('case_topics', [])
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except:
                topics = []
        if not isinstance(topics, list):
            topics = []
        
        if 'online_only' in topics:
            matching_cases.append(case)
    
    return matching_cases


def find_possession_cases(all_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find cases that fit the Possession Cluster.
    
    Criteria: Cases must have:
    - possession in case_topics
    
    Args:
        all_cases: List of all case dictionaries
        
    Returns:
        List of cases matching Possession Cluster criteria
    """
    matching_cases = []
    
    for case in all_cases:
        topics = case.get('case_topics', [])
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except:
                topics = []
        if not isinstance(topics, list):
            topics = []
        
        if 'possession' in topics:
            matching_cases.append(case)
    
    return matching_cases


def find_investigation_cases(all_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find cases that fit the Investigation Cluster.
    
    Criteria: Cases must have:
    - investigation_type set (proactive, reactive, online, undercover, or unknown)
    - Set when case text mentions "investigation" or "operation(s)" and patterns run (see extract_investigation_info).
    
    Args:
        all_cases: List of all case dictionaries
        
    Returns:
        List of cases matching Investigation Cluster criteria (cases with investigation_type)
    """
    matching_cases = []
    
    for case in all_cases:
        inv_type = case.get('investigation_type')
        
        # Only include cases that have investigation_type set
        if inv_type:  # Not None, not empty
            matching_cases.append(case)
    
    return matching_cases


def calculate_group_similarity_metrics(group_cases: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate similarity metrics for a group of cases.
    
    Computes average, minimum, and maximum pairwise similarities within the group.
    
    Args:
        group_cases: List of case dictionaries in the group
        
    Returns:
        Dictionary with 'average_similarity', 'min_similarity', 'max_similarity'
    """
    if len(group_cases) < 2:
        return {
            'average_similarity': 0.0,
            'min_similarity': 0.0,
            'max_similarity': 0.0
        }
    
    # Parse comparison_values if needed
    for case in group_cases:
        if isinstance(case.get('comparison_values'), str):
            try:
                case['comparison_values'] = json.loads(case['comparison_values'])
            except:
                case['comparison_values'] = {}
        elif not case.get('comparison_values'):
            extracted = case.get('extracted_features', {})
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except:
                    extracted = {}
            case['comparison_values'] = {}
    
    # Calculate all pairwise similarities
    similarities = []
    for i in range(len(group_cases)):
        for j in range(i+1, len(group_cases)):
            sim = calculate_case_similarity(group_cases[i], group_cases[j])
            similarities.append(sim)
    
    if not similarities:
        return {
            'average_similarity': 0.0,
            'min_similarity': 0.0,
            'max_similarity': 0.0
        }
    
    return {
        'average_similarity': round(sum(similarities) / len(similarities), 3),
        'min_similarity': round(min(similarities), 3),
        'max_similarity': round(max(similarities), 3)
    }


def find_severe_cases(all_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find cases that are considered "severe" based on severity indicators.
    
    Criteria: Cases with at least one of:
    - infant in severity_indicators
    - very_young in severity_indicators
    - sexual_abuse in severity_indicators
    - under_10 in severity_indicators
    
    Args:
        all_cases: List of case dictionaries
        
    Returns:
        List of severe cases
    """
    severe_cases = []
    
    for case in all_cases:
        severity = case.get('severity_indicators', [])
        if isinstance(severity, str):
            try:
                severity = json.loads(severity)
            except:
                severity = []
        if not isinstance(severity, list):
            severity = []
        
        # Check for severe indicators
        severe_indicators = ['infant', 'very_young', 'sexual_abuse', 'under_10', 'under_5', 'under_7', 'under_9']
        has_severe = any(indicator in severity for indicator in severe_indicators)
        
        if has_severe:
            severe_cases.append(case)
    
    return severe_cases


def find_similar_cases_general(all_cases: List[Dict[str, Any]], similarity_threshold: float = 0.45) -> List[Dict[str, Any]]:
    """
    Find cases for general Case Cluster using similarity-based clustering.
    This is used for cases that don't fit into the predefined cluster types.
    
    Uses similarity-based clustering to group remaining cases.
    
    Args:
        all_cases: List of case dictionaries (should be cases not in other clusters)
        similarity_threshold: Minimum similarity (0.0-1.0) for grouping. Default 0.45.
    
    Returns:
        List of case groups with similar cases
    """
    if not all_cases:
        return []
    
    # Ensure deterministic ordering by sorting cases by ID first
    # This ensures clusters are identical across different environments
    all_cases = sorted(all_cases, key=lambda c: c.get('id', ''))
    
    # Parse comparison_values if stored as JSON strings
    for case in all_cases:
        if isinstance(case.get('comparison_values'), str):
            try:
                case['comparison_values'] = json.loads(case['comparison_values'])
            except:
                case['comparison_values'] = {}
        elif not case.get('comparison_values'):
            extracted = case.get('extracted_features', {})
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except:
                    extracted = {}
            case['comparison_values'] = {}
    
    # Build similarity matrix
    similarity_matrix = {}
    case_ids = [c.get('id') for c in all_cases if c.get('id')]
    
    for i, case1 in enumerate(all_cases):
        case1_id = case1.get('id')
        if not case1_id:
            continue
        for j, case2 in enumerate(all_cases[i+1:], start=i+1):
            case2_id = case2.get('id')
            if not case2_id:
                continue
            sim = calculate_case_similarity(case1, case2)
            similarity_matrix[(case1_id, case2_id)] = sim
            similarity_matrix[(case2_id, case1_id)] = sim
    
    groups = []
    used_cases = set()
    
    # Sort by connectivity, then by case ID for deterministic ordering
    # This ensures clusters are identical across different environments
    case_connectivity = {}
    for case in all_cases:
        case_id = case.get('id')
        if not case_id:
            continue
        similar_count = sum(1 for other_id in case_ids 
                          if other_id != case_id and 
                          similarity_matrix.get((case_id, other_id), 0) >= similarity_threshold)
        case_connectivity[case_id] = similar_count
    
    # Sort by connectivity (descending), then by case ID (ascending) for deterministic ordering
    sorted_cases = sorted(all_cases, key=lambda c: (
        -case_connectivity.get(c.get('id'), 0),  # Negative for descending order
        c.get('id', '')  # Then by ID for deterministic tie-breaking
    ))
    
    for case1 in sorted_cases:
        case1_id = case1.get('id')
        if not case1_id or case1_id in used_cases:
            continue
        
        group = [case1]
        used_cases.add(case1_id)
        
        # Find cases similar to ALL cases in group
        # Sort all_cases by ID for deterministic ordering
        sorted_all_cases = sorted(all_cases, key=lambda c: c.get('id', ''))
        changed = True
        while changed:
            changed = False
            for case2 in sorted_all_cases:
                case2_id = case2.get('id')
                if not case2_id or case2_id in used_cases:
                    continue
                
                similar_to_all = True
                for group_case in group:
                    group_case_id = group_case.get('id')
                    sim = similarity_matrix.get((case2_id, group_case_id), 0)
                    if sim < similarity_threshold:
                        similar_to_all = False
                        break
                
                if similar_to_all:
                    group.append(case2)
                    used_cases.add(case2_id)
                    changed = True
        
        if len(group) > 1:
            # Calculate similarities
            similarities = []
            for k in range(len(group)):
                for l in range(k+1, len(group)):
                    case_k_id = group[k].get('id')
                    case_l_id = group[l].get('id')
                    sim = similarity_matrix.get((case_k_id, case_l_id), 0)
                    similarities.append(sim)
            
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
            min_similarity = min(similarities) if similarities else 0.0
            max_similarity = max(similarities) if similarities else 0.0
            
            characteristics = analyze_group_characteristics(group)
            
            groups.append({
                'group_id': f"case_cluster_{len(groups) + 1}",
                'cases': group,
                'size': len(group),
                'average_similarity': round(avg_similarity, 3),
                'min_similarity': round(min_similarity, 3),
                'max_similarity': round(max_similarity, 3),
                'group_name': 'Case Cluster',
                'description': characteristics.get('description', f"Cluster of {len(group)} similar cases"),
                'statistics': characteristics.get('statistics', {})
            })
    
    # Free O(n²) matrix before returning (peak allocation site)
    del similarity_matrix, case_connectivity
    return sorted(groups, key=lambda g: g['size'], reverse=True)


def group_similar_cases(all_cases: List[Dict[str, Any]], similarity_threshold: float = 0.45) -> List[Dict[str, Any]]:
    """
    Group cases into exactly 5 clusters by checking ALL cases against ALL cluster criteria.
    
    This is a targeted clustering approach that:
    1. Checks ALL cases against ALL 5 cluster criteria
    2. Cases can match MULTIPLE clusters if they meet multiple criteria
    3. Severe cases can ALSO be in Possession or Investigation clusters (not mutually exclusive)
    
    Cluster Types (exactly 5):
    1. Online-Only Cluster: Cases with online_only topic
    2. Possession Cluster: Cases with possession topic
    3. Investigation Cluster: Cases grouped by investigation_type (proactive, reactive, online, undercover, unknown)
    4. Severe Cluster: Cases with severe indicators (infant, very_young, sexual_abuse)
    5. General Cluster: All cases grouped by Jaccard similarity
    
    Args:
        all_cases: List of all case dictionaries
        similarity_threshold: Minimum similarity for General Cluster grouping. Default 0.45.
    
    Returns:
        List of exactly 5 case groups. Cases can appear in multiple groups.
    """
    if not all_cases:
        return []
    
    # Ensure deterministic ordering by sorting cases by ID first
    # This ensures clusters are identical across different environments (localhost vs production)
    all_cases = sorted(all_cases, key=lambda c: c.get('id', ''))
    
    groups = []
    
    # Step 1: Check ALL cases against ALL predefined cluster criteria
    # Cases can be in multiple clusters
    
    # 1a. Online-Only Cluster - Check ALL cases, then cluster internally
    online_only_cases = find_online_only_cases(all_cases)
    
    if len(online_only_cases) > 1:
        # Cluster the matching cases internally using Jaccard similarity
        internal_clusters = find_similar_cases_general(online_only_cases, similarity_threshold=similarity_threshold)
        
        # Combine all internal clusters into one group (cases organized by similarity)
        all_online_only_cases = []
        for cluster in internal_clusters:
            all_online_only_cases.extend(cluster['cases'])
        
        # Add any remaining unclustered cases
        clustered_ids = {c.get('id') for c in all_online_only_cases}
        unclustered_cases = []
        for case in online_only_cases:
            if case.get('id') not in clustered_ids:
                all_online_only_cases.append(case)
                unclustered_cases.append(case)
        
        # Build internal_groups list - include all clusters plus unclustered cases as a separate group
        internal_groups_list = [{'cases': cluster['cases'], 'size': len(cluster['cases'])} for cluster in internal_clusters]
        # Add unclustered cases as a separate internal group if any exist
        if unclustered_cases:
            internal_groups_list.append({'cases': unclustered_cases, 'size': len(unclustered_cases)})
        
        # Calculate cluster-level metrics (across all cases)
        similarity_metrics = calculate_group_similarity_metrics(all_online_only_cases)
        characteristics = analyze_group_characteristics(all_online_only_cases)
        
        base_description = f"All {len(all_online_only_cases)} cases are online-only"
        additional_info = []
        if characteristics.get('statistics', {}).get('top_platforms'):
            top_platform = list(characteristics['statistics']['top_platforms'].keys())[0]
            additional_info.append(f"Most common platform: {top_platform} ({len(all_online_only_cases)}/{len(all_online_only_cases)} cases)")
        if characteristics.get('statistics', {}).get('top_topics'):
            top_topic = list(characteristics['statistics']['top_topics'].keys())[0]
            additional_info.append(f"Most common topic: {top_topic.replace('_', ' ').title()} ({len(all_online_only_cases)}/{len(all_online_only_cases)} cases)")
        
        full_description = base_description
        if additional_info:
            full_description += " | " + " | ".join(additional_info)
        
        groups.append({
            'group_id': 'online_only_cluster',
            'cases': all_online_only_cases,
            'size': len(all_online_only_cases),
            'average_similarity': similarity_metrics['average_similarity'],
            'min_similarity': similarity_metrics['min_similarity'],
            'max_similarity': similarity_metrics['max_similarity'],
            'group_name': 'Online-Only Cluster',
            'description': full_description,
            'statistics': characteristics.get('statistics', {}),
            'internal_groups': internal_groups_list
        })
    
    # 1b. Possession Cluster - Check ALL cases, then cluster internally
    possession_cases = find_possession_cases(all_cases)
    
    if len(possession_cases) > 1:
        # Cluster the matching cases internally using Jaccard similarity
        internal_clusters = find_similar_cases_general(possession_cases, similarity_threshold=similarity_threshold)
        
        # Combine all internal clusters into one group (cases organized by similarity)
        all_possession_cases = []
        for cluster in internal_clusters:
            all_possession_cases.extend(cluster['cases'])
        
        # Add any remaining unclustered cases
        clustered_ids = {c.get('id') for c in all_possession_cases}
        unclustered_cases = []
        for case in possession_cases:
            if case.get('id') not in clustered_ids:
                all_possession_cases.append(case)
                unclustered_cases.append(case)
        
        # Build internal_groups list - include all clusters plus unclustered cases as a separate group
        internal_groups_list = [{'cases': cluster['cases'], 'size': len(cluster['cases'])} for cluster in internal_clusters]
        # Add unclustered cases as a separate internal group if any exist
        if unclustered_cases:
            internal_groups_list.append({'cases': unclustered_cases, 'size': len(unclustered_cases)})
        
        # Calculate cluster-level metrics (across all cases)
        similarity_metrics = calculate_group_similarity_metrics(all_possession_cases)
        characteristics = analyze_group_characteristics(all_possession_cases)
        
        base_description = f"All {len(all_possession_cases)} cases involve possession"
        additional_info = []
        if characteristics.get('statistics', {}).get('top_topics'):
            top_topic = list(characteristics['statistics']['top_topics'].keys())[0]
            additional_info.append(f"Most common topic: {top_topic.replace('_', ' ').title()} ({len(all_possession_cases)}/{len(all_possession_cases)} cases)")
        if characteristics.get('statistics', {}).get('top_severity'):
            top_severity = list(characteristics['statistics']['top_severity'].keys())[0]
            severity_count = characteristics['statistics']['top_severity'][top_severity]
            additional_info.append(f"Most common severity: {top_severity.replace('_', ' ').title()} ({severity_count}/{len(all_possession_cases)} cases)")
        
        full_description = base_description
        if additional_info:
            full_description += " | " + " | ".join(additional_info)
        
        groups.append({
            'group_id': 'possession_cluster',
            'cases': all_possession_cases,
            'size': len(all_possession_cases),
            'average_similarity': similarity_metrics['average_similarity'],
            'min_similarity': similarity_metrics['min_similarity'],
            'max_similarity': similarity_metrics['max_similarity'],
            'group_name': 'Possession Cluster',
            'description': full_description,
            'statistics': characteristics.get('statistics', {}),
            'internal_groups': internal_groups_list
        })
    
    # 1c. Investigation Cluster - Check ALL cases, then cluster internally by investigation type
    # Group cases that have investigation_type set
    investigation_cases = find_investigation_cases(all_cases)
    
    if len(investigation_cases) > 1:
        # Cluster the cases internally using Jaccard similarity
        internal_clusters = find_similar_cases_general(investigation_cases, similarity_threshold=similarity_threshold)
        
        # Combine all internal clusters into one group (cases organized by similarity)
        all_investigation_cases = []
        for cluster in internal_clusters:
            all_investigation_cases.extend(cluster['cases'])
        
        # Add any remaining unclustered cases
        clustered_ids = {c.get('id') for c in all_investigation_cases}
        unclustered_cases = []
        for case in investigation_cases:
            if case.get('id') not in clustered_ids:
                all_investigation_cases.append(case)
                unclustered_cases.append(case)
        
        # Build internal_groups list - include all clusters plus unclustered cases as a separate group
        internal_groups_list = [{'cases': cluster['cases'], 'size': len(cluster['cases'])} for cluster in internal_clusters]
        # Add unclustered cases as a separate internal group if any exist
        if unclustered_cases:
            internal_groups_list.append({'cases': unclustered_cases, 'size': len(unclustered_cases)})
        
        # Calculate cluster-level metrics (across all cases)
        similarity_metrics = calculate_group_similarity_metrics(all_investigation_cases)
        characteristics = analyze_group_characteristics(all_investigation_cases)
        
        # Count investigation types
        inv_type_counts = {}
        for case in all_investigation_cases:
            inv_type = case.get('investigation_type') or 'unknown'
            inv_type_counts[inv_type] = inv_type_counts.get(inv_type, 0) + 1
        
        inv_type_summary = ', '.join([f"{inv_type}: {count}" for inv_type, count in sorted(inv_type_counts.items())])
        
        groups.append({
            'group_id': 'investigation_cluster',
            'cases': all_investigation_cases,
            'size': len(all_investigation_cases),
            'average_similarity': similarity_metrics['average_similarity'],
            'min_similarity': similarity_metrics['min_similarity'],
            'max_similarity': similarity_metrics['max_similarity'],
            'group_name': 'Investigation Cluster',
            'description': f"All {len(all_investigation_cases)} cases involving investigation type ({inv_type_summary})",
            'statistics': characteristics.get('statistics', {}),
            'internal_groups': internal_groups_list
        })
    
    # 1d. Severe Cluster - Check ALL cases, then cluster internally
    severe_cases = find_severe_cases(all_cases)
    
    if len(severe_cases) > 1:
        # Cluster the matching cases internally using Jaccard similarity
        internal_clusters = find_similar_cases_general(severe_cases, similarity_threshold=similarity_threshold)
        
        # Combine all internal clusters into one group (cases organized by similarity)
        all_severe_cases = []
        for cluster in internal_clusters:
            all_severe_cases.extend(cluster['cases'])
        
        # Add any remaining unclustered cases
        clustered_ids = {c.get('id') for c in all_severe_cases}
        unclustered_cases = []
        for case in severe_cases:
            if case.get('id') not in clustered_ids:
                all_severe_cases.append(case)
                unclustered_cases.append(case)
        
        # Build internal_groups list - include all clusters plus unclustered cases as a separate group
        internal_groups_list = [{'cases': cluster['cases'], 'size': len(cluster['cases'])} for cluster in internal_clusters]
        # Add unclustered cases as a separate internal group if any exist
        if unclustered_cases:
            internal_groups_list.append({'cases': unclustered_cases, 'size': len(unclustered_cases)})
        
        # Calculate cluster-level metrics (across all cases)
        if len(all_severe_cases) == 1:
            similarity_metrics = {'average_similarity': 0.0, 'min_similarity': 0.0, 'max_similarity': 0.0}
        else:
            similarity_metrics = calculate_group_similarity_metrics(all_severe_cases)
        
        characteristics = analyze_group_characteristics(all_severe_cases)
        
        groups.append({
            'group_id': 'severe_cluster',
            'cases': all_severe_cases,
            'size': len(all_severe_cases),
            'average_similarity': similarity_metrics['average_similarity'],
            'min_similarity': similarity_metrics['min_similarity'],
            'max_similarity': similarity_metrics['max_similarity'],
            'group_name': 'Severe Cluster',
            'description': f"All {len(all_severe_cases)} cases involve severe indicators (infant, very_young, sexual_abuse)",
            'statistics': characteristics.get('statistics', {}),
            'internal_groups': internal_groups_list
        })
    
    # 1e. General Cluster - Check ALL cases using Jaccard similarity, then cluster internally
    general_clusters = find_similar_cases_general(all_cases, similarity_threshold=similarity_threshold)
    
    # Combine all general clusters into one group (cases organized by similarity)
    all_general_cases = []
    clustered_general_ids = set()
    for cluster in general_clusters:
        for case in cluster['cases']:
            all_general_cases.append(case)
            clustered_general_ids.add(case.get('id'))
    
    # Add any remaining unclustered cases (singletons that don't meet similarity threshold)
    for case in all_cases:
        if case.get('id') not in clustered_general_ids:
            all_general_cases.append(case)
    
    if len(all_general_cases) > 1:
        # Calculate cluster-level metrics (across all cases)
        similarity_metrics = calculate_group_similarity_metrics(all_general_cases)
        characteristics = analyze_group_characteristics(all_general_cases)
        
        groups.append({
            'group_id': 'general_cluster',
            'cases': all_general_cases,
            'size': len(all_general_cases),
            'average_similarity': similarity_metrics['average_similarity'],
            'min_similarity': similarity_metrics['min_similarity'],
            'max_similarity': similarity_metrics['max_similarity'],
            'group_name': 'General Cluster',
            'description': f"All {len(all_general_cases)} cases grouped by Jaccard similarity",
            'statistics': characteristics.get('statistics', {}),
            'internal_groups': [{'cases': cluster['cases'], 'size': len(cluster['cases'])} for cluster in general_clusters]
        })
    
    return sorted(groups, key=lambda g: g['size'], reverse=True)


# Normalized priority scores are on [5, 10]. Cases at or above this count as "high priority".
HIGH_PRIORITY_SCORE_THRESHOLD = 6.0


def triage_cases(all_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prioritize cases based on severity indicators, evidence volume, and urgency.
    Returns cases sorted by priority (highest first).
    """
    if not all_cases:
        return []
    
    def calculate_priority_score(case: Dict[str, Any]) -> float:
        score = 0.0
        
        # Severity indicators (weight: 0.35) - Increased to better reflect severity
        severity = case.get('severity_indicators') or []
        if isinstance(severity, str):
            try:
                severity = json.loads(severity)
            except:
                severity = []
        if not isinstance(severity, (list, tuple)):
            severity = []
        
        # Infant cases should be highest priority - but not so high that they override multi-victim cases
        has_infant = 'infant' in severity or any('infant' in str(s).lower() for s in severity)
        has_very_young = 'very_young' in severity
        
        severity_weights = {
            'infant': 15.0,  # High weight but not excessive
            'sexual_abuse': 18.0,  # Very high weight - sexual abuse is extremely severe
            'multiple_perpetrators': 15.0,  # High weight - multiple perpetrators indicates higher complexity, coordination, and severity
            'very_young': 10.0,  # Increased - very young is also critical
            'under_10': 7.0,  # Increased
            'under_5': 8.0,  # Keep for backward compatibility
            'under_9': 6.0,  # Keep for backward compatibility
            'under_7': 6.0,  # Keep for backward compatibility
        }
        
        # Calculate base severity score
        severity_base = 0.0
        for sev in severity:
            severity_base += severity_weights.get(sev, 3.0)
        
        # Bonus for multiple severity indicators (compound severity)
        if len(severity) >= 2:
            severity_base += 5.0  # Bonus for multiple indicators
        if len(severity) >= 3:
            severity_base += 3.0  # Additional bonus for 3+ indicators
        
        # Special boost for infant cases (but not excessive)
        if has_infant:
            severity_base += 8.0  # Reduced from 15.0 - still high but not excessive
        
        score += severity_base * 0.35  # Increased weight from 0.30
        
        # Evidence volume (weight: 0.10) - Reduced further
        evidence = case.get('evidence_volume') or {}
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except:
                evidence = {}
        if not isinstance(evidence, dict):
            evidence = {}
        
        if evidence:
            images = evidence.get('images') or 0
            videos = evidence.get('videos') or 0
            storage = evidence.get('storage_size') or ''
            
            # Normalize evidence score
            evidence_score = min(images / 100.0, 1.0) * 5.0 + min(videos / 10.0, 1.0) * 5.0
            if storage and ('TB' in storage or 'terabyte' in storage.lower()):
                evidence_score += 5.0
            elif storage and ('GB' in storage or 'gigabyte' in storage.lower()):
                evidence_score += 2.0
            
            score += evidence_score * 0.10  # Reduced from 0.15
        
        # Victim count (weight: 0.30) - Increased significantly - multiple victims is critical
        victim_count = case.get('victim_count')
        if victim_count:
            # Much more aggressive scoring for multiple victims
            if victim_count >= 10:
                score += 15.0 * 0.30  # Extremely high priority for 10+ victims
            elif victim_count >= 7:
                score += 12.0 * 0.30  # Very high priority for 7-9 victims
            elif victim_count >= 5:
                score += 10.0 * 0.30  # High priority for 5-6 victims (increased from 8.0)
            elif victim_count >= 3:
                score += 7.0 * 0.30  # Medium-high for 3-4 victims (increased from 6.0)
            elif victim_count >= 2:
                score += 4.0 * 0.30  # Medium for 2 victims
            else:
                score += 2.0 * 0.30  # Lower for single victim
        
        # Registered sex offender (weight: 0.10)
        if case.get('perpetrator_registered_sex_offender'):
            score += 4.0 * 0.10  # Increased from 3.0
        
        # Case type severity (weight: 0.25) - Increased - hands-on is critical
        case_topics = case.get('case_topics') or []
        if isinstance(case_topics, str):
            try:
                case_topics = json.loads(case_topics)
            except:
                case_topics = []
        if not isinstance(case_topics, list):
            case_topics = []
        
        case_type_score = 0.0
        # Allow multiple case types to compound
        if 'production' in case_topics:
            case_type_score += 10.0  # Increased from 8.0
        if 'hands_on' in case_topics:
            case_type_score += 8.0  # Increased from 6.0, and can stack with production
        if 'possession' in case_topics:
            case_type_score += 2.0  # Lower priority
        if 'online_only' in case_topics:
            case_type_score += 1.0  # Lowest priority
        
        score += case_type_score * 0.25  # Increased weight from 0.20
        
        # Severity phrases (weight: 0.15) - Non-traditional indicators of high severity
        severity_phrases = case.get('severity_phrases') or []
        if isinstance(severity_phrases, str):
            try:
                severity_phrases = json.loads(severity_phrases)
            except:
                severity_phrases = []
        if not isinstance(severity_phrases, (list, tuple)):
            severity_phrases = []
        
        # Weight different phrases based on severity indication
        phrase_weights = {
            'dangerous': 4.0,  # High - indicates dangerous behavior
            'out_of_control': 4.0,  # High - escalation indicator
            'attacked': 5.0,  # Very high - physical violence
            'continue': 3.0,  # Medium-high - ongoing abuse
            'attracted': 3.0,  # Medium-high - interest / predation language
            'stated': 2.0,  # Medium - victim disclosure
            'told': 2.0,  # Medium - victim disclosure
        }
        
        phrase_score = 0.0
        for phrase in severity_phrases:
            phrase_score += phrase_weights.get(phrase, 1.0)
        
        # Bonus for multiple phrases (compound severity)
        if len(severity_phrases) >= 2:
            phrase_score += 2.0  # Bonus for multiple indicators
        if len(severity_phrases) >= 3:
            phrase_score += 3.0  # Additional bonus for 3+ phrases
        
        score += phrase_score * 0.15  # Weight: 15% of total score
        
        return score
    
    # Calculate priority for each case
    cases_with_priority = []
    for case in all_cases:
        priority = calculate_priority_score(case)
        cases_with_priority.append({
            **case,
            'priority_score': priority
        })
    
    # Normalize scores to 5-10 scale
    if cases_with_priority:
        scores = [c['priority_score'] for c in cases_with_priority]
        min_score = min(scores)
        max_score = max(scores)
        
        # Scale to 5-10 range: min_score -> 5, max_score -> 10
        if max_score > min_score:  # Avoid division by zero
            for case in cases_with_priority:
                raw_score = case['priority_score']
                # Linear scaling: (score - min) / (max - min) maps to 0-1, then scale to 5-10
                normalized = 5.0 + (raw_score - min_score) * 5.0 / (max_score - min_score)
                case['priority_score'] = round(normalized, 2)
                case['priority_score_raw'] = raw_score  # Keep raw score for reference
        else:
            # All scores are the same, set all to 7.5 (middle of 5-10)
            for case in cases_with_priority:
                case['priority_score'] = 7.5
                case['priority_score_raw'] = case['priority_score']
    
    # Sort by priority (highest first)
    return sorted(cases_with_priority, key=lambda c: c['priority_score'], reverse=True)


def generate_automated_insights(all_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate automated insights about patterns, trends, and anomalies.
    """
    if not all_cases:
        return {'insights': [], 'patterns': [], 'trends': []}
    
    insights = []
    patterns = []
    trends = []
    
    # Parse JSON strings
    for case in all_cases:
        for key in ['platforms_used', 'severity_indicators', 'case_topics', 'agencies_involved']:
            if isinstance(case.get(key), str):
                try:
                    case[key] = json.loads(case[key])
                except:
                    case[key] = []
    
    # Insight 1: Most common platforms
    all_platforms = []
    platform_to_cases = defaultdict(list)
    for case in all_cases:
        platforms = case.get('platforms_used') or []
        if isinstance(platforms, list):
            all_platforms.extend(platforms)
            case_id = case.get('id', '')
            for platform in platforms:
                platform_to_cases[platform].append(case_id)
    
    if all_platforms:
        platform_counts = Counter(all_platforms)
        top_platform = platform_counts.most_common(1)[0]
        platform_name = top_platform[0]
        case_ids = platform_to_cases[platform_name]
        insights.append({
            'type': 'platform_analysis',
            'title': 'Most Common Platform',
            'description': f"'{platform_name}' appears in {top_platform[1]} cases ({top_platform[1]/len(all_cases)*100:.1f}% of all cases)",
            'severity': 'info',
            'cases': case_ids
        })
    
    # Insight 2: Severity distribution
    all_severity = []
    high_severity_cases = []
    high_severity_indicators = ['infant', 'very_young', 'under_5']
    for case in all_cases:
        severity = case.get('severity_indicators') or []
        if isinstance(severity, list):
            all_severity.extend(severity)
            # Check if case has high severity indicators
            has_high_severity = any(sev in severity for sev in high_severity_indicators)
            if has_high_severity:
                case_id = case.get('id', '')
                if case_id:
                    high_severity_cases.append(case_id)
    
    if all_severity:
        severity_counts = Counter(all_severity)
        high_sev_count = sum(severity_counts.get(sev, 0) for sev in high_severity_indicators)
        if high_sev_count > 0:
            insights.append({
                'type': 'severity_analysis',
                'title': 'High Severity Cases',
                'description': f"{high_sev_count} cases involve high-severity indicators (infant, very young)",
                'severity': 'warning',
                'cases': high_severity_cases
            })
    
    # Insight 3: Case topics distribution
    all_topics = []
    topic_to_cases = defaultdict(list)
    for case in all_cases:
        topics = case.get('case_topics') or []
        if isinstance(topics, list):
            all_topics.extend(topics)
            case_id = case.get('id', '')
            for topic in topics:
                topic_to_cases[topic].append(case_id)
    
    if all_topics:
        topic_counts = Counter(all_topics)
        top_topic = topic_counts.most_common(1)[0]
        topic_name = top_topic[0]
        case_ids = topic_to_cases[topic_name]
        insights.append({
            'type': 'topic_analysis',
            'title': 'Most Common Case Topic',
            'description': f"'{topic_name.replace('_', ' ').title()}' appears in {top_topic[1]} cases",
            'severity': 'info',
            'cases': case_ids
        })
    
    # Pattern: Registered sex offenders
    rso_count = sum(1 for case in all_cases if case.get('perpetrator_registered_sex_offender'))
    if rso_count > 0:
        patterns.append({
            'pattern': 'repeat_offenders',
            'description': f"{rso_count} cases ({rso_count/len(all_cases)*100:.1f}%) involve registered sex offenders",
            'count': rso_count
        })
    
    # Pattern: Family vs stranger relationship
    family_count = sum(1 for case in all_cases if 'family' in (case.get('case_topics') or []))
    stranger_count = len(all_cases) - family_count  # Total cases minus family cases
    if family_count > stranger_count:
        patterns.append({
            'pattern': 'relationship_pattern',
            'description': f"Family-related cases ({family_count}) outnumber stranger cases ({stranger_count})",
            'count': family_count
        })
    elif stranger_count > family_count:
        patterns.append({
            'pattern': 'relationship_pattern',
            'description': f"Stranger cases ({stranger_count}) outnumber family-related cases ({family_count})",
            'count': stranger_count
        })
    
    # Pattern: Investigation type distribution (exclude "unknown": keyword hit but no specific type)
    investigation_types = {}
    for case in all_cases:
        inv_type = case.get('investigation_type')
        if not inv_type or str(inv_type).lower() == 'unknown':
            continue
        key = str(inv_type).lower()
        investigation_types[key] = investigation_types.get(key, 0) + 1

    total_classified_inv = sum(investigation_types.values())
    if investigation_types and total_classified_inv > 0:
        most_common_inv = max(investigation_types.items(), key=lambda x: x[1])
        if most_common_inv[1] > total_classified_inv * 0.4:
            patterns.append({
                'pattern': 'investigation_focus',
                'description': (
                    f"{most_common_inv[1]} cases ({most_common_inv[1]/total_classified_inv*100:.1f}% of cases from known investigation types) "
                    f"involve '{most_common_inv[0]}' investigations, indicating a focus area"
                ),
                'count': most_common_inv[1]
            })
    
    # Trend: Temporal distribution
    dates = []
    for case in all_cases:
        date_start = case.get('date_start')
        if date_start:
            try:
                dates.append(datetime.fromisoformat(date_start.replace('Z', '+00:00')))
            except:
                pass
    
    if len(dates) > 1:
        dates.sort()
        date_range = (dates[-1] - dates[0]).days
        if date_range > 0:
            trends.append({
                'trend': 'temporal_span',
                'description': f"Cases span {date_range} days ({len(dates)} cases over {date_range/365:.1f} years)",
                'start_date': dates[0].isoformat(),
                'end_date': dates[-1].isoformat()
            })
    
    # Trend: Investigation type distribution (exclude "unknown")
    inv_types = []
    for case in all_cases:
        inv_type = case.get('investigation_type')
        if inv_type and str(inv_type).lower() != 'unknown':
            inv_types.append(str(inv_type).lower())

    if inv_types:
        inv_counts = Counter(inv_types)
        top_inv = inv_counts.most_common(1)[0]
        trends.append({
            'trend': 'investigation_type',
            'description': f"Most common investigation type: '{top_inv[0]}' ({top_inv[1]} cases)",
            'count': top_inv[1]
        })
    
    return {
        'insights': insights,
        'patterns': patterns,
        'trends': trends,
        'summary': {
            'total_cases': len(all_cases),
            'total_insights': len(insights),
            'total_patterns': len(patterns),
            'total_trends': len(trends)
        }
    }


def _slim_case_ref(case: Any) -> Optional[str]:
    """Collapse a case dict or id to a plain string id."""
    if isinstance(case, str) and case:
        return case
    if isinstance(case, dict):
        cid = case.get('id')
        return cid if isinstance(cid, str) and cid else None
    return None


def slim_case_groups_to_ids(case_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace nested case objects with id strings (keeps group metadata/stats)."""
    if not case_groups:
        return []
    result = []
    for group in case_groups:
        if not isinstance(group, dict):
            continue
        slim = {k: v for k, v in group.items() if k not in ('cases', 'internal_groups')}
        cases = group.get('cases') or []
        slim['cases'] = [cid for cid in (_slim_case_ref(c) for c in cases) if cid]
        internal = group.get('internal_groups') or []
        slim_internal = []
        for ig in internal:
            if not isinstance(ig, dict):
                continue
            ig_cases = ig.get('cases') or []
            slim_internal.append({
                'cases': [cid for cid in (_slim_case_ref(c) for c in ig_cases) if cid],
                'size': ig.get('size', 0),
            })
        slim['internal_groups'] = slim_internal
        result.append(slim)
    return result


def slim_triaged_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Drop heavy/raw fields from a triaged case; keep priority + display fields."""
    if not isinstance(case, dict):
        return {}
    drop = {'raw_data', 'case_text', 'extracted_features', 'comparison_values', 'notes'}
    return {k: v for k, v in case.items() if k not in drop}


def run_automated_analysis(all_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run complete automated analysis pipeline.
    Combines case grouping, triage, and insights generation.
    
    Args:
        all_cases: List of all cases from database
        
    Returns:
        Dictionary containing:
            - case_groups: List of similar case groups (case ids only)
            - triaged_cases: Cases sorted by priority (slim, no raw narratives)
            - insights: Automated insights and patterns
            - summary: Analysis summary statistics
    """
    import gc

    if not all_cases:
        return {
            'case_groups': [],
            'triaged_cases': [],
            'insights': {'insights': [], 'patterns': [], 'trends': []},
            'summary': {'total_cases': 0}
        }
    
    # 1. Group similar cases (using targeted clustering with predefined types)
    case_groups = group_similar_cases(all_cases, similarity_threshold=0.45)
    
    # 2. Triage cases by priority
    triaged_cases = triage_cases(all_cases)
    
    # 3. Generate insights
    insights = generate_automated_insights(all_cases)
    
    # 4. Extract keywords for semantic analysis (prefer case_text; fall back to raw_data)
    semantic_keywords = []
    for case in all_cases[:10]:  # Sample first 10 cases for keywords
        case_text = case.get('case_text') if isinstance(case.get('case_text'), str) else ''
        if not case_text:
            case_text = case.get('raw_data', {}).get('case_text', '') if isinstance(case.get('raw_data'), dict) else ''
        if not case_text and isinstance(case.get('raw_data'), str):
            try:
                raw_data = json.loads(case['raw_data'])
                case_text = raw_data.get('case_text', '')
            except Exception:
                pass
        
        if case_text:
            keywords = extract_keywords_semantic(case_text, top_n=5)
            semantic_keywords.extend(keywords)
    
    top_keywords = Counter(semantic_keywords).most_common(10)

    # Slim immediately so callers never hold full case-object graphs
    slim_groups = slim_case_groups_to_ids(case_groups)
    del case_groups
    slim_triaged = [slim_triaged_case(c) for c in triaged_cases[:20]]
    high_priority = len([
        c for c in triaged_cases
        if c.get('priority_score', 0) >= HIGH_PRIORITY_SCORE_THRESHOLD
    ])
    avg_priority = (
        sum(c.get('priority_score', 0) for c in triaged_cases) / len(triaged_cases)
        if triaged_cases else 0.0
    )
    del triaged_cases
    gc.collect()
    
    return {
        'case_groups': slim_groups,
        'triaged_cases': slim_triaged,
        'insights': insights,
        'semantic_keywords': [{'keyword': kw, 'frequency': freq} for kw, freq in top_keywords],
        'summary': {
            'total_cases': len(all_cases),
            'total_groups': len(slim_groups),
            'high_priority_cases': high_priority,
            'average_priority': avg_priority
        }
    }
