#!/usr/bin/env python3
"""Build and validate CAC knowledge graphs from PACER facts files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PACER_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = PACER_DIR / "facts.txt"
SDK_ROOT = PACER_DIR.parents[2] / "CASE-UCO-SDK"
CASE_VALIDATE = SDK_ROOT / ".venv/bin/case_validate"

CHARGE_LABELS: dict[str, str] = {
    "conspiracy_to_produce_csam": "Conspiracy to produce CSAM",
    "conspiracy_receive_distribute_csam": "Conspiracy to receive and distribute CSAM",
    "child_exploitation_enterprise": "Child exploitation enterprise",
    "production_of_csam": "Production of CSAM",
    "receipt_distribution_csam": "Receipt and distribution of CSAM",
    "cyberstalking": "Cyberstalking",
    "aggravated_identity_theft": "Aggravated identity theft",
    "wire_fraud": "Wire fraud",
    "coercion_enticement_minor": "Coercion and enticement of a minor",
    "travel_intent_illicit_sexual_conduct": "Travel with intent to engage in illicit sexual conduct",
    "sexual_exploitation_of_child": "Sexual exploitation of a child",
    "attempted_receipt_csam": "Attempted receipt of CSAM",
    "transportation_csam": "Transportation of CSAM",
    "possession_csam": "Possession of CSAM",
    "receipt_csam": "Receipt of CSAM",
    "attempted_sexual_exploitation_minor": "Attempted sexual exploitation of a minor",
    "access_with_intent_to_view_csam": "Access with intent to view CSAM",
    "conspiracy_interstate_threats": "Conspiracy to transmit interstate threats",
}

COERCION_LABELS: dict[str, str] = {
    "threat_of_exposure": "threat of exposure",
    "quota_demand": "quota demands",
    "false_promise_of_deletion": "false promise of deletion",
    "victim_recruitment": "victim recruitment",
    "impersonation": "impersonation (posed as teen/influencer)",
    "directed_production": "directed production of images",
    "flattery_as_inducement": "flattery as inducement",
    "persistent_solicitation": "persistent solicitation",
}

HARM_LABELS: dict[str, str] = {
    "self_harm_disclosure_present": "self-harm disclosure present",
    "victim_distress_documented": "victim distress documented",
    "victim_vulnerability_disclosed": "victim vulnerability disclosed",
    "self_harm_history_present": "self-harm history present",
}

PLATFORM_ROLE_LABELS: dict[str, str] = {
    "victim_identification": "victim identification",
    "coercion_primary": "primary coercion",
    "storage_and_distribution": "storage and distribution",
    "coercion_and_contact": "coercion and contact",
    "enterprise_infrastructure": "enterprise infrastructure",
    "live_production": "live production",
    "coercion_and_harassment": "coercion and harassment",
}

PRODUCTION_MECHANISM_LABELS: dict[str, str] = {
    "device_seizure_forfeiture_alleged": "device seizure and forfeiture alleged",
}

CURATED_ONTOLOGY_FILES = [
    "ontology/ontology/cacontology-core-spine.ttl",
    "ontology/ontology/cacontology-core-spine-shapes.ttl",
    "ontology/ontology/cacontology-core.ttl",
    "ontology/ontology/cacontology-core-shapes.ttl",
    "ontology/ontology/cacontology-extremist-enterprises.ttl",
    "ontology/ontology/cacontology-sextortion.ttl",
    "ontology/ontology/cacontology-platforms.ttl",
    "ontology/ontology/cacontology-legal-outcomes.ttl",
    "ontology/ontology/cacontology-usa-federal-law.ttl",
    "ontology/ontology/cacontology-multi-jurisdiction.ttl",
    "ontology/ontology/cacontology-asset-forfeiture.ttl",
    "ontology/ontology/cacontology-victim-impact.ttl",
    "ontology/ontology/cacontology-grooming.ttl",
    "ontology/ontology/cacontology-us-ncmec.ttl",
    "ontology/ontology/cacontology-production.ttl",
]

CONTEXT = {
    "@vocab": "http://example.org/local#",
    "case-investigation": "https://ontology.caseontology.org/case/investigation/",
    "kb": "http://example.org/kb/",
    "uco-action": "https://ontology.unifiedcyberontology.org/uco/action/",
    "uco-core": "https://ontology.unifiedcyberontology.org/uco/core/",
    "uco-identity": "https://ontology.unifiedcyberontology.org/uco/identity/",
    "uco-location": "https://ontology.unifiedcyberontology.org/uco/location/",
    "uco-observable": "https://ontology.unifiedcyberontology.org/uco/observable/",
    "uco-role": "https://ontology.unifiedcyberontology.org/uco/role/",
    "uco-victim": "https://ontology.unifiedcyberontology.org/uco/victim/",
    "cacontology": "https://cacontology.projectvic.org#",
    "cac-core": "https://cacontology.projectvic.org/core#",
    "cacontology-platforms": "https://cacontology.projectvic.org/platforms#",
    "cacontology-sextortion": "https://cacontology.projectvic.org/sextortion#",
    "cacontology-extremist-enterprises": "https://cacontology.projectvic.org/extremist-enterprises#",
    "cacontology-legal-outcomes": "https://cacontology.projectvic.org/legal-outcomes#",
    "cacontology-usa-federal-law": "https://cacontology.projectvic.org/usa-federal-law#",
    "cacontology-multi-jurisdiction": "https://cacontology.projectvic.org/multi-jurisdiction#",
    "cacontology-asset-forfeiture": "https://cacontology.projectvic.org/asset-forfeiture#",
    "cacontology-victim-impact": "https://cacontology.projectvic.org/victim-impact#",
    "cacontology-grooming": "https://cacontology.projectvic.org/grooming#",
    "cacontology-us-ncmec": "https://cacontology.projectvic.org/us/ncmec#",
    "cacontology-production": "https://cacontology.projectvic.org/production#",
    "cacontology-gufo": "https://cacontology.projectvic.org/gufo#",
    "gufo": "http://purl.org/nemo/gufo#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


def xs(value: str, typ: str) -> dict[str, str]:
    return {"@type": typ, "@value": value}


def desc(text: str) -> dict[str, str]:
    return xs(text, "xsd:string")


def slug_from_facts_path(facts_path: Path) -> str:
    stem = facts_path.stem
    if stem.endswith("_facts"):
        stem = stem[: -len("_facts")]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    if not slug:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", facts_path.parent.name).strip("-").lower()
    return slug


def output_path_for(facts_path: Path) -> Path:
    return facts_path.with_name(f"{slug_from_facts_path(facts_path)}.jsonld")


def case_token(case_number: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", case_number).strip("-").lower()


def load_facts(facts_path: Path) -> dict[str, Any]:
    text = facts_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{facts_path} must contain a YAML mapping at the top level")
    return data


def read_manifest(manifest_path: Path) -> list[Path]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    paths: list[Path] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        candidate = Path(line)
        paths.append(candidate if candidate.is_absolute() else manifest_path.parent / candidate)
    if not paths:
        raise ValueError(f"No facts files listed in {manifest_path}")
    return paths


def timeline_date(timeline: list[str], *keywords: str) -> str | None:
    for entry in timeline:
        for keyword in keywords:
            if keyword in entry.lower():
                match = re.match(r"(\d{4}-\d{2}-\d{2})", entry)
                if match:
                    return f"{match.group(1)}T00:00:00Z"
    return None


def charge_count_label(charge: dict[str, Any]) -> str:
    if "count" in charge:
        return str(charge["count"])
    if "counts" in charge:
        return str(charge["counts"])
    return "?"


def charge_display_label(charge: dict[str, Any]) -> str:
    raw = str(charge.get("label", "unknown_charge"))
    return CHARGE_LABELS.get(raw, raw.replace("_", " ").title())


def make_ids(slug: str, case_number: str) -> dict[str, str]:
    token = case_token(case_number)
    prefix = f"kb:{slug}-{token}"
    return {
        "bundle": f"{prefix}-bundle",
        "investigation": f"{prefix}-investigation",
        "prosecution": f"{prefix}-prosecution",
        "prosecutor": f"{prefix}-prosecutor",
        "pretrial_phase": f"{prefix}-pretrial-phase",
        "indictment": f"{prefix}-indictment",
        "enterprise": f"{prefix}-enterprise",
        "hierarchy": f"{prefix}-enterprise-hierarchy",
        "leadership_relator": f"{prefix}-leadership-relator",
        "exploitation_relator": f"{prefix}-exploitation-relator",
        "defendant": f"{prefix}-person-defendant",
        "subject": f"{prefix}-subject",
        "victim_role": f"{prefix}-victim-role",
        "sextortion": f"{prefix}-sextortion",
        "enticement": f"{prefix}-enticement",
        "grooming": f"{prefix}-grooming-solicitation",
        "csam_incident": f"{prefix}-csam-incident",
        "content_facet": f"{prefix}-content-facet",
        "conspiracy": f"{prefix}-conspiracy",
        "impersonation": f"{prefix}-impersonation",
        "recruitment": f"{prefix}-recruitment",
        "location_court": f"{prefix}-location-court",
        "location_abroad": f"{prefix}-location-abroad",
        "extradition": f"{prefix}-extradition",
        "forfeiture": f"{prefix}-forfeiture",
        "forfeiture_asset": f"{prefix}-forfeiture-asset",
        "impact": f"{prefix}-impact",
        "provenance": f"{prefix}-provenance",
        "provenance_action": f"{prefix}-provenance-action",
        "ban_evasion_lifecycle": f"{prefix}-ban-evasion-lifecycle",
    }


def platform_id(slug: str, case_number: str, name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return f"kb:{slug}-{case_token(case_number)}-platform-{safe}"


def coconspirator_id(slug: str, case_number: str, index: int) -> str:
    return f"kb:{slug}-{case_token(case_number)}-co-conspirator-{index}"


def device_id(slug: str, case_number: str, index: int) -> str:
    return f"kb:{slug}-{case_token(case_number)}-device-{index}"


def parallel_court_id(slug: str, case_number: str, index: int) -> str:
    return f"kb:{slug}-{case_token(case_number)}-parallel-court-{index}"


def evidentiary_label(evidentiary: str) -> str:
    return "proven" if evidentiary.lower() == "proven" else "alleged"


def charge_iri(slug: str, case_number: str, charge: dict[str, Any]) -> str:
    count_label = charge_count_label(charge)
    return f"kb:{slug}-{case_token(case_number)}-charge-{count_label.replace('-', '_')}"


def violation_id(slug: str, case_number: str, violation_key: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", violation_key.lower()).strip("-")
    return f"kb:{slug}-{case_token(case_number)}-overt-act-{safe}"


def venue_id(slug: str, case_number: str, venue_key: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", venue_key.lower()).strip("-")
    return f"kb:{slug}-{case_token(case_number)}-venue-{safe}"


def make_rel(
    *,
    slug: str,
    case_number: str,
    rel_id: str,
    source: str,
    target: str,
    kind: str,
    name: str,
) -> dict[str, Any]:
    safe_rel_id = re.sub(r"[^a-zA-Z0-9]+", "-", rel_id.lower()).strip("-")
    return {
        "@id": f"kb:{slug}-{case_token(case_number)}-rel-{safe_rel_id}",
        "@type": "uco-core:Relationship",
        "uco-core:name": name,
        "uco-core:source": {"@id": source},
        "uco-core:target": {"@id": target},
        "uco-core:kindOfRelationship": kind,
        "uco-core:isDirectional": xs("true", "xsd:boolean"),
    }


def _normalize_count_lookup_key(key: str | int) -> str:
    return str(key).replace("_", "-")


def defendant_charge_refs(
    facts: dict[str, Any],
    charges: list[dict[str, Any]],
    *,
    slug: str,
    case_number: str,
    default_label: str = "Defendant-1",
) -> dict[str, list[dict[str, str]]]:
    """Map defendant label → chargedWith object refs."""
    count_index: dict[str, dict[str, Any]] = {}
    for charge in charges:
        label = charge_count_label(charge)
        count_index[_normalize_count_lookup_key(label)] = charge
        count_index[str(label)] = charge

    raw = facts.get("defendant_counts") or {}
    if not isinstance(raw, dict) or not raw:
        return {
            default_label: [{"@id": charge_iri(slug, case_number, c)} for c in charges],
        }

    out: dict[str, list[dict[str, str]]] = {}
    for defendant, count_keys in raw.items():
        if not isinstance(count_keys, list):
            continue
        refs: list[dict[str, str]] = []
        for key in count_keys:
            charge = count_index.get(_normalize_count_lookup_key(key))
            if charge:
                refs.append({"@id": charge_iri(slug, case_number, charge)})
        out[str(defendant)] = refs
    return out


def defendant_person_id(slug: str, case_number: str, label: str) -> str:
    if label == "Defendant-1":
        return f"kb:{slug}-{case_token(case_number)}-person-defendant"
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", label.lower()).strip("-")
    return f"kb:{slug}-{case_token(case_number)}-person-{safe}"


def all_charge_refs(
    charges: list[dict[str, Any]],
    *,
    slug: str,
    case_number: str,
) -> list[dict[str, str]]:
    return [{"@id": charge_iri(slug, case_number, charge)} for charge in charges]


def apply_charged_with(
    nodes: list[dict[str, Any]],
    charge_refs: dict[str, list[dict[str, str]]],
    *,
    slug: str,
    case_number: str,
    principal_label: str,
    principal_id: str,
) -> list[dict[str, Any]]:
    """Patch principal Person chargedWith; return additional defendant Person nodes."""
    extra: list[dict[str, Any]] = []
    for label, refs in charge_refs.items():
        if not refs:
            continue
        if label == principal_label or label == "Defendant-1":
            for node in nodes:
                if node.get("@id") == principal_id:
                    node["cacontology-legal-outcomes:chargedWith"] = refs
                    break
            continue
        extra.append(
            {
                "@id": defendant_person_id(slug, case_number, label),
                "@type": "uco-identity:Person",
                "uco-core:name": label,
                "uco-core:description": desc(f"Alleged co-defendant; counts assigned per indictment."),
                "cacontology-legal-outcomes:chargedWith": refs,
            }
        )
    return extra


def apply_forfeiture_charge_links(
    nodes: list[dict[str, Any]],
    forfeiture_id: str,
    charges: list[dict[str, Any]],
    *,
    slug: str,
    case_number: str,
) -> None:
    refs = all_charge_refs(charges, slug=slug, case_number=case_number)
    if not refs:
        return
    for node in nodes:
        if node.get("@id") == forfeiture_id:
            node["cacontology-asset-forfeiture:relatedCriminalCharges"] = refs
            break


def build_forfeiture_device_links(
    forfeiture_devices: list[Any],
    *,
    slug: str,
    case_number: str,
    forfeiture_id: str,
    basis_word: str,
    device_index_offset: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    device_nodes: list[dict[str, Any]] = []
    rels: list[dict[str, Any]] = []
    if not isinstance(forfeiture_devices, list) or not forfeiture_devices:
        return device_nodes, rels

    targeted: list[dict[str, str]] = []
    for index, device in enumerate(forfeiture_devices, start=1):
        if not isinstance(device, dict):
            continue
        device_index = device_index_offset + index
        did = device_id(slug, case_number, device_index)
        make = str(device.get("make", "unknown"))
        model = str(device.get("model", "unknown"))
        device_nodes.append(
            {
                "@id": did,
                "@type": [
                    "uco-observable:ObservableObject",
                    "cacontology-production:MobileRecordingDevice",
                ],
                "uco-core:name": f"{make} {model}",
                "uco-core:description": desc(f"{basis_word} device listed for asset forfeiture."),
                "cacontology-production:equipmentType": str(device.get("equipment_type", "smartphone")),
                "cacontology-production:deviceBrand": make,
                "cacontology-production:deviceModel": model,
            }
        )
        targeted.append({"@id": did})
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"forfeiture-device-{device_index}",
                source=forfeiture_id,
                target=did,
                kind="targetedAsset",
                name=f"Forfeiture targets {make} {model}",
            )
        )
    return device_nodes, rels


def build_extradition_relationships(
    transnational: dict[str, Any],
    *,
    slug: str,
    case_number: str,
    g: dict[str, str],
    defendant_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(transnational, dict) or not transnational:
        return []
    if not g.get("extradition"):
        return []
    if not (
        transnational.get("extradition_observed")
        or transnational.get("defendant_abroad")
        or transnational.get("extradition_country")
        or transnational.get("foreign_residence")
    ):
        return []

    rels: list[dict[str, Any]] = [
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="defendant-extradition",
            source=defendant_id,
            target=g["extradition"],
            kind="Relates_To",
            name="Defendant extradition proceedings",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="extradition-prosecution",
            source=g["extradition"],
            target=g["prosecution"],
            kind="Relates_To",
            name="Extradition for federal prosecution",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="extradition-investigation",
            source=g["extradition"],
            target=g["investigation"],
            kind="Relates_To",
            name="Extradition supports investigation",
        ),
    ]
    if g.get("location_abroad"):
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id="defendant-abroad",
                source=defendant_id,
                target=g["location_abroad"],
                kind="Relates_To",
                name="Defendant alleged abroad at offense",
            )
        )
    return rels


def build_ban_evasion_lifecycle(
    ban_evasion: dict[str, Any],
    *,
    slug: str,
    case_number: str,
    g: dict[str, str],
    offense_begin: str,
    basis_word: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not isinstance(ban_evasion, dict) or not ban_evasion.get("observed"):
        return None, []

    snap_min = ban_evasion.get("snapchat_accounts_min", "?")
    insta_min = ban_evasion.get("instagram_accounts_min", "?")
    pattern = str(ban_evasion.get("pattern", "account_recreation_after_enforcement")).replace("_", " ")
    node: dict[str, Any] = {
        "@id": g["ban_evasion_lifecycle"],
        "@type": "cacontology-platforms:PlatformOperation",
        "uco-core:name": f"{basis_word} platform ban-evasion lifecycle",
        "rdfs:label": f"{basis_word} platform ban-evasion lifecycle",
        "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
        "uco-core:description": desc(
            f"Alleged ban-evasion pattern: {pattern}. "
            f"Minimum {snap_min} Snapchat and {insta_min} Instagram accounts recreated after enforcement."
        ),
    }
    rels = [
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="sextortion-ban-evasion",
            source=g["sextortion"],
            target=g["ban_evasion_lifecycle"],
            kind="Relates_To",
            name="Sextortion scheme used ban-evasion lifecycle",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="enterprise-ban-evasion",
            source=g["enterprise"],
            target=g["ban_evasion_lifecycle"],
            kind="Relates_To",
            name="Enterprise used ban-evasion lifecycle",
        ),
    ]
    return node, rels


def build_federal_prosecution_relationships(
    *,
    slug: str,
    case_number: str,
    g: dict[str, str],
    charges: list[dict[str, Any]],
    conduct_id: str,
    link_enterprise: bool = False,
    link_conspiracy: bool = True,
    link_charges_to_conduct: bool = True,
) -> list[dict[str, Any]]:
    rels: list[dict[str, Any]] = [
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="inv-indictment",
            source=g["investigation"],
            target=g["indictment"],
            kind="Relates_To",
            name="Investigation charging instrument",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="prosecution-indictment",
            source=g["prosecution"],
            target=g["indictment"],
            kind="Relates_To",
            name="Prosecution charging instrument",
        ),
    ]
    if link_conspiracy and g.get("conspiracy"):
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id="conspiracy-indictment",
                source=g["conspiracy"],
                target=g["indictment"],
                kind="Relates_To",
                name="Conspiracy resulted in indictment",
            )
        )
    if link_enterprise and g.get("enterprise"):
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id="enterprise-indictment",
                source=g["enterprise"],
                target=g["indictment"],
                kind="Relates_To",
                name="Enterprise charging instrument",
            )
        )
    for charge in charges:
        count_label = charge_count_label(charge)
        iri = charge_iri(slug, case_number, charge)
        safe_count = count_label.replace("-", "_")
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"indictment-charge-{safe_count}",
                source=g["indictment"],
                target=iri,
                kind="Relates_To",
                name=f"Indictment count {count_label}",
            )
        )
        if link_charges_to_conduct:
            rels.append(
                make_rel(
                    slug=slug,
                    case_number=case_number,
                    rel_id=f"charge-conduct-{safe_count}",
                    source=iri,
                    target=conduct_id,
                    kind="Relates_To",
                    name=f"Count {count_label} conduct",
                )
            )
    return rels


def _parallel_district_venue_map(parallel_districts: list[dict[str, Any]]) -> dict[str, str]:
    by_prefix: dict[str, str] = {}
    for entry in parallel_districts:
        if not isinstance(entry, dict):
            continue
        court = str(entry.get("court", ""))
        case_num = str(entry.get("case_number", ""))
        if "Alaska" in court or "SLG" in case_num.upper():
            by_prefix["AK"] = court
        elif "Texas" in court or "El Paso" in court:
            by_prefix["TX"] = court
    return by_prefix


def build_count_venue_nodes(
    facts: dict[str, Any],
    charges: list[dict[str, Any]],
    *,
    slug: str,
    case_number: str,
    primary_court: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    count_venues = facts.get("count_venues") or {}
    if not isinstance(count_venues, dict):
        count_venues = {}
    parallel_districts = facts.get("parallel_districts") or []
    if not isinstance(parallel_districts, list):
        parallel_districts = []
    district_by_prefix = _parallel_district_venue_map(parallel_districts)

    venue_iris: dict[str, str] = {}
    nodes: list[dict[str, Any]] = []
    rels: list[dict[str, Any]] = []

    def ensure_venue(name: str) -> str:
        if name not in venue_iris:
            iri = venue_id(slug, case_number, name)
            venue_iris[name] = iri
            nodes.append(
                {
                    "@id": iri,
                    "@type": "uco-location:Location",
                    "uco-core:name": name,
                }
            )
        return venue_iris[name]

    for charge in charges:
        count_label = charge_count_label(charge)
        venue_name = charge.get("venue")
        if not venue_name:
            venue_name = count_venues.get(count_label) or count_venues.get(str(count_label))
        if not venue_name and "-" in str(count_label):
            prefix = str(count_label).split("-", 1)[0]
            venue_name = district_by_prefix.get(prefix)
        if not venue_name:
            venue_name = primary_court
        venue_iri = ensure_venue(str(venue_name))
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"charge-venue-{count_label.replace('-', '_')}",
                source=charge_iri(slug, case_number, charge),
                target=venue_iri,
                kind="Relates_To",
                name=f"Count {count_label} venue",
            )
        )
    return nodes, rels


def build_enterprise_relators(
    g: dict[str, str],
    *,
    defendant_id: str,
    victim_role_id: str,
    co_conspirator_ids: list[str],
    basis_word: str = "Alleged",
) -> list[dict[str, Any]]:
    leadership_participants: list[dict[str, str]] = [{"@id": defendant_id}]
    if co_conspirator_ids:
        leadership_participants.append({"@id": co_conspirator_ids[0]})
    return [
        {
            "@id": g["leadership_relator"],
            "@type": "gufo:Relator",
            "rdfs:label": f"{basis_word} enterprise leadership relation",
            "gufo:hasParticipant": leadership_participants,
        },
        {
            "@id": g["exploitation_relator"],
            "@type": "gufo:Relator",
            "rdfs:label": f"{basis_word} perpetrator-victim exploitation relation",
            "gufo:hasParticipant": [{"@id": defendant_id}, {"@id": victim_role_id}],
        },
    ]


def build_overt_act_violation_nodes(
    violations: list[dict[str, Any]],
    *,
    slug: str,
    case_number: str,
    count_one_iri: str,
    basis_word: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    rels: list[dict[str, Any]] = []
    if not violations:
        return nodes, rels

    venue_iris: dict[str, str] = {}

    def ensure_venue(name: str) -> str:
        if name not in venue_iris:
            iri = venue_id(slug, case_number, name)
            venue_iris[name] = iri
            nodes.append(
                {
                    "@id": iri,
                    "@type": "uco-location:Location",
                    "uco-core:name": name,
                }
            )
        return venue_iris[name]

    for index, violation in enumerate(violations):
        if not isinstance(violation, dict):
            continue
        violation_key = str(violation.get("id", f"violation-{index + 1}"))
        vid = violation_id(slug, case_number, violation_key)
        venue_name = str(violation.get("venue", "Unknown venue"))
        lid = ensure_venue(venue_name)
        label = str(violation.get("label", violation_key))
        display = f"{basis_word} {label}"
        violation_node: dict[str, Any] = {
            "@id": vid,
            "@type": "gufo:Event",
            "uco-core:name": display,
            "rdfs:label": display,
            "uco-core:description": desc(
                f"Embedded Count 1 violation. Window: {violation.get('date_window', 'unknown')}. "
                f"Victim ref: {violation.get('victim_reference', 'aggregate')}."
            ),
        }
        nodes.append(violation_node)
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"count1-overt-act-{violation_key}",
                source=count_one_iri,
                target=vid,
                kind="Relates_To",
                name=f"Count 1 {violation.get('label', violation_key)}",
            )
        )
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"overt-act-venue-{violation_key}",
                source=vid,
                target=lid,
                kind="Relates_To",
                name=f"{violation.get('label', violation_key)} venue",
            )
        )
    return nodes, rels


SEXTORTION_STACKED_CHARGE_LABELS = frozenset(
    {"cyberstalking", "aggravated_identity_theft", "wire_fraud"}
)


def build_sextortion_charge_conduct_links(
    charges: list[dict[str, Any]],
    *,
    slug: str,
    case_number: str,
    g: dict[str, str],
) -> list[dict[str, Any]]:
    rels: list[dict[str, Any]] = []
    for charge in charges:
        label = str(charge.get("label", ""))
        count_label = charge_count_label(charge)
        iri = charge_iri(slug, case_number, charge)
        if label == "aggravated_identity_theft":
            target = g["impersonation"]
            rel_name = f"Count {count_label} impersonation conduct"
        elif label in SEXTORTION_STACKED_CHARGE_LABELS or label in CHARGE_LABELS:
            target = g["sextortion"]
            rel_name = f"Count {count_label} sextortion conduct"
        else:
            target = g["sextortion"]
            rel_name = f"Count {count_label} conduct"
        rels.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"charge-scheme-{count_label.replace('-', '_')}",
                source=iri,
                target=target,
                kind="Relates_To",
                name=rel_name,
            )
        )
    return rels


def build_platform_node(
    *,
    platform: dict[str, Any],
    platform_iri: str,
    ban_evasion: dict[str, Any],
    basis_word: str = "Alleged",
) -> dict[str, Any]:
    name = str(platform["name"])
    role = PLATFORM_ROLE_LABELS.get(str(platform.get("role", "")), str(platform.get("role", "unknown")))
    affordances = ", ".join(str(a).replace("_", " ") for a in platform.get("affordances_abused", []))
    ban_note = ""
    name_lower = name.lower()
    if ban_evasion.get("observed"):
        if "snapchat" in name_lower and ban_evasion.get("snapchat_accounts_min"):
            ban_note = f" Minimum {ban_evasion['snapchat_accounts_min']} accounts recreated after bans."
        elif "instagram" in name_lower and ban_evasion.get("instagram_accounts_min"):
            ban_note = f" Minimum {ban_evasion['instagram_accounts_min']} accounts recreated after bans."

    node: dict[str, Any] = {
        "@id": platform_iri,
        "uco-core:name": name,
        "uco-core:description": desc(
            f"{basis_word} role: {role}. Affordances abused: {affordances}.{ban_note}"
        ),
    }
    if name_lower == "dropbox":
        node["@type"] = ["uco-observable:ObservableObject", "cacontology-platforms:FileHostingService"]
    else:
        node["@type"] = ["uco-observable:ObservableObject", "cacontology-platforms:SocialMediaPlatform"]
        node["cacontology-platforms:platformType"] = "social_network"
    return node


def build_charge_nodes(
    *,
    charges: list[dict[str, Any]],
    slug: str,
    case_number: str,
    evidentiary: str,
    doc_ref: str,
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for charge in charges:
        count_label = charge_count_label(charge)
        label = charge_display_label(charge)
        statute = str(charge.get("statute", "unknown"))
        charge_iri = f"kb:{slug}-{case_token(case_number)}-charge-{count_label.replace('-', '_')}"
        disposition = charge.get("disposition")
        disposition_text = f" Disposition: {str(disposition).replace('_', ' ')}." if disposition else ""
        nodes.append(
            {
                "@id": charge_iri,
                "@type": "cacontology-legal-outcomes:FederalCharge",
                "uco-core:name": label,
                "rdfs:label": label,
                "uco-core:description": desc(
                    f"Count {count_label} under {statute}. "
                    f"Evidentiary basis: {evidentiary} ({doc_ref}).{disposition_text}"
                ),
            }
        )
    return nodes


def build_provenance_nodes(
    g: dict[str, str],
    *,
    provenance: dict[str, Any],
    doc_ref: str,
) -> list[dict[str, Any]]:
    provenance_source = str(provenance.get("source", "PACER"))
    return [
        {
            "@id": g["provenance_action"],
            "@type": "case-investigation:InvestigativeAction",
            "uco-core:name": f"{provenance_source} extraction",
            "rdfs:label": f"{provenance_source} extraction",
            "uco-core:description": desc(
                f"Extraction from {doc_ref}; retrieval={provenance.get('retrieval_method', 'unknown')}, "
                f"extraction={provenance.get('extraction_method', 'unknown')}, "
                f"human_reviewed={provenance.get('human_reviewed', False)}."
            ),
        },
        {
            "@id": g["provenance"],
            "@type": "case-investigation:ProvenanceRecord",
            "uco-core:name": f"Provenance — {doc_ref}",
            "uco-core:description": desc(f"Source: {provenance_source}, {doc_ref}."),
            "case-investigation:object": [{"@id": g["investigation"]}, {"@id": g["provenance_action"]}],
        },
    ]


def is_facet_node(node: dict[str, Any]) -> bool:
    node_type = node.get("@type", [])
    if isinstance(node_type, str):
        node_type = [node_type]
    return any("Facet" in str(t) for t in node_type)


def finalize_graph(nodes: list[dict[str, Any]], bundle_id: str) -> list[dict[str, Any]]:
    object_refs = [
        node["@id"]
        for node in nodes
        if node["@id"] != bundle_id and not is_facet_node(node)
    ]
    nodes[0]["uco-core:object"] = [{"@id": ref} for ref in object_refs]
    return nodes


def build_graph(facts: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    if "enterprise" in facts:
        if slug == "sextortion":
            return build_sextortion_enterprise_graph(facts, slug)
        return build_enterprise_graph(facts, slug)
    if "offense" in facts:
        offense_type = str(facts["offense"].get("type", ""))
        if offense_type.startswith("csam_"):
            return build_production_graph(facts, slug)
        return build_enticement_graph(facts, slug)
    raise ValueError("Facts file must contain either 'enterprise' or 'offense' section")


def build_sextortion_enterprise_graph(facts: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    case = facts["case"]
    offender = facts.get("offender", {})
    enterprise = facts.get("enterprise", {})
    platforms = facts.get("platforms", [])
    ban_evasion = facts.get("ban_evasion", {})
    coercion = facts.get("coercion_mechanisms", [])
    harm = facts.get("victim_harm_indicators", [])
    charges = facts.get("charges", [])
    stacking = facts.get("charge_stacking_note", {})
    forfeiture = facts.get("forfeiture", {})
    timeline = facts.get("procedural_timeline", [])
    provenance = facts.get("provenance", {})

    case_number = str(case["case_number"])
    court = str(case.get("court", "Unknown court"))
    date_filed = str(case.get("date_filed", "unknown"))
    evidentiary = str(case.get("evidentiary_basis", "alleged"))
    offender_label = str(offender.get("label", "Defendant-1"))

    g = make_ids(slug, case_number)
    offense_begin = timeline_date(timeline, "complaint") or f"{date_filed}T00:00:00Z"
    indictment_date = timeline_date(timeline, "indictment") or f"{date_filed}T00:00:00Z"
    extradition_date = timeline_date(timeline, "extradited", "arrest")

    victim_count = int(enterprise.get("victim_count_approx", 1))
    co_conspirator_min = int(enterprise.get("co_conspirator_count_min", 2))
    co_conspirators = max(0, co_conspirator_min - 1)

    platform_iris: dict[str, str] = {}
    platform_nodes: list[dict[str, Any]] = []
    for platform in platforms:
        iri = platform_id(slug, case_number, str(platform["name"]))
        platform_iris[str(platform["name"]).lower()] = iri
        platform_nodes.append(
            build_platform_node(
                platform=platform,
                platform_iri=iri,
                ban_evasion=ban_evasion,
                basis_word=evidentiary.capitalize(),
            )
        )

    charge_nodes = build_charge_nodes(
        charges=charges,
        slug=slug,
        case_number=case_number,
        evidentiary=evidentiary,
        doc_ref=str(provenance.get("document", "source document")),
    )

    coercion_text = ", ".join(COERCION_LABELS.get(str(c), str(c).replace("_", " ")) for c in coercion)
    harm_text = "; ".join(HARM_LABELS.get(str(h), str(h).replace("_", " ")) for h in harm)

    stacking_text = ""
    if stacking.get("observed"):
        stacking_text = (
            f" Charge stacking observed: {str(stacking.get('description', '')).replace('_', ' ')}."
        )

    ban_text = ""
    if ban_evasion.get("observed"):
        ban_text = (
            f" Ban evasion alleged: {ban_evasion.get('snapchat_accounts_min', '?')}+ Snapchat accounts and "
            f"{ban_evasion.get('instagram_accounts_min', '?')}+ Instagram accounts recreated after platform enforcement."
        )

    doc_ref = str(provenance.get("document", "source document"))
    provenance_source = str(provenance.get("source", "PACER"))

    nodes: list[dict[str, Any]] = [
        {
            "@id": g["bundle"],
            "@type": "uco-core:Bundle",
            "uco-core:name": f"{court} {case_number} (CAC Enhanced)",
            "uco-core:description": desc(
                f"CAC knowledge graph for {case_number} derived from {doc_ref}. "
                f"All conduct is {evidentiary.upper()}. Coded extraction only — no victim-identifying detail."
            ),
        },
        {
            "@id": g["investigation"],
            "@type": ["case-investigation:Investigation", "cacontology:CACInvestigation"],
            "uco-core:name": f"U.S. v. {offender_label} — {case_number}",
            "uco-core:description": desc(
                f"Federal prosecution in {court}. Approximately {victim_count} alleged victims "
                f"(minimum age {enterprise.get('victim_min_age_alleged', 'unknown')})."
                f"{stacking_text}{ban_text}"
            ),
            "case-investigation:focus": [
                "Child Sexual Exploitation Enterprise",
                "Sextortion",
                "CSAM Production and Distribution",
                "Platform Ban Evasion",
            ],
            "case-investigation:investigationForm": "case",
            "case-investigation:investigationStatus": "open",
            "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
        },
        {
            "@id": g["prosecution"],
            "@type": "cacontology-usa-federal-law:FederalProsecution",
            "uco-core:name": f"Federal prosecution — {case_number}",
            "rdfs:label": f"Federal prosecution — {case_number}",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:hasProsecutionBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:prosecutedBy": {"@id": g["prosecutor"]},
            "cacontology-usa-federal-law:hasLegalPhase": {"@id": g["pretrial_phase"]},
            "cacontology-usa-federal-law:prosecutionComplexity": "highly-complex",
            "cacontology-usa-federal-law:prosecutionSeverity": "aggravated-felony",
            "cacontology-usa-federal-law:prosecutionStatus": "active",
        },
        {
            "@id": g["prosecutor"],
            "@type": "cacontology-usa-federal-law:FederalProsecutorRole",
            "uco-core:name": court,
            "rdfs:label": court,
            "cacontology-usa-federal-law:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:roleSpecialization": "child-exploitation",
        },
        {
            "@id": g["pretrial_phase"],
            "@type": ["cac-core:Phase", "cacontology-usa-federal-law:PreTrialPhase"],
            "uco-core:name": "Pre-trial phase",
            "rdfs:label": "Pre-trial phase",
            "cacontology:hasPhaseBeginPoint": xs(indictment_date, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["indictment"],
            "@type": "cacontology:MultiDefendantIndictment",
            "uco-core:name": doc_ref,
            "rdfs:label": doc_ref,
            "uco-core:description": desc(
                f"Indictment filed {date_filed}. {len(charges)} charge groups alleged."
            ),
        },
        {
            "@id": g["enterprise"],
            "@type": ["uco-identity:Organization", "cacontology-extremist-enterprises:ChildExploitationEnterprise"],
            "uco-core:name": f"Alleged child exploitation enterprise ({enterprise.get('statute', '18 U.S.C. 2252A(g)')})",
            "rdfs:label": f"Alleged child exploitation enterprise ({enterprise.get('statute', '18 U.S.C. 2252A(g)')})",
            "uco-core:description": desc(
                f"Large-scale alleged enterprise with minimum {co_conspirator_min} co-conspirators and "
                f"approximately {victim_count} victims.{ban_text}"
            ),
            "cacontology-extremist-enterprises:leadershipCount": xs("1", "xsd:nonNegativeInteger"),
            "cacontology-extremist-enterprises:membershipRequirements": (
                "Alleged co-conspirators coordinated systematic online child exploitation using "
                "multiple platforms with ban-evasion account recreation."
            ),
            "cacontology-extremist-enterprises:hasHierarchy": {"@id": g["hierarchy"]},
            "cacontology-extremist-enterprises:hasLeadershipRelation": {"@id": g["leadership_relator"]},
            "cacontology-extremist-enterprises:hasExploitationRelation": {"@id": g["exploitation_relator"]},
            "cacontology-extremist-enterprises:hasMember": [{"@id": g["defendant"]}]
            + [{"@id": coconspirator_id(slug, case_number, i)} for i in range(2, 2 + co_conspirators)],
            "cacontology-extremist-enterprises:hasOperationalBeginDate": xs(offense_begin, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["hierarchy"],
            "@type": "cacontology-extremist-enterprises:EnterpriseHierarchy",
            "uco-core:name": "Alleged enterprise hierarchy",
            "rdfs:label": "Alleged enterprise hierarchy",
            "cacontology-extremist-enterprises:hierarchyComplexity": "moderate",
        },
        {"@id": g["leadership_relator"], "@type": "gufo:Relator", "rdfs:label": "Alleged enterprise leadership relation"},
        {"@id": g["exploitation_relator"], "@type": "gufo:Relator", "rdfs:label": "Alleged perpetrator-victim exploitation relation"},
        {
            "@id": g["defendant"],
            "@type": "uco-identity:Person",
            "uco-core:name": offender_label,
            "uco-core:description": desc(
                f"Principal alleged offender; {str(offender.get('nationality_context', 'unknown')).replace('_', ' ')}."
            ),
        },
        {
            "@id": g["subject"],
            "@type": ["case-investigation:Subject", "cacontology:OffenderRole"],
            "uco-core:name": f"{offender_label} — principal subject",
            "rdfs:label": f"{offender_label} — principal subject",
            "cacontology:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:participatesInEvent": [{"@id": g["sextortion"]}, {"@id": g["conspiracy"]}],
        },
        {
            "@id": g["victim_role"],
            "@type": ["uco-victim:Victim", "cacontology:VictimRole"],
            "uco-core:name": "Alleged victim population (aggregate)",
            "rdfs:label": "Alleged victim population (aggregate)",
            "cacontology:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:participatesInEvent": [{"@id": g["sextortion"]}, {"@id": g["conspiracy"]}],
            "uco-core:description": desc(
                f"Aggregate victim role for approximately {victim_count} alleged victims; no identifying detail."
            ),
        },
        {
            "@id": g["sextortion"],
            "@type": ["cacontology-sextortion:SextortionIncident", "cacontology-sextortion:SocialMediaSextortion"],
            "uco-core:name": "Alleged social media sextortion scheme",
            "rdfs:label": "Alleged social media sextortion scheme",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-sextortion:incidentType": "social_media_threat",
            "cacontology-sextortion:severityLevel": "extreme",
            "cacontology-sextortion:victimCount": xs(str(min(victim_count, 100)), "xsd:nonNegativeInteger"),
            "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
            "uco-core:description": desc(f"Alleged coercion via {coercion_text}. {harm_text.capitalize()}."),
        },
        {
            "@id": g["conspiracy"],
            "@type": "cacontology:ConspiracyToCommitCSA",
            "uco-core:name": "Alleged conspiracy to commit CSA",
            "rdfs:label": "Alleged conspiracy to commit CSA",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["impersonation"],
            "@type": "cacontology-sextortion:IdentityImpersonation",
            "uco-core:name": "Alleged impersonation",
            "rdfs:label": "Alleged impersonation",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["recruitment"],
            "@type": "cacontology:VictimRecruitment",
            "uco-core:name": "Alleged coerced victim recruitment",
            "rdfs:label": "Alleged coerced victim recruitment",
        },
        {
            "@id": g["location_court"],
            "@type": "uco-location:Location",
            "uco-core:name": court,
        },
        {
            "@id": g["location_abroad"],
            "@type": "uco-location:Location",
            "uco-core:name": "Location outside United States (alleged)",
            "uco-core:description": desc(
                f"Defendant alleged abroad at time of offense."
                + (f" Extradited {extradition_date[:10]}." if extradition_date else "")
            ),
        },
        {
            "@id": g["extradition"],
            "@type": "cacontology-multi-jurisdiction:ExtraditionRequest",
            "uco-core:name": f"Extradition proceedings — {offender_label}",
            "rdfs:label": f"Extradition proceedings — {offender_label}",
            "uco-core:description": desc("; ".join(str(t) for t in timeline if "extradition" in t.lower() or "extradited" in t.lower())),
        },
        {
            "@id": g["forfeiture_asset"],
            "@type": "uco-observable:ObservableObject",
            "uco-core:name": "Alleged criminal proceeds (forfeiture target)",
        },
        {
            "@id": g["forfeiture"],
            "@type": "cacontology-asset-forfeiture:AssetForfeitureAction",
            "uco-core:name": f"Alleged asset forfeiture under {forfeiture.get('statute', '18 U.S.C. 2253')}",
            "rdfs:label": f"Alleged asset forfeiture under {forfeiture.get('statute', '18 U.S.C. 2253')}",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(indictment_date, "xsd:dateTimeStamp"),
            "cacontology-gufo:forfeitureBeginTime": xs(indictment_date, "xsd:dateTime"),
            "cacontology-asset-forfeiture:targetedAsset": {"@id": g["forfeiture_asset"]},
            "uco-core:description": desc(f"Forfeiture status: {forfeiture.get('status', 'unknown')}."),
        },
        {
            "@id": g["impact"],
            "@type": "cacontology-victim-impact:ComprehensiveImpactAssessment",
            "uco-core:name": "Alleged victim harm indicators",
            "rdfs:label": "Alleged victim harm indicators",
            "cacontology-victim-impact:assessmentDate": xs(indictment_date, "xsd:dateTime"),
            "cacontology-victim-impact:assessmentType": "documented_harm_indicators",
            "cacontology-victim-impact:assessorCredentials": "indictment_extraction_agent",
            "cac-core:assesses": {"@id": g["sextortion"]},
            "uco-core:description": desc(f"Coded harm indicators only: {harm_text}."),
        },
    ]

    nodes.extend(
        build_provenance_nodes(g, provenance=provenance, doc_ref=doc_ref)
    )

    for i in range(2, 2 + co_conspirators):
        nodes.append(
            {
                "@id": coconspirator_id(slug, case_number, i),
                "@type": "uco-identity:Person",
                "uco-core:name": f"Alleged co-conspirator {i - 1}",
                "uco-core:description": desc(
                    f"Unnamed alleged co-conspirator in enterprise (minimum {co_conspirator_min} total)."
                ),
            }
        )

    nodes.extend(platform_nodes)
    nodes.extend(charge_nodes)

    co_conspirator_ids = [coconspirator_id(slug, case_number, i) for i in range(2, 2 + co_conspirators)]
    for index, node in enumerate(nodes):
        if node.get("@id") == g["leadership_relator"]:
            nodes[index] = build_enterprise_relators(
                g,
                defendant_id=g["defendant"],
                victim_role_id=g["victim_role"],
                co_conspirator_ids=co_conspirator_ids,
                basis_word=evidentiary.capitalize(),
            )[0]
        elif node.get("@id") == g["exploitation_relator"]:
            nodes[index] = build_enterprise_relators(
                g,
                defendant_id=g["defendant"],
                victim_role_id=g["victim_role"],
                co_conspirator_ids=co_conspirator_ids,
                basis_word=evidentiary.capitalize(),
            )[1]

    charge_refs = defendant_charge_refs(
        facts,
        charges,
        slug=slug,
        case_number=case_number,
        default_label=offender_label,
    )
    nodes.extend(
        apply_charged_with(
            nodes,
            charge_refs,
            slug=slug,
            case_number=case_number,
            principal_label=offender_label,
            principal_id=g["defendant"],
        )
    )
    apply_forfeiture_charge_links(nodes, g["forfeiture"], charges, slug=slug, case_number=case_number)

    venue_nodes, venue_rels = build_count_venue_nodes(
        facts, charges, slug=slug, case_number=case_number, primary_court=court
    )
    nodes.extend(venue_nodes)

    ban_evasion_node, ban_evasion_rels = build_ban_evasion_lifecycle(
        ban_evasion,
        slug=slug,
        case_number=case_number,
        g=g,
        offense_begin=offense_begin,
        basis_word=evidentiary.capitalize(),
    )
    if ban_evasion_node:
        nodes.append(ban_evasion_node)

    transnational = facts.get("transnational") or {}

    relationships: list[dict[str, Any]] = [
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="subject",
            source=g["defendant"],
            target=g["subject"],
            kind="has_role",
            name=f"{offender_label} subject role",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="enterprise-sextortion",
            source=g["enterprise"],
            target=g["sextortion"],
            kind="conducted",
            name="Enterprise conducted sextortion",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="investigation-jurisdiction",
            source=g["investigation"],
            target=g["location_court"],
            kind="located_at",
            name="Investigation jurisdiction",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="impersonation-sextortion",
            source=g["impersonation"],
            target=g["sextortion"],
            kind="Relates_To",
            name="Impersonation supported sextortion scheme",
        ),
    ]
    relationships.extend(
        build_federal_prosecution_relationships(
            slug=slug,
            case_number=case_number,
            g=g,
            charges=charges,
            conduct_id=g["sextortion"],
            link_enterprise=True,
            link_conspiracy=True,
            link_charges_to_conduct=False,
        )
    )
    relationships.extend(
        build_sextortion_charge_conduct_links(
            charges, slug=slug, case_number=case_number, g=g
        )
    )
    relationships.extend(venue_rels)
    relationships.extend(ban_evasion_rels)
    relationships.extend(
        build_extradition_relationships(
            transnational,
            slug=slug,
            case_number=case_number,
            g=g,
            defendant_id=g["defendant"],
        )
    )

    for platform in platforms:
        name = str(platform["name"])
        iri = platform_iris[name.lower()]
        role = str(platform.get("role", ""))
        if role in {"victim_identification", "coercion_primary"}:
            relationships.append(
                {
                    "@id": f"kb:{slug}-{case_token(case_number)}-rel-sextortion-{name.lower()}",
                    "@type": "uco-core:Relationship",
                    "uco-core:name": f"Sextortion used {name}",
                    "uco-core:source": {"@id": g["sextortion"]},
                    "uco-core:target": {"@id": iri},
                    "uco-core:kindOfRelationship": "used_platform",
                    "uco-core:isDirectional": xs("true", "xsd:boolean"),
                }
            )
        if role == "storage_and_distribution":
            relationships.append(
                {
                    "@id": f"kb:{slug}-{case_token(case_number)}-rel-enterprise-{name.lower()}",
                    "@type": "uco-core:Relationship",
                    "uco-core:name": f"Enterprise used {name} for distribution",
                    "uco-core:source": {"@id": g["enterprise"]},
                    "uco-core:target": {"@id": iri},
                    "uco-core:kindOfRelationship": "used_platform",
                    "uco-core:isDirectional": xs("true", "xsd:boolean"),
                }
            )

    nodes.extend(relationships)

    return finalize_graph(nodes, g["bundle"])


def build_enterprise_graph(facts: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    """Enterprise-style CSEA group prosecution (e.g. Greggy's Cult) — not sextortion-shaped."""
    case = facts["case"]
    offender = facts.get("offender", {})
    enterprise = facts.get("enterprise", {})
    platforms = facts.get("platforms", [])
    coercion = facts.get("coercion_mechanisms", [])
    harm = facts.get("victim_harm_indicators", [])
    charges = facts.get("charges", [])
    stacking = facts.get("charge_stacking_note", {})
    forfeiture = facts.get("forfeiture", {})
    timeline = facts.get("procedural_timeline", [])
    provenance = facts.get("provenance", {})

    case_number = str(case["case_number"])
    court = str(case.get("court", "Unknown court"))
    date_filed = str(case.get("date_filed", "unknown"))
    evidentiary = str(case.get("evidentiary_basis", "alleged"))
    status = str(case.get("status", "unknown"))
    offender_label = str(offender.get("label", "Defendant-1"))
    basis_word = evidentiary.capitalize()
    basis_label = evidentiary_label(evidentiary)

    g = make_ids(slug, case_number)
    offense_begin = timeline_date(timeline, "indictment", "sealed") or f"{date_filed}T00:00:00Z"
    indictment_date = offense_begin

    victim_count = int(enterprise.get("victim_count_approx", 1))
    co_conspirator_min = int(enterprise.get("co_conspirator_count_min", 2))
    co_conspirators = max(0, co_conspirator_min - 1)
    enterprise_name = str(enterprise.get("name_alleged", "Alleged child exploitation enterprise"))

    platform_iris: dict[str, str] = {}
    platform_nodes: list[dict[str, Any]] = []
    for platform in platforms:
        iri = platform_id(slug, case_number, str(platform["name"]))
        platform_iris[str(platform["name"]).lower()] = iri
        platform_nodes.append(
            build_platform_node(
                platform=platform,
                platform_iri=iri,
                ban_evasion={},
                basis_word=basis_word,
            )
        )

    charge_nodes = build_charge_nodes(
        charges=charges,
        slug=slug,
        case_number=case_number,
        evidentiary=evidentiary,
        doc_ref=str(provenance.get("document", "source document")),
    )

    coercion_text = ", ".join(COERCION_LABELS.get(str(c), str(c).replace("_", " ")) for c in coercion)
    harm_text = "; ".join(HARM_LABELS.get(str(h), str(h).replace("_", " ")) for h in harm)

    stacking_text = ""
    if stacking.get("observed"):
        stacking_text = (
            f" Charge stacking observed: {str(stacking.get('description', '')).replace('_', ' ')}."
        )

    operational_window = str(enterprise.get("operational_window", "unknown"))
    offense_window = str(enterprise.get("offense_window_charged", operational_window))
    doc_ref = str(provenance.get("document", "source document"))
    defendant_count = offender.get("defendant_count_total", offender.get("defendant_count_named", "?"))

    investigation_status = "closed" if status == "sentenced" else "open"
    prosecution_status = "resolved" if status == "sentenced" else "active"

    nodes: list[dict[str, Any]] = [
        {
            "@id": g["bundle"],
            "@type": "uco-core:Bundle",
            "uco-core:name": f"{court} {case_number} (CAC Enhanced)",
            "uco-core:description": desc(
                f"CAC knowledge graph for {case_number} derived from {doc_ref}. "
                f"Evidentiary basis: {evidentiary.upper()}. Coded extraction only — no victim-identifying detail."
            ),
        },
        {
            "@id": g["investigation"],
            "@type": ["case-investigation:Investigation", "cacontology:CACInvestigation"],
            "uco-core:name": f"U.S. v. {offender_label} et al. — {case_number}",
            "uco-core:description": desc(
                f"Federal child exploitation enterprise prosecution in {court}. "
                f"Approximately {victim_count} alleged victims; {defendant_count} defendants. "
                f"Operational window {operational_window}; charged conduct {offense_window}."
                f"{stacking_text}"
            ),
            "case-investigation:focus": [
                "Child Sexual Exploitation Enterprise",
                "Live CSAM Production",
                "Group Coercion and Harassment",
                "Interstate Threats",
            ],
            "case-investigation:investigationForm": "case",
            "case-investigation:investigationStatus": investigation_status,
            "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
        },
        {
            "@id": g["prosecution"],
            "@type": "cacontology-usa-federal-law:FederalProsecution",
            "uco-core:name": f"Federal prosecution — {case_number}",
            "rdfs:label": f"Federal prosecution — {case_number}",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:hasProsecutionBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:prosecutedBy": {"@id": g["prosecutor"]},
            "cacontology-usa-federal-law:hasLegalPhase": {"@id": g["pretrial_phase"]},
            "cacontology-usa-federal-law:prosecutionComplexity": "highly-complex",
            "cacontology-usa-federal-law:prosecutionSeverity": "aggravated-felony",
            "cacontology-usa-federal-law:prosecutionStatus": prosecution_status,
        },
        {
            "@id": g["prosecutor"],
            "@type": "cacontology-usa-federal-law:FederalProsecutorRole",
            "uco-core:name": court,
            "rdfs:label": court,
            "cacontology-usa-federal-law:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:roleSpecialization": "child-exploitation",
        },
        {
            "@id": g["pretrial_phase"],
            "@type": ["cac-core:Phase", "cacontology-usa-federal-law:PreTrialPhase"],
            "uco-core:name": "Pre-trial phase",
            "rdfs:label": "Pre-trial phase",
            "cacontology:hasPhaseBeginPoint": xs(indictment_date, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["indictment"],
            "@type": "cacontology:MultiDefendantIndictment",
            "uco-core:name": doc_ref,
            "rdfs:label": doc_ref,
            "uco-core:description": desc(
                f"Indictment filed {date_filed}. {len(charges)} counts; {defendant_count} defendants alleged."
            ),
        },
        {
            "@id": g["enterprise"],
            "@type": ["uco-identity:Organization", "cacontology-extremist-enterprises:ChildExploitationEnterprise"],
            "uco-core:name": enterprise_name,
            "rdfs:label": enterprise_name,
            "uco-core:description": desc(
                f"{basis_word} enterprise under {enterprise.get('statute', '18 U.S.C. 2252A(g)')} "
                f"with minimum {co_conspirator_min} co-conspirators and approximately {victim_count} victims."
            ),
            "cacontology-extremist-enterprises:leadershipCount": xs("1", "xsd:nonNegativeInteger"),
            "cacontology-extremist-enterprises:membershipRequirements": (
                "Alleged members coordinated systematic online child exploitation using "
                "multiple platforms including live video and group harassment."
            ),
            "cacontology-extremist-enterprises:hasHierarchy": {"@id": g["hierarchy"]},
            "cacontology-extremist-enterprises:hasLeadershipRelation": {"@id": g["leadership_relator"]},
            "cacontology-extremist-enterprises:hasExploitationRelation": {"@id": g["exploitation_relator"]},
            "cacontology-extremist-enterprises:hasMember": [{"@id": g["defendant"]}]
            + [{"@id": coconspirator_id(slug, case_number, i)} for i in range(2, 2 + co_conspirators)],
            "cacontology-extremist-enterprises:hasOperationalBeginDate": xs(offense_begin, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["hierarchy"],
            "@type": "cacontology-extremist-enterprises:EnterpriseHierarchy",
            "uco-core:name": f"{basis_word} enterprise hierarchy",
            "rdfs:label": f"{basis_word} enterprise hierarchy",
            "cacontology-extremist-enterprises:hierarchyComplexity": str(enterprise.get("scale", "moderate")),
        },
        {"@id": g["leadership_relator"], "@type": "gufo:Relator", "rdfs:label": f"{basis_word} enterprise leadership relation"},
        {"@id": g["exploitation_relator"], "@type": "gufo:Relator", "rdfs:label": f"{basis_word} perpetrator-victim exploitation relation"},
        {
            "@id": g["defendant"],
            "@type": "uco-identity:Person",
            "uco-core:name": offender_label,
            "uco-core:description": desc(
                f"Principal alleged offender; {str(offender.get('location_at_offense', 'unknown')).replace('_', ' ')}."
            ),
        },
        {
            "@id": g["subject"],
            "@type": ["case-investigation:Subject", "cacontology:OffenderRole"],
            "uco-core:name": f"{offender_label} — principal subject",
            "rdfs:label": f"{offender_label} — principal subject",
            "cacontology:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:participatesInEvent": [{"@id": g["csam_incident"]}, {"@id": g["conspiracy"]}],
        },
        {
            "@id": g["victim_role"],
            "@type": ["uco-victim:Victim", "cacontology:VictimRole"],
            "uco-core:name": "Alleged victim population (aggregate)",
            "rdfs:label": "Alleged victim population (aggregate)",
            "cacontology:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:participatesInEvent": [{"@id": g["csam_incident"]}, {"@id": g["conspiracy"]}],
            "uco-core:description": desc(
                f"Aggregate victim role for approximately {victim_count} alleged victims; no identifying detail."
            ),
        },
        {
            "@id": g["content_facet"],
            "@type": "uco-observable:ContentDataFacet",
        },
        {
            "@id": g["csam_incident"],
            "@type": "cacontology:CSAMIncident",
            "uco-core:name": f"{basis_word} CSAM production and distribution ({basis_label})",
            "rdfs:label": f"{basis_word} CSAM production and distribution ({basis_label})",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
            "uco-core:hasFacet": [{"@id": g["content_facet"]}],
            "cacontology:participatesInEvent": [
                {"@id": g["subject"]},
                {"@id": g["victim_role"]},
            ],
            "uco-core:description": desc(
                f"{basis_word} enterprise CSAM conduct {offense_window}. Coercion via {coercion_text}."
            ),
        },
        {
            "@id": g["conspiracy"],
            "@type": "cacontology:ConspiracyToCommitCSA",
            "uco-core:name": f"{basis_word} conspiracy to commit CSA",
            "rdfs:label": f"{basis_word} conspiracy to commit CSA",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["location_court"],
            "@type": "uco-location:Location",
            "uco-core:name": court,
        },
        {
            "@id": g["forfeiture_asset"],
            "@type": "uco-observable:ObservableObject",
            "uco-core:name": f"{basis_word} criminal proceeds and digital devices (forfeiture target)",
        },
        {
            "@id": g["forfeiture"],
            "@type": "cacontology-asset-forfeiture:AssetForfeitureAction",
            "uco-core:name": f"{basis_word} asset forfeiture under {forfeiture.get('statute', '18 U.S.C. 2253')}",
            "rdfs:label": f"{basis_word} asset forfeiture under {forfeiture.get('statute', '18 U.S.C. 2253')}",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(indictment_date, "xsd:dateTimeStamp"),
            "cacontology-gufo:forfeitureBeginTime": xs(indictment_date, "xsd:dateTime"),
            "cacontology-asset-forfeiture:targetedAsset": {"@id": g["forfeiture_asset"]},
            "uco-core:description": desc(f"Forfeiture status: {forfeiture.get('status', 'unknown')}."),
        },
        {
            "@id": g["impact"],
            "@type": "cacontology-victim-impact:ComprehensiveImpactAssessment",
            "uco-core:name": f"{basis_word} victim harm indicators",
            "rdfs:label": f"{basis_word} victim harm indicators",
            "cacontology-victim-impact:assessmentDate": xs(indictment_date, "xsd:dateTime"),
            "cacontology-victim-impact:assessmentType": "documented_harm_indicators",
            "cacontology-victim-impact:assessorCredentials": "indictment_extraction_agent",
            "cac-core:assesses": {"@id": g["csam_incident"]},
            "uco-core:description": desc(f"Coded harm indicators only: {harm_text}."),
        },
    ]

    nodes.extend(build_provenance_nodes(g, provenance=provenance, doc_ref=doc_ref))

    for i in range(2, 2 + co_conspirators):
        nodes.append(
            {
                "@id": coconspirator_id(slug, case_number, i),
                "@type": "uco-identity:Person",
                "uco-core:name": f"Alleged co-conspirator {i - 1}",
                "uco-core:description": desc(
                    f"Unnamed alleged co-conspirator in enterprise (minimum {co_conspirator_min} total)."
                ),
            }
        )

    nodes.extend(platform_nodes)
    nodes.extend(charge_nodes)

    co_conspirator_ids = [coconspirator_id(slug, case_number, i) for i in range(2, 2 + co_conspirators)]
    relator_nodes = build_enterprise_relators(
        g,
        defendant_id=g["defendant"],
        victim_role_id=g["victim_role"],
        co_conspirator_ids=co_conspirator_ids,
        basis_word=basis_word,
    )
    for index, node in enumerate(nodes):
        if node.get("@id") == g["leadership_relator"]:
            nodes[index] = relator_nodes[0]
        elif node.get("@id") == g["exploitation_relator"]:
            nodes[index] = relator_nodes[1]

    charge_refs = defendant_charge_refs(
        facts,
        charges,
        slug=slug,
        case_number=case_number,
        default_label=offender_label,
    )
    nodes.extend(
        apply_charged_with(
            nodes,
            charge_refs,
            slug=slug,
            case_number=case_number,
            principal_label=offender_label,
            principal_id=g["defendant"],
        )
    )
    apply_forfeiture_charge_links(nodes, g["forfeiture"], charges, slug=slug, case_number=case_number)

    venue_nodes, venue_rels = build_count_venue_nodes(
        facts, charges, slug=slug, case_number=case_number, primary_court=court
    )
    nodes.extend(venue_nodes)

    count_one_iri = charge_iri(slug, case_number, charges[0]) if charges else ""
    overt_act_violations = facts.get("overt_act_violations") or []
    overt_nodes, overt_rels = build_overt_act_violation_nodes(
        overt_act_violations if isinstance(overt_act_violations, list) else [],
        slug=slug,
        case_number=case_number,
        count_one_iri=count_one_iri,
        basis_word=basis_word,
    )
    nodes.extend(overt_nodes)

    relationships: list[dict[str, Any]] = [
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="subject",
            source=g["defendant"],
            target=g["subject"],
            kind="has_role",
            name=f"{offender_label} subject role",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="enterprise-csam",
            source=g["enterprise"],
            target=g["csam_incident"],
            kind="conducted",
            name="Enterprise conducted CSAM offenses",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="investigation-jurisdiction",
            source=g["investigation"],
            target=g["location_court"],
            kind="located_at",
            name="Investigation jurisdiction",
        ),
    ]
    relationships.extend(
        build_federal_prosecution_relationships(
            slug=slug,
            case_number=case_number,
            g=g,
            charges=charges,
            conduct_id=g["csam_incident"],
            link_enterprise=True,
            link_conspiracy=True,
        )
    )
    relationships.extend(venue_rels)
    relationships.extend(overt_rels)

    for platform in platforms:
        name = str(platform["name"])
        iri = platform_iris[name.lower()]
        role = str(platform.get("role", ""))
        target = g["csam_incident"] if role in {"live_production", "coercion_and_harassment"} else g["enterprise"]
        relationships.append(
            {
                "@id": f"kb:{slug}-{case_token(case_number)}-rel-{role}-{name.lower()}",
                "@type": "uco-core:Relationship",
                "uco-core:name": f"Enterprise conduct used {name}",
                "uco-core:source": {"@id": target},
                "uco-core:target": {"@id": iri},
                "uco-core:kindOfRelationship": "used_platform",
                "uco-core:isDirectional": xs("true", "xsd:boolean"),
            }
        )

    nodes.extend(relationships)
    return finalize_graph(nodes, g["bundle"])


def build_production_graph(facts: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    """CSAM production/possession/transport prosecution — multi-district when present."""
    case = facts["case"]
    offender = facts.get("offender", {})
    offense = facts.get("offense", {})
    charges = facts.get("charges", [])
    forfeiture = facts.get("forfeiture", {})
    timeline = facts.get("procedural_timeline", [])
    provenance = facts.get("provenance", {})
    parallel_districts = facts.get("parallel_districts", [])
    parallel_prosecution = facts.get("parallel_prosecution", {})
    production_mechanisms = facts.get("production_mechanisms", [])
    devices = facts.get("devices_forfeiture_alleged", [])

    case_number = str(case["case_number"])
    court = str(case.get("court", "Unknown court"))
    date_filed = str(case.get("date_filed", "unknown"))
    evidentiary = str(case.get("evidentiary_basis", "alleged"))
    status = str(case.get("status", "unknown"))
    offender_label = str(offender.get("label", "Defendant-1"))
    basis_word = evidentiary.capitalize()
    basis_label = evidentiary_label(evidentiary)

    g = make_ids(slug, case_number)
    offense_begin = str(offense.get("conduct_window_start", "")) or timeline_date(timeline, "indictment", "arrest")
    if offense_begin and "T" not in offense_begin:
        offense_begin = f"{offense_begin}T00:00:00Z"
    if not offense_begin:
        offense_begin = f"{date_filed}T00:00:00Z"

    offense_end = str(offense.get("conduct_window_end", ""))
    if offense_end and "T" not in offense_end:
        offense_end = f"{offense_end}T00:00:00Z"

    doc_ref = str(provenance.get("document", "source document"))
    charge_nodes = build_charge_nodes(
        charges=charges,
        slug=slug,
        case_number=case_number,
        evidentiary=evidentiary,
        doc_ref=doc_ref,
    )

    mechanism_text = ", ".join(
        PRODUCTION_MECHANISM_LABELS.get(str(m), str(m).replace("_", " ")) for m in production_mechanisms
    )
    conduct_flags = []
    for flag, label in (
        ("production_alleged", "production"),
        ("receipt_alleged", "receipt"),
        ("possession_alleged", "possession"),
        ("transport_alleged", "transport"),
    ):
        if offense.get(flag):
            conduct_flags.append(label)
    conduct_text = ", ".join(conduct_flags) if conduct_flags else "unspecified conduct"

    multi_district_text = ""
    if parallel_prosecution.get("multi_district_federal"):
        districts = parallel_prosecution.get("districts", [])
        if districts:
            multi_district_text = f" Parallel federal prosecutions in {', '.join(str(d) for d in districts)}."

    military_text = ""
    if offender.get("military_context_alleged"):
        military_text = " Military context alleged (docket signal only)."

    investigation_status = "closed" if status == "sentenced" else "open"
    prosecution_status = "resolved" if status == "sentenced" else "active"

    victim_count_known = int(offense.get("known_victim_count_in_indictment", 0))

    csam_node: dict[str, Any] = {
        "@id": g["csam_incident"],
        "@type": "cacontology:CSAMIncident",
        "uco-core:name": f"{basis_word} CSAM {conduct_text} ({basis_label})",
        "rdfs:label": f"{basis_word} CSAM {conduct_text} ({basis_label})",
        "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
        "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
        "uco-core:hasFacet": [{"@id": g["content_facet"]}],
        "cacontology:participatesInEvent": [{"@id": g["subject"]}],
        "uco-core:description": desc(
            f"{basis_word} {str(offense.get('type', 'csam offense')).replace('_', ' ')} "
            f"under {offense.get('primary_statute_alleged', 'federal CSAM statutes')}. "
            f"Conduct window {offense.get('conduct_window_start', '?')} to "
            f"{offense.get('conduct_window_end', '?')}. "
            f"Interstate commerce element: {offense.get('interstate_commerce_element', False)}. "
            f"Mechanisms: {mechanism_text or 'not specified in indictment'}."
            f"{military_text}"
        ),
    }
    if offense_end:
        csam_node["gufo:hasEndPointInXSDDateTimeStamp"] = xs(offense_end, "xsd:dateTimeStamp")

    nodes: list[dict[str, Any]] = [
        {
            "@id": g["bundle"],
            "@type": "uco-core:Bundle",
            "uco-core:name": f"{court} {case_number} (CAC Enhanced)",
            "uco-core:description": desc(
                f"CAC knowledge graph for {case_number} derived from {doc_ref}. "
                f"Evidentiary basis: {evidentiary.upper()}. Coded extraction only — no victim-identifying detail."
            ),
        },
        {
            "@id": g["investigation"],
            "@type": ["case-investigation:Investigation", "cacontology:CACInvestigation"],
            "uco-core:name": f"U.S. v. {offender_label} — {case_number}",
            "uco-core:description": desc(
                f"Federal CSAM production/possession/transport prosecution in {court}."
                f"{multi_district_text}{military_text} "
                f"Victim count in indictment: {victim_count_known if victim_count_known else 'not specified'}."
            ),
            "case-investigation:focus": [
                "CSAM Production",
                "CSAM Possession",
                "CSAM Transport and Receipt",
                "Multi-District Prosecution",
            ],
            "case-investigation:investigationForm": "case",
            "case-investigation:investigationStatus": investigation_status,
            "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
        },
        {
            "@id": g["prosecution"],
            "@type": "cacontology-usa-federal-law:FederalProsecution",
            "uco-core:name": f"Federal prosecution — {case_number}",
            "rdfs:label": f"Federal prosecution — {case_number}",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:hasProsecutionBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:prosecutedBy": {"@id": g["prosecutor"]},
            "cacontology-usa-federal-law:hasLegalPhase": {"@id": g["pretrial_phase"]},
            "cacontology-usa-federal-law:prosecutionComplexity": "moderate",
            "cacontology-usa-federal-law:prosecutionSeverity": "aggravated-felony",
            "cacontology-usa-federal-law:prosecutionStatus": prosecution_status,
        },
        {
            "@id": g["prosecutor"],
            "@type": "cacontology-usa-federal-law:FederalProsecutorRole",
            "uco-core:name": court,
            "rdfs:label": court,
            "cacontology-usa-federal-law:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:roleSpecialization": "child-exploitation",
        },
        {
            "@id": g["pretrial_phase"],
            "@type": ["cac-core:Phase", "cacontology-usa-federal-law:PreTrialPhase"],
            "uco-core:name": "Pre-trial phase",
            "rdfs:label": "Pre-trial phase",
            "cacontology:hasPhaseBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["indictment"],
            "@type": "cacontology:MultiDefendantIndictment",
            "uco-core:name": doc_ref,
            "rdfs:label": doc_ref,
            "uco-core:description": desc(
                f"Primary indictment filed {date_filed}. {len(charges)} federal counts alleged."
            ),
        },
        {
            "@id": g["defendant"],
            "@type": "uco-identity:Person",
            "uco-core:name": offender_label,
            "uco-core:description": desc(
                f"Principal alleged offender; {str(offender.get('location_at_offense', 'unknown')).replace('_', ' ')}."
                f"{military_text}"
            ),
        },
        {
            "@id": g["subject"],
            "@type": ["case-investigation:Subject", "cacontology:OffenderRole"],
            "uco-core:name": f"{offender_label} — principal subject",
            "rdfs:label": f"{offender_label} — principal subject",
            "cacontology:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:participatesInEvent": [{"@id": g["csam_incident"]}],
        },
        {
            "@id": g["content_facet"],
            "@type": "uco-observable:ContentDataFacet",
        },
        csam_node,
        {
            "@id": g["location_court"],
            "@type": "uco-location:Location",
            "uco-core:name": court,
        },
        {
            "@id": g["forfeiture_asset"],
            "@type": "uco-observable:ObservableObject",
            "uco-core:name": f"{basis_word} devices and criminal proceeds (forfeiture target)",
        },
        {
            "@id": g["forfeiture"],
            "@type": "cacontology-asset-forfeiture:AssetForfeitureAction",
            "uco-core:name": f"{basis_word} asset forfeiture under {forfeiture.get('statute', '18 U.S.C. 2253')}",
            "rdfs:label": f"{basis_word} asset forfeiture under {forfeiture.get('statute', '18 U.S.C. 2253')}",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-gufo:forfeitureBeginTime": xs(offense_begin, "xsd:dateTime"),
            "cacontology-asset-forfeiture:targetedAsset": {"@id": g["forfeiture_asset"]},
            "uco-core:description": desc(
                f"Forfeiture status: {forfeiture.get('status', 'unknown')}. "
                f"Devices enumerated: {forfeiture.get('devices_enumerated', False)}."
            ),
        },
    ]

    device_nodes: list[dict[str, Any]] = []
    for index, device in enumerate(devices, start=1):
        make = str(device.get("make", "unknown"))
        model = str(device.get("model", "unknown"))
        device_nodes.append(
            {
                "@id": device_id(slug, case_number, index),
                "@type": [
                    "uco-observable:ObservableObject",
                    "cacontology-production:MobileRecordingDevice",
                ],
                "uco-core:name": f"{make} {model}",
                "uco-core:description": desc(f"{basis_word} mobile device listed for forfeiture."),
                "cacontology-production:equipmentType": "smartphone",
                "cacontology-production:deviceBrand": make,
                "cacontology-production:deviceModel": model,
            }
        )

    parallel_nodes: list[dict[str, Any]] = []
    for index, district in enumerate(parallel_districts):
        parallel_nodes.append(
            {
                "@id": parallel_court_id(slug, case_number, index),
                "@type": "uco-location:Location",
                "uco-core:name": str(district.get("court", "Parallel district court")),
                "uco-core:description": desc(
                    f"Parallel case {district.get('case_number', '?')} filed {district.get('date_filed', '?')}. "
                    f"Role: {str(district.get('role', 'parallel prosecution')).replace('_', ' ')}."
                ),
            }
        )

    nodes.extend(build_provenance_nodes(g, provenance=provenance, doc_ref=doc_ref))
    nodes.extend(device_nodes)
    nodes.extend(parallel_nodes)
    nodes.extend(charge_nodes)

    charge_refs = defendant_charge_refs(
        facts,
        charges,
        slug=slug,
        case_number=case_number,
        default_label=offender_label,
    )
    nodes.extend(
        apply_charged_with(
            nodes,
            charge_refs,
            slug=slug,
            case_number=case_number,
            principal_label=offender_label,
            principal_id=g["defendant"],
        )
    )
    apply_forfeiture_charge_links(nodes, g["forfeiture"], charges, slug=slug, case_number=case_number)

    venue_nodes, venue_rels = build_count_venue_nodes(
        facts, charges, slug=slug, case_number=case_number, primary_court=court
    )
    nodes.extend(venue_nodes)

    forfeiture_devices = facts.get("forfeiture_devices") or []
    ff_device_nodes, ff_device_rels = build_forfeiture_device_links(
        forfeiture_devices if isinstance(forfeiture_devices, list) else [],
        slug=slug,
        case_number=case_number,
        forfeiture_id=g["forfeiture"],
        basis_word=basis_word,
        device_index_offset=len(devices),
    )
    nodes.extend(ff_device_nodes)

    relationships: list[dict[str, Any]] = [
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="subject",
            source=g["defendant"],
            target=g["subject"],
            kind="has_role",
            name=f"{offender_label} subject role",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="investigation-jurisdiction",
            source=g["investigation"],
            target=g["location_court"],
            kind="located_at",
            name="Investigation jurisdiction",
        ),
    ]
    relationships.extend(
        build_federal_prosecution_relationships(
            slug=slug,
            case_number=case_number,
            g=g,
            charges=charges,
            conduct_id=g["csam_incident"],
            link_enterprise=False,
            link_conspiracy=False,
        )
    )
    relationships.extend(venue_rels)
    relationships.extend(ff_device_rels)

    for index, _district in enumerate(parallel_districts):
        relationships.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"parallel-{index}",
                source=g["investigation"],
                target=parallel_court_id(slug, case_number, index),
                kind="parallel_jurisdiction",
                name="Parallel federal prosecution district",
            )
        )

    for index, _device in enumerate(devices, start=1):
        relationships.append(
            make_rel(
                slug=slug,
                case_number=case_number,
                rel_id=f"device-{index}",
                source=g["csam_incident"],
                target=device_id(slug, case_number, index),
                kind="used_equipment",
                name="CSAM incident involved device",
            )
        )

    nodes.extend(relationships)
    return finalize_graph(nodes, g["bundle"])


