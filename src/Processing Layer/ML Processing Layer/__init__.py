"""
ML Processing Layer

Purpose: ML/NLP enhancements for case processing.
Provides semantic similarity, NER extraction, and content sanitization.

These components are designed to enhance (not replace) the existing
regex-based extraction in Pattern Processing Layer/pattern_processing.py.

Usage:
    from ml_models import MLModelManager
    from semantic_similarity import SemanticSimilarity
    from ner_extraction import NERExtractor
    from content_sanitization import ContentSanitizer
    
    # Initialize models
    ml_manager = MLModelManager(enable_ml=True)
    
    # Use components
    semantic = SemanticSimilarity(ml_manager.get_model('semantic'))
    ner = NERExtractor(ml_manager.get_model('ner'))
    sanitizer = ContentSanitizer(ml_manager.get_model('summarization'))
"""

from .ml_models import MLModelManager
from .semantic_similarity import SemanticSimilarity
from .ner_extraction import NERExtractor
from .content_sanitization import ContentSanitizer

__all__ = [
    'MLModelManager',
    'SemanticSimilarity',
    'NERExtractor',
    'ContentSanitizer',
]
