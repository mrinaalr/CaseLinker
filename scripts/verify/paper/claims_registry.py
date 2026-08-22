"""Curated registry of empirical and background claims in the paper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ClaimKind = Literal[
    "corpus_stat",
    "q1_stat",
    "platform_manifest",
    "affordance_count",
    "pacer",
    "lifecycle",
    "external_citation",
    "literature",
    "theoretical",
    "methodology",
]

VerifyMethod = Literal[
    "db",
    "q1_json",
    "file",
    "lifecycle",
    "paper_substring",
    "external",
    "literature",
    "manual",
    "computed",
]


@dataclass(frozen=True)
class Claim:
    id: str
    section: str
    text: str
    kind: ClaimKind
    verify: VerifyMethod
    bold: bool = False
    why: str = ""
    citation: str = ""
    expected: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def build_claims() -> list[Claim]:
    """All claims picked for verification (headline stats, corpus, Q1, external cites)."""
    c: list[Claim] = []

    def add(
        id_: str,
        section: str,
        text: str,
        kind: ClaimKind,
        verify: VerifyMethod,
        *,
        bold: bool = False,
        why: str = "",
        citation: str = "",
        expected: str = "",
        tags: tuple[str, ...] = (),
    ) -> None:
        c.append(
            Claim(
                id=id_,
                section=section,
                text=text,
                kind=kind,
                verify=verify,
                bold=bold,
                why=why,
                citation=citation,
                expected=expected,
                tags=tags,
            )
        )

    # --- Cover / headline (bold in PDF metadata block) ---
    add(
        "cover.corpus_cases",
        "Cover",
        "Corpus comprises 7,426 ICAC case records.",
        "corpus_stat",
        "db",
        bold=True,
        why="Primary scale claim; drives every rate and Q1 denominator.",
        expected="7426",
    )
    add(
        "cover.features",
        "Cover",
        "Corpus yields 80,000+ structured features.",
        "corpus_stat",
        "computed",
        bold=True,
        why="Headline pipeline scale; must match extraction dimension accounting.",
        expected=">=80000",
    )
    add(
        "cover.sources",
        "Cover",
        "Cases collected from 56 law enforcement sources.",
        "corpus_stat",
        "db",
        bold=True,
        why="Source diversity claim on cover.",
        expected="56",
    )
    add(
        "cover.task_forces",
        "Cover",
        "Coverage spans 61 ICAC task forces.",
        "corpus_stat",
        "db",
        bold=True,
        why="ICAC ecosystem breadth; cross-check narrative + ingest mapping.",
        expected="61",
    )
    add(
        "cover.agencies",
        "Cover",
        "Corpus reflects 3,500+ law enforcement agencies.",
        "corpus_stat",
        "db",
        bold=True,
        why="Agency normalization headline.",
        expected=">=3500",
    )
    add(
        "cover.pacer_records",
        "Cover",
        "PACER layer includes 8 federal prosecution records (3 indictments, 2 Statements of Offense).",
        "pacer",
        "file",
        bold=True,
        why="Ground-truth court anchor count; must match BULK_FOLDER + canonical 5.",
        expected="8",
    )
    add(
        "cover.timespan",
        "Cover",
        "Corpus timespan is 2002–2026.",
        "corpus_stat",
        "db",
        bold=True,
        why="Temporal scope for era analysis.",
        expected="2002-2026",
    )
    add(
        "cover.platforms_analyzed",
        "Cover",
        "30+ platforms analyzed in affordance framework.",
        "corpus_stat",
        "db",
        bold=True,
        why="Platform breadth for Q1 manifest.",
        expected=">=30",
    )

    # --- Abstract ---
    add(
        "abstract.corpus",
        "Abstract",
        "Analysis draws on 7,426 curated ICAC case records spanning 2002 to 2026.",
        "corpus_stat",
        "db",
        why="Restates cover corpus claim.",
    )
    add(
        "abstract.affordance_stability",
        "Abstract",
        "Same capability types (anonymity, ephemerality, distribution, contact discovery, trust-building) recur across platforms.",
        "theoretical",
        "paper_substring",
        why="Core thesis; verified as stated in paper text, not independently counted here.",
    )

    # --- §2 Prior work (external citations) ---
    add(
        "prior.icac_task_forces",
        "§2.1",
        "ICAC program: 61 federally coordinated task forces representing 5,400+ agencies (est. 1998).",
        "external_citation",
        "external",
        citation="ICAC / OJJDP program materials",
        why="Background enforcement infrastructure; not derived from CaseLinker DB.",
    )
    add(
        "prior.icac_fy2024_investigations",
        "§2.1",
        "FY2024 ICAC task forces conducted ~203,467 investigations.",
        "external_citation",
        "external",
        citation="ICAC annual report FY2024",
        why="External scale comparator for triage argument.",
    )
    add(
        "prior.icac_fy2024_arrests",
        "§2.1",
        "FY2024 ICAC arrests exceeded 12,600 suspected offenders.",
        "external_citation",
        "external",
        citation="ICAC annual report FY2024",
        why="Pairs with CyberTipline volume argument.",
    )
    add(
        "prior.ncmec_cybertipline_2024",
        "§2.1",
        "2024 NCMEC received ~20.5M CyberTipline reports (~29.2M incidents).",
        "external_citation",
        "external",
        citation="NCMEC CyberTipline annual data",
        why="Detection-vs-investigation scale gap.",
    )
    add(
        "prior.tech_coalition_hash_89",
        "§2.1",
        "Tech Coalition 2023 survey: 89% of members deploy image hash-matching.",
        "external_citation",
        "external",
        citation="Tech Coalition Transparency Report 2023",
        why="Detection infrastructure background.",
    )
    add(
        "prior.thorn_safer_76m",
        "§2.1",
        "Thorn Safer uses 76M+ verified CSAM hashes.",
        "external_citation",
        "external",
        citation="Thorn Safer product documentation",
        why="Hash corpus scale for detection layer.",
    )
    add(
        "prior.wolak_internet_initiated",
        "§2.1",
        "Wolak et al. documented internet-initiated sex crime dynamics via LE survey.",
        "literature",
        "literature",
        citation="[24]",
        why="Behavioral research anchor cited in paper.",
    )
    add(
        "prior.livingstone_digital_physical",
        "§1",
        "Livingstone and Smith [12] document inseparability of digital and physical child risk.",
        "literature",
        "literature",
        citation="[12]",
        why="Cited theoretical bridge for harm signatures.",
    )
    add(
        "prior.gibson_affordance",
        "§2.2",
        "Affordance concept originates with Gibson [5] (ecological psychology).",
        "literature",
        "literature",
        citation="[5]",
        why="Framework provenance.",
    )

    # --- §3 Corpus & pipeline ---
    add(
        "s3.corpus_public",
        "§3.1",
        "All 7,426 records are publicly available; no private investigative files.",
        "methodology",
        "paper_substring",
        why="Ethics / NHSR scope statement.",
    )
    add(
        "s3.hrpo_determination",
        "§3.1",
        "Research under UMass HRPO NHSR Determination #7668.",
        "methodology",
        "paper_substring",
        why="IRB determination cited in methods.",
    )
    add(
        "s3.agency_variants",
        "§3.1",
        "Agency normalization resolves 3,796 unique agency string variants.",
        "corpus_stat",
        "db",
        why="Named normalization workload.",
        expected="3796",
    )
    add(
        "s3.q1_candidates",
        "§3.1",
        "Q1 candidate pool: 1,875 cases (25.1% of corpus) with named platforms.",
        "q1_stat",
        "q1_json",
        why="Q1 denominator for affordance evidence.",
        expected="1875",
    )
    add(
        "s3.q1_no_platform_pct",
        "§3.1",
        "74.9% of corpus lacks named platform for affordance-level analysis.",
        "q1_stat",
        "computed",
        why="Complement of Q1 candidate share.",
        expected="74.9",
    )
    add(
        "s3.q1_platform_pairs",
        "§3.1",
        "Q1 evidence base: 1,875 cases across 3,128 platform–case records.",
        "q1_stat",
        "q1_json",
        why="Platform-case pair count from evidence pipeline.",
        expected="3128",
    )
    add(
        "s3.q1_named_platforms",
        "§3.1",
        "54 named platforms in Q1 candidate pool.",
        "q1_stat",
        "q1_json",
        why="Manifest platform count.",
        expected="54",
    )
    add(
        "s3.q1_stated_cases",
        "§3.1",
        "856 cases (45.8%) contain at least one stated platform-offense record.",
        "q1_stat",
        "q1_json",
        bold=True,
        why="Strongest evidentiary tier; headline Q1 quality stat.",
        expected="856",
    )
    add(
        "s3.q1_inferred_only",
        "§3.1",
        "134 cases (7.2%) carry inferred-only platform evidence.",
        "q1_stat",
        "q1_json",
        expected="134",
    )
    add(
        "s3.q1_named_only",
        "§3.1",
        "881 cases (47.1%) are named-only platform mentions.",
        "q1_stat",
        "q1_json",
        expected="881",
    )
    add(
        "s3.shacl_graphs",
        "§3.2",
        "1,500+ SHACL-validated case graphs support Q1 analysis.",
        "corpus_stat",
        "file",
        why="Knowledge graph corpus size.",
        expected=">=1500",
    )
    add(
        "s3.mcp_tools",
        "§3.2",
        "CaseLinker MCP server exposes 37 structured tools.",
        "corpus_stat",
        "computed",
        why="Reproducibility / tooling claim.",
        expected="37",
    )
    add(
        "s3.case_uco_classes",
        "§3.2",
        "CASE-UCO SDK implements 428+ ontology classes.",
        "external_citation",
        "external",
        citation="CASE-UCO SDK / Project VIC",
        why="External SDK scope cited for PACER graphs.",
    )
    add(
        "s3.opensource_mit",
        "§3.1",
        "CaseLinker released open-source under MIT License at github.com/mrinaalr/CaseLinker.",
        "methodology",
        "external",
        why="Artifact availability.",
    )

    # --- §3.3 PACER / Q2 ---
    add(
        "s3.pacer_expansion_four",
        "§3.3",
        "Four additional federal prosecution records captured via facet-tree traversal (targeting 50 total).",
        "pacer",
        "file",
        why="Expansion beyond canonical 5 lifecycle cases.",
        expected=">=4",
    )
    add(
        "s3.q2_canonical_five",
        "§3.3",
        "Q2 anchored on five PACER federal cases (Rehman, Amin, Pathmanathan, Bermudez, Riley).",
        "lifecycle",
        "lifecycle",
        why="Harm-signature ground truth set.",
        expected="5",
    )

    # --- §4 Platform manifest (bold table stats) ---
    platforms = [
        ("kik", "Kik", "208 stated", "352 total"),
        ("snapchat", "Snapchat", "169 stated", "257 total"),
        ("discord", "Discord", "43 stated", "99 total"),
        ("facebook", "Facebook", "55 stated", "274 total"),
        ("instagram", "Instagram", "27 stated", "174 total"),
        ("reddit", "Reddit", "10 stated", "22 total"),
        ("tiktok", "TikTok", "4 stated", "25 total"),
        ("dropbox", "Dropbox", "33 stated", "86 total"),
        ("mega", "Mega.nz", "3 stated", "15 total"),
        ("whisper", "Whisper", "3 stated", "11 total"),
        ("omegle", "Omegle", "2 stated", "7 total"),
        ("genai", "Gen AI", "21 stated", "54 total"),
        ("p2p", "BitTorrent/P2P", "3 stated", "8 total"),
        ("video", "Video streaming", "6 stated", "28 total"),
        ("gaming", "Gaming platforms", "4 stated", "29 total"),
    ]
    for pid, name, stated, total in platforms:
        add(
            f"manifest.{pid}",
            "§4 Table 1",
            f"{name}: {stated} · {total} in Q1 evidence.",
            "platform_manifest",
            "q1_json",
            bold=True,
            why="Table 1 headline platform row; verified against q1_evidence.json tiers.",
            expected=f"{stated}|{total}",
        )

    add(
        "s4.platform_labels",
        "§4",
        "Q1 evidence base names 54 distinct platform labels.",
        "q1_stat",
        "q1_json",
        expected="54",
    )
    add(
        "s4.affordance_predicts_harm",
        "§4",
        "A platform's affordance profile predicts its harm profile.",
        "theoretical",
        "paper_substring",
        bold=True,
        why="Analytical thesis statement in §4 intro.",
    )

    # --- §4 affordance class case counts ---
    affordance_counts = [
        ("contact", "1,720", "Contact and approach affordances"),
        ("production", "177", "Production affordances"),
        ("possession", "1,708", "Possession and trade affordances"),
        ("coordination", "198", "Coordination affordances"),
    ]
    for aid, count, label in affordance_counts:
        add(
            f"affordance.{aid}_cases",
            f"§4.{aid}",
            f"{label} appear across {count} cases in Q1 evidence base.",
            "affordance_count",
            "manual",
            bold=True,
            why="Section affordance-class denominators; require harm_analysis crosswalk.",
            expected=count.replace(",", ""),
        )

    # --- §5 PACER case specifics ---
    add(
        "s5.amin_accounts",
        "§5.3",
        "Amin enterprise: 80+ Snapchat and 40+ Instagram accounts (indictment).",
        "lifecycle",
        "paper_substring",
        citation="U.S. v. Amin indictment",
        why="PACER-grounded sextortion scale fact.",
    )
    add(
        "s5.bermudez_defendants",
        "§5.4",
        "Bermudez enterprise: six-defendant §2252A(g) coordinated network.",
        "lifecycle",
        "paper_substring",
        why="Enterprise harm signature anchor.",
    )

    # --- §6 external ---
    add(
        "s6.ncmec_2023_incidents",
        "§6.1",
        "35.9 million suspected CSAM incidents reported to NCMEC in 2023.",
        "external_citation",
        "external",
        citation="[21] NCMEC annual report",
        why="Detection volume for intervention framing.",
    )
    add(
        "s6.report_act_2024",
        "§6.1",
        "REPORT Act of 2024 extended mandatory reporting to enticement and trafficking.",
        "external_citation",
        "external",
        citation="Public Law / DOJ summary",
        why="Policy lever background.",
    )

    # --- §7 empirical laws ---
    add(
        "s7.law1_contact_primacy",
        "§7.3 Law 1",
        "Law 1 (Contact Primacy): N=7,426 – no case documents exploitation without initial contact.",
        "theoretical",
        "lifecycle",
        bold=True,
        why="Formal invariant induced from corpus + PACER lifecycles.",
        expected="7426",
    )
    add(
        "s7.law2_backbone",
        "§7.3 Law 2",
        "Backbone stages achieve 5/5 coverage across five canonical PACER offense types.",
        "lifecycle",
        "lifecycle",
        bold=True,
        why="L* fundamental stages from state_machines compute_lstar.",
        expected="5/5",
    )
    add(
        "s7.theorem_h_closed",
        "§7.3",
        "Theorem 1: victim-facing harm set H is finite and closed.",
        "theoretical",
        "paper_substring",
        why="Formal claim; proof in paper not empirically falsifiable via DB alone.",
    )

    # --- §9 artifacts ---
    add(
        "s9.pacer_cost",
        "§9 / PACER",
        "PACER pull cost tracker totals $10.20 for three expansion cases.",
        "pacer",
        "file",
        why="Budget claim for Cory; matches pacer_cost.csv.",
        expected="10.20",
    )

    return c