def build_enticement_graph(facts: dict[str, Any], slug: str) -> list[dict[str, Any]]:
    case = facts["case"]
    offender = facts.get("offender", {})
    offense = facts.get("offense", {})
    platforms = facts.get("platforms", [])
    coercion = facts.get("coercion_mechanisms", [])
    harm = facts.get("victim_harm_indicators", [])
    charges = facts.get("charges", [])
    forfeiture = facts.get("forfeiture", {})
    disposition = facts.get("disposition", {})
    timeline = facts.get("procedural_timeline", [])
    provenance = facts.get("provenance", {})
    multi_victim = facts.get("multi_victim_context", {})
    post_offense = facts.get("post_offense_conduct", {})
    parallel = facts.get("parallel_prosecution", {})

    case_number = str(case["case_number"])
    court = str(case.get("court", "Unknown court"))
    date_filed = str(case.get("date_filed", "unknown"))
    evidentiary = str(case.get("evidentiary_basis", "alleged"))
    status = str(case.get("status", "unknown"))
    offender_label = str(offender.get("label", "Defendant-1"))
    basis_word = evidentiary.capitalize()
    basis_label = evidentiary_label(evidentiary)

    g = make_ids(slug, case_number)
    offense_begin = timeline_date(timeline, "indictment", "arrest") or f"{date_filed}T00:00:00Z"
    plea_date = timeline_date(timeline, "guilty plea")
    if not plea_date and disposition.get("plea_date"):
        plea_date = f"{disposition['plea_date']}T00:00:00Z"
    sentencing_date = timeline_date(timeline, "sentencing")
    if not sentencing_date and disposition.get("sentencing_date"):
        sentencing_date = f"{disposition['sentencing_date']}T00:00:00Z"
    if not sentencing_date:
        sentencing_date = f"{date_filed}T00:00:00Z"

    victim_count = 1
    if multi_victim.get("additional_minors_solicited"):
        victim_count += int(multi_victim.get("additional_count_approx", 0))

    doc_ref = str(provenance.get("document", "source document"))

    platform_iris: dict[str, str] = {}
    platform_nodes: list[dict[str, Any]] = []
    for platform in platforms:
        iri = platform_id(slug, case_number, str(platform["name"]))
        platform_iris[str(platform["name"]).lower()] = iri
        platform_nodes.append(
            build_platform_node(
                platform=platform,
                platform_iri=iri,
                ban_evasion={},
                basis_word=basis_word,
            )
        )

    charge_nodes = build_charge_nodes(
        charges=charges,
        slug=slug,
        case_number=case_number,
        evidentiary=evidentiary,
        doc_ref=doc_ref,
    )

    coercion_text = ", ".join(COERCION_LABELS.get(str(c), str(c).replace("_", " ")) for c in coercion)
    harm_text = "; ".join(HARM_LABELS.get(str(h), str(h).replace("_", " ")) for h in harm)

    parallel_text = ""
    if parallel.get("state_case_present"):
        parallel_text = (
            f" Parallel state prosecution in {parallel.get('jurisdiction', 'unknown state')} "
            f"({parallel.get('relationship', 'dual sovereign')})."
        )

    post_offense_text = ""
    if isinstance(post_offense, dict):
        conduct = post_offense.get("items", [])
        if isinstance(conduct, list):
            conduct = [str(x).replace("_", " ") for x in conduct]
            if conduct:
                post_offense_text = f" Post-offense conduct: {', '.join(conduct)}."
        if post_offense.get("obstruction_present"):
            post_offense_text += " Obstruction present."

    investigation_status = "closed" if status == "sentenced" else "open"
    prosecution_status = "resolved" if status == "sentenced" else "active"

    nodes: list[dict[str, Any]] = [
        {
            "@id": g["bundle"],
            "@type": "uco-core:Bundle",
            "uco-core:name": f"{court} {case_number} (CAC Enhanced)",
            "uco-core:description": desc(
                f"CAC knowledge graph for {case_number} derived from {doc_ref}. "
                f"Evidentiary basis: {evidentiary.upper()}. Coded extraction only — no victim-identifying detail."
            ),
        },
        {
            "@id": g["investigation"],
            "@type": ["case-investigation:Investigation", "cacontology:CACInvestigation"],
            "uco-core:name": f"U.S. v. {offender_label} — {case_number}",
            "uco-core:description": desc(
                f"Federal online enticement prosecution in {court}. Single primary victim "
                f"(age {offense.get('victim_age_at_offense', 'unknown')} at offense)."
                f"{parallel_text}{post_offense_text}"
            ),
            "case-investigation:focus": [
                "Online Enticement",
                "Grooming and Solicitation",
                "Interstate Travel",
            ],
            "case-investigation:investigationForm": "case",
            "case-investigation:investigationStatus": investigation_status,
            "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
        },
        {
            "@id": g["prosecution"],
            "@type": "cacontology-usa-federal-law:FederalProsecution",
            "uco-core:name": f"Federal prosecution — {case_number}",
            "rdfs:label": f"Federal prosecution — {case_number}",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:hasProsecutionBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:hasProsecutionEndPoint": xs(sentencing_date, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:prosecutedBy": {"@id": g["prosecutor"]},
            "cacontology-usa-federal-law:hasLegalPhase": {"@id": g["pretrial_phase"]},
            "cacontology-usa-federal-law:prosecutionComplexity": "moderate",
            "cacontology-usa-federal-law:prosecutionSeverity": "aggravated-felony",
            "cacontology-usa-federal-law:prosecutionStatus": prosecution_status,
        },
        {
            "@id": g["prosecutor"],
            "@type": "cacontology-usa-federal-law:FederalProsecutorRole",
            "uco-core:name": court,
            "rdfs:label": court,
            "cacontology-usa-federal-law:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology-usa-federal-law:roleSpecialization": "child-exploitation",
        },
        {
            "@id": g["pretrial_phase"],
            "@type": ["cac-core:Phase", "cacontology-usa-federal-law:PreTrialPhase"],
            "uco-core:name": "Pre-trial through sentencing phase",
            "rdfs:label": "Pre-trial through sentencing phase",
            "cacontology:hasPhaseBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:hasPhaseEndPoint": xs(sentencing_date, "xsd:dateTimeStamp"),
        },
        {
            "@id": g["indictment"],
            "@type": "cacontology:MultiDefendantIndictment",
            "uco-core:name": doc_ref,
            "rdfs:label": doc_ref,
            "uco-core:description": desc(
                f"Indictment filed {date_filed}. {len(charges)} counts; "
                f"guilty plea {plea_date[:10] if plea_date else 'unknown'}."
            ),
        },
        {
            "@id": g["defendant"],
            "@type": "uco-identity:Person",
            "uco-core:name": offender_label,
            "uco-core:description": desc(
                f"Principal offender; {str(offender.get('location_at_offense', 'unknown')).replace('_', ' ')}."
                + (" Age misrepresentation to victim." if offender.get("age_misrepresentation") else "")
            ),
        },
        {
            "@id": g["subject"],
            "@type": ["case-investigation:Subject", "cacontology:OffenderRole"],
            "uco-core:name": f"{offender_label} — principal subject",
            "rdfs:label": f"{offender_label} — principal subject",
            "cacontology:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:participatesInEvent": [{"@id": g["grooming"]}],
        },
        {
            "@id": g["victim_role"],
            "@type": ["uco-victim:Victim", "cacontology:VictimRole"],
            "uco-core:name": "Victim (single primary)",
            "rdfs:label": "Victim (single primary)",
            "cacontology:hasRoleBeginPoint": xs(offense_begin, "xsd:dateTimeStamp"),
            "cacontology:participatesInEvent": [{"@id": g["grooming"]}],
            "uco-core:description": desc(
                f"Primary victim age {offense.get('victim_age_at_offense', 'unknown')} at offense; no identifying detail."
            ),
        },
        {
            "@id": g["grooming"],
            "@type": [
                "cacontology:GroomingSolicitation",
                "cacontology-us-ncmec:OnlineEnticementIncident",
            ],
            "uco-core:name": f"Online enticement to contact ({basis_label})",
            "rdfs:label": f"Online enticement to contact ({basis_label})",
            "cacontology-us-ncmec:incidentCode": "OE",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(offense_begin, "xsd:dateTimeStamp"),
            "uco-core:startTime": xs(offense_begin, "xsd:dateTime"),
            "cacontology:participatesInEvent": [
                {"@id": g["subject"]},
                {"@id": g["victim_role"]},
            ],
            "uco-core:description": desc(
                f"{basis_word} {str(offense.get('type', 'online enticement')).replace('_', ' ')} under "
                f"{offense.get('statute_of_conviction', 'unknown')}. Coercion via {coercion_text}. "
                f"Online-to-in-person contact: {offense.get('online_to_inperson', False)}; "
                f"interstate travel: {offense.get('interstate_travel', False)}; "
                f"physical contact: {offense.get('physical_contact_occurred', False)}."
            ),
        },
        {
            "@id": g["location_court"],
            "@type": "uco-location:Location",
            "uco-core:name": court,
        },
        {
            "@id": g["forfeiture_asset"],
            "@type": "uco-observable:ObservableObject",
            "uco-core:name": "Criminal proceeds (forfeiture target)",
        },
        {
            "@id": g["forfeiture"],
            "@type": "cacontology-asset-forfeiture:AssetForfeitureAction",
            "uco-core:name": "Asset forfeiture",
            "rdfs:label": "Asset forfeiture",
            "gufo:hasBeginPointInXSDDateTimeStamp": xs(sentencing_date, "xsd:dateTimeStamp"),
            "cacontology-gufo:forfeitureBeginTime": xs(sentencing_date, "xsd:dateTime"),
            "cacontology-asset-forfeiture:targetedAsset": {"@id": g["forfeiture_asset"]},
            "uco-core:description": desc(f"Forfeiture status: {forfeiture.get('status', 'unknown')}."),
        },
        {
            "@id": g["impact"],
            "@type": "cacontology-victim-impact:ComprehensiveImpactAssessment",
            "uco-core:name": "Victim harm indicators",
            "rdfs:label": "Victim harm indicators",
            "cacontology-victim-impact:assessmentDate": xs(sentencing_date, "xsd:dateTime"),
            "cacontology-victim-impact:assessmentType": "documented_harm_indicators",
            "cacontology-victim-impact:assessorCredentials": "statement_of_offense_extraction_agent",
            "cac-core:assesses": {"@id": g["grooming"]},
            "uco-core:description": desc(f"Coded harm indicators only: {harm_text}."),
        },
    ]

    nodes.extend(build_provenance_nodes(g, provenance=provenance, doc_ref=doc_ref))
    nodes.extend(platform_nodes)
    nodes.extend(charge_nodes)

    charge_refs = defendant_charge_refs(
        facts,
        charges,
        slug=slug,
        case_number=case_number,
        default_label=offender_label,
    )
    nodes.extend(
        apply_charged_with(
            nodes,
            charge_refs,
            slug=slug,
            case_number=case_number,
            principal_label=offender_label,
            principal_id=g["defendant"],
        )
    )
    if forfeiture.get("alleged"):
        apply_forfeiture_charge_links(nodes, g["forfeiture"], charges, slug=slug, case_number=case_number)

    relationships: list[dict[str, Any]] = [
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="subject",
            source=g["defendant"],
            target=g["subject"],
            kind="has_role",
            name=f"{offender_label} subject role",
        ),
        make_rel(
            slug=slug,
            case_number=case_number,
            rel_id="investigation-jurisdiction",
            source=g["investigation"],
            target=g["location_court"],
            kind="located_at",
            name="Investigation jurisdiction",
        ),
    ]
    relationships.extend(
        build_federal_prosecution_relationships(
            slug=slug,
            case_number=case_number,
            g=g,
            charges=charges,
            conduct_id=g["grooming"],
            link_enterprise=False,
            link_conspiracy=False,
        )
    )

    for platform in platforms:
        name = str(platform["name"])
        iri = platform_iris[name.lower()]
        relationships.append(
            {
                "@id": f"kb:{slug}-{case_token(case_number)}-rel-grooming-{name.lower()}",
                "@type": "uco-core:Relationship",
                "uco-core:name": f"Enticement used {name}",
                "uco-core:source": {"@id": g["grooming"]},
                "uco-core:target": {"@id": iri},
                "uco-core:kindOfRelationship": "used_platform",
                "uco-core:isDirectional": xs("true", "xsd:boolean"),
            }
        )

    nodes.extend(relationships)
    return finalize_graph(nodes, g["bundle"])


