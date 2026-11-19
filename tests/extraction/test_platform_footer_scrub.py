"""Agency social-media footers must not become platforms_used (#21).

Fixture footers are copied from live releases (nj_ag_2016_004 / _013,
doj_safe_childhood_2021_040, ice_2024_001, us_marshals_2026_013,
cbp_2021_002, south_florida_icac_2024_023); bodies are synthetic, no names.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROC = REPO / "src" / "Processing Layer"
PATTERN = PROC / "Pattern Processing Layer" / "pattern_processing.py"


def _load_processing():
    for p in (PATTERN.parent, PROC):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    name = "pattern_processing_under_test_footer_scrub"
    spec = importlib.util.spec_from_file_location(name, PATTERN)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pp = _load_processing()

NJ_AG_FOOTER = (
    "Defense Attorney: Defense Counsel, Esq.\n"
    "Follow the New Jersey Attorney General’s Office online at Twitter , Facebook , "
    "Instagram & YouTube . The\nsocial media links provided are for reference only. "
    "The New Jersey Attorney General’s Office does not endorse\nany non-governmental "
    "websites, companies or applications."
)

P2P_BODY = (
    "Detectives identified a computer at the defendant's residence that was being used "
    "to share child pornography on a peer-to-peer network. A forensic review of a "
    "computer tower seized from the home found approximately 180 videos.\n"
)


def _platforms(text: str) -> list[str]:
    return pp.extract_platforms({"case_text": text})


class TestAgencyFooterScrub(unittest.TestCase):
    def test_nj_ag_footer_only_brands_are_dropped(self):
        got = _platforms(P2P_BODY + NJ_AG_FOOTER)
        for brand in ("Twitter / X", "Facebook", "Instagram", "YouTube", "social media", "online"):
            self.assertNotIn(brand, got, got)

    def test_nj_ag_footer_without_follow_lead_in(self):
        # nj_ag_2017_022: extraction starts the footer at "Office online at".
        footer = (
            "Defense Attorneys : Defense Counsel, Esq.\nOffice online at Twitter , Facebook , "
            "Instagram & YouTube . The social media links provided are for reference\nonly."
        )
        got = _platforms(P2P_BODY + footer)
        for brand in ("Twitter / X", "Facebook", "Instagram", "YouTube", "social media", "online"):
            self.assertNotIn(brand, got, got)

    def test_nj_ag_genuine_twitter_instrument_kept(self):
        body = (
            "NCMEC reported a Twitter account that allegedly was uploading child "
            "pornography. Detectives identified 12 images the defendant allegedly "
            "distributed via the Twitter account.\n"
        )
        got = _platforms(body + NJ_AG_FOOTER)
        self.assertIn("Twitter / X", got)
        for brand in ("Facebook", "Instagram", "YouTube", "social media"):
            self.assertNotIn(brand, got, got)

    def test_federal_follow_us_footers_dropped(self):
        footers = [
            "Case No. 20-cr-165\n# # #\nVisit our website | Follow us on Twitter @DCoNews",
            "For more news on how ERO carries out its mission, follow us on X, formerly "
            "known as Twitter,\n@ERONewOrleans .",
            "Follow the USMS on X (formerly Twitter) @USMSDenver.",
            "Follow the U.S. Attorney’s Office, District of Arizona, on Twitter @USAO_AZ "
            "for the latest news.",
            "You can also follow the latest news and updates about the U.S. Marshals Service "
            "on Facebook and X (formerly Twitter); @USMarshalsHQ or @USMSDenver.",
            "Follow the Director of CBP’s Laredo Field Office on Twitter at @DFOLaredo , "
            "on Instagram at @dfolaredo\nand U.S. Customs and Border Protection at "
            "@CBPSouthTexas for breaking news.",
            "Bond was set at $1,460,000.\nFollow us on social: Facebook | Twitter | "
            "Instagram | TikTok | YouTube\n",
        ]
        for footer in footers:
            got = _platforms(P2P_BODY + footer)
            for brand in ("Twitter / X", "Facebook", "Instagram", "TikTok", "YouTube"):
                self.assertNotIn(brand, got, (footer, got))

    def test_offender_follow_request_is_not_a_footer(self):
        # Instrument phrasing that starts with "Follow" must survive the scrub.
        text = P2P_BODY + (
            "The defendant messaged the victim, “Follow me on Snapchat,” and later "
            "asked her to follow him on Instagram where he sent explicit images."
        )
        got = _platforms(text)
        self.assertIn("Snapchat", got)
        self.assertIn("Instagram", got)

    def test_extract_features_uses_scrubbed_platforms(self):
        feats = pp.extract_features(
            {"case_id": "t", "source": "NJ AG", "case_text": P2P_BODY + NJ_AG_FOOTER}
        )
        self.assertNotIn("Facebook", feats["platforms_used"])


if __name__ == "__main__":
    unittest.main()
