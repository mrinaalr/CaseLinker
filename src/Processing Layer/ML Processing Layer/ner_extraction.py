"""
Named Entity Recognition (NER) Module

Purpose: Extract named entities from case text using spaCy or Transformers NER.
Complements regex-based pattern processing by identifying entities that
may not match structured patterns.

Assumes cases are already batched (NCMEC, AZICAC cases are pre-batched).
Works with the same source and process as pattern processing.

Usage:
    from ner_extraction import NERExtractor
    
    # Option 1: Initialize with Transformers (Python 3.14 compatible)
    ner = NERExtractor(backend='transformers')
    
    # Option 2: Initialize with spaCy model (Python 3.11/3.12)
    import spacy
    nlp = spacy.load("en_core_web_sm")
    ner = NERExtractor(nlp_model=nlp)
    
    # Process batched cases (assumes cases are already batched)
    batched_cases = [...]  # List of case dicts with case_text, case_id, etc.
    enhanced_cases = ner.process_batched_cases_with_ner(batched_cases)
    
    # Or enhance individual case (after pattern processing)
    case_with_features = {...}  # Case with extracted features from pattern processing
    enhanced_case = ner.enhance_case_with_entities(case_with_features)
"""

import os
import warnings
from typing import Dict, List, Any, Optional, Set
import re
import traceback


# ──────────────────────────────────────────────────────────────────────────
# Age-classification context filter
# ──────────────────────────────────────────────────────────────────────────
# When NER (or our regex pass) sees a small integer near a person word, it
# is easy to mistake sentencing/legal numbers ("25 years in prison", "Count
# 2", "$500 fine") for a person age. These constants drive a context-window
# check (~12 words on either side of the number) that rejects any candidate
# age which sits inside sentencing language.

# Sentencing / legal-outcome vocabulary. Multi-word phrases work because we
# do a substring match against the joined window text.
_SENTENCING_KEYWORDS = (
    'sentenced', 'sentence', 'sentencing',
    'prison', 'imprisonment', 'imprisoned',
    'probation', 'parole', 'supervised release',
    'incarceration', 'incarcerated',
    'jail',
    'fine', 'fined', 'fines',
    'mandatory minimum', 'maximum sentence', 'maximum penalty', 'maximum of',
    'counts of', 'count of', 'count one', 'count two', 'count three',
    'counts', 'count',
    'charges', 'charge',
    'indictment', 'indicted',
    'restitution',
    'term of', 'years to life',
    'consecutive', 'concurrent',
    'plea agreement', 'pleaded guilty', 'pled guilty', 'plead guilty',
    'awaiting minimum', 'awaiting sentencing',
    'years in', 'months in',  # "25 years in prison", "6 months in jail"
    'mandatory life',
)

# Matches when the number is immediately preceded by an ordinal/counter
# context such as "Count 1", "charge 2", "indictment 3", "No. 4".
_COUNT_PREFIX_RE = re.compile(
    r'\b(?:count|counts|charge|charges|indictment|indictments|no\.?|number)'
    r'\s*$',
    re.IGNORECASE,
)

# Tokenizer for context-window word counting.
_WORD_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _is_sentencing_context(text: str,
                           num_start: int,
                           num_end: int,
                           window_words: int = 12) -> bool:
    """
    Return True if the number at ``text[num_start:num_end]`` is surrounded
    by sentencing / legal language and therefore should NOT be accepted as
    a person age.

    The check looks at roughly ``window_words`` tokens on each side of the
    number. Multi-word sentencing phrases (e.g. "years in", "mandatory
    minimum") are matched as substrings of the joined window text.

    It also rejects numbers preceded by counter context like "Count 2".
    """
    if num_start < 0 or num_end > len(text) or num_start >= num_end:
        return False
    left_raw  = text[max(0, num_start - 240):num_start]
    right_raw = text[num_end:min(len(text), num_end + 240)]

    left_words  = _WORD_TOKEN_RE.findall(left_raw)[-window_words:]
    right_words = _WORD_TOKEN_RE.findall(right_raw)[:window_words]
    window = (' '.join(left_words) + ' ' + ' '.join(right_words)).lower()

    for kw in _SENTENCING_KEYWORDS:
        if kw in window:
            return True
    if _COUNT_PREFIX_RE.search(left_raw):
        return True
    return False