def write_graph(facts_path: Path, output_path: Path) -> None:
    facts = load_facts(facts_path)
    slug = slug_from_facts_path(facts_path)
    ontology_dir = PACER_DIR.parent
    if str(ontology_dir) not in sys.path:
        sys.path.insert(0, str(ontology_dir))
    from pacer_jsonld_to_ttl import pacer_graph_iri  # noqa: E402

    document = {
        "@context": CONTEXT,
        "@id": str(pacer_graph_iri(slug)),
        "@graph": build_graph(facts, slug),
    }
    output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    from pacer_jsonld_to_ttl import convert_jsonld_file  # noqa: E402

    ttl = convert_jsonld_file(output_path, slug=slug)
    print(f"Wrote {ttl['destination']}")


def validate_graph(output_path: Path) -> bool:
    ext_dir = SDK_ROOT / "extensions/cac"
    ontology_graphs = [str(ext_dir / rel) for rel in CURATED_ONTOLOGY_FILES]
    cmd = [
        str(CASE_VALIDATE),
        "--built-version",
        "case-1.4.0",
        "--inference",
        "rdfs",
        "--allow-info",
    ]
    for graph_path in ontology_graphs:
        cmd.extend(["--ontology-graph", graph_path])
    cmd.append(str(output_path))

    print(f"Validating {output_path.name} with {len(ontology_graphs)} ontology graphs...")
    result = subprocess.run(cmd, cwd=SDK_ROOT, capture_output=True, text=True)
    if "Conforms: True" in result.stdout:
        print("Conforms: True")
        return True
    print(result.stdout[-4000:])
    if result.stderr:
        print(result.stderr[-2000:], file=sys.stderr)
    return False


