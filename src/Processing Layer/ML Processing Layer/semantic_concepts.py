"""
Semantic Concepts (ML)

Goal: Given a case text, identify key severity and investigative
**concepts** semantically (not just via regex) so we can:

- enrich cases with ML extracted features that downstream code can use
  for analysis and false‑positive correction; and
- later build a `semantic_ideas` / concepts table for statistics and
  grouping cases by ideas instead of only regex tags.

Aim to model a much broader set of ICAC / CSAM concepts (production vs
possession, grooming, sextortion, law‑enforcement operations, online
platforms, etc.).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import os
import warnings

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is optional
    np = None  # type: ignore



class ConceptScore:
    """Score for a single semantic concept."""

    def __init__(self, key: str, score: float) -> None:
        self.key = key
        self.score = score


class SemanticConcepts:
    """
    Core semantic concept detector.

    Responsibilities:
      - encode case text using a sentence‑transformer model
      - compare to natural‑language concept descriptions
      - return concept keys + scores (for ideas DB / stats)
      - optionally enrich a case dict with:
          * `phrases` / `scores` / `concept_metadata`

    Typical usage:

        from semantic_concepts import SemanticConcepts
        from ml_models import get_global_ml_manager

        ml_manager = get_global_ml_manager(enable_ml=True)
        semantic_model = ml_manager.get_model("semantic")
        detector = SemanticConcepts(semantic_model)

        scores = detector.get_concept_scores(case_text)
        concepts = detector.get_concepts(case_text)
        detector.enhance_case_with_concepts(case)
    """

    # Map concept keys → natural language descriptions for embedding
    _CONCEPT_TEXT: Dict[str, str] = {
        # Matches pattern key: 'dangerous'
        "dangerous": (
            "The offender is described as dangerous, high risk, escalating, "
            "or likely to seriously harm victims."
        ),
        # Matches pattern key: 'stated'
        "stated": (
            "The victim or witnesses made clear statements or disclosures "
            "about the abuse or exploitation."
        ),
        # Matches pattern key: 'told'
        "told": (
            "The victim told someone about the abuse, reported it, or "
            "communicated clear disclosures."
        ),
        # Matches pattern key: 'continue'
        "continue": (
            "The abuse or exploitation continued over time, repeated conduct, "
            "or ongoing behavior rather than a single incident."
        ),
        # Matches pattern key: 'attacked'
        "attacked": (
            "Physical or violent attack against the victim, including assault, "
            "beating, or hands-on abuse."
        ),
        # Matches pattern key: 'out_of_control'
        "out_of_control": (
            "The situation or behavior is described as out of control, "
            "escalating, or unable to be stopped."
        ),
        # Additional severity / content concepts
        "violent": (
            "Explicit descriptions of violence or violent behavior, including "
            "physical harm, threats of violence, or extremely aggressive acts."
        ),
        "obscene": (
            "Obscene, graphic, or extremely explicit sexual content, including "
            "obscene material or obscene communications involving minors."
        ),
        "assault": (
            "Sexual abuse or physical assault against the victim, including "
            "forcible contact, penetration, or repeated assaultive conduct."
        ),
        "abuse": (
            "Ongoing or serious abuse of the victim, including sexual abuse, "
            "physical abuse, emotional abuse, or exploitation over time."
        ),
        "depictions": (
            "Depictions, images, or visual recordings of child sexual abuse or "
            "exploitation, including child sexual abuse material and explicit "
            "imagery of minors."
        ),
        # --- ICAC / CSAM: possession (is_production=False) ---
        "possession_csam": (
            "Possession of child sexual abuse material: possessing, collecting, "
            "downloading, storing, or having hundreds of images or pictures, "
            "printed pictures, images depicting sexual exploitation of minors."
        ),
        # --- ICAC / CSAM: production of content (is_production=True) ---
        "production_csam": (
            "Production of child sexual abuse material: created or produced "
            "videos, images, or photos of child sexual abuse, took photos, "
            "made videos, recorded or filmed minors in sexual or exploitive contexts."
        ),
        # --- Account/platform only (is_production=False) ---
        "account_platform": (
            "Creating or using online accounts, platform accounts, social media "
            "accounts, profiles, or pages for communication or access; not the "
            "creation of abuse images or videos."
        ),
        "online_platforms": (
            "Use of online platforms, apps, or services: social media, messaging "
            "apps, chat rooms, Discord, Facebook, Instagram, Roblox, Snapchat, TikTok, "
            "dating apps, gaming platforms, or other websites and apps used to "
            "contact, lure, or exchange material involving minors."
        ),
        # --- Perpetrator status / RSO ---
        "registered_sex_offender": (
            "Registered sex offender, RSO, sex offender registry, sex offender "
            "terms, previously convicted of sex offenses against children or "
            "child molestation."
        ),
        "probation_violation": (
            "Probation violation, violated probation, failure to abide by sex "
            "offender terms, violating release conditions or court-ordered terms."
        ),
        # --- Paraphilia / fetish details (from case narratives) ---
        "paraphilia_fetish": (
            "Sexually attracted to children, sexual attraction to minors, fetish "
            "involving children, paraphilia, specific fetish details such as "
            "children's feet or body parts, collecting or keeping body parts or "
            "clippings from children."
        ),
        # --- Evidence / investigation ---
        "evidence_seizure": (
            "Search warrant executed, seized evidence, seized computer, thumb "
            "drive or storage devices seized, forensic examination, forensics "
            "pending, evidence discovered on devices."
        ),
        "dissemination": (
            "Trading, distributing, sharing, or dissemination of child sexual "
            "abuse material or images; sending or exchanging such content."
        ),
        # --- Severity / content details ---
        "exploitive_positions": (
            "Children tied up, bound, posed in sexually exploitive positions, "
            "sexual exploitation of minors, images depicting bondage or posed "
            "sexual abuse of children."
        ),
        "large_collection": (
            "Hundreds of images, large collection of abuse material, thousands "
            "of files, extensive collection of child sexual abuse images or videos."
        ),
        # --- Not production: \"created/produced\" in non-CSAM sense (is_production=False) ---
        "produced_evidence": (
            "A warrant produced evidence, an affidavit produced evidence, "
            "investigation produced results, records produced, discovery produced "
            "evidence; produced meaning yielded or obtained, not created abuse content."
        ),
        "created_committee_or_entity": (
            "A board or organization created a committee, created a task force, "
            "created a special committee, created an entity or group; created "
            "meaning established or formed, not creation of abuse images or videos."
        ),
        "created_account_for_storage": (
            "Created a Dropbox account to store, created an account to store "
            "collection, created account for storage; creating an online account "
            "or cloud storage account to store material, not creating the abuse content itself."
        ),
        # --- Grooming, sextortion, and online tactics ---
        "grooming": (
            "Grooming of a minor: building trust or emotional connection with a "
            "child for sexual abuse or exploitation, manipulating the victim over "
            "time, gift-giving, isolation, or gradual boundary violations."
        ),
        "sextortion": (
            "Sextortion: threatening to share sexual images or information to "
            "extort the victim, demanding more images or money, blackmail involving "
            "sexual content or nude photos of minors."
        ),
        "ai_and_internet_tools": (
            "Press release or criminal charging language about AI-generated child sexual "
            "abuse material, computer-generated or digitally generated child pornography, "
            "synthetic exploitative images, deepfake child abuse images, obscene visual "
            "representations produced with artificial intelligence, or offender use of "
            "generative AI and AI chatbots to create child exploitation images."
        ),
        "online_luring_social_engineering": (
            "Online luring or social engineering: persuading or tricking a minor "
            "online to meet, share images, or engage in sexual activity; posing as "
            "someone else, fake profiles, catfishing, or manipulating the victim through chat or apps."
        ),
        # --- Criminal networks and trafficking ---
        "criminal_networks_trafficking": (
            "Criminal networks, trafficking, or organized exploitation: multiple "
            "offenders, distribution rings, trafficking of minors for sexual "
            "exploitation, cross-border or coordinated abuse, organized crime involvement."
        ),
        # --- Law enforcement operations and investigations ---
        "law_enforcement_operations": (
            "Law enforcement operations and investigations: task force involvement, "
            "multi-agency investigation, undercover operations, federal or state "
            "partnerships, ICAC operations, arrest, warrant execution, or referral to prosecution."
        ),
    }

    # Concepts related to production vs possession (for concept_metadata only; no semantic production flag).
    _CONCEPT_IS_PRODUCTION: Dict[str, bool] = {
        "production_csam": True,
        "account_platform": False,
        "possession_csam": False,
        "produced_evidence": False,
        "created_committee_or_entity": False,
        "created_account_for_storage": False,
    }

    def __init__(self, semantic_model: Optional[Any] = None, enable_ml: bool = True):
        """
        Initialize the semantic concept detector.

        Args:
            semantic_model: Optional sentence-transformers model instance.
                If provided, we use it directly (e.g., from MLModelManager).
                If None and enable_ml is True, we will try MLModelManager
                first, then fall back to a local SentenceTransformer.
            enable_ml: If False, disables ML entirely and always returns [].
        """
        self.enable_ml = enable_ml
        self.model = semantic_model
        self._concept_embeddings: Optional[Any] = None
        self._concept_keys: List[str] = list(self._CONCEPT_TEXT.keys())

        if not self.enable_ml:
            return

        # 1) If caller passed a model (e.g. via MLModelManager), use it.
        # 2) Otherwise, try MLModelManager to keep centralized control.
        # 3) If that fails (e.g., import issues in ad‑hoc scripts), fall back
        #    to a local SentenceTransformer instance.
        if self.model is None:
            try:
                from .ml_models import get_global_ml_manager

                ml_manager = get_global_ml_manager(enable_ml=True)
                self.model = ml_manager.get_model("semantic")
            except Exception as exc:  # pragma: no cover - defensive
                warnings.warn(
                    f"SemanticConcepts: failed to obtain semantic model from "
                    f"MLModelManager: {exc}"
                )
                self.model = None

        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as exc:  # pragma: no cover - defensive
                warnings.warn(
                    f"SemanticConcepts: failed to load semantic model via "
                    f"sentence-transformers: {exc}"
                )
                self.model = None

        if self.model is None or np is None:
            warnings.warn(
                "SemanticConcepts: semantic model or numpy unavailable. "
                "Semantic concepts will be disabled."
            )
        else:
            self._precompute_concept_embeddings()

    def is_available(self) -> bool:
        """Return True if semantic concept detection is available."""
        return bool(self.model is not None and self._concept_embeddings is not None and np is not None)

    # ------------------------------------------------------------------ #
    # Primary concept scoring 
    # ------------------------------------------------------------------ #
    def get_concept_scores(
        self,
        text: str,
        min_score: float = 0.35,
    ) -> List[ConceptScore]:
        """
        Compute similarity scores between case text and all configured
        semantic concepts.
        """
        if not text or not self.is_available():
            return []

        try:
            case_emb = self.model.encode(  # type: ignore[attr-defined]
                text,
                normalize_embeddings=True,
            )
            concept_embs = self._concept_embeddings
            if concept_embs is None:
                return []

            case_vec = np.asarray(case_emb)
            concept_mat = np.asarray(concept_embs)
            sims = concept_mat @ case_vec  # type: ignore[operator]

            scores: List[ConceptScore] = []
            for key, sim in zip(self._concept_keys, sims):
                score = float(sim)
                if score >= min_score:
                    scores.append(ConceptScore(key=key, score=score))

            scores.sort(key=lambda s: s.score, reverse=True)
            return scores
        except Exception as exc:  # pragma: no cover - defensive
            warnings.warn(f"SemanticConcepts: error computing scores: {exc}")
            return []

    def get_concepts(
        self,
        text: str,
        min_score: float = 0.35,
        top_k: Optional[int] = None,
    ) -> List[str]:
        """
        Return just the concept keys for a case (thin wrapper around
        get_concept_scores).
        """
        scores = self.get_concept_scores(text, min_score=min_score)
        if top_k is not None and top_k > 0:
            scores = scores[:top_k]
        return [s.key for s in scores]

    # ------------------------------------------------------------------ #
    # Case enrichment w/ semantic concepts
    # ------------------------------------------------------------------ #
    def enhance_case_with_concepts(
        self,
        case: Dict[str, Any],
        min_score: float = 0.35,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Add semantic concept information to a case dict.

        This writes:

            case['ml_features']['semantic_severity'] = {
                'phrases': [...],
                'scores': {key: float},
                'concept_metadata': {key: {...}},  # e.g. {'is_production': bool}
            }
        """
        if not case:
            return case

        if not self.is_available():
            if "ml_features" not in case:
                case["ml_features"] = {}
            case["ml_features"].setdefault(
                "semantic_severity",
                {"phrases": [], "scores": {}, "concept_metadata": {}},
            )
            return case

        case_text = (
            case.get("case_text")
            or (case.get("raw_data") or {}).get("case_text")  # type: ignore[union-attr]
            or (case.get("extracted_features") or {}).get("case_text")  # type: ignore[union-attr]
            or ""
        )

        if not isinstance(case_text, str) or not case_text.strip():
            if "ml_features" not in case:
                case["ml_features"] = {}
            case["ml_features"].setdefault(
                "semantic_severity",
                {"phrases": [], "scores": {}, "concept_metadata": {}},
            )
            return case

        all_scores = self.get_concept_scores(case_text, min_score=0.0)

        scores = [s for s in all_scores if s.score >= min_score]
        if top_k is not None and top_k > 0:
            scores = scores[:top_k]
        phrases = [s.key for s in scores]
        score_map = {s.key: s.score for s in scores}
        concept_metadata: Dict[str, Dict[str, bool]] = {}
        for key in phrases:
            if key in self._CONCEPT_IS_PRODUCTION:
                concept_metadata[key] = {"is_production": self._CONCEPT_IS_PRODUCTION[key]}

        if "ml_features" not in case:
            case["ml_features"] = {}

        case["ml_features"]["semantic_severity"] = {
            "phrases": phrases,
            "scores": score_map,
            "concept_metadata": concept_metadata,
        }

        return case

    def enhance_cases_with_concepts(
        self,
        cases: List[Dict[str, Any]],
        min_score: float = 0.35,
        top_k: Optional[int] = None,
        encode_batch_size: int = 64,
    ) -> List[Dict[str, Any]]:
        """
        Enrich many cases with semantic concepts via one batched MiniLM encode.

        Same fields as enhance_case_with_concepts; encode_batch_size controls
        SentenceTransformer.encode batching (default 64).
        """
        if not cases:
            return cases

        def _empty_semantic(case: Dict[str, Any]) -> None:
            if "ml_features" not in case:
                case["ml_features"] = {}
            case["ml_features"].setdefault(
                "semantic_severity",
                {"phrases": [], "scores": {}, "concept_metadata": {}},
            )

        def _case_text(case: Dict[str, Any]) -> str:
            text = (
                case.get("case_text")
                or (case.get("raw_data") or {}).get("case_text")  # type: ignore[union-attr]
                or (case.get("extracted_features") or {}).get("case_text")  # type: ignore[union-attr]
                or ""
            )
            return text if isinstance(text, str) else ""

        if not self.is_available():
            for case in cases:
                if case:
                    _empty_semantic(case)
            return cases

        texts: List[str] = []
        indices: List[int] = []
        for i, case in enumerate(cases):
            if not case:
                continue
            text = _case_text(case)
            if not text.strip():
                _empty_semantic(case)
                continue
            texts.append(text)
            indices.append(i)

        if not texts:
            return cases

        try:
            try:
                batch_size = int(os.environ.get("SEMANTIC_ENCODE_BATCH", str(encode_batch_size)))
            except ValueError:
                batch_size = encode_batch_size
            batch_size = max(1, batch_size)

            case_embs = self.model.encode(  # type: ignore[attr-defined]
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            concept_mat = np.asarray(self._concept_embeddings)
            case_mat = np.asarray(case_embs)
            sims_mat = case_mat @ concept_mat.T  # type: ignore[operator]

            for row_i, case_i in enumerate(indices):
                case = cases[case_i]
                sims = sims_mat[row_i]
                all_scores = [
                    ConceptScore(key=key, score=float(sim))
                    for key, sim in zip(self._concept_keys, sims)
                ]
                all_scores.sort(key=lambda s: s.score, reverse=True)
                scores = [s for s in all_scores if s.score >= min_score]
                if top_k is not None and top_k > 0:
                    scores = scores[:top_k]
                phrases = [s.key for s in scores]
                score_map = {s.key: s.score for s in scores}
                concept_metadata: Dict[str, Dict[str, bool]] = {}
                for key in phrases:
                    if key in self._CONCEPT_IS_PRODUCTION:
                        concept_metadata[key] = {
                            "is_production": self._CONCEPT_IS_PRODUCTION[key]
                        }
                if "ml_features" not in case:
                    case["ml_features"] = {}
                case["ml_features"]["semantic_severity"] = {
                    "phrases": phrases,
                    "scores": score_map,
                    "concept_metadata": concept_metadata,
                }
        except Exception as exc:  # pragma: no cover - defensive
            warnings.warn(f"SemanticConcepts: bulk encode failed: {exc}")
            for case in cases:
                if case:
                    try:
                        self.enhance_case_with_concepts(case, min_score=min_score, top_k=top_k)
                    except Exception:
                        _empty_semantic(case)

        return cases

    def _precompute_concept_embeddings(self) -> None:
        """Precompute normalized embeddings for concepts."""
        if self.model is None or np is None:
            return

        try:
            sentences = [self._CONCEPT_TEXT[k] for k in self._concept_keys]
            emb = self.model.encode(  # type: ignore[attr-defined]
                sentences,
                normalize_embeddings=True,
            )
            self._concept_embeddings = emb
        except Exception as exc:  # pragma: no cover - defensive
            warnings.warn(f"SemanticConcepts: failed to precompute embeddings: {exc}")
            self._concept_embeddings = None


def enhance_case_with_concepts(
    case: Dict[str, Any],
    min_score: float = 0.35,
    top_k: Optional[int] = None,
    semantic_model: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Convenience function to enrich a single case with semantic concepts.
    """
    detector = SemanticConcepts(semantic_model=semantic_model)
    return detector.enhance_case_with_concepts(case, min_score=min_score, top_k=top_k)


# Backwards‑compatible alias for older code/tests that still refer to
# `SemanticSeverity` and `enhance_case_with_semantic_severity`.
SemanticSeverity = SemanticConcepts


def enhance_case_with_semantic_severity(
    case: Dict[str, Any],
    min_score: float = 0.35,
    top_k: Optional[int] = None,
    semantic_model: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Backwards‑compatible wrapper that enriches the case with concepts.
    Prefer `enhance_case_with_concepts` in new code.
    """
    return enhance_case_with_concepts(
        case,
        min_score=min_score,
        top_k=top_k,
        semantic_model=semantic_model,
    )


