"""Controlled vocabularies for the evidence and trajectory layers.

One source of truth: the JSON Schema (``trajectories.schema``), the validator, the
ontology emitter and the extension shapes all read these tuples. Codes are defined
in ``trajectories/CODEBOOK.md``; change both together and bump CODEBOOK_VERSION.

The core is domain-neutral: nothing here requires a phase, a contact event or an
offense type. The AfH scheme (affordances O, harm categories H0) is one scheme.
"""
from __future__ import annotations

CODEBOOK_VERSION = "0.3.0"
SCHEMA_VERSION = "2.0.0"
# 2.0.0 replaces the role-coded actor table with persons and event roles (R04/R10), keeps
# every dated assertion (T1-T5) and records platform interaction modes (I1-I3).
# 1.x bundles are converted by state_machines.evidence.migrate, never read directly.
SUPPORTED_SCHEMA_VERSIONS = ("2.0.0",)

# --- evidence status -----------------------------------------------------------------
# Assertion-level: does the cited passage support this specific claim?
# SYNTHETIC is deliberately absent: nothing introduced for modelling may enter the evidence layer.
ASSERTION_STATUS = ("DIRECT", "INFERRED", "UNSUPPORTED", "CONTRADICTED")
# Statuses a derived trajectory may rely on, strictest first.
ADMISSIBLE = {"DIRECT": ("DIRECT",), "INFERRED": ("DIRECT", "INFERRED")}

# Legal/procedural standing of the passage's claim (not of the case outcome).
SOURCE_STATUS = (
    "ALLEGATION", "SWORN_AFFIDAVIT", "ADMITTED", "ADMITTED_UNDER_OATH", "JUDICIAL_FINDING",
    "VERDICT_ELEMENT", "COURT_RECORD", "ADVOCACY", "PROCEDURAL",
)

DOC_TYPES = {
    # doc_type: (default source status, statuses a passage from it may carry)
    "docket": ("PROCEDURAL", ("PROCEDURAL", "COURT_RECORD")),
    "complaint": ("SWORN_AFFIDAVIT", ("SWORN_AFFIDAVIT", "ALLEGATION")),
    "information": ("ALLEGATION", ("ALLEGATION",)),
    "indictment": ("ALLEGATION", ("ALLEGATION",)),
    "superseding_indictment": ("ALLEGATION", ("ALLEGATION",)),
    "plea_agreement": ("ADMITTED", ("ADMITTED", "PROCEDURAL", "ALLEGATION")),
    "statement_of_offense": ("ADMITTED", ("ADMITTED",)),
    "statement_of_facts": ("ADMITTED", ("ADMITTED",)),
    "stipulation_of_facts": ("ADMITTED", ("ADMITTED",)),
    "factual_basis": ("ADMITTED", ("ADMITTED",)),
    "factual_proffer": ("ADMITTED", ("ADMITTED",)),
    "plea_transcript": ("ADMITTED_UNDER_OATH", ("ADMITTED_UNDER_OATH", "PROCEDURAL", "COURT_RECORD", "ALLEGATION")),
    "findings_of_fact": ("JUDICIAL_FINDING", ("JUDICIAL_FINDING", "COURT_RECORD")),
    "judgment": ("COURT_RECORD", ("COURT_RECORD", "VERDICT_ELEMENT", "PROCEDURAL")),
    "amended_judgment": ("COURT_RECORD", ("COURT_RECORD", "VERDICT_ELEMENT", "PROCEDURAL")),
    "statement_of_reasons": ("COURT_RECORD", ("COURT_RECORD", "JUDICIAL_FINDING")),
    "sentencing_memorandum": ("ADVOCACY", ("ADVOCACY",)),
    "trial_brief": ("ADVOCACY", ("ADVOCACY",)),
    "brief": ("ADVOCACY", ("ADVOCACY",)),                       # a party's brief on a motion (not a trial or sentencing brief)
    "opinion": ("JUDICIAL_FINDING", ("JUDICIAL_FINDING", "COURT_RECORD", "PROCEDURAL")),   # a court's memorandum opinion or order
    "other": ("PROCEDURAL", SOURCE_STATUS),
}

