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


# Cap pairwise comparisons for metrics / candidate edges so 10k+ corpora finish in seconds.
_METRIC_PAIR_CAP = 4000
_CANDIDATE_CAP_PER_CASE = 96
# Skip ultra-generic tokens that would explode inverted-index blocks.
_BLOCK_STOP = frozenset({
    "online", "internet", "unknown", "other", "n/a", "na", "none", "unspecified",
})


def _as_str_set(value: Any) -> frozenset:
    if not value:
        return frozenset()
    if isinstance(value, (set, frozenset)):
        return frozenset(str(x).strip().lower() for x in value if x is not None and str(x).strip())
    if isinstance(value, (list, tuple)):
        return frozenset(str(x).strip().lower() for x in value if x is not None and str(x).strip())
    if isinstance(value, str) and value.strip():
        return frozenset([value.strip().lower()])
    return frozenset()


def _ensure_comparison_values(case: Dict[str, Any]) -> Dict[str, Any]:
    """Parse/normalize comparison_values in-place; synthesize from columns if missing."""
    comp = case.get("comparison_values")
    if isinstance(comp, str):
        try:
            comp = json.loads(comp)
        except Exception:
            comp = {}
    if not isinstance(comp, dict) or not comp:
        # Fall back to top-level columns so slim loads still cluster.
        inv_types = case.get("investigation_types")
        if isinstance(inv_types, list) and inv_types:
            inv_type = str(inv_types[0]).strip().lower()
        else:
            inv_type = (case.get("investigation_type") or "unknown")
            inv_type = str(inv_type).strip().lower() if inv_type else "unknown"
        agencies = case.get("agencies_involved") or []
        if isinstance(agencies, str):
            try:
                agencies = json.loads(agencies)
            except Exception:
                agencies = []
        rel = case.get("relationship_to_victim")
        pa = case.get("perpetrator_age")
        if isinstance(pa, int):
            pa_list = [pa]
        elif isinstance(pa, list):
            pa_list = pa
        else:
            pa_list = []
        comp = {
            "platform_vector": case.get("platforms_used") or [],
            "topic_vector": case.get("case_topics") or [],
            "severity_vector": case.get("severity_indicators") or [],
            "relationship_vector": [rel] if rel else [],
            "investigation_vector": {
                "type": inv_type,
                "agencies": agencies if isinstance(agencies, list) else [],
            },
            "demographic_vector": {
                "victim_count": case.get("victim_count"),
                "perpetrator_age": pa_list,
                "multiple_perpetrators": bool(case.get("perpetrator_count") and case.get("perpetrator_count", 0) > 1),
                "perpetrator_registered": bool(case.get("perpetrator_registered_sex_offender")),
                "case_age_range": None,
            },
        }
    case["comparison_values"] = comp
    return comp


