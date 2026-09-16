# CaseLinker → CAC Ontology Mapping Plan

**Status:** Draft v1.0  
**Author:** Generated from codebase + ontology audit  
**Target file:** `ontology/features_to_cac.py`  
**CAC Ontology version:** 3.0.0 (ProjectVIC)  
**CaseLinker corpus:** ~5,092 ICAC cases in PostgreSQL

---

## Table of Contents

1. [Feature Inventory](#1-feature-inventory)
2. [CAC Ontology Target Classes](#2-cac-ontology-target-classes)
3. [Deterministic Mapping Dictionary](#3-deterministic-mapping-dictionary)
4. [NLP / Semantic Features](#4-nlp--semantic-features)
5. [Unmappable Features](#5-unmappable-features)
6. [Node Creation Strategy](#6-node-creation-strategy)
7. [Open Questions for Mrinaal](#7-open-questions-for-mrinaal)

---

## 1. Feature Inventory

### 1.1 `cases` Table Columns

These are the top-level PostgreSQL columns on the `cases` table. Fields marked **D** are deterministically extracted; fields marked **M** are manually ingested.

| Feature Key | Type | Source | Deterministic? | Example Values |
|---|---|---|---|---|
| `id` | `TEXT` (PK) | Manual / scraper | D | `azicac_2011_006` |
| `source` | `TEXT` | Manual / scraper | D | `AZICAC`, `SVICAC`, `wa_ag` |
| `source_url` | `TEXT` | Scraper | D | `https://...` |
| `date_start` | `TEXT` | Extracted / scraper | D | `2011-03`, `2014` |
| `date_end` | `TEXT` | Extracted / scraper | D | `2011-06`, `2014` |
| `victim_count` | `INTEGER` | `extract_victim_count()` regex | D | `1`, `3`, `12` |
| `perpetrator_count` | `INTEGER` | Extracted | D | `1`, `2` |
| `relationship_to_victim` | `TEXT` | `extract_relationship()` regex | D | `father`, `teacher`, `stranger`, `uncle`, `parent`, `sibling`, `cousin`, `mother`, `brother`, `sister`, `aunt` |
| `platforms_used` | `TEXT` (JSON list) | `extract_platforms()` via `_PLATFORM_SPECS` | D | `["Snapchat","Instagram"]` |
| `severity_indicators` | `TEXT` (JSON list) | `extract_severity()` regex | D | `["infant","under_12","sexual_abuse","multiple_perpetrators","very_young"]` |
| `case_topics` | `TEXT` (JSON list) | `extract_topics()` regex | D | `["production","csam","hands_on","family"]` |
| `tags` | `TEXT` | Manual editorial | M | freeform |
| `notes` | `TEXT` | Manual editorial | M | freeform narrative |
| `raw_data` | `TEXT` (JSON blob) | Scraper output | — | full source text + metadata |
| `extracted_features` | `TEXT` (JSON blob) | `slim_extracted_features_for_storage()` | D | see §1.3 |
| `created_at` / `updated_at` | `TIMESTAMP` | DB auto | — | — |

### 1.2 Satellite Tables

#### `victim_demographics`

| Feature Key | Type | Source | Deterministic? | Example Values |
|---|---|---|---|---|
| `case_id` | `TEXT` (FK) | — | — | — |
| `age_range` | `TEXT` | `extract_case_demographics()` | D | `8-12`, `13-15`, `under_10` |
| `region` | `TEXT` | NER / regex | D/NLP | `Arizona`, `Southeast` |
| `anonymized_id` | `TEXT` | Generated | D | `V-azicac-2011-001` |

#### `perpetrator_demographics`

| Feature Key | Type | Source | Deterministic? | Example Values |
|---|---|---|---|---|
| `case_id` | `TEXT` (FK) | — | — | — |
| `age_range` | `TEXT` | `extract_perpetrator_demographics()` | D | `30-40`, `25-35` |
| `region` | `TEXT` | NER / regex | D/NLP | `Mesa, AZ` |
| `anonymized_id` | `TEXT` | Generated | D | `P-azicac-2011-001` |
| `previous_conviction` | `TEXT` | `extract_previous_conviction()` regex | D | `true`, `false`, JSON obj |

#### `prosecution_outcomes`

| Feature Key | Type | Source | Deterministic? | Example Values |
|---|---|---|---|---|
| `case_id` | `TEXT` (FK) | — | — | — |
| `status` | `TEXT` | `extract_prosecution_outcome()` | D | `convicted`, `charged`, `arrested`, `pleaded_guilty` |
| `charges` | `TEXT` (JSON list) | regex parse | D | `[{"count":3,"charge":"CSAM Possession"}]` |
| `sentences` | `TEXT` (JSON) | regex parse | D | `{"jail":"15 years","probation":"lifetime"}` |

### 1.3 `extracted_features` JSON Blob Keys

These keys are stored inside the `extracted_features` column (everything in the case dict that is NOT in `_SLIM_EXCLUDED_KEYS`). At read time, they are merged into the flat case dict.

| Feature Key | Type | Source Function | Deterministic? | Example Values / Notes |
|---|---|---|---|---|
| `date_range` | `dict` | `extract_date_range()` | D | `{"start":"2011-03","end":"2011-06"}` |
| `case_demographics` | `dict` | `extract_case_demographics()` | D | `{"ages":[10,12],"age_range":{"min":10,"max":12},"gender":"female"}` |
| `perpetrator_age` | `int` or `list[int]` | `extract_perpetrator_demographics()` | D | `38`, `[28,45]` (multiple perps) |
| `perpetrator_registered_sex_offender` | `bool` | regex on case text | D | `true`, `false` |
| `previous_conviction` | `dict` or `bool` | `extract_previous_conviction()` | D | `{"is_registered":true,"age_at_first_offense":null}` |
| `investigation_type` | `TEXT` | `extract_investigation_info()` | D | `undercover`, `proactive`, `reactive`, `online`, `unknown` |
| `agencies_involved` | `list[str]` | `extract_investigation_info()` + NER merge | D/NLP | `["FBI","Mesa PD","AZICAC"]` |
| `organizations` | `list[str]` | NER extraction (merge layer) | NLP | `["Maricopa County Attorney's Office"]` |
| `locations` | `list[str]` | NER extraction (merge layer) | NLP | `["Mesa, Arizona","San Diego"]` |
| `prosecution_outcome` | `dict` | `extract_prosecution_outcome()` | D | `{"charges":[...],"booking_status":"convicted","jail":"15 years"}` |
| `evidence_volume` | `dict` | `extract_evidence_volume()` | D | `{"images":1500,"videos":20,"storage_size":"2TB","messages":null}` |
| `severity_phrases` | `list[str]` | `extract_severity_phrases()` | D | `["dangerous","out_of_control","stated"]` |
| `investigation_technology` | `list[str]` | `extract_technology_signals()` | D | `["PhotoDNA","CyberTipline","hash matching","CSAI Match"]` |
| `anonymization_network` | `list[str]` | `extract_technology_signals()` | D | `["Tor","dark web","cryptocurrency","I2P"]` |
| `p2p_clients` | `list[str]` | `extract_technology_signals()` | D | `["LimeWire","BitTorrent","Kazaa","Gigatribe"]` |
| `ml_features` | `dict` | semantic pipeline + NER | NLP | `{"semantic_severity":{...},"ner_entities":{...}}` |
| `comparison_values` | `dict` | `assign_comparison_values()` | D | see §1.4 |

### 1.4 `comparison_values` Sub-Keys (Feature Vectors)

These are **clustering/similarity artifacts** produced by `assign_comparison_values()`. They duplicate or summarize fields from the case dict and are used by the ML layer — they do NOT represent independent facts.

| Vector Key | Type | Contents |
|---|---|---|
| `platform_vector` | `list[str]` | copy of `platforms_used` |
| `demographic_vector` | `dict` | `case_age_range`, `victim_count`, `perpetrator_age` (list), `multiple_perpetrators`, `perpetrator_registered` |
| `relationship_vector` | `list[str]` | `[relationship_to_victim]` |
| `investigation_vector` | `dict` | `type`, `agencies` |
| `technology_signal_vector` | `dict` | `investigation_technology`, `anonymization_network`, `p2p_clients` |
| `evidence_vector` | `dict` | `images`, `videos`, `storage_size` |
| `temporal_value` | `str` or `null` | `date_range.start` |
| `topic_vector` | `list[str]` | copy of `case_topics` |
| `severity_vector` | `list[str]` | copy of `severity_indicators` + `multiple_perpetrators` flag |

### 1.5 Deterministic Topic Values (from `extract_topics()`)

All topics are mutually-non-exclusive strings appended to the `case_topics` list:

| Topic String | Detection Logic | Regex Cue |
|---|---|---|
| `production` | `_PRODUCTION_TOPIC_RE` phrase-level match | `production of`, `minor production`, `produced … videos/images`, `created … CSAM`, `took … photos` |
| `possession` | keyword match | `trading`, `downloading`, `possessing`, `collecting`, `possessed`, `traded`, `possession`, `dissemination` |
| `international` | country/keyword match | `Australia`, `Philippines`, `Japan`, `India`, `Thailand`, `international`, `overseas` |
| `multi_state` | count > 1 of US state names | 36-state list with word-boundary anchors |
| `hands_on` | sexual contact keywords | `rape`, `raped`, `raping`, `molest*`, `hands on`, `sexually abused`, `sexually assaulted` |
| `online_only` | online keyword (only if no `hands_on` and no sexual abuse) | `online`, `chat`, `trading images` |
| `family` | family-relationship keywords | `father`, `mother`, `parent`, `brother`, `sister`, `uncle`, `aunt`, `cousin`, `biological` |
| `stranger` | explicit keyword (only if no `family`) | `stranger` |
| `csam` | `_CSAM_TOPIC_RE` phrase-level match | `csam`, `child sexual abuse material`, `child pornography`, `child pornographic`, `child porn` |

Note: `grooming` is NOT a deterministic topic — it is injected by the merge layer only if `ml_features.semantic_severity["grooming"] >= 0.35`.

### 1.6 Severity Indicator Values (from `extract_severity()`)

| Severity String | Source |
|---|---|
| `infant` | regex on case text |
| `very_young` | regex on case text |
| `under_12` | regex on case text |
| `sexual_abuse` | regex on case text |
| `multiple_perpetrators` | injected by `assign_comparison_values()` when `perpetrator_age` is a list with >1 entries |
| `physical_abuse` | extracted as severity indicator (not a topic) |

### 1.7 Platform Values (from `_PLATFORM_SPECS`)

Complete canonical platform label inventory:

| Label | Category |
|---|---|
| `Facebook Messenger` | Messaging |
| `Facebook` | Social Media |
| `Instagram` | Social Media |
| `Snapchat` | Messaging / Ephemeral |
| `TikTok` | Social Media / Video |
| `Twitter / X` | Social Media |
| `WhatsApp` | Messaging |
| `Telegram` | Messaging |
| `Skype` | Messaging / VOIP |
| `Kik` | Messaging |
| `Discord` | Messaging / Community |
| `Omegle` | Anonymous Chat |
| `MeWe` | Social Media |
| `Roblox` | Gaming |
| `Minecraft` | Gaming |
| `Xbox Live` | Gaming |
| `PlayStation Network` | Gaming |
| `Fortnite` | Gaming |
| `Dropbox` | File Hosting |
| `Google Drive` | File Hosting |
| `Mega.nz` | File Hosting |
| `MediaFire` | File Hosting |
| `OneDrive` | File Hosting |
| `AOL Instant Messenger` | Messaging (legacy) |
| `IRC` | Messaging (legacy) |
| `Yahoo Chat` | Messaging (legacy) |
| `MySpace` | Social Media (legacy) |
| `Craigslist` | Classifieds |
| `YouTube Live` | Video Streaming |
| `YouTube` | Video Streaming |
| `Twitch` | Video Streaming |
| `Webcam platform` | Video Streaming / Adult |
| `online` | Generic (non-specific) |
| `chat` | Generic (non-specific) |
| `social media` | Generic (non-specific) |

Note: `_GENERIC_PLATFORMS = frozenset({"online", "social media", "chat"})` is defined in `scripts/verify/verify_claims.py` for stats exclusion.

### 1.8 Semantic Concepts (`semantic_concepts.py`)

Detected via cosine similarity against sentence-transformer embeddings (`all-MiniLM-L6-v2`, `normalize_embeddings=True`, `min_score=0.35`). Written to `ml_features.semantic_severity`.

| Concept Key | Description (from `_CONCEPT_TEXT`) | Is Production? |
|---|---|---|
| `dangerous` | dangerous/threatening behavior | — |
| `stated` | stated/described activity | — |
| `told` | told/reported activity | — |
| `continue` | ongoing/continuing behavior | — |
| `attacked` | physical attack/assault | — |
| `out_of_control` | uncontrolled behavior | — |
| `violent` | violent behavior | — |
| `obscene` | obscene material | — |
| `assault` | assault/battery | — |
| `abuse` | abuse/mistreatment | — |
| `depictions` | visual depictions of minors | — |
| `possession_csam` | possession of child sexual abuse material | False |
| `production_csam` | production of child sexual abuse material | True |
| `account_platform` | platform/account used for offense | False |
| `online_platforms` | online platforms involved | — |
| `registered_sex_offender` | registered sex offender status | — |
| `probation_violation` | probation violation | — |
| `paraphilia_fetish` | paraphilia or fetish behavior | — |
| `evidence_seizure` | evidence seized | — |
| `dissemination` | dissemination/distribution | — |
| `exploitive_positions` | positions of trust exploitation | — |
| `large_collection` | large collection of material | — |
| `produced_evidence` | evidence of production | False |
| `created_committee_or_entity` | created organization for offense | False |
| `created_account_for_storage` | created account to store material | False |
| `grooming` | grooming behavior | — |
| `sextortion` | sextortion | — |
| `ai_and_internet_tools` | AI or internet tools used | — |
| `online_luring_social_engineering` | online luring / social engineering | — |
| `criminal_networks_trafficking` | criminal networks / trafficking | — |
| `law_enforcement_operations` | law enforcement operation details | — |

Merge-layer thresholds (from `merge_processing.py`):
- `possession_csam >= 0.5` → append `possession` to `case_topics`
- `grooming >= 0.35` → append `grooming` to `severity_indicators`

---

## 2. CAC Ontology Target Classes

### Namespaces

| Prefix | URI |
|---|---|
| `cac-core:` | `https://cacontology.projectvic.org/core#` |
| `cacontology:` | `https://cacontology.projectvic.org#` |
| `cacontology-grooming:` | `https://cacontology.projectvic.org/grooming#` |
| `cacontology-custodial:` | `https://cacontology.projectvic.org/custodial#` |
| `cacontology-platforms:` | `https://cacontology.projectvic.org/platforms#` |
| `cacontology-legal-outcomes:` | `https://cacontology.projectvic.org/legal-outcomes#` |
| `cacontology-sextortion:` | `https://cacontology.projectvic.org/sextortion#` |
| `cacontology-detection:` | `https://cacontology.projectvic.org/detection#` |
| `cacontology-production:` | `https://cacontology.projectvic.org/production#` |
| `cacontology-taskforce:` | `https://cacontology.projectvic.org/taskforce#` |
| `cacontology-us-ncmec:` | `https://cacontology.projectvic.org/us/ncmec#` |
| `cacontology-multi:` | `https://cacontology.projectvic.org/multi-jurisdiction#` |

### Five Spine Branches

All classes ultimately root in one of five spine categories from `cacontology-core-spine.ttl`:

| Spine Branch | gUFO Root | Meaning |
|---|---|---|
| `cac-core:EnduringEntity` | `gufo:Object` | Persistent things: people, orgs, platforms, artifacts |
| `cac-core:Event` | `gufo:Event` | Occurrences with temporal extent |
| `cac-core:Role` | `gufo:Role` | Capacities played by entities in situations |
| `cac-core:Phase` | `gufo:Phase` | Time-bounded states an entity passes through |
| `cac-core:Situation` | `gufo:Situation` | Ongoing circumstances (contextual frames) |

### 2.1 Core Investigation Classes (`cacontology-core.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology:CACInvestigation` | EnduringEntity | `hasPhase`, `investigationStatus`, `currentPhase` | The investigation case as a whole; the root node for a CaseLinker case |
| `cacontology:ChildSexualAbuseEvent` | Event | `severityLevel` (0–3), `involvesVictim`, `involvesOffender`, `occursDuringPhase` | Abstract parent for all criminal exploitation events |
| `cacontology:CSAMIncident` | Event | `producesArtifact`, `depictsChild`, `severityLevel` | Any incident involving CSAM possession/distribution (subclass of ChildSexualAbuseEvent) |
| `cacontology:DigitallyGeneratedCSAMIncident` | Event | inherits CSAMIncident | AI-generated CSAM variant |
| `cacontology:LiveStreamingCSA` | Event | inherits ChildSexualAbuseEvent | Live-stream sexual abuse |
| `cacontology:GroomingSolicitation` | Event | inherits ChildSexualAbuseEvent | Grooming/solicitation event; further typed by grooming module |
| `cacontology:Sextortion` | Event | inherits ChildSexualAbuseEvent | Sextortion event; further typed by sextortion module |
| `cacontology:VictimRole` | Role | `hasRoleBeginPoint`, `hasRoleEndPoint`, `involvesVictim` | Victim capacity |
| `cacontology:OffenderRole` | Role | `hasRoleBeginPoint`, `hasRoleEndPoint`, `involvesOffender` | Offender capacity |
| `cacontology:InvestigatorRole` | Role | — | Investigator capacity |
| `cacontology:InitialPhase` | Phase | `hasPhaseBeginPoint`, `phaseDuration` | Investigation lifecycle: initial phase |
| `cacontology:AnalysisPhase` | Phase | — | Investigation lifecycle: analysis phase |
| `cacontology:LegalProcessPhase` | Phase | — | Investigation lifecycle: legal process phase |
| `cacontology:ConspiracyToCommitCSA` | Event | `conspiracyMemberCount`, `conspiracyDuration`, `indictmentCounts` | Multi-defendant offense |
| `cacontology:CriminalEnterprise` | EnduringEntity | — | Criminal organization |

### 2.2 Grooming Classes (`cacontology-grooming.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-grooming:OnlineGrooming` | Event | `groomingStage`, `behaviorDuration`, `communicationFrequency` | Online grooming behavior (top-level grooming type) |
| `cacontology-grooming:GroomingPhase` | Phase | `hasPhaseBeginPoint`, `hasPhaseEndPoint` | One of: Initial Contact, Trust Building, Isolation, Sexualization, Exploitation, Maintenance |
| `cacontology-grooming:InitialContactPhase` | Phase | `timeOfContact`, `contactFrequency`, `anonymousContactMethod` | First contact with victim |
| `cacontology-grooming:TrustBuildingPhase` | Phase | `usesGifts`, `emotionalTone`, `rolePlayingTactic` | Building trust / relationship |
| `cacontology-grooming:IsolationPhase` | Phase | `isolationMethod` | Isolating victim from support |
| `cacontology-grooming:SexualizationPhase` | Phase | `explicitnessLevel`, `contentType` | Introduction of sexual content |
| `cacontology-grooming:ExploitationPhase` | Phase | `requestsSecrecy`, `usesThreats`, `victimCompliance` | Active exploitation |
| `cacontology-grooming:MaintenancePhase` | Phase | `manipulationTechnique` | Maintaining ongoing abuse |
| `cacontology-grooming:EscalationPattern` | Situation | `escalationRate`, `patternConfidence` | Online-to-offline escalation |
| `cacontology-grooming:OnlineToOfflineProgression` | Situation | — | Pattern where online contact progresses to physical meeting |
| `cacontology-grooming:PhysicalMeetingArrangement` | Event | `meetingLocationSpecified`, `transportationProposed` | Arranged physical meeting |
| `cacontology-grooming:TravelArrangement` | Event | `crossesStateBoundaries` | Travel to meet victim |
| `cacontology-grooming:ChildVictim` | Role | — | Child victim role in grooming context |
| `cacontology-grooming:OnlinePredator` | Role | `impersonatesRole`, `accountsUsed` | Offender role in online grooming |
| `cacontology-grooming:EducatorGrooming` | Event | `leveragesPosition`, `institutionsTargeted` | Grooming in educational context (subclass of OnlineGrooming) |
| `cacontology-grooming:SubstanceFacilitatedGrooming` | Event | `substanceType`, `impairmentLevel` | Grooming using substances |
| `cacontology-grooming:RapidEscalationGrooming` | Event | `escalationTimeframe`, `sameDayProgression`, `skippedPhases` | Grooming with unusually fast escalation |

### 2.3 Custodial / Position of Trust Classes (`cacontology-custodial.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-custodial:PositionOfTrust` | Role | `authorityLevel`, `authorityScope`, `trustLevel`, `accessLevel` | Abstract role for authority figures with access to children |
| `cacontology-custodial:AuthorityFigure` | Role | same | Subclass of PositionOfTrust |
| `cacontology-custodial:Teacher` | Role | — | Teacher/educator in position of trust |
| `cacontology-custodial:Coach` | Role | — | Coach/sports instructor |
| `cacontology-custodial:Mentor` | Role | — | Mentor role |
| `cacontology-custodial:Guardian` | Role | — | Legal guardian |
| `cacontology-custodial:Babysitter` | Role | — | Childcare provider |
| `cacontology-custodial:Relative` | Role | — | Family relative (non-parent) |
| `cacontology-custodial:FamilyFriend` | Role | — | Family friend with access |
| `cacontology-custodial:ChildcareProvider` | Role | — | Professional childcare |
| `cacontology-custodial:CaregiverRelationship` | EnduringEntity | `relationshipType`, `relationshipDuration`, `violationType` | Caregiver-child relationship |
| `cacontology-custodial:FamilialRelationship` | EnduringEntity | `relationshipType`, `contactRestrictionType` | Family relationship |
| `cacontology-custodial:TrustViolation` | Event | `violationSeverity`, `violationPattern`, `breachDuration` | Event where position of trust was violated |
| `cacontology-custodial:CustodialAbuse` | Event | inherits TrustViolation | Abuse within custodial relationship |

### 2.4 Platform Classes (`cacontology-platforms.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-platforms:SocialMediaPlatform` | EnduringEntity | `platformType`, `encryptionLevel`, `primaryUserBase`, `csaiDetectionEnabled` | Social media service (Facebook, Instagram, TikTok, etc.) |
| `cacontology-platforms:MessagingService` | EnduringEntity | `encryptionLevel`, `requiresRegistration`, `conversationLogging` | Messaging app (WhatsApp, Telegram, Kik, etc.) |
| `cacontology-platforms:VideoStreamingPlatform` | EnduringEntity | `moderationPresence`, `hashMatchingEnabled` | Video streaming (YouTube, Twitch, etc.) |
| `cacontology-platforms:FileHostingService` | EnduringEntity | `userDataRetentionPeriod`, `contentRetentionPeriod` | File sharing (Dropbox, Mega.nz, etc.) |
| `cacontology-platforms:GamePlatform` | EnduringEntity | `ageVerificationMethod`, `allowsAnonymousChat` | Gaming platform (Roblox, Xbox Live, etc.) |
| `cacontology-platforms:AnonymousChatPlatform` | EnduringEntity | `anonymityLevel`, `guestAccountsAllowed`, `identityVerificationRequired`, `anonymousUserDataRetention` | Anonymous chat (Omegle, IRC, etc.) |
| `cacontology-platforms:DarkWebService` | EnduringEntity | — | Dark web services |
| `cacontology-platforms:ElectronicServiceProvider` | EnduringEntity | `acceptsLegalProcess`, `emergencyDisclosureCapable`, `responseTimeFrame` | Platform as legal entity receiving process |
| `cacontology-platforms:ContentModerationAction` | Event | `moderationDecision`, `reviewLatencyHours` | Platform content moderation event |
| `cacontology-platforms:CyberTipAnalysis` | Event | — | NCMEC tip analysis action (in platforms context) |

### 2.5 Legal Outcome Classes (`cacontology-legal-outcomes.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-legal-outcomes:CriminalCharge` | EnduringEntity | `chargeClassification`, `electronicCommunicationUsed`, `travelOccurred` | A filed criminal charge |
| `cacontology-legal-outcomes:CSAM_Possession` | EnduringEntity | inherits FederalCharge | Federal possession charge (18 U.S.C.) |
| `cacontology-legal-outcomes:CSAM_Distribution` | EnduringEntity | — | Federal distribution charge |
| `cacontology-legal-outcomes:CSAM_Production` | EnduringEntity | — | Federal production charge |
| `cacontology-legal-outcomes:CSAM_CausingProduction` | EnduringEntity | — | Federal causing-production charge |
| `cacontology-legal-outcomes:OnlineEnticement` | EnduringEntity | `solicitationType`, `communicationPlatform` | Online enticement charge |
| `cacontology-legal-outcomes:SextortionCharge` | EnduringEntity | — | Sextortion charge |
| `cacontology-legal-outcomes:SexTrafficking` | EnduringEntity | — | Sex trafficking charge |
| `cacontology-legal-outcomes:CriminalSentence` | AssessmentResult | `sentenceConcurrency` | Sentence imposed |
| `cacontology-legal-outcomes:PrisonSentence` | AssessmentResult | — | Prison term |
| `cacontology-legal-outcomes:LifeImprisonmentSentence` | AssessmentResult | — | Life sentence |
| `cacontology-legal-outcomes:MandatoryMinimumSentencing` | AssessmentResult | — | Mandatory minimum applied |
| `cacontology-legal-outcomes:ProbationSentence` | AssessmentResult | — | Probation |
| `cacontology-legal-outcomes:SupervisedRelease` | AssessmentResult | — | Supervised release |
| `cacontology-legal-outcomes:LegalProceeding` | Event | `hasLegalPhase`, `bailStatus` | Trial / legal proceeding |

### 2.6 Sextortion Classes (`cacontology-sextortion.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-sextortion:SextortionIncident` | Event | `victimCount`, `victimAgeGroup`, `incidentDuration`, `progressionStage` | Sextortion incident |
| `cacontology-sextortion:AgeDeceptionTactic` | Event | `claimedAge`, `actualAge`, `falsePersonaType` | Age deception used in sextortion |
| `cacontology-sextortion:ThreatMechanism` | Event | `threatType`, `threatSpecificity`, `threatFollowThrough` | Threat used in extortion |
| `cacontology-sextortion:ExtortionDemand` | Event | `demandType`, `monetaryAmount`, `giftCardType` | Demand made |
| `cacontology-sextortion:SextortionCommunication` | EnduringEntity | `conversationLength`, `explicitnessLevel` | Communication artifact |

### 2.7 CSAM Detection Classes (`cacontology-detection.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-detection:ContentHashingAction` | Event | `photoDNAValue`, `perceptualHashValue`, `hashAlgorithm`, `matchType` | Hash-based CSAM detection action |
| `cacontology-detection:DetectionResult` | AssessmentResult | `confidenceScore`, `sarClassification`, `copineClassification` | Result of detection |
| `cacontology-detection:ClassificationResult` | AssessmentResult | `sarClassification` (1–5), `copineClassification`, `ageEstimate` | SAR/COPINE classification result |
| `cacontology-detection:RiskStratificationResult` | AssessmentResult | `riskScore`, `riskTier`, `riskRationale` | Risk tier assignment |
| SAR SKOS concepts: `sar-1` through `sar-5` | — | — | Severity Assessment Rating scale |

### 2.8 CSAM Production Classes (`cacontology-production.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-production:ProductionOffense` | Event | `productionPeriod`, `imageCount`, `videoCount`, `totalContentVolume`, `sessionCount` | CSAM production offense |
| `cacontology-production:LiveProductionEvent` | Event | inherits ProductionOffense | Live-streamed production |
| `cacontology-production:PrivateSpaceSurveillance` | Event | `privacyExpectation`, `surveillanceAngle` | Hidden-camera surveillance offense |
| `cacontology-production:HiddenRecordingDevice` | EnduringEntity | `deviceBrand`, `concealmentMethod`, `concealmentLocation` | Hidden recording equipment |
| `cacontology-production:ProducedContent` | EnduringEntity | `evidenceRecovered`, `metadataPreserved`, `forensicValue` | Produced image/video artifact |
| `cacontology-production:ProductionLocation` | EnduringEntity | `productionMethod`, `recordingQuality` | Where production occurred |

### 2.9 Task Force Classes (`cacontology-taskforce.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-taskforce:ICACtaskForce` | EnduringEntity | `taskForceId`, `coverageArea`, `memberCount`, `agencyCount`, `cyberTipsReceived`, `arrestsSince2019` | ICAC Task Force |
| `cacontology-taskforce:StateICACtaskForce` | EnduringEntity | — | State-level ICAC TF |
| `cacontology-taskforce:TaskForceOperation` | Event | `operationType`, `operationScale` | Single TF operation |
| `cacontology-taskforce:ProactiveOperation` | Event | — | Proactive sting/operation |
| `cacontology-taskforce:ReactiveOperation` | Event | — | Reactive investigation |
| `cacontology-taskforce:DigitalForensicsUnit` | EnduringEntity | — | Forensics unit within TF |
| `cacontology-taskforce:UndercoverUnit` | EnduringEntity | — | Undercover unit |

### 2.10 NCMEC CyberTip Classes (`cacontology-us-ncmec.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-us-ncmec:NCMECCybertipReport` | EnduringEntity | `processingTime`, `priorityLevel`, `validationStatus` | A CyberTipline report |
| `cacontology-us-ncmec:OnlineEnticementIncident` | EnduringEntity | `incidentCode` ("OE") | Enticement tip type |
| `cacontology-us-ncmec:TaskForceReferral` | Event | `referralJurisdiction`, `urgencyLevel` | Referral to task force from NCMEC |
| `cacontology-us-ncmec:SextortionAnnotation` | EnduringEntity | — | Sextortion annotation on a tip |

### 2.11 Multi-Jurisdiction Classes (`cacontology-multi.ttl`)

| Class | Spine | Key Properties | Description |
|---|---|---|---|
| `cacontology-multi:MultiJurisdictionalInvestigation` | Event | `jurisdictionCount`, `agencyCount`, `crossesBorders`, `statesInvolved` | Multi-agency investigation |
| `cacontology-multi:ProjectSafeChildhoodOperation` | Event | `operationName`, `totalArrests` | PSC operation |
| `cacontology-multi:FederalAgency` | EnduringEntity | — | Federal law enforcement (FBI, HSI, etc.) |
| `cacontology-multi:StateAgency` | EnduringEntity | — | State law enforcement |
| `cacontology-multi:LocalAgency` | EnduringEntity | — | Local law enforcement |
| `cacontology-multi:InterstateTransportationOffense` | Event | `transportationIntent`, `statesCrossed` | Interstate transport of victim |
| `cacontology-multi:JurisdictionalHandoff` | Event | `primaryJurisdiction` | Case passed between jurisdictions |

---

## 3. Deterministic Mapping Dictionary

### 3.1 PLATFORM_MAP

**Fiat payment apps (no CAC platform class):** Cash App and similar fiat P2P transfer services have no `cacontology-platforms:` class in CAC v3.0.0 (`CryptocurrencyService` is crypto-only). CaseLinker still extracts them to `platforms_used` and tracks the financial-transfer misuse surface in the Q1 pipeline as `FinancialTransferService` only. In the knowledge graph, `Cash App` is listed in `PLATFORM_MAP` with the `_SKIP` sentinel (no platform node). For sextortion cases with a `SextortionCharge` in prosecution and Cash App in `platforms_used`, `features_to_cac.py` emits `cacontology-sextortion:MonetaryDemand` linked via `makesDemand` to the sextortion incident. **Gap to raise with Project VIC:** `PaymentTransferService` / digital-wallet platform class for fiat rails.

**Values to map:** 35 (from `_PLATFORM_SPECS`)  
**Mapped confidently:** 30  
**Ambiguous / needs review:** 5 (marked †)

| CaseLinker Value | CAC Class | CAC Module | Notes |
|---|---|---|---|
| `Facebook` | `SocialMediaPlatform` | `cacontology-platforms:` | Specific IRI: `cacontology-platforms:Facebook` (shared singleton) |
| `Facebook Messenger` | `MessagingService` | `cacontology-platforms:` | Specific IRI: `cacontology-platforms:FacebookMessenger` |
| `Instagram` | `SocialMediaPlatform` | `cacontology-platforms:` | |
| `Snapchat` | `MessagingService` | `cacontology-platforms:` | Ephemeral messaging; `encryptionLevel=end-to-end` |
| `TikTok` | `SocialMediaPlatform` | `cacontology-platforms:` | Also `VideoStreamingPlatform` — **Q7.4** |
| `Twitter / X` | `SocialMediaPlatform` | `cacontology-platforms:` | |
| `WhatsApp` | `MessagingService` | `cacontology-platforms:` | E2E encrypted |
| `Telegram` | `MessagingService` | `cacontology-platforms:` | Note: can also function as channel/group |
| `Skype` | `MessagingService` | `cacontology-platforms:` | VOIP capable |
| `Kik` | `MessagingService` | `cacontology-platforms:` | Anonymous-ish; minimal verification |
| `Discord` | `MessagingService` | `cacontology-platforms:` | Also community/gaming; `MessagingService` is primary type |
| `Omegle` | `AnonymousChatPlatform` | `cacontology-platforms:` | `guestAccountsAllowed=true`, `identityVerificationRequired=false` |
| `MeWe` | `SocialMediaPlatform` | `cacontology-platforms:` | |
| `Roblox` | `GamePlatform` | `cacontology-platforms:` | Has in-game chat — set `allowsAnonymousChat=true` |
| `Minecraft` | `GamePlatform` | `cacontology-platforms:` | |
| `Xbox Live` | `GamePlatform` | `cacontology-platforms:` | |
| `PlayStation Network` | `GamePlatform` | `cacontology-platforms:` | |
| `Fortnite` | `GamePlatform` | `cacontology-platforms:` | |
| `Dropbox` | `FileHostingService` | `cacontology-platforms:` | |
| `Google Drive` | `FileHostingService` | `cacontology-platforms:` | |
| `Mega.nz` | `FileHostingService` | `cacontology-platforms:` | E2E encrypted file hosting; `_REVOLVER_LABEL_SYNONYMS` entry |
| `MediaFire` | `FileHostingService` | `cacontology-platforms:` | |
| `OneDrive` | `FileHostingService` | `cacontology-platforms:` | |
| `AOL Instant Messenger` | `MessagingService` | `cacontology-platforms:` | Legacy; set `platformType=legacy` |
| `IRC` | `AnonymousChatPlatform` | `cacontology-platforms:` | Anonymous, no registration required |
| `Yahoo Chat` | `MessagingService` | `cacontology-platforms:` | Legacy |
| `MySpace` | `SocialMediaPlatform` | `cacontology-platforms:` | Legacy |
| `Craigslist` | `SocialMediaPlatform` | `cacontology-platforms:` | † Classifieds/marketplace — no exact CAC class; `SocialMediaPlatform` is a rough fit. Consider `OnlineDatingPlatform` if context is solicitation. **Q7.4** |
| `YouTube Live` | `VideoStreamingPlatform` | `cacontology-platforms:` | |
| `YouTube` | `VideoStreamingPlatform` | `cacontology-platforms:` | |
| `Twitch` | `VideoStreamingPlatform` | `cacontology-platforms:` | |
| `Webcam platform` | `VideoStreamingPlatform` | `cacontology-platforms:` | † Generic; actual platform unknown. Set `allowsAnonymousChat=true`. **Q7.4** |
| `online` † | SKIP — `_GENERIC_PLATFORMS` | — | Non-specific; do not create platform node. Flag case for review. |
| `chat` † | SKIP — `_GENERIC_PLATFORMS` | — | Non-specific; do not create platform node. |
| `social media` † | SKIP — `_GENERIC_PLATFORMS` | — | Non-specific; do not create platform node. |

**Strategy for shared platform IRIs:**  
Platforms are shared singletons in the graph (e.g., `ex:platform/snapchat` is one node referenced by many cases). Do not create a new platform node per case — look up or create once, then reuse via `cac-core:usesMethod` or equivalent edge from the investigation node.

---

### 3.2 TOPIC_MAP

**Values to map:** 9 deterministic topics + `grooming` (injected by merge layer)  
**Mapped confidently:** 10/10

| CaseLinker Topic | Primary CAC Class | CAC Module | Secondary / Decomposition | Notes |
|---|---|---|---|---|
| `production` | `cacontology-production:ProductionOffense` | `cacontology-production:` | + `cacontology-legal-outcomes:CSAM_Production` | Create ProductionOffense node; link to CSAM_Production charge if charges exist |
| `possession` | `cacontology:CSAMIncident` | `cacontology:` | + `cacontology-legal-outcomes:CSAM_Possession` | Core CSAM event node; link to Possession charge if charges exist |
| `csam` | `cacontology:CSAMIncident` | `cacontology:` | + `cacontology-legal-outcomes:CSAM_Possession` or `CSAM_Distribution` | Similar to `possession`; `csam` is broader — create CSAMIncident regardless |
| `international` | `cacontology-multi:MultiJurisdictionalInvestigation` | `cacontology-multi:` | Set `crossesBorders=true`, `jurisdictionCount≥2` | May also require `InternationalAgency` node |
| `multi_state` | `cacontology-multi:MultiJurisdictionalInvestigation` | `cacontology-multi:` | Set `statesInvolved`, `crossesBorders=false` | Domestic multi-state; set `jurisdictionCount` from state count in text |
| `hands_on` | `cacontology:ChildSexualAbuseEvent` | `cacontology:` | Set `severityLevel=3`; + `cacontology-custodial:CustodialAbuse` if relationship is familial | Physical contact offense — highest severity |
| `online_only` | `cacontology:GroomingSolicitation` | `cacontology:` | + `cacontology-grooming:OnlineGrooming` | No physical contact; primarily online |
| `family` | `cacontology-custodial:FamilialRelationship` | `cacontology-custodial:` | + `CaregiverRelationship` if role is parent/guardian | Creates a Relationship node in addition to event node |
| `stranger` | `cacontology-grooming:OnlinePredator` (Role) | `cacontology-grooming:` | — | Offender role classification |
| `grooming` | `cacontology-grooming:OnlineGrooming` | `cacontology-grooming:` | + `GroomingPhases` if detectable from text | NLP-injected (merge layer); include with `cac-core:hasConfidence` score from `ml_features` |

---

### 3.3 INVESTIGATION_TYPE_MAP

**Values to map:** 5  
**Mapped confidently:** 5/5

| CaseLinker Value | Primary CAC Class | CAC Module | Notes |
|---|---|---|---|
| `undercover` | `cacontology-taskforce:UndercoverUnit` + `cacontology-taskforce:ProactiveOperation` | `cacontology-taskforce:` | Investigation involved undercover officer/decoy |
| `proactive` | `cacontology-taskforce:ProactiveOperation` | `cacontology-taskforce:` | Proactive sting or monitoring operation |
| `reactive` | `cacontology-taskforce:ReactiveOperation` | `cacontology-taskforce:` | Reactive to a complaint or CyberTip |
| `online` | `cacontology-taskforce:TaskForceOperation` | `cacontology-taskforce:` | Generic online investigation — use base class |
| `unknown` | `cacontology:CACInvestigation` only | `cacontology:` | Do not create operation node; set `investigationStatus=unknown` |

---

### 3.4 PROSECUTION_MAP

**Values to map:** `status` field from `prosecution_outcomes` + `charges` and `sentences` sub-fields.

#### Prosecution Status → Investigation Phase

| CaseLinker `status` | CAC Phase / Event | Notes |
|---|---|---|
| `arrested` | `cacontology:InitialPhase` (ongoing) | Set `currentPhase=InitialPhase` |
| `charged` | `cacontology:LegalProcessPhase` | |
| `convicted` | `cacontology-legal-outcomes:SentencingPhase` (complete) | |
| `pleaded_guilty` | `cacontology-legal-outcomes:PleaBargaining` (complete) | |
| `acquitted` | `cacontology-legal-outcomes:TrialProceeding` (complete, not guilty) | |

#### Charge Type → CAC Criminal Charge Class

| CaseLinker Charge String Pattern | CAC Class | Module |
|---|---|---|
| `CSAM Possession` / `possession of child pornography` | `cacontology-legal-outcomes:CSAM_Possession` | `cacontology-legal-outcomes:` |
| `CSAM Distribution` / `distribution of child pornography` | `cacontology-legal-outcomes:CSAM_Distribution` | |
| `CSAM Production` / `production of child pornography` | `cacontology-legal-outcomes:CSAM_Production` | |
| `CSAM Causing Production` / `coercion and enticement` | `cacontology-legal-outcomes:CSAM_CausingProduction` | |
| `Online Enticement` / `luring` | `cacontology-legal-outcomes:OnlineEnticement` | |
| `Sex Trafficking` / `trafficking` | `cacontology-legal-outcomes:SexTrafficking` | |
| `Sextortion` | `cacontology-legal-outcomes:SextortionCharge` | |
| `Traveling to meet a minor` | `cacontology-legal-outcomes:TravelingToMeetAfterComputerLure` | |

Note: CaseLinker charge strings are free-text from regex parsing. The mapper should apply fuzzy/keyword matching to normalize to one of the above classes.

#### Sentence → CAC Sentence Class

| CaseLinker Sentence Pattern | CAC Class | Key Property |
|---|---|---|
| `N years` prison | `cacontology-legal-outcomes:PrisonSentence` | duration |
| `life` / `life imprisonment` | `cacontology-legal-outcomes:LifeImprisonmentSentence` | — |
| `N months probation` | `cacontology-legal-outcomes:ProbationSentence` | duration |
| `supervised release` | `cacontology-legal-outcomes:SupervisedRelease` | duration |
| `$N fine` | `cacontology-legal-outcomes:MonetaryPenalty` | amount |
| `mandatory minimum` | `cacontology-legal-outcomes:MandatoryMinimumSentencing` | — |

---

### 3.5 SEVERITY_MAP

Severity indicators decompose into multiple CAC nodes and property values.

**Values to map:** 6 (`infant`, `very_young`, `under_12`, `sexual_abuse`, `multiple_perpetrators`, `physical_abuse`)  

| Severity Indicator | Decomposition | CAC Target | How to Apply |
|---|---|---|---|
| `infant` | Victim age signal | `cacontology:CSAMIncident` (or `ChildSexualAbuseEvent`) | Set `severityLevel=3`; set `cacontology-detection:ageEstimate="<2"` on ClassificationResult; set `victimAge` on production/grooming nodes |
| `very_young` | Victim age signal | Same as above | Set `severityLevel=2 or 3`; set `ageEstimate="<6"` |
| `under_12` | Victim age signal | Same | `severityLevel=2`; `ageEstimate="<12"` |
| `sexual_abuse` | Physical contact | `cacontology:ChildSexualAbuseEvent` | Set `severityLevel=3` on event node |
| `multiple_perpetrators` | Offender count | `cacontology:ConspiracyToCommitCSA` | Create conspiracy node with `conspiracyMemberCount≥2`; also creates multiple `OffenderRole` nodes |
| `physical_abuse` | Physical contact | `cacontology:ChildSexualAbuseEvent` | `severityLevel=3`; distinguishable from `sexual_abuse` by absence of sexual contact regex (note: physical_abuse is severity only, hands_on is topic) |

**Severity level integer mapping** (for `cacontology:severityLevel`):

| Conditions | `severityLevel` |
|---|---|
| No severity indicators | 0 |
| `under_12` only | 2 |
| `very_young` | 2 |
| `infant` | 3 |
| `sexual_abuse` OR `physical_abuse` | 3 |
| `multiple_perpetrators` | +1 to base (capped at 3) |

---

### 3.6 ROLE_MAP

Mapping from `relationship_to_victim` (extracted string) and occupational cues to CAC Role and Relationship classes.

**Values identified in codebase:** `father`, `mother`, `parent`, `brother`, `sister`, `sibling`, `uncle`, `aunt`, `cousin`, `teacher`, `stranger` (default)  
**Additionally from semantic detection:** `coach`, `mentor`, `babysitter`, `family friend`, `childcare provider`, `guardian`  
**Mapped confidently:** 13+

| CaseLinker Value | Primary CAC Role/Class | CAC Module | Secondary Node | Notes |
|---|---|---|---|---|
| `father` | `cacontology-custodial:FamilialRelationship` | `cacontology-custodial:` | + `OffenderRole` | Set `relationshipType=father`; creates TrustViolation |
| `mother` | `cacontology-custodial:FamilialRelationship` | `cacontology-custodial:` | + `OffenderRole` | Set `relationshipType=mother` |
| `parent` | `cacontology-custodial:CaregiverRelationship` | `cacontology-custodial:` | + `OffenderRole` | Generic parent when father/mother not specified |
| `brother` | `cacontology-custodial:FamilialRelationship` | `cacontology-custodial:` | + `OffenderRole` | Set `relationshipType=sibling` |
| `sister` | `cacontology-custodial:FamilialRelationship` | `cacontology-custodial:` | + `OffenderRole` | Set `relationshipType=sibling` |
| `sibling` | `cacontology-custodial:FamilialRelationship` | `cacontology-custodial:` | | |
| `uncle` | `cacontology-custodial:FamilialRelationship` + `Relative` | `cacontology-custodial:` | | Set `relationshipType=uncle` |
| `aunt` | `cacontology-custodial:FamilialRelationship` + `Relative` | `cacontology-custodial:` | | Set `relationshipType=aunt` |
| `cousin` | `cacontology-custodial:FamilialRelationship` + `Relative` | `cacontology-custodial:` | | |
| `teacher` | `cacontology-custodial:Teacher` (PositionOfTrust) | `cacontology-custodial:` | + `TrustViolation`, `AuthorityAbuse` | Set `authorityLevel=high`, `accessLevel=supervised` |
| `coach` | `cacontology-custodial:Coach` (PositionOfTrust) | `cacontology-custodial:` | + `TrustViolation` | |
| `mentor` | `cacontology-custodial:Mentor` (PositionOfTrust) | `cacontology-custodial:` | | |
| `babysitter` | `cacontology-custodial:Babysitter` (PositionOfTrust) | `cacontology-custodial:` | | |
| `guardian` | `cacontology-custodial:Guardian` (PositionOfTrust) | `cacontology-custodial:` | + `CaregiverRelationship` | |
| `family friend` | `cacontology-custodial:FamilyFriend` (PositionOfTrust) | `cacontology-custodial:` | | |
| `stranger` | `cacontology-grooming:OnlinePredator` | `cacontology-grooming:` | No custodial relationship node | No relationship or trust node; offender role only |
| *(absent / unknown)* | `cacontology:OffenderRole` only | `cacontology:` | — | Minimal node; do not fabricate relationship |

---

### 3.7 AGENCY_MAP

**Problem:** `agencies_involved` is a free-text list extracted from case narratives. There are ~2,864 unique strings in the corpus (estimated from NER layer).

**Strategy (do NOT map all 2,864 individually):**

#### Tier 1 — Federal agencies (map by name pattern to `FederalAgency`)
These appear in nearly every case with task force involvement:

| Agency Pattern | CAC Class | Notes |
|---|---|---|
| `FBI` / `Federal Bureau of Investigation` | `cacontology-multi:FederalAgency` | Set `agencyName=FBI` |
| `HSI` / `Homeland Security Investigations` | `cacontology-multi:FederalAgency` | |
| `ICE` / `Immigration and Customs Enforcement` | `cacontology-multi:FederalAgency` | |
| `USMS` / `U.S. Marshals` | `cacontology-multi:FederalAgency` | |
| `USAO` / `U.S. Attorney` / `U.S. Attorney's Office` | `cacontology-multi:FederalAgency` | |
| `DEA` | `cacontology-multi:FederalAgency` | |
| `ATF` | `cacontology-multi:FederalAgency` | |
| `NCMEC` | `cacontology-us-ncmec:` context | Also triggers `NCMECCybertipReport` node creation |
| `CEOS` / `Child Exploitation and Obscenity Section` | `cacontology-multi:FederalAgency` | DOJ unit |

#### Tier 2 — ICAC Task Forces (map by pattern to `ICACtaskForce`)
Any string matching `ICAC`, `Internet Crimes Against Children`, `[State] ICAC`:

| Pattern | CAC Class | Notes |
|---|---|---|
| `*ICAC*` / `Internet Crimes Against Children*` | `cacontology-taskforce:ICACtaskForce` | Subtype based on state prefix if detectable (e.g., `AZICAC` → `StateICACtaskForce`) |

#### Tier 3 — State agencies (map by state name + type keyword to `StateAgency`)
Pattern: `[State] [Attorney General | State Police | Bureau | Division | Department]`

| Pattern | CAC Class |
|---|---|
| `*Attorney General*` | `cacontology-multi:StateAgency` |
| `*State Police*` | `cacontology-multi:StateAgency` |
| `*[State] Bureau*` (e.g., GBI, CBI) | `cacontology-multi:StateAgency` |

#### Tier 4 — Local agencies (default fallback)
Any agency not matched above → `cacontology-multi:LocalAgency` with `agencyName` set to the raw string.

#### Shared-singleton IRI strategy
Major agencies (FBI, HSI, NCMEC, CEOS) should have stable shared IRIs reused across cases:
```
ex:agency/fbi        a cacontology-multi:FederalAgency
ex:agency/hsi        a cacontology-multi:FederalAgency
ex:agency/ncmec      a cacontology-us-ncmec:  # special
```
All other agencies: `ex:agency/{slugify(name)}`

---

### 3.8 TECHNOLOGY_SIGNAL_MAP

#### `investigation_technology` Values

| CaseLinker Value | CAC Action/Tool Class | CAC Module | Notes |
|---|---|---|---|
| `PhotoDNA` | `cacontology-detection:ContentHashingAction` | `cacontology-detection:` | Set `hashAlgorithm=PhotoDNA` |
| `CSAI Match` | `cacontology-detection:AutomatedDetectionAction` | `cacontology-detection:` | Google CSAI Match API |
| `hash matching` | `cacontology-detection:ContentHashingAction` | `cacontology-detection:` | Generic hash match |
| `CyberTipline` | `cacontology-us-ncmec:NCMECCybertipReport` | `cacontology-us-ncmec:` | Create CyberTip node; triggers `TaskForceReferral` |

#### `anonymization_network` Values

| CaseLinker Value | CAC Class | Notes |
|---|---|---|
| `Tor` | `cacontology-platforms:DarkWebService` | Set platform type to Tor |
| `I2P` | `cacontology-platforms:DarkWebService` | |
| `dark web` | `cacontology-platforms:DarkWebService` | Generic |
| `cryptocurrency` | `cacontology-platforms:CryptocurrencyService` | |

#### `p2p_clients` Values

| CaseLinker Value | CAC Class | Notes |
|---|---|---|
| `LimeWire` | `cacontology-platforms:FileHostingService` | Legacy P2P; `platformType=p2p` |
| `BitTorrent` | `cacontology-platforms:FileHostingService` | `platformType=p2p` |
| `Kazaa` | `cacontology-platforms:FileHostingService` | Legacy P2P |
| `Gigatribe` | `cacontology-platforms:FileHostingService` | P2P with private groups |

---

## 4. NLP / Semantic Features

### 4.1 What `semantic_concepts.py` Currently Detects

Detection method: cosine similarity via `sentence-transformers/all-MiniLM-L6-v2`, comparing case text embeddings against fixed concept-description strings. Threshold: `min_score=0.35` (configurable). Output stored in `ml_features.semantic_severity`.

### 4.2 Semantic Concept → CAC Mapping

| Concept Key | Score Threshold | Reliability | CAC Target | Include in v1? |
|---|---|---|---|---|
| `grooming` | ≥ 0.35 (merge) | Moderate | `cacontology-grooming:OnlineGrooming` | **Yes** — with `cac-core:hasConfidence` |
| `sextortion` | ≥ 0.35 | Moderate | `cacontology-sextortion:SextortionIncident` | **Yes** — with confidence |
| `possession_csam` | ≥ 0.50 (merge) | High | `cacontology:CSAMIncident` + `CSAM_Possession` | **Yes** — already merge-layer promoted |
| `production_csam` | ≥ 0.35 | High | `cacontology-production:ProductionOffense` | **Yes** — with confidence; cross-check with `production` topic |
| `dissemination` | ≥ 0.35 | Moderate | `cacontology-legal-outcomes:CSAM_Distribution` | **Yes** — with confidence |
| `online_luring_social_engineering` | ≥ 0.35 | Moderate | `cacontology-grooming:OnlineGrooming` | **Yes** — maps same as `grooming` |
| `criminal_networks_trafficking` | ≥ 0.35 | Low | `cacontology:ConspiracyToCommitCSA` + `cacontology-legal-outcomes:SexTrafficking` | **Deferred** — needs higher threshold |
| `exploitive_positions` | ≥ 0.35 | Moderate | `cacontology-custodial:PositionOfTrust` + `TrustViolation` | **Yes** — supplement ROLE_MAP |
| `large_collection` | ≥ 0.35 | Moderate | `cacontology-production:ProductionOffense` (`totalContentVolume`) | **Yes** — set `evidenceVolume` property |
| `registered_sex_offender` | ≥ 0.35 | High | `cacontology:OffenderRole` + prior offense flag | **Yes** — supplement `perpetrator_registered_sex_offender` |
| `evidence_seizure` | ≥ 0.35 | Moderate | `cacontology-production:ProducedContent` / `cacontology-detection:DetectionResult` | **Yes** — triggers evidence artifact node |
| `paraphilia_fetish` | ≥ 0.35 | Low | `cacontology:ChildSexualAbuseEvent` (tag only) | **Deferred** — no well-defined CAC subclass |
| `probation_violation` | ≥ 0.35 | Moderate | `cacontology-legal-outcomes:SupervisedRelease` (violation) | **Yes** — if prior prosecution record exists |
| `ai_and_internet_tools` | ≥ 0.35 | Low | `cacontology:DigitallyGeneratedCSAMIncident` | **Deferred** — needs specificity about AI generation vs. general internet use |
| `law_enforcement_operations` | ≥ 0.35 | Low | `cacontology-taskforce:TaskForceOperation` | **No** — too generic; already captured by `investigation_type` |
| All other concepts (`dangerous`, `stated`, `told`, `continue`, `attacked`, `out_of_control`, `violent`, `obscene`, `assault`, `abuse`, `depictions`, `account_platform`, `online_platforms`, `produced_evidence`, `created_committee_or_entity`, `created_account_for_storage`) | — | Low–Moderate | No direct CAC class | **Deferred** — useful as severity annotations but no distinct ontology node |

### 4.3 Confidence / Reliability

The `all-MiniLM-L6-v2` model at 0.35 threshold is a weak semantic signal designed for broad detection, not high-precision classification. Precision on legal/forensic text is estimated at 60–75% for well-defined concepts (grooming, possession_csam, sextortion) and 40–60% for vague concepts (dangerous, stated, ai_and_internet_tools).

### 4.4 Recommendation: Include vs. Defer

**Include in v1 (with `cac-core:hasConfidence`):**
- `grooming` → `OnlineGrooming` node; confidence from `ml_features.semantic_severity.scores.grooming`
- `sextortion` → `SextortionIncident` node; confidence from score
- `production_csam` → `ProductionOffense` node; confidence from score
- `dissemination` → `CSAM_Distribution` charge node; confidence from score
- `possession_csam` (already promoted by merge layer, include as high-confidence)
- `exploitive_positions` → supplement `ROLE_MAP` custodial detection
- `registered_sex_offender` → supplement `perpetrator_registered_sex_offender`

**Defer to Phase 2:**
- `criminal_networks_trafficking` — needs threshold tuning (suggest ≥0.60)
- `ai_and_internet_tools` — needs specificity
- `paraphilia_fetish` — needs CAC subclass definition from Cory
- `law_enforcement_operations` — not useful without more specificity
- All generic severity/affect concepts (`dangerous`, `violent`, `obscene`, etc.)

### 4.5 Future Enrichment (New NLP Work)

These features **cannot** be detected by existing `semantic_concepts.py` and would require dedicated pipelines:

| Desired Feature | CAC Target | Required NLP Work |
|---|---|---|
| **Grooming phase identification** | `cacontology-grooming:GroomingPhase` subclasses | Sequence classification over conversation segments; requires access to conversation text (not just narrative) |
| **Platform anonymity feature extraction** | `cacontology-platforms:PlatformAnonymityFeature` | Named entity + relation extraction to link platform mention to its anonymity properties |
| **Victim vulnerability typing** | `cacontology-grooming:VictimVulnerabilitySituation` | Multi-label classification; needs labeled training data |
| **Manipulation tactic extraction** | `cacontology-grooming:ManipulationPattern` subclasses | Relation extraction over grooming sequences |
| **SAR/COPINE level assignment** | `cacontology-detection:ClassificationResult` | Requires access to actual CSAM content descriptors; unavailable in narrative text |
| **Interstate transport detection** | `cacontology-multi:InterstateTransportationOffense` | Currently partially detected via `multi_state` topic; needs intent extraction |
| **Organization/enterprise detection** | `cacontology:CriminalEnterprise` | Entity resolution across cases; multi-document |
| **Cybertip report linkage** | `cacontology-us-ncmec:NCMECCybertipReport` | Requires NCMEC report IDs not currently stored in CaseLinker |

---

## 5. Unmappable Features

The following CaseLinker features have **no reasonable CAC Ontology target**. These are the **known gaps** for feedback to Cory and for the Patterns page.

### 5.1 Comparison Values Vectors (Clustering Artifacts)

These exist purely for ML similarity computation and represent no independent case facts.

| Feature | Why Unmappable |
|---|---|
| `comparison_values.platform_vector` | Duplicate of `platforms_used`; used for cosine distance only |
| `comparison_values.demographic_vector` | Aggregates already-mapped fields; not a new fact |
| `comparison_values.relationship_vector` | Duplicate of `relationship_to_victim` |
| `comparison_values.investigation_vector` | Duplicate of `investigation_type` + `agencies_involved` |
| `comparison_values.technology_signal_vector` | Duplicate of investigation_technology, anonymization_network, p2p_clients |
| `comparison_values.evidence_vector` | Duplicate of `evidence_volume` sub-fields |
| `comparison_values.temporal_value` | Duplicate of `date_range.start` |
| `comparison_values.topic_vector` | Duplicate of `case_topics` |
| `comparison_values.severity_vector` | Duplicate of `severity_indicators` |

**Recommendation:** Do not map any `comparison_values` keys. Assert at the top of the mapper that `comparison_values` is read-only for ML and skipped for ontology output.

### 5.2 ML-Derived Scores and Metadata

| Feature | Why Unmappable |
|---|---|
| `ml_features.semantic_severity.scores` (all raw scores) | Continuous model outputs; no CAC class for a similarity score. Use as `cac-core:hasConfidence` annotations on the nodes they contribute to, not as standalone nodes. |
| `ml_features.semantic_severity.concept_metadata` | Internal model metadata (model name, threshold used) |
| `ml_features.ner_entities` | Raw NER output before resolution; intermediate representation |
| `ml_features.semantic_severity.phrases` | Source phrase spans for debugging; no semantic meaning as ontology nodes |

### 5.3 CaseLinker-Internal Metadata

| Feature | Why Unmappable |
|---|---|
| `id` | CaseLinker primary key; use as `dcterms:identifier` on `CACInvestigation` node (literal, not a class) |
| `source` | Source corpus label (AZICAC, SVICAC, etc.); use as `dcterms:source` literal |
| `source_url` | URL; use as `dcterms:source` URL literal |
| `created_at` / `updated_at` | DB row timestamps; use as `dcterms:created` / `dcterms:modified` |
| `notes` | Free-text editorial; use as `rdfs:comment` |
| `tags` | Editorial labels; no CAC target; use as `skos:altLabel` or omit |
| `raw_data` | Full source text blob; store as `case_text` provenance only |
| `severity_phrases` | Sub-phrase list from `extract_severity_phrases()`; used as debug evidence for severity indicators, not a separate CAC node |
| `date_range.start` / `.end` | Temporal coverage; use as `cac-core:hasPhaseBeginPoint` / `hasPhaseEndPoint` literals on `CACInvestigation` phase nodes |
| `organizations` (raw NER) | Unresolved; used as input to `agencies_involved` after deduplication; may partially map to `cacontology-multi:LocalAgency` after resolution |
| `locations` (raw NER) | Geographic strings → shared `uco-location:Location` + `cac-core:PlaceLikeEntity` singletons (`resource/location/{slug}`); linked from `CACInvestigation` via `dcterms:spatial` and `caselinker:mentionsLocation`. Not `ProductionLocation` (production-site subclass only). |
| `case_demographics.gender` | Victim gender; no CaseLinker→CAC mapping defined. Flag for Cory. |
| `anonymized_id` (victim / perpetrator) | Internal anonymization handles; use as `dcterms:identifier` literals if Person nodes are created |
| `era` (from `case_studies.json`) | CaseLinker editorial periodization (I, II, III); no CAC equivalent |

### 5.4 Gaps to Report to Cory (CAC Ontology)

| Gap | Description |
|---|---|
| No dedicated CAC press-release geo class | Geographic locations (`locations` NER) map to UCO `uco-location:Location` + `cac-core:PlaceLikeEntity` (same pattern as PACER venues). A CAC subclass for narrative place mentions would still be useful. |
| No `VictimGender` property on `VictimRole` | `case_demographics.gender` has no mapping target |
| No `EvidenceVolume` class | `evidence_volume.images`, `.videos`, `.storage_size` could be properties on `ProductionOffense` or `ProducedContent` but no dedicated class exists |
| No P2P-specific platform subclass | `FileHostingService` is the closest for P2P clients but is imprecise |
| No `era` / periodization concept | CaseLinker's Era I/II/III taxonomy has no CAC equivalent |
| `paraphilia_fetish` has no subclass | If Cory wants this in the ontology, a `ParaphiliaContext` situation class would be needed |
| `Craigslist` / classified-ads platform type | No dedicated CAC platform type for classifieds/marketplace |

---

## 6. Node Creation Strategy

### 6.1 Sample Case: `azicac_2011_006`

From corpus (narrative reconstructed from `case_studies.json` editorial dimensions):
- Mesa, Arizona, 2011
- Two adult male co-defendants sharing a residence
- P2P file sharing (desktop)
- In-home production (physical abuse of child)
- Multi-agency ICAC response
- State-level prosecution via Maricopa County Attorney's Office
- Proactive federal P2P monitoring → reactive state prosecution

**Reconstructed flat dict (illustrative):**
```python
{
  "id": "azicac_2011_006",
  "source": "AZICAC",
  "date_range": {"start": "2011", "end": "2011"},
  "victim_count": 1,
  "case_demographics": {"ages": [8], "age_range": {"min": 8, "max": 8}, "gender": "unknown"},
  "perpetrator_age": [32, 41],
  "perpetrator_registered_sex_offender": False,
  "relationship_to_victim": "family",
  "platforms_used": ["LimeWire"],
  "investigation_type": "proactive",
  "agencies_involved": ["FBI", "AZICAC", "Maricopa County Attorney's Office"],
  "prosecution_outcome": {"charges": [{"count": 2, "charge": "CSAM Production"}], "booking_status": "convicted", "jail": "15 years"},
  "evidence_volume": {"images": None, "videos": None, "storage_size": None},
  "severity_indicators": ["under_12", "sexual_abuse", "multiple_perpetrators"],
  "case_topics": ["production", "hands_on", "family", "csam"],
  "investigation_technology": [],
  "anonymization_network": [],
  "p2p_clients": ["LimeWire"],
  "ml_features": {"semantic_severity": {"scores": {"grooming": 0.31, "production_csam": 0.72}}}
}
```

### 6.2 Node Inventory for This Case

| Node IRI | CAC Type | Source Field |
|---|---|---|
| `ex:case/azicac_2011_006` | `cacontology:CACInvestigation` | `id` |
| `ex:event/azicac_2011_006/csam` | `cacontology:CSAMIncident` | `case_topics: csam` |
| `ex:event/azicac_2011_006/production` | `cacontology-production:ProductionOffense` | `case_topics: production` |
| `ex:event/azicac_2011_006/hands_on` | `cacontology:ChildSexualAbuseEvent` | `case_topics: hands_on`, `severity_indicators: sexual_abuse` |
| `ex:event/azicac_2011_006/conspiracy` | `cacontology:ConspiracyToCommitCSA` | `severity_indicators: multiple_perpetrators` |
| `ex:role/azicac_2011_006/victim_1` | `cacontology:VictimRole` | `victim_count`, `case_demographics` |
| `ex:role/azicac_2011_006/offender_1` | `cacontology:OffenderRole` | `perpetrator_age[0]=32` |
| `ex:role/azicac_2011_006/offender_2` | `cacontology:OffenderRole` | `perpetrator_age[1]=41` |
| `ex:relationship/azicac_2011_006/familial` | `cacontology-custodial:FamilialRelationship` | `relationship_to_victim: family`, `case_topics: family` |
| `ex:trust_violation/azicac_2011_006` | `cacontology-custodial:CustodialAbuse` | derived from family + hands_on |
| `ex:platform/limewire` | `cacontology-platforms:FileHostingService` | `p2p_clients: LimeWire` (shared singleton) |
| `ex:operation/azicac_2011_006` | `cacontology-taskforce:ProactiveOperation` | `investigation_type: proactive` |
| `ex:agency/fbi` | `cacontology-multi:FederalAgency` | `agencies_involved: FBI` (shared singleton) |
| `ex:agency/azicac` | `cacontology-taskforce:StateICACtaskForce` | `agencies_involved: AZICAC` (shared singleton) |
| `ex:agency/maricopa-county-attorney` | `cacontology-multi:StateAgency` | `agencies_involved: Maricopa County Attorney's Office` |
| `ex:charge/azicac_2011_006/csam_production_1` | `cacontology-legal-outcomes:CSAM_Production` | `prosecution_outcome.charges[0]` |
| `ex:charge/azicac_2011_006/csam_production_2` | `cacontology-legal-outcomes:CSAM_Production` | `prosecution_outcome.charges[1]` |
| `ex:sentence/azicac_2011_006` | `cacontology-legal-outcomes:PrisonSentence` | `prosecution_outcome.jail: 15 years` |
| `ex:phase/azicac_2011_006/sentencing` | `cacontology-legal-outcomes:SentencingPhase` | `prosecution_outcome.booking_status: convicted` |

### 6.3 Edge Inventory

| From Node | Property | To Node | Source |
|---|---|---|---|
| `ex:case/azicac_2011_006` | `cacontology:hasStep` | `ex:event/azicac_2011_006/csam` | CSAMIncident is part of investigation |
| `ex:case/azicac_2011_006` | `cacontology:hasStep` | `ex:event/azicac_2011_006/production` | ProductionOffense is part of investigation |
| `ex:case/azicac_2011_006` | `cacontology:hasStep` | `ex:event/azicac_2011_006/hands_on` | ChildSexualAbuseEvent is part of investigation |
| `ex:case/azicac_2011_006` | `cacontology:hasPhase` | `ex:phase/azicac_2011_006/sentencing` | prosecution phase |
| `ex:event/azicac_2011_006/production` | `cacontology-production:involvesVictim` | `ex:role/azicac_2011_006/victim_1` | victim in production event |
| `ex:event/azicac_2011_006/production` | `cacontology-production:producedBy` | `ex:role/azicac_2011_006/offender_1` | offender 1 produced |
| `ex:event/azicac_2011_006/production` | `cacontology-production:producedBy` | `ex:role/azicac_2011_006/offender_2` | offender 2 produced |
| `ex:event/azicac_2011_006/conspiracy` | `cacontology:participatesInConspiracy` | `ex:role/azicac_2011_006/offender_1` | conspiracy member |
| `ex:event/azicac_2011_006/conspiracy` | `cacontology:participatesInConspiracy` | `ex:role/azicac_2011_006/offender_2` | conspiracy member |
| `ex:relationship/azicac_2011_006/familial` | `cacontology-custodial:involvesCustodian` | `ex:role/azicac_2011_006/offender_1` | familial offender |
| `ex:relationship/azicac_2011_006/familial` | `cacontology-custodial:involvesChild` | `ex:role/azicac_2011_006/victim_1` | child in relationship |
| `ex:trust_violation/azicac_2011_006` | `cacontology-custodial:violatesRelationship` | `ex:relationship/azicac_2011_006/familial` | violation of family relationship |
| `ex:operation/azicac_2011_006` | `cacontology-multi:involvesAgency` | `ex:agency/fbi` | FBI involved |
| `ex:operation/azicac_2011_006` | `cacontology-multi:involvesAgency` | `ex:agency/azicac` | AZICAC TF involved |
| `ex:operation/azicac_2011_006` | `cacontology-multi:involvesAgency` | `ex:agency/maricopa-county-attorney` | prosecutor |
| `ex:event/azicac_2011_006/production` | `cacontology-production:usesEquipment` | `ex:platform/limewire` | P2P used for distribution |
| `ex:charge/azicac_2011_006/csam_production_1` | `cacontology-legal-outcomes:appliesTo` | `ex:role/azicac_2011_006/offender_1` | charge against offender 1 |
| `ex:sentence/azicac_2011_006` | `cacontology-legal-outcomes:resultsSentence` | `ex:phase/azicac_2011_006/sentencing` | sentence from phase |

### 6.4 ASCII Mini-Graph

```
ex:case/azicac_2011_006
  [CACInvestigation]
  │
  ├──hasStep──► ex:event/.../production [ProductionOffense]
  │                │ severityLevel=3
  │                │ totalContentVolume=?
  │                ├──involvesVictim──► ex:role/.../victim_1 [VictimRole] age=8
  │                ├──producedBy────► ex:role/.../offender_1 [OffenderRole] age=32
  │                └──producedBy────► ex:role/.../offender_2 [OffenderRole] age=41
  │
  ├──hasStep──► ex:event/.../csam [CSAMIncident]
  │
  ├──hasStep──► ex:event/.../hands_on [ChildSexualAbuseEvent] severityLevel=3
  │
  ├──hasStep──► ex:event/.../conspiracy [ConspiracyToCommitCSA]
  │                │ conspiracyMemberCount=2
  │                ├──participatesInConspiracy──► offender_1
  │                └──participatesInConspiracy──► offender_2
  │
  ├──hasPhase──► ex:phase/.../sentencing [SentencingPhase]
  │                └──resultsSentence──► ex:sentence/... [PrisonSentence] "15 years"
  │                    └──appliesTo──► charge_1 [CSAM_Production]
  │
  └──hasStep──► ex:operation/... [ProactiveOperation]
                   ├──involvesAgency──► ex:agency/fbi [FederalAgency]
                   ├──involvesAgency──► ex:agency/azicac [StateICACtaskForce]
                   └──involvesAgency──► ex:agency/maricopa-county-attorney [StateAgency]

ex:relationship/.../familial [FamilialRelationship]
  ├──involvesCustodian──► offender_1
  └──involvesChild─────► victim_1
       └──violatesRelationship──► ex:trust_violation/... [CustodialAbuse]

ex:platform/limewire [FileHostingService] (shared singleton)
  ←─usesEquipment─── production event
```

---

## 7. Open Questions for Mrinaal

### 7.1 Platform Ambiguity

| Question | Context | Options |
|---|---|---|
| **Q7.1a** What to do with `online`, `chat`, `social media`? | These three generic labels are in `_PLATFORM_SPECS` and appear in many cases. Currently proposed: skip node creation. | (A) Skip — no platform node; (B) Create a generic `cacontology-platforms:SocialMediaPlatform` node with a "generic" flag; (C) Create an `AnonymousChatPlatform` node for `chat` |
| **Q7.1b** Should `Craigslist` map to `SocialMediaPlatform` or `OnlineDatingPlatform`? | Craigslist is classifieds; in ICAC cases it often appears in the context of solicitation/meeting arrangements, not social networking. | (A) `SocialMediaPlatform` with `platformType=classifieds`; (B) `OnlineDatingPlatform`; (C) Request a new CAC subclass from Cory |
| **Q7.1c** Should `TikTok` be `SocialMediaPlatform` or `VideoStreamingPlatform`? | TikTok is both. | (A) Dual-type (both); (B) Primary type only (`SocialMediaPlatform`); (C) Decide based on case context |
| **Q7.1d** Should `Webcam platform` (matches `MyFreeCams`) get a more specific subclass? | Adult webcam services are distinct from YouTube/Twitch. The ontology has `VideoStreamingPlatform` but no adult-content-specific subclass. | Ask Cory if a subclass is planned |

### 7.2 Topic / Event Ambiguity

| Question | Context | Options |
|---|---|---|
| **Q7.2a** `csam` and `possession` often co-occur. Create one node or two? | Both map to `CSAMIncident`. When both are present, is a second node warranted? | (A) Merge into one `CSAMIncident` node when both topics present; (B) Create two nodes with different semantic labels |
| **Q7.2b** Should `online_only` create a `GroomingSolicitation` or a plain `ChildSexualAbuseEvent`? | `online_only` means no physical contact. It may or may not involve grooming. | (A) Default to `GroomingSolicitation`; (B) Only use `GroomingSolicitation` if `grooming` topic/semantic is also present; (C) Create `ChildSexualAbuseEvent` only |
| **Q7.2c** `international` and `multi_state` both map to `MultiJurisdictionalInvestigation`. When both present, one node or two? | The ontology distinguishes `crossesBorders` (boolean) — they could be the same node with both properties. | (A) Single node with `crossesBorders=true` and `statesInvolved`; (B) Two nodes (domestic + international) |

### 7.3 Person Node Creation

| Question | Context |
|---|---|
| **Q7.3a** Should the mapper create `Person` nodes for victims and offenders, or only `VictimRole` / `OffenderRole` nodes? | CASE/UCO supports `uco-identity:Person` as a separate EnduringEntity that holds the role. Creating Person nodes enables linking roles across cases (e.g., recidivist offenders). But CaseLinker does not store unique person identifiers — only anonymized IDs. |
| **Q7.3b** If Person nodes are created for victims, should they be anonymized (no PII) even in the local graph? | The anonymized_id exists but the ages, region, and demographics are potentially re-identifying if combined. |
| **Q7.3c** What to do when `victim_count > 1` but only one `case_demographics` object exists? | The current schema does not individuate victims. Create N generic `VictimRole` nodes? Or one role node with `victim_count` as a property? |
| **Q7.3d** What to do when `perpetrator_age` is `null`? | No age known. Create an `OffenderRole` node with no age property, or skip? |

### 7.4 IRI Naming Strategy

| Question | Options |
|---|---|
| **Q7.4a** Base IRI for CaseLinker-generated nodes | (A) `https://caselinker.example.org/cases/{id}#`; (B) `urn:caselinker:{id}:`; (C) Something tied to the ProjectVIC namespace |
| **Q7.4b** Shared entity IRIs (platforms, agencies) | Use a stable `ex:platform/{slug}` and `ex:agency/{slug}` namespace shared across all cases. Who owns this namespace? Should it be a separate named graph? |
| **Q7.4c** IRI collision for agencies with long/variable names | `Maricopa County Attorney's Office` → `maricopa-county-attorneys-office` (slug). Is that stable enough? Should a lookup table be maintained? |
| **Q7.4d** Versioning: if a case is re-processed, should the IRI be stable or versioned? | (A) Stable — same IRI overwritten; (B) Versioned — `{id}/v2`; (C) Use blank nodes for ephemeral data |

### 7.5 Ontology / Coverage Questions for Cory

| Question | Why It Matters |
|---|---|
| **Q7.5a** Is there a `Location` or `GeographicEntity` class in the CAC Ontology? | `locations` NER output has no current target. CASE/UCO `uco-location:Location` may work if the CASE SDK supports it. |
| **Q7.5b** Is `cacontology-detection:ClassificationResult` intended for narrative-derived severity assessments, or only for algorithmic hash/ML detection? | CaseLinker uses `severity_indicators` derived from text regex, not CSAM hash analysis. Using `ClassificationResult` may be semantically incorrect. |
| **Q7.5c** Should P2P clients (LimeWire, BitTorrent) map to `FileHostingService` or does Cory want a `PeerToPeerNetwork` subclass? | P2P networks have different risk profiles and evidentiary implications than hosted file services. |
| **Q7.5d** Is there a planned subclass for victim gender / demographic profile? | `case_demographics.gender` has no CAC target today. |
| **Q7.5e** Does `cacontology-custodial:Relative` cover the uncle/aunt/cousin cases, or should there be more specific subclasses? | The `Relative` class is the only non-parent, non-sibling family option in the custodial module. |
| **Q7.5f** What is the intended use of `cacontology:severityLevel` (0–3)? Is it case-level or event-level? | CaseLinker severity indicators are aggregated at the case level, but the CAC property is on `ChildSexualAbuseEvent`. |
| **Q7.5g** For multi-defendant cases, should each defendant get their own `CACInvestigation` node, or is one investigation node correct with multiple `OffenderRole` nodes? | |

### 7.6 Threshold / Confidence Decisions

| Question | Context |
|---|---|
| **Q7.6a** What minimum semantic score warrants creating an NLP-derived CAC node (vs. just annotating it as possible)? | Currently using merge-layer thresholds (grooming: 0.35, possession_csam: 0.50). Should these be tightened for ontology output? |
| **Q7.6b** Should NLP-derived nodes be emitted into the same named graph as deterministic nodes, or a separate named graph for lower-confidence data? | Separation enables consumers to filter by confidence. |

---

## Appendix A: File Locations Referenced

| File | Purpose |
|---|---|
| `src/Storage Layer/storage_postgres.py` | Table definitions |
| `src/Processing Layer/Pattern Processing Layer/processing.py` | `extract_features`, `assign_comparison_values`, `extract_topics`, `_PLATFORM_SPECS`, `extract_technology_signals` |
| `src/Storage Layer/case_storage_utils.py` | `_SLIM_EXCLUDED_KEYS` |
| `src/Processing Layer/ML Processing Layer/semantic_concepts.py` | Semantic concept detection |
| `src/Processing Layer/merge_processing.py` | Merge-layer thresholds |
| `run/main.py` | API shape, `_REVOLVER_LABEL_SYNONYMS` |
| `scripts/verify/verify_claims.py` | `_GENERIC_PLATFORMS` |
| `data/case_studies.json` | Editorial case metadata |
| `../CAC-Ontology/ontology/*.ttl` | Ontology source files |

## Appendix B: CAC Ontology Files Read

| File | Lines | Content |
|---|---|---|
| `cacontology-core-spine.ttl` | 211 | Five spine branches, base properties |
| `cacontology-core.ttl` | 454 | CACInvestigation, phases, criminal events, roles |
| `cacontology-grooming.ttl` | 994 | Grooming behaviors, phases, patterns |
| `cacontology-custodial.ttl` | 563 | Positions of trust, custodial relationships |
| `cacontology-platforms.ttl` | 942 | Platform types, ESP capabilities, evidence |
| `cacontology-legal-outcomes.ttl` | 708 | Charges, sentences, legal proceedings |
| `cacontology-sextortion.ttl` | 582 | Sextortion patterns, threats, demands |
| `cacontology-detection.ttl` | 503 | CSAM detection, SAR/COPINE classifications |
| `cacontology-production.ttl` | 561 | CSAM production, recording devices, content |
| `cacontology-taskforce.ttl` | 1,142 | ICAC task forces, operations, metrics |
| `cacontology-us-ncmec.ttl` | 352 | CyberTipline structures, annotations |
| `cacontology-multi-jurisdiction.ttl` | 1,217 | Multi-agency investigations, interstate offenses |

---

*This document is the spec for `ontology/features_to_cac.py`. No mapping code should be written until the questions in §7 are resolved and this plan is signed off.*