VERIFICATION_STATUS = ("VERIFIED", "UNVERIFIED", "FAILED")
# ocr_text_exact: the quote matches the OCR text exactly, but nobody checked the page image (machine coding)
VERIFICATION_METHOD = ("text_layer_exact", "ocr_plus_page_image", "manual_page_image", "ocr_text_exact")
TEXT_METHOD = ("text_layer", "ocr", "manual_transcription", "none")
PAGE_LIMITATIONS = (
    "strikethrough", "handwriting", "redaction", "stamp_overlap", "low_contrast",
    "multi_column", "table", "line_numbers", "rotated", "partial_page",
)

# Coder adjudication: who agreed on this coded assertion. Separate from SOURCE_STATUS.
REVIEW_STATUS = ("single_coder", "agreed", "adjudicated", "disputed")
CODER_METHOD = ("human", "agent_assisted", "agent")

# --- participants and roles (R04/R10) ----------------------------------------------------
# A participant is role-neutral: P1, P2, ... Roles belong to events (the actor role decides
# the action family, rule T08). Legal status is a separate, sourced record on the participant.
PARTICIPANT_REF_PATTERN = r"^P[0-9]+$"
PARTICIPANT_KINDS = ("person", "persona", "collective", "organization")
LEGAL_STATUS = (
    "charged_defendant", "uncharged_coconspirator", "named_victim", "undercover_persona",
    "law_enforcement", "platform_provider", "third_party", "court",
)
PARTICIPATION_MODES = ("performer", "directing", "assisting")   # directing: instructed the act
TARGET_ROLES = ("victim", "recipient", "counterparty", "subject")
COUNT_STATED = ("exact", "at_least", "at_most", "approximate", "unknown")
# Event roles (who acts in which capacity in one event)
ACTOR_ROLES = (
    "offender", "co_offender", "victim", "undercover", "law_enforcement",
    "platform", "guardian", "third_party", "court",
)
VICTIM_KIND = ("minor", "adult", "undercover_persona", "unknown")
AGE_BAND = ("0-5", "6-9", "10-12", "13-15", "16-17", "adult", "unknown")