def process_facts_file(facts_path: Path, *, validate: bool) -> int:
    if not facts_path.exists():
        print(f"Facts file not found: {facts_path}", file=sys.stderr)
        return 1
    output_path = output_path_for(facts_path)
    write_graph(facts_path, output_path)
    if not validate:
        return 0
    if not CASE_VALIDATE.exists():
        print("case_validate not found; graph written but not validated.", file=sys.stderr)
        return 1
    return 0 if validate_graph(output_path) else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build CAC JSON-LD graphs from PACER facts files.",
        epilog=(
            "Examples:\n"
            "  python build_facts_graphs.py\n"
            "  python build_facts_graphs.py ALASKA/alaska_facts.txt\n"
            "  python build_facts_graphs.py --facts ALASKA/alaska_facts.txt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "facts_files",
        nargs="*",
        help="Optional specific facts .txt file(s). If omitted, reads facts.txt manifest.",
    )
    parser.add_argument(
        "--facts",
        dest="facts_flag",
        metavar="FILE",
        help="Build graph from a specific facts file (alias for positional argument).",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help=f"Manifest of facts files to build (default: {DEFAULT_MANIFEST.name})",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip case_validate after writing JSON-LD.",
    )
    return parser.parse_args(argv)


def resolve_facts_paths(args: argparse.Namespace) -> list[Path]:
    explicit = list(args.facts_files)
    if args.facts_flag:
        explicit.append(args.facts_flag)
    if explicit:
        resolved: list[Path] = []
        for item in explicit:
            path = Path(item)
            resolved.append(path if path.is_absolute() else PACER_DIR / path)
        return resolved
    return read_manifest(Path(args.manifest))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    facts_paths = resolve_facts_paths(args)
    exit_code = 0
    for facts_path in facts_paths:
        print(f"Building from {facts_path}...")
        result = process_facts_file(facts_path, validate=not args.no_validate)
        if result != 0:
            exit_code = result
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
