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