# --- actions (A) ------------------------------------------------------------------------
# family -> codes. Family decides which actor roles may perform the action.
ACTION_FAMILIES = {
    "offender": (
        "SEEK_TARGETS", "INITIATE_CONTACT", "ACQUIRE_REPRESENTATION", "ACQUIRE_MATERIAL",
        "COMMUNICATE", "MISREPRESENT_IDENTITY", "BUILD_RAPPORT", "OFFER_INDUCEMENT",
        "SEXUALIZE_COMMUNICATION", "SOLICIT_IMAGERY", "DIRECT_CONDUCT",
        "THREATEN_EXPOSURE", "THREATEN_HARM", "DIRECT_VICTIM_TO_RECRUIT",
        "MOVE_CHANNEL", "RECREATE_ACCOUNT", "RECONTACT",
        "RECEIVE_SELF_GENERATED", "RECORD_LIVE_SESSION", "PRODUCE_IN_PERSON", "SYNTHESIZE_OR_ALTER_IMAGERY",
        "STORE_MATERIAL", "ORGANIZE_MATERIAL", "DISTRIBUTE_MATERIAL", "ADVERTISE_MATERIAL_OR_ACCESS",
        "EXPOSE_TO_VICTIM_NETWORK",
        "ADMINISTER_SPACE", "GATEKEEP_MEMBERSHIP", "SET_RULES", "ASSIGN_ROLE",
        "COORDINATE_CO_OFFENDERS", "SHARE_TRADECRAFT", "PAY_THIRD_PARTY",
        "ARRANGE_MEETING", "TRAVEL_TO_MEET", "IN_PERSON_SEXUAL_ABUSE",
        "ADVERTISE_COMMERCIAL_SEX", "ARRANGE_COMMERCIAL_SEX", "COLLECT_PROCEEDS", "CONTROL_VICTIM",
        "CONCEAL_OR_DESTROY_EVIDENCE", "EVADE_DETECTION", "OBSTRUCT_OR_TAMPER", "FLEE",
        "OTHER_OFFENDER_ACTION",
    ),
    "response": ("RESP_REFUSE", "RESP_BLOCK", "RESP_REPORT", "RESP_DISCLOSE", "RESP_PLATFORM_ENFORCE"),
    "law_enforcement": (
        "LE_RECEIVE_TIP", "LE_UNDERCOVER_ENGAGE", "LE_SURVEIL", "LE_LEGAL_PROCESS",
        "LE_SEARCH_SEIZE", "LE_FORENSIC_EXAM", "LE_INTERVIEW", "LE_INTERDICT", "LE_ARREST",
    ),
    "procedure": ("PROC_CHARGE", "PROC_PLEA", "PROC_VERDICT", "PROC_SENTENCE", "PROC_OTHER"),
}
ACTION_CODES = tuple(code for codes in ACTION_FAMILIES.values() for code in codes)
# Codebook A groups of offender actions, in codebook order. Categories of conduct, not stages:
# the order between events comes only from the record.
ACTION_GROUPS = {
    "access": ("SEEK_TARGETS", "INITIATE_CONTACT", "ACQUIRE_REPRESENTATION", "ACQUIRE_MATERIAL"),
    "influence": ("COMMUNICATE", "MISREPRESENT_IDENTITY", "BUILD_RAPPORT", "OFFER_INDUCEMENT", "SEXUALIZE_COMMUNICATION",
                  "SOLICIT_IMAGERY", "DIRECT_CONDUCT", "THREATEN_EXPOSURE", "THREATEN_HARM", "DIRECT_VICTIM_TO_RECRUIT",
                  "MOVE_CHANNEL", "RECREATE_ACCOUNT", "RECONTACT"),
    "production": ("RECEIVE_SELF_GENERATED", "RECORD_LIVE_SESSION", "PRODUCE_IN_PERSON", "SYNTHESIZE_OR_ALTER_IMAGERY"),
    "distribution": ("STORE_MATERIAL", "ORGANIZE_MATERIAL", "DISTRIBUTE_MATERIAL", "ADVERTISE_MATERIAL_OR_ACCESS",
                     "EXPOSE_TO_VICTIM_NETWORK"),
    "coordination": ("ADMINISTER_SPACE", "GATEKEEP_MEMBERSHIP", "SET_RULES", "ASSIGN_ROLE", "COORDINATE_CO_OFFENDERS",
                     "SHARE_TRADECRAFT", "PAY_THIRD_PARTY"),
    "in_person": ("ARRANGE_MEETING", "TRAVEL_TO_MEET", "IN_PERSON_SEXUAL_ABUSE", "ADVERTISE_COMMERCIAL_SEX",
                  "ARRANGE_COMMERCIAL_SEX", "COLLECT_PROCEEDS", "CONTROL_VICTIM"),
    "concealment": ("CONCEAL_OR_DESTROY_EVIDENCE", "EVADE_DETECTION", "OBSTRUCT_OR_TAMPER", "FLEE", "OTHER_OFFENDER_ACTION"),
}
GROUP_OF = {code: g for g, codes in ACTION_GROUPS.items() for code in codes}
FAMILY_OF = {code: fam for fam, codes in ACTION_FAMILIES.items() for code in codes}
FAMILY_ROLES = {
    "offender": ("offender", "co_offender"),
    "response": ("victim", "guardian", "platform", "third_party"),
    "law_enforcement": ("law_enforcement", "undercover"),
    "procedure": ("court",),
}
# Only these families can appear as trajectory steps (offender conduct).
TRAJECTORY_FAMILIES = ("offender",)
OUTCOMES = ("completed", "attempted_not_completed", "refused", "blocked", "interrupted", "unknown")

# --- affordances (O) and candidates -----------------------------------------------------
CAC_PLATFORMS = "https://cacontology.projectvic.org/platforms#"
AFFORDANCE_CLASSES = {
    # AfH §7 class: CAC 3.1.0 class (all rdfs:subClassOf cac-platforms:PlatformAffordance)
    "anonymity": CAC_PLATFORMS + "Anonymity",
    "ephemerality": CAC_PLATFORMS + "Ephemerality",
    "contact_discovery": CAC_PLATFORMS + "ContactDiscovery",
    "unmonitored_communication": CAC_PLATFORMS + "UnmonitoredCommunication",
    "distribution_infrastructure": CAC_PLATFORMS + "DistributionInfrastructure",
    "generative_synthesis": CAC_PLATFORMS + "GenerativeSynthesis",
}
AFFORDANCES = tuple(AFFORDANCE_CLASSES)
# Candidate concepts pending evidence; never merged into O without a codebook version bump.
CANDIDATE_AFFORDANCES = ("persistent_storage", "multi_party_coordination")