def _feat_from_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Precompute frozensets / scalars used by similarity (one-time per case)."""
    comp = _ensure_comparison_values(case)
    demo = comp.get("demographic_vector") or {}
    if not isinstance(demo, dict):
        demo = {}
    inv = comp.get("investigation_vector") or {}
    if not isinstance(inv, dict):
        inv = {}
    pa = demo.get("perpetrator_age")
    if isinstance(pa, int):
        pa_list = [pa]
    elif isinstance(pa, list):
        pa_list = [x for x in pa if isinstance(x, (int, float))]
    else:
        pa_list = []
    age_range = demo.get("case_age_range")
    if not isinstance(age_range, dict):
        age_range = None
    platforms = _as_str_set(comp.get("platform_vector"))
    topics = _as_str_set(comp.get("topic_vector"))
    severity = _as_str_set(comp.get("severity_vector"))
    rel = _as_str_set(comp.get("relationship_vector"))
    agencies = _as_str_set(inv.get("agencies"))
    # Blocking tokens: prefer informative tags; drop stopwords that join everyone.
    block = frozenset(
        t for t in (platforms | topics | severity)
        if t and t not in _BLOCK_STOP and len(t) > 1
    )
    return {
        "id": case.get("id"),
        "case": case,
        "platforms": platforms,
        "topics": topics,
        "severity": severity,
        "rel": rel,
        "agencies": agencies,
        "inv_type": (str(inv.get("type")).strip().lower() if inv.get("type") else None),
        "age_range": age_range,
        "victim_count": demo.get("victim_count"),
        "pa_set": frozenset(pa_list),
        "pa_avg": (sum(pa_list) / len(pa_list)) if pa_list else None,
        "multi_perp": bool(demo.get("multiple_perpetrators")),
        "rso": bool(demo.get("perpetrator_registered")),
        "block": block,
    }


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def _feat_similarity(f1: Dict[str, Any], f2: Dict[str, Any]) -> float:
    """Same weighted formula as legacy calculate_case_similarity, on precomputed feats."""
    score = 0.0
    weight_sum = 0.0

    if f1["platforms"] or f2["platforms"]:
        score += _jaccard(f1["platforms"], f2["platforms"]) * 0.15
        weight_sum += 0.15

    demo_sim = 0.0
    demo_count = 0
    ar1, ar2 = f1["age_range"], f2["age_range"]
    if ar1 and ar2:
        overlap = min(ar1.get("max", 0), ar2.get("max", 0)) - max(ar1.get("min", 0), ar2.get("min", 0))
        r1 = ar1.get("max", 0) - ar1.get("min", 0)
        r2 = ar2.get("max", 0) - ar2.get("min", 0)
        if overlap > 0 and (r1 + r2) > 0:
            demo_sim += overlap / max(r1, r2)
            demo_count += 1
    vc1, vc2 = f1["victim_count"], f2["victim_count"]
    if vc1 is not None and vc2 is not None:
        try:
            vc1f, vc2f = float(vc1), float(vc2)
            if vc1f == vc2f:
                demo_sim += 1.0
            elif max(vc1f, vc2f) > 0:
                demo_sim += min(vc1f, vc2f) / max(vc1f, vc2f)
            demo_count += 1
        except (TypeError, ValueError):
            pass
    if f1["pa_set"] and f2["pa_set"]:
        if f1["pa_set"] == f2["pa_set"]:
            demo_sim += 1.0
        elif f1["pa_set"] & f2["pa_set"]:
            demo_sim += len(f1["pa_set"] & f2["pa_set"]) / len(f1["pa_set"] | f2["pa_set"])
        elif f1["pa_avg"] is not None and f2["pa_avg"] is not None:
            demo_sim += max(0.0, 1.0 - abs(f1["pa_avg"] - f2["pa_avg"]) / 20.0)
        if f1["multi_perp"] and f2["multi_perp"]:
            demo_sim += 0.2
            demo_count += 1
        demo_count += 1
    # Always count RSO agreement when both feats exist
    demo_sim += 1.0 if f1["rso"] == f2["rso"] else 0.0
    demo_count += 1
    if demo_count > 0:
        score += (demo_sim / demo_count) * 0.20
        weight_sum += 0.20

    if f1["rel"] or f2["rel"]:
        rel_sim = 1.0 if f1["rel"] == f2["rel"] else (0.5 if f1["rel"] & f2["rel"] else 0.0)
        score += rel_sim * 0.10
        weight_sum += 0.10

    inv_sim = 0.0
    inv_count = 0
    if f1["inv_type"] and f2["inv_type"]:
        inv_sim += 1.0 if f1["inv_type"] == f2["inv_type"] else 0.0
        inv_count += 1
    if f1["agencies"] or f2["agencies"]:
        inv_sim += _jaccard(f1["agencies"], f2["agencies"])
        inv_count += 1
    if inv_count > 0:
        score += (inv_sim / inv_count) * 0.15
        weight_sum += 0.15

    if f1["topics"] or f2["topics"]:
        score += _jaccard(f1["topics"], f2["topics"]) * 0.25
        weight_sum += 0.25
    if f1["severity"] or f2["severity"]:
        score += _jaccard(f1["severity"], f2["severity"]) * 0.15
        weight_sum += 0.15

    if weight_sum > 0:
        return score / weight_sum
    return 0.0


def calculate_case_similarity(case1: Dict[str, Any], case2: Dict[str, Any]) -> float:
    """
    Calculate similarity score between two cases using comparison values.
    Returns a score between 0.0 and 1.0.
    """
    return _feat_similarity(_feat_from_case(case1), _feat_from_case(case2))


class _UnionFind:
    __slots__ = ("parent", "rank")

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        p = self.parent
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            self.parent[ra] = rb
        elif self.rank[ra] > self.rank[rb]:
            self.parent[rb] = ra
        else:
            self.parent[rb] = ra
            self.rank[ra] += 1


def _sample_pair_indices(n: int, cap: int = _METRIC_PAIR_CAP) -> List[Tuple[int, int]]:
    """Deterministic pair sample: diagonal stripes, then stride fill. O(cap)."""
    if n < 2:
        return []
    total = n * (n - 1) // 2
    if total <= cap:
        return [(i, j) for i in range(n) for j in range(i + 1, n)]
    pairs: List[Tuple[int, int]] = []
    # Near-diagonal (local structure)
    for dist in range(1, n):
        for i in range(0, n - dist):
            pairs.append((i, i + dist))
            if len(pairs) >= cap:
                return pairs
    return pairs


def _metrics_from_feats(feats: List[Dict[str, Any]]) -> Dict[str, float]:
    n = len(feats)
    if n < 2:
        return {"average_similarity": 0.0, "min_similarity": 0.0, "max_similarity": 0.0}
    sims = [_feat_similarity(feats[i], feats[j]) for i, j in _sample_pair_indices(n)]
    if not sims:
        return {"average_similarity": 0.0, "min_similarity": 0.0, "max_similarity": 0.0}
    return {
        "average_similarity": round(sum(sims) / len(sims), 3),
        "min_similarity": round(min(sims), 3),
        "max_similarity": round(max(sims), 3),
    }


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

    Uses a deterministic capped pair sample (not full O(n²)) so large clusters
    stay interactive at corpus scale.
    """
    if len(group_cases) < 2:
        return {
            "average_similarity": 0.0,
            "min_similarity": 0.0,
            "max_similarity": 0.0,
        }
    feats = [_feat_from_case(c) for c in group_cases]
    return _metrics_from_feats(feats)


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
    Similarity clustering via blocked candidate edges + greedy clique packing.

    Replaces the legacy full O(n²) matrix while preserving the old *tight* moons
    the clusters.html satellites need (similar-to-all growth), instead of
    single-linkage Union-Find which collapsed 10k cases into 1–3 giant blobs.

    Fast path:
      1. Precompute feature frozensets once
      2. Inverted-index blocking on topics/platforms/severity (stopwords dropped)
      3. Cap candidates per case; keep edges with sim >= threshold
      4. Greedy clique packing on that sparse graph (deterministic seed order)

    Deterministic: cases sorted by id; seeds by (-degree, id).
    """
    if not all_cases:
        return []

    all_cases = sorted(all_cases, key=lambda c: c.get("id") or "")
    feats = [_feat_from_case(c) for c in all_cases if c.get("id")]
    n = len(feats)
    if n < 2:
        return []

    # Inverted index: token -> sorted indices
    index: Dict[str, List[int]] = defaultdict(list)
    for i, f in enumerate(feats):
        for tok in f["block"]:
            index[tok].append(i)

    # Sparse undirected adjacency for edges with sim >= threshold
    adj: List[set] = [set() for _ in range(n)]
    seen_pairs: set = set()
    for i, f in enumerate(feats):
        cand: set = set()
        for tok in f["block"]:
            bucket = index.get(tok)
            if not bucket:
                continue
            if len(bucket) > 2500:
                continue
            for j in bucket:
                if j > i:
                    cand.add(j)
                if len(cand) >= _CANDIDATE_CAP_PER_CASE:
                    break
            if len(cand) >= _CANDIDATE_CAP_PER_CASE:
                break
        if not cand and not f["block"]:
            for j in range(i + 1, min(n, i + 1 + _CANDIDATE_CAP_PER_CASE)):
                cand.add(j)
        for j in sorted(cand)[:_CANDIDATE_CAP_PER_CASE]:
            key = (i, j)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if _feat_similarity(feats[i], feats[j]) >= similarity_threshold:
                adj[i].add(j)
                adj[j].add(i)

    # Greedy cliques: seed by connectivity (desc), then id — same spirit as legacy
    used = [False] * n
    order = sorted(range(n), key=lambda i: (-len(adj[i]), feats[i]["id"] or ""))

    groups: List[Dict[str, Any]] = []
    for seed in order:
        if used[seed]:
            continue
        # Need at least one unused neighbor to form a moon
        if not any((not used[j]) for j in adj[seed]):
            continue

        clique = [seed]
        used[seed] = True
        # Candidates: neighbors of seed, sorted by id for determinism
        frontier = sorted(
            (j for j in adj[seed] if not used[j]),
            key=lambda j: feats[j]["id"] or "",
        )
        changed = True
        while changed:
            changed = False
            still: List[int] = []
            for j in frontier:
                if used[j]:
                    continue
                # Must be adjacent to every member (complete-linkage / old similar-to-all)
                if all(j in adj[m] for m in clique):
                    clique.append(j)
                    used[j] = True
                    changed = True
                else:
                    still.append(j)
            frontier = still

        if len(clique) < 2:
            # Seed had neighbors but none formed a pair under complete-linkage —
            # leave them unused for a later seed (or singleton).
            for idx in clique:
                used[idx] = False
            continue

        clique = sorted(clique)  # stable by feature index / id order
        group_cases = [feats[k]["case"] for k in clique]
        group_feats = [feats[k] for k in clique]
        metrics = _metrics_from_feats(group_feats)
        characteristics = analyze_group_characteristics(group_cases)
        groups.append({
            "group_id": f"case_cluster_{len(groups) + 1}",
            "cases": group_cases,
            "size": len(group_cases),
            "average_similarity": metrics["average_similarity"],
            "min_similarity": metrics["min_similarity"],
            "max_similarity": metrics["max_similarity"],
            "group_name": "Case Cluster",
            "description": characteristics.get(
                "description", f"Cluster of {len(group_cases)} similar cases"
            ),
            "statistics": characteristics.get("statistics", {}),
        })

    return sorted(groups, key=lambda g: (-g["size"], g["group_id"]))


# Satellite moons for /clusters: keep the page scannable (old full-matrix cliques
# produced tens of moons per hub; sparse packing made hundreds of size-2/3 moons).
_MAX_MOONS_PER_HUB = 42
_MIN_MOON_SIZE = 10


def _curate_internal_groups(
    internal_clusters: List[Dict[str, Any]],
    unclustered_cases: Optional[List[Dict[str, Any]]] = None,
    *,
    max_moons: int = _MAX_MOONS_PER_HUB,
    min_size: int = _MIN_MOON_SIZE,
) -> List[Dict[str, Any]]:
    """
    Keep the largest tight moons for the bubble chart; fold the rest into one overflow moon.

    Hub ``cases`` still holds every member — this only shapes ``internal_groups`` satellites.
    """
    moons: List[Dict[str, Any]] = []
    overflow: List[Dict[str, Any]] = []
    for cluster in internal_clusters or []:
        cases = list(cluster.get("cases") or [])
        if len(cases) >= min_size:
            moons.append({"cases": cases, "size": len(cases)})
        else:
            overflow.extend(cases)
    if unclustered_cases:
        overflow.extend(unclustered_cases)

    moons.sort(key=lambda m: (-m["size"], str((m["cases"][0] or {}).get("id", "") if m["cases"] else "")))
    if len(moons) > max_moons:
        moons = moons[:max_moons]

    # Do not emit a giant overflow satellite (reads as a second hub / kills layout).
    # Tiny cliques + unclustered remain on the main hub bubble for click-through.
    return moons


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
        
        # Curate moons for /clusters (cap + min size); overflow folded into one satellite
        internal_groups_list = _curate_internal_groups(internal_clusters, unclustered_cases)
        
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
        
        # Curate moons for /clusters (cap + min size); overflow folded into one satellite
        internal_groups_list = _curate_internal_groups(internal_clusters, unclustered_cases)
        
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
        
        # Curate moons for /clusters (cap + min size); overflow folded into one satellite
        internal_groups_list = _curate_internal_groups(internal_clusters, unclustered_cases)
        
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
        
        # Curate moons for /clusters (cap + min size); overflow folded into one satellite
        internal_groups_list = _curate_internal_groups(internal_clusters, unclustered_cases)
        
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
            'internal_groups': _curate_internal_groups(general_clusters, [
                c for c in all_cases if c.get('id') not in clustered_general_ids
            ])
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
