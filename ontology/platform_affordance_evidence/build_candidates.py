"""Stage 1: Build candidates.json — platform → case IDs with per-platform counts."""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src/Processing Layer/Pattern Processing Layer"))
from ai_extraction_patterns import (  # noqa: E402
    AI_CSAM_IMPLIES_TOOL_RE,
    AI_CSAM_TOPIC_RE,
    GEN_AI_TOOL_RE,
)

DB = "caselinker.db"
OUT = "ontology/platform_affordance_evidence/candidates.json"

PLATFORM_TYPE = {
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
    # Broad labels — keep but flag as generic
    "social media": "SocialMediaPlatform",
    "gaming": "GamePlatform",
    "email": "MessagingService",
    "internet": "Unknown",
    "dark web": "DarkWebService",
    "chat": "MessagingService",
    "other": "Unknown",
}

# Generics to exclude
GENERICS = {
    "online",
    "internet",
}

_PHOTO_BELOW_MARKERS = ("booking photo is below", "photo is below")


def _gen_ai_match_starts(text: str) -> list[int]:
    """Start offsets of regex matches that justify a Gen AI platforms_used tag."""
    starts: list[int] = []
    for pat in (GEN_AI_TOOL_RE, AI_CSAM_IMPLIES_TOOL_RE, AI_CSAM_TOPIC_RE):
        for m in pat.finditer(text):
            starts.append(m.start())
    return starts


def _photo_below_cutoff(text: str) -> int | None:
    """End offset of the latest photo-below embed marker, or None."""
    tl = text.lower()
    cutoff: int | None = None
    for marker in _PHOTO_BELOW_MARKERS:
        i = tl.find(marker)
        if i >= 0:
            end = i + len(marker)
            if cutoff is None or end > cutoff:
                cutoff = end
    return cutoff


def _gen_ai_footer_start(text: str) -> int | None:
    """Start offset of syndicated site chrome / unrelated AG legislation rails."""
    tl = text.lower()
    idx: int | None = None
    for marker in (
        "notice under the americans with disabilities",
        "applauds passage of s.",
        "accessibility 2. privacy policy",
    ):
        i = tl.rfind(marker)
        if i >= 0 and (idx is None or i < idx):
            idx = i
    return idx


def gen_ai_candidate_valid(case_id: str, case_text: str) -> bool:
    """False when every Gen AI match sits in trailing embed text after photo-below or site footer."""
    if case_id.startswith("nj_ag_"):
        return True
    if not case_text or not case_text.strip():
        return False
    starts = _gen_ai_match_starts(case_text)
    if not starts:
        return False
    cutoff = _photo_below_cutoff(case_text)
    if cutoff is not None and not any(s < cutoff for s in starts):
        return False
    footer = _gen_ai_footer_start(case_text)
    if footer is not None and all(s >= footer for s in starts):
        return False
    return True


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT cases.id, j.value AS platform
        FROM cases, json_each(cases.platforms_used) AS j
        WHERE cases.platforms_used IS NOT NULL
    """)

    platform_to_cases = defaultdict(set)
    skipped_platforms = defaultdict(int)
    skipped_gen_ai_embed: list[str] = []
    gen_ai_ids: list[str] = []
    rows = cur.fetchall()
    for row in rows:
        if row["platform"] == "Gen AI":
            gen_ai_ids.append(row["id"])

    gen_ai_text: dict[str, str] = {}
    if gen_ai_ids:
        # Case text is only needed for the Gen AI embed check. Pulling raw_data
        # for every platform row re-reads the full release once per platform.
        for start in range(0, len(gen_ai_ids), 500):
            chunk = gen_ai_ids[start : start + 500]
            placeholders = ",".join("?" * len(chunk))
            for cid, raw in cur.execute(
                f"SELECT id, json_extract(raw_data, '$.case_text') FROM cases WHERE id IN ({placeholders})",
                chunk,
            ):
                gen_ai_text[cid] = raw or ""

    for row in rows:
        p = row["platform"]
        if p.lower() in GENERICS or p.lower().startswith("unknown"):
            skipped_platforms[p] += 1
            continue
        if p == "Gen AI":
            if not gen_ai_candidate_valid(row["id"], gen_ai_text.get(row["id"], "")):
                skipped_gen_ai_embed.append(row["id"])
                continue
        if p not in PLATFORM_TYPE:
            # Unknown named platform — still include, type = Unknown
            pass
        platform_to_cases[p].add(row["id"])

    conn.close()

    # Build output grouped by platform_type
    by_type = defaultdict(list)
    for platform, case_ids in sorted(platform_to_cases.items(), key=lambda x: -len(x[1])):
        ptype = PLATFORM_TYPE.get(platform, "Unknown")
        by_type[ptype].append({
            "platform": platform,
            "platform_type": ptype,
            "case_count": len(case_ids),
            "case_ids": sorted(case_ids),
        })

    # Sort within each type by count desc
    for ptype in by_type:
        by_type[ptype].sort(key=lambda x: -x["case_count"])

    output = {
        "summary": {
            "total_candidate_cases": len({cid for cases in platform_to_cases.values() for cid in cases}),
            "total_platform_case_pairs": sum(len(v) for v in platform_to_cases.values()),
            "platforms_with_named_label": len(platform_to_cases),
            "skipped_generic_labels": dict(skipped_platforms),
        },
        "by_platform_type": dict(by_type),
        "flat": [
            {
                "platform": platform,
                "platform_type": PLATFORM_TYPE.get(platform, "Unknown"),
                "case_count": len(case_ids),
                "case_ids": sorted(case_ids),
            }
            for platform, case_ids in sorted(platform_to_cases.items(), key=lambda x: -len(x[1]))
        ],
    }

    with open(OUT, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {OUT}")
    print(f"\nSummary:")
    print(f"  Total candidate cases (distinct): {output['summary']['total_candidate_cases']}")
    print(f"  Total platform-case pairs:         {output['summary']['total_platform_case_pairs']}")
    print(f"  Named platforms:                   {output['summary']['platforms_with_named_label']}")
    print(f"\nPer-platform counts:")
    print(f"{'Platform':<30} {'Type':<30} {'Cases':>6}")
    print("-" * 70)
    for entry in output["flat"]:
        print(f"{entry['platform']:<30} {entry['platform_type']:<30} {entry['case_count']:>6}")

    print(f"\nSkipped generics:")
    for k, v in sorted(skipped_platforms.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    if skipped_gen_ai_embed:
        print(f"\nSkipped Gen AI (photo-below embed): {len(skipped_gen_ai_embed)}")
        for cid in sorted(skipped_gen_ai_embed):
            print(f"  {cid}")

if __name__ == "__main__":
    main()