# Three levels of affordance evidence (codebook B). Only level C enters O_i.
#   A available       the platform provided the capability in the period (capability registry,
#                     cited to public platform documentation; platform-level, not case evidence)
#   B action-relevant a documented action was carried out through that platform, and the
#                     capability is relevant to that kind of action (derived: A x interaction x R)
#   C instrumental    the court record supports that the capability was used to carry out the
#                     action (coded per event, with its own passage and status)
AFFORDANCE_LEVELS = ("available", "action_relevant", "instrumental")
# Level C needs the source to name the feature or the mechanism. A platform name is level A/B
# material (a platform mention or interaction), never an instrumental claim (rule B0).
AFFORDANCE_BASIS = ("feature_stated", "mechanism_stated")

# R(action): affordance classes relevant to an action of that kind when it is done through a
# platform that provides them. PROPOSED (codebook 0.2.0), awaiting author review. Anonymity is
# relevant only to identity-bearing actions: messaging through a pseudonymous service makes
# communication capability relevant, not identity concealment.
_COMMS = ("unmonitored_communication", "ephemerality")
ACTION_RELEVANCE = {
    "SEEK_TARGETS": ("contact_discovery",),
    "INITIATE_CONTACT": ("contact_discovery", "unmonitored_communication"),
    "ACQUIRE_REPRESENTATION": ("contact_discovery",),
    "ACQUIRE_MATERIAL": ("distribution_infrastructure",),
    "COMMUNICATE": _COMMS, "BUILD_RAPPORT": _COMMS, "OFFER_INDUCEMENT": _COMMS,
    "SEXUALIZE_COMMUNICATION": _COMMS, "SOLICIT_IMAGERY": _COMMS, "DIRECT_CONDUCT": _COMMS,
    "THREATEN_EXPOSURE": _COMMS, "THREATEN_HARM": _COMMS, "DIRECT_VICTIM_TO_RECRUIT": _COMMS,
    "RECONTACT": _COMMS, "ARRANGE_MEETING": _COMMS, "ARRANGE_COMMERCIAL_SEX": _COMMS,
    "COORDINATE_CO_OFFENDERS": _COMMS, "SHARE_TRADECRAFT": _COMMS, "OBSTRUCT_OR_TAMPER": _COMMS,
    "RECEIVE_SELF_GENERATED": _COMMS, "RECORD_LIVE_SESSION": _COMMS,
    "MOVE_CHANNEL": ("unmonitored_communication",),
    "MISREPRESENT_IDENTITY": ("anonymity",), "RECREATE_ACCOUNT": ("anonymity",), "EVADE_DETECTION": ("anonymity",),
    "DISTRIBUTE_MATERIAL": ("distribution_infrastructure",),
    "ADVERTISE_MATERIAL_OR_ACCESS": ("distribution_infrastructure", "contact_discovery"),
    "EXPOSE_TO_VICTIM_NETWORK": ("distribution_infrastructure",),
    "ADVERTISE_COMMERCIAL_SEX": ("distribution_infrastructure", "contact_discovery"),
    "ADMINISTER_SPACE": ("distribution_infrastructure",), "GATEKEEP_MEMBERSHIP": ("distribution_infrastructure",),
    "SET_RULES": ("distribution_infrastructure",),
    "SYNTHESIZE_OR_ALTER_IMAGERY": ("generative_synthesis",),
    "CONCEAL_OR_DESTROY_EVIDENCE": ("ephemerality",),
}
# Platform kinds in the capability registry -> CAC 3.1.0 platform class (all declared, all
# rdfs:subClassOf uco-observable:ObservableObject). Kinds without a CAC class use the UCO class.
UCO_OBSERVABLE = "https://ontology.unifiedcyberontology.org/uco/observable/"
PLATFORM_KIND_CLASS = {
    "messaging": CAC_PLATFORMS + "MessagingService",
    "anonymous_chat": CAC_PLATFORMS + "AnonymousChatPlatform",
    "social_media": CAC_PLATFORMS + "SocialMediaPlatform",
    "file_hosting": CAC_PLATFORMS + "FileHostingService",
    "dating": CAC_PLATFORMS + "OnlineDatingPlatform",
    "gaming": CAC_PLATFORMS + "GamePlatform",
    "video_streaming": CAC_PLATFORMS + "VideoStreamingPlatform",
    "dark_web": CAC_PLATFORMS + "DarkWebService",
    "classified_ads": UCO_OBSERVABLE + "ObservableObject",
    "telephony": UCO_OBSERVABLE + "ObservableObject",
    "other": UCO_OBSERVABLE + "ObservableObject",
}
CAPABILITY_REVIEW = ("proposed", "reviewed", "rejected")