class NERExtractor:
    """
    Named Entity Recognition extractor using spaCy or Transformers.
    
    Extracts entities like organizations, locations, dates, and ages
    that complement regex-based extraction from pattern processing.
    
    Note: Person names are excluded to avoid extracting reporter names.
    
    Designed to work with batched cases (assumes cases are already split).
    
    Supports multiple backends:
    - 'stanza': Uses Stanza (Stanford NLP) - extracts DATE, ORG, LOC, PER, MISC (Python 3.14 compatible, BEST for dates/ages)
    - 'transformers': Uses Hugging Face transformers - extracts ORG, LOC, PER, MISC (Python 3.14 compatible)
    - 'spacy': Uses spaCy - extracts DATE, ORG, LOC, PER, etc. (requires Python 3.11/3.12)
    """
    
    def __init__(self, nlp_model=None, backend='stanza'):
        """
        Initialize NER extractor.
        
        Args:
            nlp_model: spaCy NLP model instance (for spaCy backend). Ignored for other backends.
            backend: Backend to use ('stanza', 'transformers', or 'spacy'). Default: 'stanza' (best for dates/ages)
        """
        self.backend = backend
        self.nlp = nlp_model
        self.transformer_pipeline = None
        self.stanza_pipeline = None
        # Stanza diagnostics (filled only when backend == 'stanza')
        self._stanza_imported = False
        self._stanza_pipeline_loaded = False
        self._stanza_import_error: Optional[str] = None
        self._stanza_load_error: Optional[str] = None
        self._stanza_import_traceback: Optional[str] = None
        self._stanza_load_traceback: Optional[str] = None
        
        if backend == 'stanza':
            try:
                import stanza
                self._stanza_imported = True
            except ImportError as e:
                self._stanza_import_error = str(e)
                self._stanza_import_traceback = traceback.format_exc()
                warnings.warn(
                    "stanza library not installed. Install with: pip install stanza"
                )
                self.stanza_pipeline = None
            else:
                # Stanza extracts DATE entities (includes dates and sometimes ages)
                # Important: do NOT set download_method=None here; in ingest we want a
                # deterministic primary stanza backend even when models are missing.
                try:
                    self.stanza_pipeline = stanza.Pipeline(
                        'en',
                        processors='tokenize,ner',
                    )
                    self._stanza_pipeline_loaded = self.stanza_pipeline is not None
                except Exception as e:
                    self._stanza_load_error = str(e)
                    self._stanza_load_traceback = traceback.format_exc()
                    warnings.warn(f"Error loading stanza model: {e}")
                    self.stanza_pipeline = None
        elif backend == 'transformers':
            try:
                from transformers import pipeline
                # Use a fast, accurate NER model
                self.transformer_pipeline = pipeline(
                    "ner",
                    model="dslim/bert-base-NER",  # Fast, accurate NER model
                    aggregation_strategy="simple"
                )
            except ImportError:
                warnings.warn("transformers library not installed. Install with: pip install transformers torch")
                self.transformer_pipeline = None
            except Exception as e:
                warnings.warn(f"Error loading transformers model: {e}")
                self.transformer_pipeline = None
        elif backend == 'spacy':
            self.nlp = nlp_model
            if nlp_model is None:
                warnings.warn("No spaCy model provided. NER extraction will not work.")
        else:
            raise ValueError(f"Unknown backend: {backend}. Use 'stanza', 'transformers', or 'spacy'")

        self._stanza_batch_size = int(os.environ.get("STANZA_NER_BATCH_SIZE", "16"))
        # Bulk is the default. Set STANZA_NER_BATCH=0 to force serial.
        self._stanza_use_bulk = os.environ.get("STANZA_NER_BATCH", "1").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
    
    def process_batched_cases_with_ner(
        self,
        batched_cases: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process a list of batched cases with NER extraction.
        
        Assumes cases are already batched (split into individual cases).
        Each case should have at minimum:
        - 'case_text': The text content of the case
        - 'case_id': Unique identifier for the case
        
        This complements pattern processing - can be run before or after
        pattern-based feature extraction.
        
        Args:
            batched_cases: List of case dictionaries (already batched)
                Each case dict should have: case_text, case_id, and optionally
                month, year, source, etc.
                
        Returns:
            List of enhanced case dictionaries with NER entities added.
            Each case will have 'ml_features' -> 'ner_entities' added.
        """
        if not self._is_available():
            warnings.warn("No NER model available. Returning cases unchanged.")
            return batched_cases
        
        enhanced_cases = []
        
        for case in batched_cases:
            try:
                enhanced_case = self.enhance_case_with_entities(case)
                enhanced_cases.append(enhanced_case)
            except Exception as e:
                warnings.warn(f"Error processing case {case.get('case_id', 'unknown')}: {e}")
                # Return case unchanged if NER fails
                enhanced_cases.append(case)
        
        return enhanced_cases
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract named entities from text.
        
        Note: Person names are excluded as they often include reporter names
        which are not useful for case analysis.
        
        Args:
            text: Case text to extract entities from
            
        Returns:
            Dictionary with entity types as keys and lists of entities as values:
            {
                'organizations': [...],
                'locations': [...],
                'dates': [...],
                'ages': [...]
            }
        """
        if not self._is_available() or not text:
            return {
                'organizations': [],
                'locations': [],
                'dates': [],
                'ages': []
            }
        
        try:
            if self.backend == 'stanza':
                return self._extract_entities_stanza(text)
            elif self.backend == 'transformers':
                return self._extract_entities_transformers(text)
            elif self.backend == 'spacy':
                return self._extract_entities_spacy(text)
            else:
                return {
                    'organizations': [],
                    'locations': [],
                    'dates': [],
                    'ages': []
                }
        except Exception as e:
            warnings.warn(f"Error in NER extraction: {e}")
            return {
                'organizations': [],
                'locations': [],
                'dates': [],
                'ages': []
            }
    
    def _entities_from_stanza_doc(self, doc: Any, text: str) -> Dict[str, List[str]]:
        """Post-process one Stanza doc (shared by serial and bulk_process paths)."""
        entities = {
            'organizations': [],
            'locations': [],
            'dates': [],
            'ages': []
        }

        for ent in doc.ents:
            entity_text = ent.text.strip()
            entity_type = ent.type

            if entity_type == 'ORG':
                entities['organizations'].append(entity_text)
            elif entity_type in ['LOC', 'GPE']:
                entities['locations'].append(entity_text)
            elif entity_type == 'DATE':
                entity_lower = entity_text.lower()
                context = text[max(0, ent.start_char-30):min(len(text), ent.end_char+30)].lower()

                is_age = False
                if any(word in entity_lower for word in ['year', 'old', 'aged', 'age']):
                    is_age = True
                elif entity_text.isdigit():
                    age_num = int(entity_text)
                    if 1 <= age_num <= 100:
                        age_indicators = ['teacher', 'coach', 'man', 'woman', 'boy', 'girl', 'person', 'suspect',
                                        'defendant', 'perpetrator', 'victim', 'individual', 'adult', 'minor',
                                        'teenager', 'teen', 'child', 'kid', 'arrested', 'charged', 'convicted']
                        if any(indicator in context for indicator in age_indicators):
                            is_age = True

                if is_age:
                    try:
                        age_match = re.search(r'\d+', entity_text)
                        if age_match:
                            age = int(age_match.group())
                            if 1 <= age <= 100:
                                num_start = ent.start_char + age_match.start()
                                num_end   = ent.start_char + age_match.end()
                                if not _is_sentencing_context(text, num_start, num_end):
                                    entities['ages'].append(age)
                    except Exception:
                        pass
                else:
                    if entity_text.lower() in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                        if not re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}', context):
                            continue
                    entities['dates'].append(entity_text)

        ages = self._extract_ages_with_context(None, text)
        entities['ages'].extend(ages)

        for key in entities:
            if key == 'ages':
                entities[key] = sorted(list(set(entities[key])))
            else:
                entities[key] = list(dict.fromkeys(entities[key]))

        return entities

    def _extract_entities_stanza(self, text: str) -> Dict[str, List[str]]:
        """Extract entities using Stanza pipeline (extracts DATE, ORG, LOC, PER, etc.)."""
        if not self.stanza_pipeline:
            return {
                'organizations': [],
                'locations': [],
                'dates': [],
                'ages': []
            }
        doc = self.stanza_pipeline(text)
        return self._entities_from_stanza_doc(doc, text)

    def extract_entities_bulk(self, texts: List[str]) -> List[Dict[str, List[str]]]:
        """
        Same output as ``[extract_entities(t) for t in texts]``.
        Uses Stanza ``bulk_process`` when ``STANZA_NER_BATCH=1``; otherwise serial.
        """
        if not texts:
            return []
        if not (
            self._stanza_use_bulk
            and self.backend == 'stanza'
            and self.stanza_pipeline
        ):
            return [self.extract_entities(t) for t in texts]

        out: List[Dict[str, List[str]]] = []
        for start in range(0, len(texts), self._stanza_batch_size):
            chunk = texts[start : start + self._stanza_batch_size]
            docs = self.stanza_pipeline.bulk_process(chunk)
            if len(docs) != len(chunk):
                raise RuntimeError(
                    f"Stanza bulk_process returned {len(docs)} docs for {len(chunk)} texts"
                )
            for text, doc in zip(chunk, docs):
                out.append(self._entities_from_stanza_doc(doc, text))
        return out
    
    def _extract_entities_transformers(self, text: str) -> Dict[str, List[str]]:
        """Extract entities using Transformers pipeline."""
        entities = {
            'organizations': [],
            'locations': [],
            'dates': [],
            'ages': []
        }
        
        if not self.transformer_pipeline:
            return entities
        
        # Transformers NER labels: ORG, LOC, PER, MISC, etc.
        # Map to our schema
        ner_results = self.transformer_pipeline(text)
        
        for entity in ner_results:
            entity_text = entity['word'].strip()
            entity_label = entity['entity_group']
            
            # Clean up tokenization artifacts (## prefix from BERT tokenization)
            entity_text = entity_text.replace('##', '')
            
            # Skip very short entities (likely tokenization artifacts)
            if len(entity_text) < 2:
                continue
            
            # Map transformers labels to our categories
            if entity_label == 'ORG':
                entities['organizations'].append(entity_text)
            elif entity_label in ['LOC', 'GPE']:
                entities['locations'].append(entity_text)
            # Note: Transformers doesn't extract dates/ages well, use pattern matching
        
        # Extract dates and ages using pattern matching
        ages = self._extract_ages_with_context(None, text)
        entities['ages'].extend(ages)
        
        # Extract dates using regex (since transformers doesn't do dates well)
        date_patterns = [
            # Full month names with day and year: "September 27th 2022", "January 15, 2022"
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b',
            # Abbreviated months: "Apr 13, 2022", "Jun 23, 2022", "Sep 30, 2022"
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4}\b',
            # Numeric formats: "4/13/2022", "04-20-2022", "4/13/22"
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
            # Month and year only: "September 2022", "Apr 2022"
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{4}\b',
            # Year only (if standalone): "\b(19|20)\d{2}\b" - but this is too broad, skip
        ]
        dates_found = []
        for pattern in date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match.group().strip()
                # Skip if it's just a year that might be part of something else
                if re.match(r'^\d{4}$', date_str) and len(dates_found) == 0:
                    # Only add standalone years if they're clearly dates
                    continue
                dates_found.append(date_str)
        entities['dates'].extend(dates_found)
        
        # Remove duplicates while preserving order
        for key in entities:
            entities[key] = list(dict.fromkeys(entities[key]))
        
        return entities
    
    def _extract_entities_spacy(self, text: str) -> Dict[str, List[str]]:
        """Extract entities using spaCy."""
        entities = {
            'organizations': [],
            'locations': [],
            'dates': [],
            'ages': []
        }
        
        if not self.nlp:
            return entities
        
        doc = self.nlp(text)
        
        # Extract entities by type (excluding PERSON to avoid reporter names)
        for ent in doc.ents:
            if ent.label_ == 'ORG':
                entities['organizations'].append(ent.text.strip())
            elif ent.label_ in ['GPE', 'LOC']:  # Geopolitical entity or location
                entities['locations'].append(ent.text.strip())
            elif ent.label_ == 'DATE':
                entities['dates'].append(ent.text.strip())
        
        # Extract ages using pattern + context
        ages = self._extract_ages_with_context(doc, text)
        entities['ages'].extend(ages)
        
        # Remove duplicates while preserving order
        for key in entities:
            entities[key] = list(dict.fromkeys(entities[key]))
        
        return entities
    
    def _extract_ages_with_context(self, doc, text: str) -> List[int]:
        """
        Extract ages from text using pattern matching with context awareness.
        
        Args:
            doc: spaCy doc object (can be None for transformers backend)
            text: Original text
            
        Returns:
            List of extracted ages
        """
        ages = []
        
        # Pattern: "X year old", "X-year-old", "age X", "X years old", "aged X"
        # Also handle: "teacher, 29", "29, teacher", "man, 29", etc.
        age_patterns = [
            r'(\d+)[-\s]+year[-\s]+old',  # "25 year old" or "25-year-old"
            r'age\s+(\d+)',                # "age 25"
            r'aged\s+(\d+)',               # "aged 25"
            r'(\d+)[-\s]+years[-\s]+old',  # "25 years old" or "25-years-old"
            r'(\d+)[-\s]+yr[-\s]+old',     # "25 yr old" or "25-yr-old"
            r'(\d+)[-\s]+yrs[-\s]+old',    # "25 yrs old"
            # Also catch "X-year-old man/woman/boy/girl"
            r'(\d+)[-\s]+year[-\s]+old\s+(?:man|woman|boy|girl|male|female)',
            r'(\d+)[-\s]+years[-\s]+old\s+(?:man|woman|boy|girl|male|female)',
            # Handle "teacher, 29" or "29, teacher" format (comma-separated age)
            # Look for number followed by comma or comma followed by number, with context
            r'(?:teacher|coach|man|woman|boy|girl|male|female|person|suspect|defendant|perpetrator|victim|individual|adult|minor|teenager|teen|child|kid),?\s+(\d{1,2})\b',
            r'\b(\d{1,2}),?\s+(?:year|years|yr|yrs|year-old|years-old)\s+(?:old\s+)?(?:teacher|coach|man|woman|boy|girl|male|female|person|suspect|defendant|perpetrator|victim|individual|adult|minor|teenager|teen|child|kid)',
            # Handle standalone age in context: ", 29," or ", 29 " with nearby age-related words
            r',\s+(\d{1,2})\s*,',  # ", 29," - but validate context
            r',\s+(\d{1,2})\s+(?:was|is|has|had|did|arrested|charged|convicted|sentenced)',
        ]
        
        for pattern in age_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    age = int(match.group(1))
                    # Validate age range (sanity bound; nobody is >100)
                    if not (1 <= age <= 100):
                        continue
                    # Sentencing-context guard. Patterns like
                    # ", 25 sentenced" or "the 25 charged" used to slip
                    # through and pollute the age list.
                    num_start = match.start(1)
                    num_end   = match.end(1)
                    if _is_sentencing_context(text, num_start, num_end):
                        continue
                    # Check context to avoid other false positives
                    context_start = max(0, match.start() - 50)
                    context_end = min(len(text), match.end() + 50)
                    context = text[context_start:context_end].lower()

                    # For patterns that already have context (like "teacher, 29"), trust them
                    if any(word in pattern for word in ['teacher', 'coach', 'man', 'woman', 'boy', 'girl', 'person', 'suspect', 'defendant', 'perpetrator', 'victim']):
                        ages.append(age)
                    # For comma-separated patterns, check for age-related context
                    elif ',' in pattern:
                        # Look for age-related words nearby
                        age_indicators = ['teacher', 'coach', 'man', 'woman', 'boy', 'girl', 'person', 'suspect', 'defendant', 'perpetrator', 'victim', 'individual', 'adult', 'minor', 'teenager', 'teen', 'child', 'kid', 'arrested', 'charged', 'convicted']
                        if any(indicator in context for indicator in age_indicators):
                            # Make sure it's not a year (like 2022, 2014)
                            if age < 18 or (age >= 18 and age <= 100 and not any(str(year) in context for year in range(2000, 2030))):
                                ages.append(age)
                    # For standard patterns, check context
                    elif 'year' in context or 'old' in context or 'age' in context:
                        ages.append(age)
                except (ValueError, IndexError):
                    continue
        
        return list(set(ages))  # Remove duplicates
    
    def merge_with_pattern_results(
        self,
        pattern_results: Dict[str, Any],
        ner_entities: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Merge NER results with pattern processing (regex) extraction results.
        
        Pattern processing is authoritative for structured data (ages, platforms, etc.).
        NER supplements with contextual entities (organizations, locations, persons).
        
        Args:
            pattern_results: Results from pattern processing (extract_features)
            ner_entities: Results from NER extraction
            
        Returns:
            Merged results with NER entities in ml_features and enhanced agencies
        """
        merged = pattern_results.copy()
        
        # Merge organizations (NER can catch ones pattern processing misses)
        pattern_orgs = set(pattern_results.get('agencies_involved', []))
        ner_orgs = set(ner_entities.get('organizations', []))
        
        # Combine and deduplicate
        all_orgs = list(pattern_orgs | ner_orgs)
        merged['agencies_involved'] = all_orgs
        
        # Add NER entities to ml_features
        if 'ml_features' not in merged:
            merged['ml_features'] = {}
        merged['ml_features']['ner_entities'] = ner_entities
        
        # Add extraction confidence metrics
        merged['ml_features']['extraction_confidence'] = {
            'pattern_organizations': len(pattern_orgs),
            'ner_organizations': len(ner_orgs),
            'merged_organizations': len(all_orgs),
            'ner_supplemented': len(ner_orgs - pattern_orgs) > 0
        }
        
        return merged
    
    def enhance_case_with_entities(
        self,
        case: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enhance case dictionary with NER-extracted entities.
        
        Works with both:
        - Raw batched cases (before pattern processing)
        - Cases with extracted features (after pattern processing)
        
        Args:
            case: Case dictionary with case_text (or raw_data.case_text)
            
        Returns:
            Enhanced case dictionary with NER entities in ml_features
        """
        if not self._is_available():
            return case
        
        enhanced_case = case.copy()
        
        # Get case text (supports multiple formats)
        case_text = (
            case.get('case_text', '') or
            case.get('raw_data', {}).get('case_text', '') or
            ''
        )
        
        if not case_text:
            return enhanced_case
        
        # Extract entities
        entities = self.extract_entities(case_text)
        
        # Initialize ml_features if not present
        if 'ml_features' not in enhanced_case:
            enhanced_case['ml_features'] = {}
        enhanced_case['ml_features']['ner_entities'] = entities
        
        # Merge with existing agencies if present (from pattern processing)
        existing_agencies = enhanced_case.get('agencies_involved', [])
        if existing_agencies:
            # Merge NER organizations with existing
            all_agencies = list(set(existing_agencies + entities['organizations']))
            enhanced_case['agencies_involved'] = all_agencies
        else:
            # Use NER organizations if no pattern processing results
            enhanced_case['agencies_involved'] = entities['organizations']
        
        return enhanced_case
    
    def get_entity_statistics(self, entities: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Get statistics about extracted entities.
        
        Args:
            entities: Dictionary of extracted entities
            
        Returns:
            Statistics dictionary
        """
        return {
            'total_entities': sum(len(v) for v in entities.values()),
            'organizations_count': len(entities.get('organizations', [])),
            'locations_count': len(entities.get('locations', [])),
            'dates_count': len(entities.get('dates', [])),
            'ages_count': len(entities.get('ages', []))
        }
    
    def _is_available(self) -> bool:
        """Check if NER extraction is available."""
        if self.backend == 'stanza':
            return self.stanza_pipeline is not None
        elif self.backend == 'transformers':
            return self.transformer_pipeline is not None
        elif self.backend == 'spacy':
            return self.nlp is not None
        return False
    
    def is_available(self) -> bool:
        """Check if NER extraction is available."""
        return self._is_available()

    @property
    def active_backend(self) -> str:
        """Resolved backend name (``stanza``, ``transformers``, ``spacy``, or ``none``)."""
        if self._is_available():
            return self.backend
        return "none"


_primary_ner_extractor: Optional["NERExtractor"] = None
_primary_ner_extractor_probed: bool = False


def create_primary_ner_extractor() -> Optional["NERExtractor"]:
    """
    Ingest-time NER: Stanza first, Hugging Face transformers only if Stanza unavailable.

    Cached for the process lifetime so multi-group ingest does not reload Stanza.

    Returns:
        Configured ``NERExtractor``, or ``None`` if no backend loads.
    """
    global _primary_ner_extractor, _primary_ner_extractor_probed
    if _primary_ner_extractor_probed:
        return _primary_ner_extractor

    stanza_ext: Optional[NERExtractor] = None
    transformers_ext: Optional[NERExtractor] = None

    # Attempt stanza first (primary backend)
    try:
        stanza_ext = NERExtractor(backend="stanza")
        stanza_ok = stanza_ext.is_available()

        # Loud-ish diagnostics: we only emit these when stanza is not available,
        # or when an exception exists. This is meant for debugging ingest-time
        # backend selection issues.
        if not stanza_ok:
            import sys as _sys
            print(
                "NER backend probe: stanza constructed but unavailable. "
                f"imported={getattr(stanza_ext, '_stanza_imported', None)} "
                f"loaded={getattr(stanza_ext, '_stanza_pipeline_loaded', None)} "
                f"import_error={getattr(stanza_ext, '_stanza_import_error', None)!r} "
                f"load_error={getattr(stanza_ext, '_stanza_load_error', None)!r} "
                f"cwd={os.getcwd()!r} "
                f"home={os.environ.get('HOME', '')!r} "
                f"stanza_resources_dir={os.environ.get('STANZA_RESOURCES_DIR', '')!r}",
                file=_sys.stderr,
            )
            import_tb = getattr(stanza_ext, "_stanza_import_traceback", None)
            load_tb = getattr(stanza_ext, "_stanza_load_traceback", None)
            if import_tb:
                print("NER backend probe: stanza import traceback:", file=_sys.stderr)
                print(import_tb, file=_sys.stderr)
            if load_tb:
                print("NER backend probe: stanza load traceback:", file=_sys.stderr)
                print(load_tb, file=_sys.stderr)
    except Exception as e:
        # If construction itself fails, capture that too.
        import sys as _sys
        print(f"NER backend probe: stanza construction threw exception: {e!r}", file=_sys.stderr)
        stanza_ext = None

    if stanza_ext is not None and stanza_ext.is_available():
        _primary_ner_extractor = stanza_ext
        _primary_ner_extractor_probed = True
        return _primary_ner_extractor

    # Fallback to transformers (only if stanza isn't available)
    try:
        transformers_ext = NERExtractor(backend="transformers")
        if transformers_ext.is_available():
            import sys as _sys
            print(
                "WARNING: Stanza unavailable, falling back to transformers. "
                "Location NER fragmentation may increase; please verify.",
                file=_sys.stderr,
            )
            _primary_ner_extractor = transformers_ext
            _primary_ner_extractor_probed = True
            return _primary_ner_extractor
    except Exception:
        pass
    _primary_ner_extractor = None
    _primary_ner_extractor_probed = True
    return None
