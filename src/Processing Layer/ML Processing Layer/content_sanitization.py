"""
Content Sanitization Module

Purpose: Generate "clean case" representations that preserve analytical value
while removing harmful or explicit details. This enables safer viewing,
training, and stakeholder presentations.

Usage:
    from ml_models import MLModelManager
    from content_sanitization import ContentSanitizer
    
    ml_manager = MLModelManager(enable_ml=True)
    summarization_model = ml_manager.get_model('summarization')
    
    if summarization_model:
        sanitizer = ContentSanitizer(summarization_model)
        clean_case = sanitizer.sanitize_case(case_dict)
"""

import warnings
import re
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter


class ContentSanitizer:
    """
    Content sanitizer for generating clean case representations.
    
    Uses summarization and redaction to create analytical summaries
    that preserve patterns and facts while removing explicit details.
    """
    
    def __init__(self, summarization_model=None):
        """
        Initialize content sanitizer.
        
        Args:
            summarization_model: HuggingFace summarization pipeline. If None, uses rule-based fallback.
        """
        self.summarization_model = summarization_model
        self._harmful_patterns = self._load_harmful_patterns()
    
    def _load_harmful_patterns(self) -> List[Tuple[str, str]]:
        """
        Load patterns for identifying harmful content.
        
        Returns:
            List of (pattern, replacement) tuples
        """
        # Patterns that indicate explicit/harmful content
        # These are used to identify content that should be redacted
        patterns = [
            # Explicit descriptions (context-dependent, so we'll be careful)
            (r'\b(explicit|graphic|detailed description)\b', '[explicit content]'),
            
            # Very specific age mentions in harmful contexts
            # (We preserve age ranges but redact specific harmful contexts)
            (r'\b(infant|toddler|baby)\s+\d+\s+year', '[very young victim]'),
            
            # Explicit abuse descriptions (be careful - preserve severity indicators)
            # This is a delicate balance - we want to preserve analytical value
        ]
        
        return patterns
    
    def identify_harmful_spans(self, text: str) -> List[Tuple[int, int, str]]:
        """
        Identify spans of text that contain harmful content.
        
        Args:
            text: Case text to analyze
            
        Returns:
            List of (start, end, reason) tuples for harmful spans
        """
        harmful_spans = []
        
        # This is a simplified version - in production, you'd want more sophisticated
        # detection, possibly using a fine-tuned classifier
        
        # For now, we'll focus on summarization rather than redaction
        # Redaction can be added later based on evaluation
        
        return harmful_spans
    
    def generate_analytical_summary(
        self,
        text: str,
        max_length: int = 150,
        min_length: int = 50
    ) -> Optional[str]:
        """
        Generate analytical summary focusing on facts and patterns.
        
        Args:
            text: Case text to summarize
            max_length: Maximum summary length
            min_length: Minimum summary length
            
        Returns:
            Summary text or None if summarization unavailable
        """
        if not text or len(text.strip()) < 50:
            return None
        
        # Use ML model if available
        if self.summarization_model:
            try:
                # Truncate if too long (models have token limits)
                max_input_length = 1024
                if len(text) > max_input_length:
                    # Take first and last parts to preserve context
                    text = text[:max_input_length//2] + " ... " + text[-max_input_length//2:]
                
                summary = self.summarization_model(
                    text,
                    max_length=max_length,
                    min_length=min_length,
                    do_sample=False
                )
                
                if isinstance(summary, list) and len(summary) > 0:
                    return summary[0].get('summary_text', '')
                elif isinstance(summary, str):
                    return summary
                else:
                    return None
                    
            except Exception as e:
                warnings.warn(f"Error in ML summarization: {e}, falling back to extractive")
                return self._extractive_summary(text, max_length)
        else:
            # Fallback to extractive summarization
            return self._extractive_summary(text, max_length)
    
    def _extractive_summary(
        self,
        text: str,
        max_length: int = 150
    ) -> str:
        """
        Simple extractive summarization fallback.
        
        Extracts key sentences based on:
        - Sentence position (first/last sentences often important)
        - Keyword frequency (case-related terms)
        - Length (prefer medium-length sentences)
        
        Args:
            text: Case text
            max_length: Maximum summary length
            
        Returns:
            Summary text
        """
        # Split into sentences
        sentences = re.split(r'[.!?]+\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return text[:max_length] + "..." if len(text) > max_length else text
        
        # Key terms that indicate important information
        key_terms = [
            'arrested', 'charged', 'booked', 'investigation', 'case',
            'victim', 'perpetrator', 'platform', 'evidence', 'images',
            'videos', 'police', 'fbi', 'azicac', 'counts', 'jail'
        ]
        
        # Score sentences
        scored_sentences = []
        for i, sentence in enumerate(sentences):
            score = 0
            
            # Position bonus (first and last sentences)
            if i == 0:
                score += 3
            if i == len(sentences) - 1:
                score += 2
            
            # Keyword bonus
            sentence_lower = sentence.lower()
            for term in key_terms:
                if term in sentence_lower:
                    score += 1
            
            # Length bonus (prefer medium-length sentences)
            length = len(sentence.split())
            if 10 <= length <= 30:
                score += 1
            
            scored_sentences.append((score, sentence))
        
        # Sort by score and take top sentences
        scored_sentences.sort(key=lambda x: x[0], reverse=True)
        
        # Build summary
        summary_parts = []
        total_length = 0
        
        for score, sentence in scored_sentences:
            if total_length + len(sentence) <= max_length:
                summary_parts.append(sentence)
                total_length += len(sentence)
            else:
                break
        
        # If we didn't get enough, add first sentence
        if not summary_parts and sentences:
            summary_parts = [sentences[0]]
        
        summary = '. '.join(summary_parts)
        if summary and not summary.endswith('.'):
            summary += '.'
        
        return summary if summary else text[:max_length] + "..."
    
    def extract_key_facts(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract key analytical facts from case (structured data only).
        
        This preserves analytical value without harmful details.
        
        Args:
            case: Case dictionary
            
        Returns:
            Dictionary of key facts
        """
        key_facts = {
            'case_id': case.get('id'),
            'source': case.get('source'),
            'date_range': case.get('date_range'),
            'victim_count': case.get('victim_count'),
            'platforms_used': case.get('platforms_used', []),
            'severity_indicators': case.get('severity_indicators', []),
            'case_topics': case.get('case_topics', []),
            'investigation_type': case.get('investigation_type'),
            'agencies_involved': case.get('agencies_involved', []),
            'prosecution_outcome': {
                'booking_status': case.get('prosecution_outcome', {}).get('booking_status'),
                'charge_count': len(case.get('prosecution_outcome', {}).get('charges', []))
            },
            'evidence_summary': self._summarize_evidence(case.get('evidence_volume') or {})
        }
        
        # Add demographic ranges (not specific ages)
        victim_demo = case.get('case_demographics') or case.get('victim_demographics')
        if victim_demo:
            # Same rule as processing.victim_age_span: the stated span widened by any single ages.
            span = victim_demo.get('age_range') if isinstance(victim_demo.get('age_range'), dict) else {}
            values = [a for a in (victim_demo.get('ages') or []) if isinstance(a, int)]
            values += [span[k] for k in ('min', 'max') if isinstance(span.get(k), int)]
            if values:
                key_facts['victim_age_range'] = {'min': min(values), 'max': max(values)}
        
        return key_facts
    
    def _summarize_evidence(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize evidence volume without explicit details."""
        if not evidence:
            return {'has_images': False, 'has_videos': False, 'has_other': False}
        
        summary = {}
        
        if evidence.get('images'):
            summary['has_images'] = True
            summary['image_count'] = evidence['images']
        else:
            summary['has_images'] = False
        
        if evidence.get('videos'):
            summary['has_videos'] = True
            summary['video_count'] = evidence['videos']
        else:
            summary['has_videos'] = False
        
        if evidence.get('storage_size'):
            summary['storage_size'] = evidence['storage_size']
        
        return summary
    
    def sanitize_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate complete clean case representation.
        
        Args:
            case: Case dictionary with case_text
            
        Returns:
            Dictionary with clean case data:
            {
                'clean_text': str,              # Sanitized full text
                'analytical_summary': str,      # High-level summary
                'key_facts': Dict,              # Structured facts only
                'sanitization_metadata': Dict   # What was done
            }
        """
        case_text = (
            case.get('case_text', '') or
            case.get('raw_data', {}).get('case_text', '') or
            ''
        )
        
        # Identify harmful spans (for metadata)
        harmful_spans = self.identify_harmful_spans(case_text)
        
        # Generate analytical summary
        analytical_summary = self.generate_analytical_summary(case_text)
        
        # Extract key facts (structured)
        key_facts = self.extract_key_facts(case)
        
        # For now, clean_text is same as original (redaction can be added later)
        # In production, you'd redact harmful spans
        clean_text = case_text  # Placeholder - can add redaction logic
        
        return {
            'clean_text': clean_text,
            'analytical_summary': analytical_summary or "Summary unavailable",
            'key_facts': key_facts,
            'sanitization_metadata': {
                'harmful_spans_count': len(harmful_spans),
                'sanitization_method': 'summarization',
                'has_ml_summarization': self.summarization_model is not None,
                'preserved_analytical_value': True
            }
        }
    
    def enhance_case_with_clean_data(
        self,
        case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enhance case dictionary with clean case data.
        
        Args:
            case: Case dictionary
            
        Returns:
            Enhanced case with clean_case field
        """
        enhanced_case = case.copy()
        
        # Generate clean case
        clean_case = self.sanitize_case(case)
        
        # Add to case
        enhanced_case['clean_case'] = clean_case
        
        return enhanced_case
    
    def is_available(self) -> bool:
        """Check if content sanitization is available."""
        # Works with or without ML model (has fallback)
        return True