# --- access (AfH H2) --------------------------------------------------------------------
ACCESS_FORMS = ("person_physical", "person_communicative", "representation", "material")

# --- harm (E) ---------------------------------------------------------------------------
# harm code: AfH H0 category (None = outside H0; feeds the closure test).
HARM_H0 = {
    "HARM_IN_PERSON_SEXUAL_ABUSE": "h1",
    "HARM_COERCED_SELF_GENERATED_IMAGERY": "h2",
    "HARM_PRODUCTION_IN_PERSON_RECORDED": None,
    "HARM_DISTRIBUTION_RECIRCULATION": "h3",
    "HARM_EXPOSURE_THREAT": "h4",
    "HARM_EXPOSURE_REALIZED": "h3",
    "HARM_COMMERCIAL_SEXUAL_EXPLOITATION": "h5",
    "HARM_SYNTHETIC_LIKENESS": "h6",
    "HARM_SEXUALIZED_CONTACT_ONLINE": None,
    "HARM_PSYCHOLOGICAL_DISTRESS_DOCUMENTED": None,
    "HARM_PHYSICAL_VIOLENCE_OR_CONTROL": None,
    "HARM_OTHER": None,
}
HARM_CODES = tuple(HARM_H0)
H0 = ("h1", "h2", "h3", "h4", "h5", "h6")

# --- temporal and relational structure (F) -----------------------------------------------
# BEFORE = known to precede, nothing implied about what lies between.
# MEETS  = immediately precedes (only with explicit sequence language).
ORDER_RELATIONS = ("BEFORE", "MEETS")
RELATION_TYPES = (
    "BEFORE", "MEETS", "OVERLAPS", "DURING", "SAME_TIME", "UNORDERED",
    "PART_OF", "REPEATS", "RESPONDS_TO", "BACKED_BY_THREAT", "INTERRUPTS",
    "RESUMES_AFTER", "SAME_MATERIAL", "SAME_ACT",
)
# SAME_ACT (R05): two source observations may describe one act. Status INFERRED = possible;
# UNSUPPORTED/CONTRADICTED = a candidate considered and rejected. Confirmed identity is one
# event citing every passage, never a DIRECT SAME_ACT. It never merges events, creates
# order or changes a count.
IDENTITY_RELATIONS = ("SAME_ACT",)
RELATION_BASIS = ("explicit_sequence_language", "dated_events", "count_windows", "document_structure", "coder_inference")
TIME_PRECISION = ("day", "month", "season", "year", "range")
TIME_BASIS = ("explicit_date", "date_range", "count_window", "enclosing_window", "relative_statement")
# enclosing_window (T2): the act's own passage is undated and the date comes from an enclosing
# count or conspiracy window. It is a constraint, never an observed date: status INFERRED.
REPETITION_KIND = ("single", "repeated_count_known", "repeated_count_unknown", "continuous_period")
TRACK_KINDS = ("victim", "undercover", "material", "co_offender_network", "case_procedure")
SUPPORT_FACETS = ("action", "actor", "target", "outcome", "time", "repetition", "platform", "feature",
                  "legal_status", "membership", "count", "configuration", "channel")

# --- platform interactions (I1-I3, I5) -------------------------------------------------
# mode: the act went through the platform; contact moved from/to it; or the act was done to
# the platform itself (deleting an account, a platform report). Only through/to feed level B.
INTERACTION_MODES = ("through", "from", "to", "acted_on")
LEVEL_B_MODES = ("through", "to")
AUDIENCES = ("one_to_one", "group", "public", "unknown")
# Channels are not platforms (I3): they never join the capability registry.
CHANNELS = ("sms", "voice_call", "email", "mail", "in_person", "unknown")
FEATURE_SETTINGS = ("on", "off", "default_on", "default_off", "unknown")
# Level-A availability of a capability at an event's time (I4)
AVAILABILITY = ("supported", "uncertain", "unsupported")
