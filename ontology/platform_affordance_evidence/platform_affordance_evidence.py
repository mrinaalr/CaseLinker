#!/usr/bin/env python3
"""
Q1 affordance-evidence extraction — fast, string-based.

For each (case_id, platform) in candidates.json: read case_text, drop PSA
boilerplate, pick an offense sentence, classify stated/inferred/named_only,
extract quote + harm. No nested regex; all text capped before processing.

Outputs:
  ontology/platform_affordance_evidence/platform_affordance_evidence.json
  ontology/platform_affordance_evidence/platform_affordance_evidence_table.md
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

DB = "caselinker.db"
CANDIDATES_FILE = "ontology/platform_affordance_evidence/candidates.json"
OUTPUT_DIR = Path("ontology/platform_affordance_evidence")
TEXT_CAP = 6000
QUOTE_MAX = 120
# Max chars between platform mention and offense keyword for stated (same sentence).
INSTRUMENTAL_WINDOW = 60

# Synced with build_candidates.py
PLATFORM_TYPE: Dict[str, str] = {
    "Kik": "MessagingService",
    "Snapchat": "MessagingService",
    "Discord": "MessagingService",
    "WhatsApp": "MessagingService",
    "Telegram": "MessagingService",
    "Facebook Messenger": "MessagingService",
    "Skype": "MessagingService",
    "FaceTime": "MessagingService",
    "IRC": "MessagingService",
    "MeWe": "MessagingService",
    "AOL Instant Messenger": "MessagingService",
    "Signal": "MessagingService",
    "Wickr": "MessagingService",
    "Chat Avenue": "MessagingService",
    "Facebook": "SocialMediaPlatform",
    "Twitter / X": "SocialMediaPlatform",
    "Instagram": "SocialMediaPlatform",
    "TikTok": "SocialMediaPlatform",
    "MySpace": "SocialMediaPlatform",
    "Grindr": "OnlineDatingPlatform",
    "Skout": "OnlineDatingPlatform",
    "Tinder": "OnlineDatingPlatform",
    "MeetMe": "OnlineDatingPlatform",
    "Reddit": "SocialMediaPlatform",
    "Tumblr": "SocialMediaPlatform",
    "Yubo": "SocialMediaPlatform",
    "Dropbox": "FileHostingService",
    "Google Drive": "FileHostingService",
    "Mega.nz": "FileHostingService",
    "OneDrive": "FileHostingService",
    "iCloud": "FileHostingService",
    "Cash App": "FinancialTransferService",
    "BitTorrent": "P2PService",
    "LimeWire": "P2PService",
    "Kazaa": "P2PService",
    "Tor": "AnonymizationService",
    "IMVU": "MessagingService",
    "Omegle": "AnonymousChatPlatform",
    "Whisper": "AnonymousChatPlatform",
    "Monkey": "AnonymousChatPlatform",
    "Chatroulette": "AnonymousChatPlatform",
    "YouNow": "AnonymousChatPlatform",
    "YouTube": "VideoStreamingPlatform",
    "Twitch": "VideoStreamingPlatform",
    "Webcam platform": "VideoStreamingPlatform",
    "Minecraft": "GamePlatform",
    "Wizard 101": "GamePlatform",
    "Call of Duty": "GamePlatform",
    "CS:GO": "GamePlatform",
    "Steam": "GamePlatform",
    "Oculus": "GamePlatform",
    "VRChat": "GamePlatform",
    "Xbox Live": "GamePlatform",
    "Roblox": "GamePlatform",
    "Fortnite": "GamePlatform",
    "PlayStation Network": "GamePlatform",
    "Craigslist": "ClassifiedsMarketplace",
    "Gen AI": "AIService",
    "social media": "SocialMediaPlatform",
    "gaming": "GamePlatform",
    "email": "MessagingService",
    "internet": "Unknown",
    "dark web": "DarkWebService",
    "chat": "MessagingService",
    "other": "Unknown",
}

# Canonical label → substrings to search in case_text (lowercase).
ALIASES: Dict[str, Tuple[str, ...]] = {
    "Webcam platform": ("webcam", "web cam", "myfreecams", "mfc"),
    "Twitter / X": ("twitter", " x.com", "x.com", "twitter.com"),
    "Xbox Live": ("xbox live", "xbox"),
    "Gen AI": (
        "gen ai",
        "ai-generated",
        "artificial intelligence",
        "generative intelligence",
        "generated ai",
        "ai csam",
    ),
    "Mega.nz": ("mega", "mega.nz"),
}

KNOWN_PLATFORM_NAMES: Tuple[str, ...] = tuple(
    sorted(set(PLATFORM_TYPE.keys()) | {
        "WeChat", "Bumble", "LiveMe", "Houseparty",
        "Periscope", "Twitter", "Nintendo", "Counter-Strike",
        "Google Hangouts", "Google Chat", "Meta Quest", "Tagged",
    })
)

PSA_TRIGGERS: Tuple[str, ...] = (
    "below is a list of popular apps",
    "apps that predators can use",
    "tips for parents",
    "talk to your kids",
    "talk to your children",
    "resources for parents",
    "internet safety",
    "parents should know",
    "help protect your child",
    "precautions for parents",
)

# Hypothetical / advisory framing — platform in these sentences is not a case fact.
AWARENESS_TRIGGERS: Tuple[str, ...] = (
    "predators can use",
    "predators use",
    "predators may use",
    "predators have used",
    "offenders often",
    "offenders can",
    "offenders may",
    "kids may",
    "children may",
    "can be used to",
    "apps like",
    "apps such as",
    "even games",
    "such as",
    "including but not limited",
    "include, but are not limited",
    "include but are not limited",
    "not limited to",
    "common apps used",
    "common apps include",
    "popular apps",
    "may encounter",
    "parents should",
    "talk to your",
    "be aware",
    "watch out for",
    "they have a chat feature",
    "have a chat feature",
    "in past cases",
    "following chat apps",
    "urged parents",
    "familiarize themselves",
    "may be out to harm",
    "strangers they meet",
)

# Offense stems that must match as words (avoid Snapchat / Chat Avenue false positives).
BOUNDED_OFFENSE_KEYWORDS: frozenset = frozenset({
    "chat", "sent", "trad", "lur", "entic", "shar",
})

GENERIC_PLATFORM_LABELS: frozenset = frozenset({
    "chat", "social media", "gaming", "internet", "online",
})

# Substring offense stems that appear inside benign platform descriptors.
_OFFENSE_SPAN_SKIP_CONTEXTS: Tuple[str, ...] = (
    "messaging application",
    "messaging applications",
    "messaging app",
    "messaging apps",
    "chat application",
    "chat applications",
    "chat app",
    "chat apps",
    "online messaging",
)

_ENUM_VERBS: Tuple[str, ...] = (
    " arrested ", " charged ", " convicted ", " sentenced ", " contacted ",
    " communicated ", " sent ", " uploaded ", " distributed ", " solicited ",
    " groomed ", " exchanged ", " traded ", " produced ", " met ", " lured ",
    " enticed ", " transmitted ", " reported ", " flagged ",
)

OFFENSE_KEYWORDS: Tuple[str, ...] = (
    "upload", "shar", "distribut", "sent", "contact", "solicit", "soliciting",
    "groom", "entic", "lur", "communicat", "chat", "messag",
    "exchang", "trad", "produc", "stream", "utiliz", "used to",
    "transmit", "reported", "flagged", "cybertip", "found victim", "found victims",
    "through the",
)

INVESTIGATIVE_KEYWORDS: Tuple[str, ...] = (
    "file sharing", "p2p", "peer-to-peer", "undercover",
    "operation", "task force", "investigation", "cybertip",
    "charged with", "convicted of", "arrested",
)

HARM_PATTERNS: Tuple[str, ...] = (
    r"charged with ([^.;]{5,80})",
    r"convicted of ([^.;]{5,80})",
    r"pleaded guilty to ([^.;]{5,80})",
    r"faces? (?:a )?charges? of ([^.;]{5,80})",
    r"arrested (?:for|on) ([^.;]{5,80})",
)

TIER_RANK = {"stated": 3, "inferred": 2, "named_only": 1}

_INSTRUMENTAL_RE_CACHE: Dict[str, List[re.Pattern]] = {}

# Gen AI only: CSAM noun phrases and creation/possession verbs are offense evidence, not
# contact/distribution stems. Kept separate so other platforms are unchanged.
_GEN_AI_CSAM_OFFENSE_PATTERNS: Tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bchild porn(?:ography)?\b",
        r"\bchild sexual abuse\b",
        r"\bchild sex abuse\b",
        r"\bsexual abuse material\b",
        r"\bsex abuse material\b",
        r"\bcsam\b",
        r"\bsexual exploitation\b",
        r"\bchild exploitation\b",
        r"\bexploitation material\b",
        r"\bexploitative material\b",
        r"\bobscene image",
        r"\bsexual performance\b",
        r"\bgenerated ai csam\b",
        r"\bai[- ]generated\b[\w\s,\-\"'()]{0,35}\b(?:child|csam|porn|exploit|abuse|obscene|lewd|depict)",
        r"\b(?:child|csam|porn|exploit|sexual abuse|sex abuse)\b[\w\s,\-\"'()]{0,35}\bai[- ]generated\b",
    )
)

_GEN_AI_INSTRUMENTAL_PATTERNS: Tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(?:used|using|create[ds]?|generat(?:e|ed|ing)|produc(?:e|ed|ing)|possess(?:ed|ing)?)\b"
        r"[\w\s,\-\"'()]{0,55}\b(?:artificial intelligence|generative artificial intelligence|"
        r"ai[- ]generated|generated ai)\b",
        r"\b(?:artificial intelligence|generative artificial intelligence|ai[- ]generated|generated ai)\b"
        r"[\w\s,\-\"'()]{0,55}\b(?:child|csam|porn|exploit|sexual abuse|sex abuse|obscene|lewd|exploitative)\b",
        r"\bai[- ]generated\b[\w\s,\-\"'()]{0,40}\b(?:child|csam|porn|exploit|sexual abuse|sex abuse|"
        r"images?|material|content|files?|depic|exploitative)\b",
        r"\b(?:computer[- ]generated|ai[- ]generated)\s+child porn",
        r"\bpossess(?:ed|ion|ing)?\s+(?:files?\s+)?of\s+(?:artificial intelligence|ai)[- ]generated\b",
        r"\b(?:artificial intelligence|generative artificial intelligence)\b"
        r"[\w\s,\-\"'()]{0,20}\b(?:child exploitation|exploitation material)\b",
        r"\bpossessing\s+generated\s+child\s+porn",
        r"\bappeared\s+to\s+be\s+ai(?:/computer)?[- ]generated\b",
    )
)

_GEN_AI_CONDUCT_RE = re.compile(
    r"\b(?:arrested|charged|sentenced|possess(?:ed|ing)?|created|admitted|indicted|"
    r"found|seized|uncovered|faces?|investigators state|used)\b",
    re.IGNORECASE,
)


def psa_boundary(text: str) -> int:
    tl = text.lower()
    earliest = len(text)
    for trigger in PSA_TRIGGERS:
        i = tl.find(trigger)
        if 0 <= i < earliest:
            earliest = max(0, text.rfind("\n", 0, i))
    return earliest


def offense_lines(text: str) -> Tuple[List[str], List[str], bool]:
    """Return (offense_lines, psa_lines, hit_text_cap)."""
    hit_cap = len(text) > TEXT_CAP
    capped = text[:TEXT_CAP]
    boundary = psa_boundary(capped)
    offense_raw = capped[:boundary]
    psa_raw = capped[boundary:]
    offense = [ln.strip() for ln in offense_raw.split("\n") if len(ln.strip()) > 20]
    psa = [ln.strip() for ln in psa_raw.split("\n") if len(ln.strip()) > 20]
    return offense, psa, hit_cap


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 10]


def platform_text_terms(platform: str) -> Tuple[str, ...]:
    return ALIASES.get(platform, (platform.lower(),))


def line_mentions_platform(line: str, platform: str) -> bool:
    ll = line.lower()
    for alias in platform_text_terms(platform):
        if alias in ll:
            return True
    return False


def lines_with_platform(lines: List[str], platform: str) -> List[str]:
    return [ln for ln in lines if line_mentions_platform(ln, platform)]


def sentences_with_platform(lines: List[str], platform: str) -> List[str]:
    out: List[str] = []
    for ln in lines:
        for sent in split_sentences(ln):
            if line_mentions_platform(sent, platform):
                out.append(sent)
    return out


def _platform_positions(sentence: str, platform: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    sl = sentence.lower()
    for term in platform_text_terms(platform):
        pl = term.lower()
        start = 0
        while True:
            i = sl.find(pl, start)
            if i < 0:
                break
            spans.append((i, i + len(pl)))
            start = i + max(1, len(pl))
    return spans


def _span_in_skipped_context(sentence: str, span: Tuple[int, int]) -> bool:
    sl = sentence.lower()
    s, e = span
    window = sl[max(0, s - 35): min(len(sl), e + 35)]
    return any(ctx in window for ctx in _OFFENSE_SPAN_SKIP_CONTEXTS)


def _offense_keyword_spans(sentence: str) -> List[Tuple[int, int]]:
    sl = sentence.lower()
    spans: List[Tuple[int, int]] = []
    for kw in OFFENSE_KEYWORDS:
        if kw in BOUNDED_OFFENSE_KEYWORDS:
            for m in re.finditer(rf"\b{re.escape(kw)}", sl):
                sp = (m.start(), m.end())
                if not _span_in_skipped_context(sentence, sp):
                    spans.append(sp)
        else:
            start = 0
            while True:
                i = sl.find(kw, start)
                if i < 0:
                    break
                sp = (i, i + len(kw))
                if not _span_in_skipped_context(sentence, sp):
                    spans.append(sp)
                start = i + max(1, len(kw))
    return spans


def _within_window(a: Tuple[int, int], b: Tuple[int, int], window: int) -> bool:
    return abs(a[0] - b[0]) <= window or abs(a[1] - b[1]) <= window or (
        a[0] <= b[1] + window and b[0] <= a[1] + window
    )


def has_offense_keyword(sentence: str) -> bool:
    sl = sentence.lower()
    return any(k in sl for k in OFFENSE_KEYWORDS)


def has_gen_ai_offense_keyword(sentence: str) -> bool:
    return any(p.search(sentence) for p in _GEN_AI_CSAM_OFFENSE_PATTERNS)


def has_offense_keyword_for_platform(sentence: str, platform: str) -> bool:
    if platform == "Gen AI" and has_gen_ai_offense_keyword(sentence):
        return True
    return has_offense_keyword(sentence)


def _gen_ai_offense_keyword_spans(sentence: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    for pat in _GEN_AI_CSAM_OFFENSE_PATTERNS:
        for m in pat.finditer(sentence):
            spans.append((m.start(), m.end()))
    return spans


def has_gen_ai_instrumental_construction(sentence: str) -> bool:
    if not line_mentions_platform(sentence, "Gen AI"):
        return False
    return any(p.search(sentence) for p in _GEN_AI_INSTRUMENTAL_PATTERNS)


def has_instrumental_for_platform(sentence: str, platform: str) -> bool:
    if platform == "Gen AI" and has_gen_ai_instrumental_construction(sentence):
        return True
    return has_instrumental_construction(sentence, platform)


def is_gen_ai_scrape_noise(sentence: str) -> bool:
    """Syndicated footer / unrelated legislation — not case conduct."""
    sl = sentence.lower()
    if re.search(r"notice under the americans with disabilities|applauds passage of s\.", sl):
        return True
    if "crack down on" in sl and not _GEN_AI_CONDUCT_RE.search(sentence):
        return True
    return False


def is_gen_ai_weak_stated(sentence: str) -> bool:
    """Downgrade stated when AI mention is incidental, speculative, or non-CSAM."""
    sl = sentence.lower()
    if re.search(r"reported to be artificial intelligence", sl) and not has_gen_ai_offense_keyword(sentence):
        return True
    if re.search(r"\bartificial intelligence of some kind\b", sl):
        return True
    if re.search(r"\bPOSSIBLE\b", sentence) and len(sentence.strip()) < 140:
        return True
    if re.search(r"\b(?:new law that targets|a new law targeting|first case prosecuted under)\b", sl):
        if not _GEN_AI_CONDUCT_RE.search(sentence):
            return True
    if re.search(r"\b(?:advanced through new threats|people who create and share)\b", sl):
        if not _GEN_AI_CONDUCT_RE.search(sentence):
            return True
    return False


def _merge_fragment_lines(lines: List[str]) -> List[str]:
    """Join broken news lines ('among other things,' / trailing commas) before sentence split."""
    out: List[str] = []
    buf = ""
    for raw in lines:
        ln = raw.strip()
        if not ln:
            continue
        buf = f"{buf} {ln}".strip() if buf else ln
        tail = buf.rstrip()
        if tail.endswith(",") or tail.lower().endswith("among other things"):
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def _gen_ai_sentence_rank(sentence: str, tier: str) -> Tuple[int, int, int, int, int]:
    conduct = 1 if _GEN_AI_CONDUCT_RE.search(sentence) else 0
    noise = 1 if is_gen_ai_scrape_noise(sentence) else 0
    weak = 1 if is_gen_ai_weak_stated(sentence) else 0
    return (TIER_RANK[tier], conduct, -noise, -weak, len(sentence))


def offense_keyword_near_platform(sentence: str, platform: str, window: int) -> bool:
    p_spans = _platform_positions(sentence, platform)
    if not p_spans:
        return False
    o_spans = _offense_keyword_spans(sentence)
    if platform == "Gen AI":
        o_spans = o_spans + _gen_ai_offense_keyword_spans(sentence)
    if not o_spans:
        return False
    return any(
        _within_window(ps, os_, window) for ps in p_spans for os_ in o_spans
    )


def _instrumental_patterns(platform: str) -> List[re.Pattern]:
    pl = re.escape(platform.lower())
    if platform not in _INSTRUMENTAL_RE_CACHE:
        raw = [
            rf"\bthrough (?:the )?{pl}\b",
            rf"\bthrough\b[\w\s,\"']{{0,72}}{pl}\b",
            rf"\bvia (?:the )?{pl}\b",
            rf"\bvia\b[\w\s,\"']{{0,48}}{pl}\b",
            rf"\busing (?:the )?{pl}\b",
            rf"\bon (?:the )?{pl}\b",
            rf"\bwith (?:the )?{pl}\b",
            rf"\bfrom (?:the )?{pl}\b",
            rf"\bover (?:the )?{pl}\b",
            rf"\bthrough (?:the )?{pl}\b",
            rf"\b{pl} (?:to|for) (?:send|share|upload|distribut|communicat|contact|solicit|groom|entic|lure|meet|exchang|trad)",
            rf"\b(?:send|sent|share|shared|upload|communicat|contact|solicit|groom|entic|lure|meet|exchang|trad).{{0,25}}{pl}\b",
        ]
        _INSTRUMENTAL_RE_CACHE[platform] = [
            re.compile(p, re.IGNORECASE) for p in raw
        ]
    return _INSTRUMENTAL_RE_CACHE[platform]


def has_instrumental_construction(sentence: str, platform: str) -> bool:
    """Explicit through/via/using/on/with [platform] (short gap allowed) or verb-linked platform."""
    if not line_mentions_platform(sentence, platform):
        return False
    for term in platform_text_terms(platform):
        for pat in _instrumental_patterns(term):
            if pat.search(sentence):
                return True
    return False


def is_awareness_or_list_framing(sentence: str) -> bool:
    sl = sentence.lower()
    if any(trig in sl for trig in AWARENESS_TRIGGERS):
        return True
    # Comma-heavy enumerations without instrumental language (suspect app lists).
    if sl.count(",") >= 3 and "include" in sl:
        return True
    if "are not limited to" in sl or "not limited to:" in sl:
        return True
    return False


def is_enumeration_only(sentence: str, platform: str) -> bool:
    """Comma-separated app lists without case-specific offense verbs."""
    sl = sentence.lower()
    if sl.count(",") < 3:
        return False
    if any(v in sl for v in _ENUM_VERBS):
        return False
    if has_instrumental_construction(sentence, platform):
        return False
    return True


def _generic_chat_as_platform(sentence: str) -> bool:
    """True when 'chat' names a platform/surface, not merely the verb 'chats/chatting'."""
    return bool(
        re.search(
            r"\b(?:chat app|chat apps|chat platform|chat platforms|chat room|chat rooms|"
            r"chat site|chat sites|video chat|live chat|encrypted chat|anonymous chat|"
            r"via chat|through chat|on chat(?! line)|the chat(?! line| room| site| app)|"
            r"chat service|chat feature)\b",
            sentence,
            re.IGNORECASE,
        )
    )


def generic_platform_mention_valid(sentence: str, platform: str) -> bool:
    """Stricter rules for generic DB labels (chat, social media, …)."""
    pl = platform.lower()
    if pl not in GENERIC_PLATFORM_LABELS:
        return True
    sl = sentence.lower()
    if pl == "chat":
        if _generic_chat_as_platform(sentence):
            return True
        # Quoted or labeled as a platform name only.
        if re.search(r'["\']chat["\']', sl):
            return True
        return False
    if pl == "social media":
        return bool(
            re.search(
                r"\bsocial media (?:site|sites|app|apps|platform|platforms|account|accounts)\b",
                sl,
            )
            or "on social media" in sl
            or "via social media" in sl
            or "through social media" in sl
        )
    return pl in sl


def classify_sentence(sentence: str, platform: str) -> str:
    """Strict tiering: default named_only; promote only on strong sentence-level evidence."""
    if not line_mentions_platform(sentence, platform):
        return "named_only"

    if not generic_platform_mention_valid(sentence, platform):
        return "named_only"

    if is_awareness_or_list_framing(sentence):
        return "named_only"

    if is_enumeration_only(sentence, platform):
        return "named_only"

    if not has_offense_keyword_for_platform(sentence, platform):
        sl = sentence.lower()
        if any(k in sl for k in INVESTIGATIVE_KEYWORDS):
            return "inferred"
        return "named_only"

    if has_instrumental_for_platform(sentence, platform):
        tier = "stated"
    elif offense_keyword_near_platform(sentence, platform, INSTRUMENTAL_WINDOW):
        tier = "stated"
    else:
        tier = "inferred"

    if platform == "Gen AI":
        if is_gen_ai_scrape_noise(sentence):
            return "named_only"
        if tier == "stated" and is_gen_ai_weak_stated(sentence):
            return "inferred"
    return tier


def best_sentence(lines: List[str], platform: str) -> Tuple[str, str]:
    """Return (tier, best_sentence) from offense lines."""
    work_lines = _merge_fragment_lines(lines) if platform == "Gen AI" else lines
    candidates = sentences_with_platform(work_lines, platform)
    if not candidates:
        return "named_only", ""

    best_tier = "named_only"
    best_sent = candidates[0]
    best_rank = _gen_ai_sentence_rank(best_sent, best_tier) if platform == "Gen AI" else (TIER_RANK[best_tier], 0, 0, 0, 0)
    for sent in candidates:
        tier = classify_sentence(sent, platform)
        if platform == "Gen AI":
            rank = _gen_ai_sentence_rank(sent, tier)
            if rank > best_rank:
                best_tier, best_sent, best_rank = tier, sent, rank
        elif TIER_RANK[tier] > TIER_RANK[best_tier]:
            best_tier, best_sent = tier, sent
        elif TIER_RANK[tier] == TIER_RANK[best_tier] and len(sent) > len(best_sent):
            best_sent = sent
    return best_tier, best_sent


def extract_quote(line: str, max_len: int = QUOTE_MAX) -> str:
    line = line.strip()
    if len(line) <= max_len:
        return line
    return line[: max_len - 3].rstrip() + "..."


def extract_harm(text: str) -> str:
    snippet = text[:3000]
    for pat in HARM_PATTERNS:
        m = re.search(pat, snippet, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:120]
    return ""


def simple_role(line: str, platform: str = "") -> str:
    ll = line.lower()
    if any(k in ll for k in ("upload", "shar", "distribut", "trad", "exchang")):
        return "distribution of CSAM"
    if any(k in ll for k in ("solicit", "groom", "entic", "lur")):
        return "grooming / soliciting minor"
    if any(k in ll for k in ("contact", "communicat", "messag", "chat")):
        return "contact and communication with victim"
    if platform == "Gen AI" and (
        has_gen_ai_offense_keyword(line)
        or any(k in ll for k in ("produc", "stream", "creat", "generat"))
    ):
        return "CSAM production"
    if any(k in ll for k in ("produc", "stream", "creat")):
        return "CSAM production"
    if "cybertip" in ll or "reported" in ll or "flagged" in ll:
        return "platform-reported CSAM (distribution inferred)"
    return "used in offense (specific role unspecified)"


def reasoning_for(tier: str, platform: str, line: str) -> str:
    preview = extract_quote(line, 70)
    if tier == "stated":
        return (
            f"Sentence ties {platform} instrumentally to offense conduct "
            f"(through/via/using or offense verb within {INSTRUMENTAL_WINDOW} chars): "
            f"\"{preview}\""
        )
    if tier == "inferred":
        return (
            f"{platform} and offense language co-occur in the same sentence without "
            f"instrumental proximity; role inferred: \"{preview}\""
        )
    return f"'{platform}' named without instrumental offense role in matching sentence."


def find_db_gaps(offense_text: str, db_platforms: Set[str]) -> List[Dict[str, str]]:
    gaps: List[Dict[str, str]] = []
    db_lower = {p.lower() for p in db_platforms}
    ol = offense_text.lower()
    lines = [ln.strip() for ln in offense_text.split("\n") if len(ln.strip()) > 20]
    for plat in KNOWN_PLATFORM_NAMES:
        if plat.lower() in db_lower:
            continue
        if plat.lower() not in ol:
            continue
        snippet = "(found in text)"
        for ln in lines:
            if plat.lower() in ln.lower():
                snippet = extract_quote(ln, 80)
                break
        gaps.append({"platform": plat, "found_in": snippet})
    return gaps


def process_case(case_id: str, platforms: List[str], case_text: str) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    exclusions: List[Dict[str, str]] = []
    hit_cap = False

    if not case_text or not case_text.strip():
        harm = ""
        for p in platforms:
            records.append({
                "case_id": case_id,
                "platform": p,
                "platform_type": PLATFORM_TYPE.get(p, "Unknown"),
                "platform_role_in_offense": "",
                "harm": harm,
                "evidence_quote": "",
                "stated_vs_inferred": "named_only",
                "your_reasoning": "Case text is empty; cannot verify offense context.",
            })
        return {"records": records, "exclusions": exclusions, "db_gaps": [], "hit_text_cap": False}

    offense, psa, hit_cap = offense_lines(case_text)
    offense_blob = "\n".join(offense)
    harm = extract_harm(offense_blob)

    for platform in platforms:
        off_hits = lines_with_platform(offense, platform)
        psa_hits = lines_with_platform(psa, platform)

        if platform == "Gen AI":
            clean_hits = [ln for ln in off_hits if not is_gen_ai_scrape_noise(ln)]
            if off_hits and not clean_hits:
                exclusions.append({
                    "case_id": case_id,
                    "platform": platform,
                    "exclusion_reason": (
                        "Scrape noise only — Gen AI mention appears only in site footer / "
                        "unrelated legislation rail, not case conduct. "
                        f"Sample: \"{extract_quote(off_hits[0], 80)}\""
                    ),
                })
                continue
            off_hits = clean_hits

        if not off_hits:
            if psa_hits:
                exclusions.append({
                    "case_id": case_id,
                    "platform": platform,
                    "exclusion_reason": (
                        f"PSA-only — '{platform}' appears only after PSA boundary. "
                        f"Sample: \"{extract_quote(psa_hits[0], 80)}\""
                    ),
                })
            else:
                records.append({
                    "case_id": case_id,
                    "platform": platform,
                    "platform_type": PLATFORM_TYPE.get(platform, "Unknown"),
                    "platform_role_in_offense": "",
                    "harm": harm,
                    "evidence_quote": "",
                    "stated_vs_inferred": "named_only",
                    "your_reasoning": (
                        "Platform tagged in DB platforms_used but not found in capped case text."
                    ),
                    "_text_not_found": True,
                })
            continue

        tier, picked = best_sentence(off_hits, platform)

        records.append({
            "case_id": case_id,
            "platform": platform,
            "platform_type": PLATFORM_TYPE.get(platform, "Unknown"),
            "platform_role_in_offense": simple_role(picked, platform),
            "harm": harm,
            "evidence_quote": extract_quote(picked),
            "stated_vs_inferred": tier,
            "your_reasoning": reasoning_for(tier, platform, picked),
        })

    db_gaps = find_db_gaps(offense_blob, set(platforms))
    return {
        "records": records,
        "exclusions": exclusions,
        "db_gaps": db_gaps,
        "hit_text_cap": hit_cap,
    }


def md_cell(value: str, max_len: int = 60) -> str:
    v = str(value).replace("|", "\\|").replace("\n", " ")
    if len(v) > max_len:
        return v[: max_len - 3] + "..."
    return v


def write_affordance_md(
    all_records: List[Dict[str, Any]],
    all_exclusions: List[Dict[str, str]],
    all_db_gaps: List[Dict[str, Any]],
    path: Path,
) -> None:
    by_platform: Dict[str, Dict[str, List]] = defaultdict(
        lambda: {"stated": [], "inferred": [], "named_only": []}
    )
    for r in all_records:
        plat = r["platform"]
        tier = r["stated_vs_inferred"]
        by_platform[plat][tier if tier in ("stated", "inferred") else "named_only"].append(r)

    excl_by: Dict[str, List] = defaultdict(list)
    for e in all_exclusions:
        excl_by[e["platform"]].append(e)

    gap_by: Dict[str, List] = defaultdict(list)
    for g in all_db_gaps:
        gap_by[g["platform"]].append(g)

    order = sorted(by_platform.keys(), key=lambda p: -len(by_platform[p]["stated"]))
    lines = [
        "# Q1 Platform-Affordance Evidence Table",
        "",
        "> Affordance / harm vector is manual analytical layer. This file is the evidence base.",
        "",
        "---",
        "",
    ]

    for plat in order:
        pdata = by_platform[plat]
        ptype = PLATFORM_TYPE.get(plat, "Unknown")
        stated = pdata["stated"]
        inferred = pdata["inferred"]
        named = pdata["named_only"]
        lines.append(f"## {plat} ({ptype})")
        lines.append("")
        lines.append("**Affordance / Surface / Harm:** *(blank — manual)*")
        lines.append("")
        lines.append(f"**Stated evidence** ({len(stated)} cases):")
        if stated:
            lines.append("| case_id | platform_role | harm | quote |")
            lines.append("|---|---|---|---|")
            for r in sorted(stated, key=lambda x: x["case_id"]):
                lines.append(
                    f"| {r['case_id']} | {md_cell(r['platform_role_in_offense'], 50)} "
                    f"| {md_cell(r['harm'], 55)} | {md_cell(r['evidence_quote'], 60)} |"
                )
        else:
            lines.append("*(none)*")
        lines.append("")
        lines.append(f"**Inferred evidence** ({len(inferred)} cases):")
        if inferred:
            lines.append("| case_id | platform_role | harm | quote | reasoning |")
            lines.append("|---|---|---|---|---|")
            for r in sorted(inferred, key=lambda x: x["case_id"]):
                lines.append(
                    f"| {r['case_id']} | {md_cell(r['platform_role_in_offense'], 45)} "
                    f"| {md_cell(r['harm'], 50)} | {md_cell(r['evidence_quote'], 55)} "
                    f"| {md_cell(r['your_reasoning'], 80)} |"
                )
        else:
            lines.append("*(none)*")
        lines.append("")
        lines.append(
            f"**Named only** ({len(named)} cases): "
            + (", ".join(sorted({r['case_id'] for r in named})) if named else "*(none)*")
        )
        lines.append("")
        excl = excl_by.get(plat, [])
        lines.append(f"**PSA exclusions** ({len(excl)} cases):")
        if excl:
            for e in sorted(excl, key=lambda x: x["case_id"]):
                lines.append(f"- `{e['case_id']}`: {e['exclusion_reason'][:100]}")
        else:
            lines.append("*(none)*")
        lines.append("")
        gaps = gap_by.get(plat, [])
        lines.append(f"**DB gaps flagged** ({len(gaps)} cases):")
        if gaps:
            for g in sorted(gaps, key=lambda x: x["case_id"])[:20]:
                lines.append(
                    f"- `{g['case_id']}`: `{g['platform']}` — \"{g['found_in'][:60]}\""
                )
        else:
            lines.append("*(none)*")
        lines.append("")
        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    test_mode = "--test" in sys.argv

    print("Loading candidates...", flush=True)
    with open(CANDIDATES_FILE, encoding="utf-8") as f:
        candidates = json.load(f)

    case_to_platforms: Dict[str, List[str]] = defaultdict(list)
    for entry in candidates["flat"]:
        plat = entry["platform"]
        for cid in entry["case_ids"]:
            case_to_platforms[cid].append(plat)

    all_case_ids = sorted(case_to_platforms.keys())
    if test_mode:
        all_case_ids = all_case_ids[:50]
        print("TEST MODE: first 50 cases", flush=True)
    print(f"Total cases to process: {len(all_case_ids)}", flush=True)

    print("Loading case texts from DB...", flush=True)
    conn = sqlite3.connect(DB)
    db_rows: Dict[str, str] = {}
    # SQLite's default variable limit is 32766. Chunk so a doubled corpus still fits.
    for start in range(0, len(all_case_ids), 5000):
        chunk = all_case_ids[start : start + 5000]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT id, json_extract(raw_data, '$.case_text') "
            f"FROM cases WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            db_rows[row[0]] = row[1] or ""
    corpus_identity = None
    try:
        run_dir = Path(__file__).resolve().parents[2] / "run"
        if str(run_dir) not in sys.path:
            sys.path.insert(0, str(run_dir))
        from platform_affordance_evidence_freshness import read_corpus_identity

        corpus_identity = read_corpus_identity(conn)
    except Exception as exc:
        print(f"Corpus identity not recorded: {exc}", flush=True)
    conn.close()
    print(f"Loaded {len(db_rows)} case texts.", flush=True)

    all_records: List[Dict[str, Any]] = []
    all_exclusions: List[Dict[str, str]] = []
    all_db_gaps: List[Dict[str, Any]] = []
    text_cap_hits = 0

    for i, case_id in enumerate(all_case_ids, 1):
        if test_mode or i % 200 == 0:
            print(f"  processing {i}/{len(all_case_ids)}: {case_id}", flush=True)
        result = process_case(case_id, case_to_platforms[case_id], db_rows.get(case_id, ""))
        all_records.extend(result["records"])
        all_exclusions.extend(result["exclusions"])
        for gap in result["db_gaps"]:
            all_db_gaps.append({"case_id": case_id, **gap})
        if result.get("hit_text_cap"):
            text_cap_hits += 1

    print("Processing complete.", flush=True)
    print(f"  Records:    {len(all_records)}", flush=True)
    print(f"  Exclusions: {len(all_exclusions)}", flush=True)
    print(f"  DB gaps:    {len(all_db_gaps)}", flush=True)
    print(f"  TEXT_CAP hits ({TEXT_CAP} chars): {text_cap_hits}/{len(all_case_ids)}", flush=True)

    evidence_out = {
        "_meta": {
            "generated": str(date.today()),
            "cases_processed": len(all_case_ids),
            "offense_records": len(all_records),
            "psa_exclusions": len(all_exclusions),
            "db_gaps": len(all_db_gaps),
            "text_cap_hits": text_cap_hits,
            "text_cap": TEXT_CAP,
            **(
                {
                    "corpus_case_count": corpus_identity["case_count"],
                    "extraction_run_fingerprint": corpus_identity["extraction_run_fingerprint"],
                }
                if corpus_identity
                else {}
            ),
        },
        "records": all_records,
        "excluded_platforms": all_exclusions,
        "db_gaps": all_db_gaps,
    }
    (OUTPUT_DIR / "platform_affordance_evidence.json").write_text(
        json.dumps(evidence_out, indent=2), encoding="utf-8"
    )
    print("Wrote platform_affordance_evidence.json", flush=True)

    summary: Dict[str, Dict[str, Any]] = {}
    for r in all_records:
        plat = r["platform"]
        if plat not in summary:
            summary[plat] = {
                "platform": plat,
                "stated": 0,
                "inferred": 0,
                "named_only": 0,
            }
        tier = r["stated_vs_inferred"]
        if tier == "stated":
            summary[plat]["stated"] += 1
        elif tier == "inferred":
            summary[plat]["inferred"] += 1
        else:
            summary[plat]["named_only"] += 1

    summary_list = sorted(summary.values(), key=lambda x: -x["stated"])

    write_affordance_md(all_records, all_exclusions, all_db_gaps, OUTPUT_DIR / "platform_affordance_evidence_table.md")
    print("Wrote platform_affordance_evidence_table.md", flush=True)

    total_stated = sum(1 for r in all_records if r["stated_vs_inferred"] == "stated")
    total_inferred = sum(1 for r in all_records if r["stated_vs_inferred"] == "inferred")
    total_named = sum(1 for r in all_records if r["stated_vs_inferred"] == "named_only")

    print()
    print("=" * 50)
    print("PIPELINE COMPLETE")
    print("=" * 50)
    print(f"Cases processed:          {len(all_case_ids)}")
    print(f"Total offense records:    {len(all_records)}")
    print(f"  Stated:                 {total_stated}")
    print(f"  Inferred:               {total_inferred}")
    print(f"  Named-only:             {total_named}")
    print(f"PSA exclusions:           {len(all_exclusions)}")
    print(f"DB gaps flagged:          {len(all_db_gaps)}")
    print(f"TEXT_CAP hits:            {text_cap_hits}")
    print()
    print("Top 10 platforms by stated-evidence case count:")
    for s in summary_list[:10]:
        print(
            f"  {s['platform']:<30} stated={s['stated']:>4}  "
            f"inferred={s['inferred']:>4}  named={s['named_only']:>4}"
        )
    print("=" * 50)


if __name__ == "__main__":
    main()
