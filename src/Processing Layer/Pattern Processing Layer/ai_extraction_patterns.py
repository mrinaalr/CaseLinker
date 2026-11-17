"""
Regex and thresholds for Gen AI (tool) vs AI-CSAM (offense product) extraction.

Imported by processing.py and audit scripts.
"""

from __future__ import annotations

import re

# AI-CSAM offense product (case_topics: ai_csam)
# Lexical only — do not promote from embedding scores alone (see merge_processing).
AI_CSAM_TOPIC_RE = re.compile(
    r"""
    \bai[- ]generated\b
    | \bai\s+created\b
    | \bai\s*[-\s]?created\b
    | \bartificially[- ]generated\b
    | \bartificially\s+generated\b
    | \bcomputer[- ]generated\b.*\b(?:child|minor|pornograph|sexual|csam|exploit)\b
    | \b(?:child|minor|pornograph|sexual|csam|exploit).*\bcomputer[- ]generated\b
    | \bdigitally[- ]generated\b.*\b(?:child|minor|pornograph|sexual|csam|exploit)\b
    | \bsynthetic\s+(?:csam|child\s+porn|child\s+sexual|image|media|material|porn|imagery|exploitative)\b
    | \bdeepfake
    | \bobscene\s+visual\s+represent
    | \bai\s+csam\b
    | \bartificial\s+intelligence\b(?:(?!\beasier\b)[^.]){0,60}\bto\s+(?:creat|generat|produc|manufactur)\w*
    | \bartificial\s+intelligence\b[^.]{0,60}\b(?:created|generated|produced|manufactured)\b
    | \b(?:created|generated|produced|manufactured)\b[^.]{0,100}\b(?:using|with|by|via|through)\s+(?:generative\s+)?artificial\s+intelligence\b
    | \b(?:creat|generat|manufactur)\w*[^.]{0,100}\bartificial\s+intelligence\b
    | \bimages?\s+(?:and\s+videos?\s+)?(?:were\s+|was\s+)?(?:created|generated|produced|made)\s+(?:using|through|with)\s+artificial\s+intelligence\b
    | \bartificial\s+intelligence\s*[\(\s,]*\s*ai\s*[\)\s,]*(?:(?!\beasier\b)[^.]){0,40}\bto\s+(?:creat|generat|produc|manufactur)\w*
    | \b(?:possess|possession|possessed|distribut|receiv|trading|collect|manufactur|produc|creat|generat)\w*[^.]{0,80}\bai[- ]generated\b
    | \b(?:possess|possession|possessed|distribut|receiv|trading|collect)\w*[^.]{0,80}\bartificially[- ]generated\b
    | \bai[- ]generated\b[^.]{0,80}\b(?:possess|possession|possessed|distribut|child|minor|csam|pornograph|sexual|exploit|depict)\w*
    | \bartificially[- ]generated\b[^.]{0,80}\b(?:possess|possession|possessed|distribut|child|minor|csam|pornograph|sexual|exploit|file|material|image)\w*
    | \bexploitative\s+images?\b[^.]{0,40}\bai[- ]generated\b
    | \bai[- ]generated\b[^.]{0,40}\bexploitative\s+images?\b
    | \bmachine\s+learning\s+models?\b[^.]{0,60}\b(?:child|minor|csam|sexual|pornograph)\b
    | \bartificial\s+intelligence[- ]generated\s+child\s+sexual\s+abuse\s+material\b
    | \bchild\s+erotic\s+material\s+generated\s+using\b
    | \bcomputer[- ]generated\s+or\s+animated\s+content\s+showing\s+children\b
    | \bai\s+child\s+pornograph
    | \bchild\s+pornograph\w*\s+using\s+(?:a[-\s]?i|artificial\s+intelligence)\b
    | \bgenerated\s+(?:using|by)\s+an?\s+(?:ai\s+computer\s+program|artificial\s+intelligence)\b
    | \bbe(?:en)?\s+generated\s+by\s+artificial\s+intelligence\b
    | \bgenerated\s+artificial\s+intelligence\s+child\b
    | \bai\s+technology\s+applications?\s+to\s+produc
    | \bdeep\s+fakes?\b
    | \breported\s+to\s+be\s+artificial\s+intelligence\b
    | \b(?:images?|material|content)\s+manipulation\s+technologies\b.*\bartificial\s+intelligence\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Gen AI tool (platforms_used: Gen AI)
GEN_AI_TOOL_RE = re.compile(
    r"""
    \bgenerative\s+(?:artificial\s+)?intelligence\b
    | \bgen\s*ai\b
    | \bai\s+chatbots?\b
    | \bartificial\s+intelligence\s+chatbots?\b
    | \bai\s+tools?\b
    | \b(?:used|using|utiliz\w+|employ\w+)\s+(?:generative\s+)?(?:artificial\s+intelligence|ai)\b
    | \b(?:artificial\s+intelligence|ai)\s+to\s+(?:creat|generat|produc|manufactur|mak)\w*\b
    | \b(?:creat|generat|produc|manufactur)\w*\s+(?:using|with|via|through)\s+(?:generative\s+)?(?:artificial\s+intelligence|ai)\b
    | \bimages?\s+(?:and\s+videos?\s+)?(?:were\s+|was\s+)?(?:created|generated|produced|made)\s+(?:using|through|with)\s+(?:generative\s+)?(?:artificial\s+intelligence|ai)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

AI_CSAM_IMPLIES_TOOL_RE = re.compile(
    r"""
    \b(?:artificial\s+intelligence|\bai\b)\b
    | \bgenerative\s+(?:artificial\s+)?intelligence\b
    | \bgen\s*ai\b
    | \bchatgpt\b
    | \bstable\s+diffusion\b
    | \bmidjourney\b
    | \bdall[\s-]?e\b
    | \bai\s+chatbot
    | \bmachine\s+learning\b
    | \bartificially[- ]generated\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Deprecated: embedding scores alone must not set case_topics ai_csam (false positives
# on ordinary CSAM digests). Kept for reference / older callers; unused by merge.
AI_CSAM_SEMANTIC_THRESHOLD = 0.50

# Sextortion offense (case_topics: sextortion) — regex only; not promoted from NLP scores.
SEXTORTION_TOPIC_RE = re.compile(
    r"""
    \bsextort\w*\b
    | \bsexual(?:ly)?\s+extort\w*\b
    | \bsextortion\s+scheme\b
    | \bcyber[\s-]?sextort\w*\b
    | \b(?:blackmail|extort)\w*\b[^.]{0,70}\b(?:nude|naked|sexual|explicit|indecent)\s+(?:photos?|images?|videos?|content|material)\b
    | \b(?:nude|naked|sexual|explicit|indecent)\s+(?:photos?|images?|videos?|content|material)\b[^.]{0,70}\b(?:blackmail|extort)\w*\b
    | \bthreaten\w*\s+to\s+(?:share|post|send|publish|distribute|release)\b[^.]{0,60}\b(?:nude|naked|sexual|explicit|indecent)\b
    | \b(?:share|post|send|publish|distribute|release)\b[^.]{0,40}\b(?:nude|naked|sexual|explicit|indecent)\s+(?:photos?|images?|videos?)\b[^.]{0,40}\b(?:unless|if|until)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Project Safe Childhood (case_topics: project_safe_childhood) — lexical only.
# Federal DOJ/ICE/CEOS press boilerplate; do not infer from embeddings.
PROJECT_SAFE_CHILDHOOD_TOPIC_RE = re.compile(
    r"\bProject\s+Safe\s+Childhood\b",
    re.IGNORECASE,
)

# Registered / previously-convicted sex offender — not bare "sex offender"
# (ICE/HSI footers often say "sex offenders and child sex traffickers").
REGISTERED_SEX_OFFENDER_RE = re.compile(
    r"\bregistered\s+sex\s+offender\b",
    re.IGNORECASE,
)
PREVIOUSLY_CONVICTED_SEX_OFFENDER_RE = re.compile(
    r"""
    \b(?:previously|prior(?:ly)?)\s+convicted\s+sex\s+offender\b
    | \ba\s+convicted\s+sex\s+offender\b
    | \bconvicted\s+sex\s+offender\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Prior conviction language (previous_conviction.has_prior_conviction) — not RSO alone (#64).
# Plurals and up to two words between ("two prior felony convictions", "a previous federal
# felony conviction"), but not "prior to his conviction". Supervision at the time of the
# offense and "convicted felon" / failure to register imply an earlier conviction.
# Negations, hypotheticals and this case's own conviction are dropped in
# processing.extract_previous_conviction, which reads the words before each match.
# The parts below give prior_history its kinds; PRIOR_CONVICTION_RE is their union.
PRIOR_CONVICTION_WORDING_RE = re.compile(
    r"""
    \b(?:previous|prior)\s+(?:(?!to\b)[a-z][a-z-]*\s+){0,2}convictions?\b
    | \bpreviously\s+(?:been\s+)?convicted\b
    | \brepeat\s+(?:CSAM\s+|child\s+pornograph\w*\s+|sex\s+)?offenses?\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
PRIOR_STATUS_RE = re.compile(
    r"\bconvicted\s+felon\b|\bfail(?:ure|ed|ing)?\s+to\s+register\s+as\s+a\s+sex\s+offender\b",
    re.IGNORECASE,
)
PRIOR_SUPERVISION_RE = re.compile(
    r"\b(?:while|was|were|is|been|already)\s+(?:on|serving)\s+(?:federal\s+|state\s+)?"
    r"(?:parole|probation|supervised\s+release)\b",
    re.IGNORECASE,
)
PRIOR_CONVICTION_RE = re.compile(
    "|".join(f"(?:{rx.pattern})" for rx in (PRIOR_CONVICTION_WORDING_RE, PRIOR_STATUS_RE, PRIOR_SUPERVISION_RE)),
    re.IGNORECASE | re.VERBOSE,
)
# "was convicted in 1996 of …": an earlier conviction only when the year is at least two
# years before the release's own year (a year-only match is this case's conviction otherwise).
DATED_CONVICTION_RE = re.compile(
    r"\b(?:was|had\s+been|been|were)\s+(?:previously\s+|also\s+)?convicted\s+in\s+((?:19|20)\d\d)\b",
    re.IGNORECASE,
)
# Words before a match that make it not this defendant's earlier conviction.
PRIOR_CONVICTION_NOT_BEFORE_RE = re.compile(
    r"""
    (?:\b(?:no|without|never\s+had\s+(?:a|any)|not\s+have\s+(?:a|any)|lacks?\s+(?:a|any)
        |neither\s+(?:\w+\s+){0,2}?(?:has|had)\s+(?:a|any)|(?:does|did)\s+not\s+have\s+(?:a|any))\s+(?:\w+\s+){0,2}
     | \bif\s+(?:he|she|they|the\s+defendant)\s+(?:has|had|have)\s+(?:a\s+|any\s+|two\s+or\s+more\s+)?(?:\w+\s+){0,2}
     | \b(?:defendants?|offenders?|those|anyone|individuals?|people)\s+(?:with|who\s+have)\s+(?:a\s+|any\s+)?(?:\w+\s+){0,2}
     | \b(?:following|after)\s+(?:his|her|their)\s+
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)
