"""The observation layer: what a record names, kept apart from what anyone did (state_machines/observations)."""
from __future__ import annotations

import copy
import json

import pytest
import rdflib

from state_machines.evidence import evidence as E
from state_machines.observations import observe as O
from tests.pacer import fixtures as F

CASE = "obs_case"
PAGES = {
    ("sof", 1): ("STATEMENT OF FACTS. On May 2, 2020, the defendant asked Minor Victim 1 for images through the Kitebox application. "
                 "The defendant had the Snapwire application installed on his phone. Minor Victim 1 did not reply on Kitebox. "
                 "He used the disappearing-message feature on Kitebox to ask Minor Victim 1 for more images. "
                 "A forensic report describes a group chat found on the phone."),
    ("docket", 1): "03/04/2024 12 MINUTE ENTRY: hearing held via Zoom video conference. The parties appeared on Zoom.",
}


def _store(tmp_path):
    docs = []
    for (doc_id, page), text in PAGES.items():
        E.write_page(CASE, doc_id, page, text, tmp_path)
        docs.append({"doc_id": doc_id, "doc_type": "docket" if doc_id == "docket" else "statement_of_facts", "sha256": E.sha256_text(doc_id),
                     "pages": [{"pdf_page": page, "text_method": "text_layer", "page_text_sha256": E.sha256_text(E.normalize(text))}]})
    (tmp_path / CASE / "sources.json").write_text(json.dumps({"case_id": CASE, "documents": docs}), encoding="utf-8")
    return docs


def _bundle(tmp_path, docs, acts):
    """A minimal published bundle: one offender act per (event id, action, sentence start words)."""
    page = E.normalize(PAGES[("sof", 1)])
    passages, events = [], []
    for eid, action, words in acts:
        a = page.index(words)
        b = page.index(".", a) + 1
        passages.append({"passage_id": f"q{eid}", "doc_id": "sof", "pdf_page": 1, "char_start": a, "char_end": b})
        events.append({"event_id": eid, "action": action, "support": [{"passage_id": f"q{eid}", "facet": "action", "status": "DIRECT"}],
                       "platform_interactions": [], "affordances": []})
    return {"case_id": CASE, "documents": docs, "passages": passages, "events": events}


def test_sentences_split_at_terminators_not_abbreviations():
    page = "The U.S. Attorney filed it. He wrote to Minor Victim 1 on Kitebox; she did not answer him."
    assert [page[a:b] for a, b in O.sentences(page)] == [
        "The U.S. Attorney filed it.", "He wrote to Minor Victim 1 on Kitebox;", "she did not answer him."]


def test_only_listed_services_are_observed_and_ordinary_words_need_a_service_word():
    names = lambda s: [n for n, _, _ in O.platforms_in(s)]
    assert names("They spoke on Facebook Messenger and on Instagram.") == ["Facebook Messenger", "Instagram"]
    assert names("He sent the files to Greggy using the RexRiddle account.") == []            # not on the list: never recorded
    assert names("The agents received a Signal from the tower and will Zoom in on it.") == []   # ordinary words
    assert names("He wrote to her on Signal and in a Discord server.") == ["Signal", "Discord"]
    assert names("They talked on Face- Time and on INSTAGRAM.") == ["FaceTime", "Instagram"]    # a line break; a caption in capitals
    assert names("He contacted her through Facebook Mes- senger.") == ["Facebook Messenger"]    # a word broken across a line


def test_feature_phrases_are_whole_codebook_phrases():
    feats = lambda s: [(c, p) for c, p, _, _ in O.features_in(s)]
    assert feats("He used the disappearing-message feature.") == [("ephemerality", "disappearing-message")]
    assert feats("The government recommended a sentence and the operator agreed.") == []       # everyday wording; "Tor" inside a word
    assert feats("The app showed him recommended friends.") == [("contact_discovery", "recommended friends")]
    assert feats("He joined a public group search page.") == [("contact_discovery", "public group search")]   # the longest phrase, once


def test_observations_cite_their_sentence_and_skip_docket_sheets(tmp_path):
    _store(tmp_path)
    doc = O.observe(CASE, tmp_path)
    got = [(o["kind"], o.get("platform") or o["feature_term"], o["source_status"]) for o in doc["observations"]]
    assert got == [("platform", "Kitebox", "ADMITTED"), ("platform", "Snapwire", "ADMITTED"), ("platform", "Kitebox", "ADMITTED"),
                   ("feature", "disappearing-message", "ADMITTED"), ("platform", "Kitebox", "ADMITTED"), ("feature", "group chat", "ADMITTED")]
    assert all(o["doc_id"] != "docket" for o in doc["observations"])                          # "held via Zoom" is court business
    page = E.normalize(PAGES[("sof", 1)])
    for o in doc["observations"]:
        assert E.sha256_text(page[o["char_start"]:o["char_end"]]) == o["quote_sha256"] and o["relations"] == []
    assert O.check(doc, tmp_path) == []
    # a date in the sentence is kept as what the sentence mentions, nothing more
    assert doc["observations"][0]["dates_in_sentence"] == [{"earliest": "2020-05-02", "latest": "2020-05-02", "precision": "day"}]
    assert doc["observations"][1]["dates_in_sentence"] == []
    # the page changes: every observation on it is reported
    E.write_page(CASE, "sof", 1, PAGES[("sof", 1)].replace("Snapwire", "Snapwyre"), tmp_path)
    assert any("hash differs" in p for p in O.check(doc, tmp_path))


def test_a_relationship_needs_the_act_sentence_to_state_the_means(tmp_path):
    docs = _store(tmp_path)
    acts = [("e1", "SOLICIT_IMAGERY", "On May 2, 2020"),            # "... through the Kitebox application"
            ("e2", "STORE_MATERIAL", "The defendant had the Snapwire"),   # named, not a means
            ("e3", "COMMUNICATE", "Minor Victim 1 did not reply"),   # negated
            ("e4", "SOLICIT_IMAGERY", "He used the disappearing-message"),
            ("e5", "LE_FORENSIC_EXAM", "A forensic report describes")]   # not an offender act
    bundle = _bundle(tmp_path, docs, acts)
    doc = O.relate(O.observe(CASE, tmp_path), bundle, tmp_path)
    tied = {(o.get("platform") or o["feature_term"], r["event_id"], r["relationship"]) for o in doc["observations"] for r in o["relations"]}
    assert tied == {("Kitebox", "e1", "Carried_Out_Through"), ("disappearing-message", "e4", "Supports_Action"),
                    ("Kitebox", "e4", "Carried_Out_Through")}
    assert O.check(doc, tmp_path, bundle) == []
    # no published act cites the sentence: the observation stands alone
    doc = O.relate(O.observe(CASE, tmp_path), _bundle(tmp_path, docs, acts[1:3]), tmp_path)
    assert all(o["relations"] == [] for o in doc["observations"])
    # a relation to an act that does not cite the sentence is refused
    doc["observations"][0]["relations"] = [{"event_id": "e2", "relationship": "Carried_Out_Through", "cue": "on", "basis": "x"}]
    assert any("does not cite this sentence" in p for p in O.check(doc, tmp_path, _bundle(tmp_path, docs, acts[1:3])))


def test_observation_graph_uses_existing_terms_and_claims_no_use(tmp_path):
    pytest.importorskip("case_uco")
    import sys
    from pathlib import Path
    from rdflib import RDF, URIRef
    from state_machines.graphs.emit import evidence_graph, observation_graph, serialize
    from state_machines.graphs.shacl import EXTENSION, validation_report
    from state_machines.evidence import vocab as V
    bundle, _ = F.build()
    F.write_pages(tmp_path)
    (tmp_path / F.CASE / "sources.json").write_text(json.dumps({"case_id": F.CASE, "documents": bundle["documents"]}), encoding="utf-8")
    plain = O.observe(F.CASE, tmp_path)
    assert {o["feature_term"] for o in plain["observations"]} >= {"public group", "private direct messages"}
    g = rdflib.Graph().parse(data=serialize(observation_graph(bundle, plain)), format="json-ld")
    OA, CLT = rdflib.Namespace("http://www.w3.org/ns/oa#"), rdflib.Namespace("https://w3id.org/caselinker/trajectory#")
    obs = set(g.subjects(OA.motivatedBy, OA.classifying))
    assert len(obs) == len(plain["observations"]) and all((a, CLT.derivationRule, rdflib.Literal(O.RULE_VERSION)) in g for a in obs)
    classes = {URIRef(c) for c in V.AFFORDANCE_CLASSES.values()}
    assert {g.value(a, OA.hasBody) for a in obs} <= classes            # the passage is classified under the CAC class ...
    assert not any((None, RDF.type, c) in g for c in classes)          # ... and no affordance individual exists without a stated means
    assert not list(g.subjects(RDF.type, URIRef("https://ontology.unifiedcyberontology.org/uco/core/Relationship")))
    assert not any("time" in str(p).lower() or "temporal" in str(p).lower() for p in g.predicates())   # sentence dates stay out of the graph
    # with the published acts: the same graph plus only the relationships a sentence supports, and it conforms
    tied = O.relate(copy.deepcopy(plain), bundle, tmp_path)
    ob = serialize(observation_graph(bundle, tied))
    assert validation_report(serialize(evidence_graph(bundle)), ob)["violations"] == []
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ontology" / "pipeline"))
    from term_resolution import declared_terms, graph_terms, parse_jsonld
    ext = rdflib.Graph().parse(EXTENSION / "caselinker-trajectory.ttl", format="turtle")
    known = declared_terms() | {str(s) for s in ext.subjects(RDF.type, None) if isinstance(s, URIRef)}
    path = tmp_path / "ob.jsonld"
    path.write_text(ob, encoding="utf-8")
    missing = {k: sorted(t for t in terms if t not in known) for k, terms in graph_terms(parse_jsonld(path)).items()}
    assert {k: v for k, v in missing.items() if v} == {}


def test_benchmark_scoring_counts_mentions_features_and_relationships():
    from state_machines.benchmark.score import DATA, score_observations, summarize_observations
    gold = json.loads((DATA / "synth_001" / "gold.json").read_text())
    doc = O.relate(O.observe("synth_001", DATA), gold, DATA)       # the gold as the published bundle
    s = summarize_observations(score_observations(gold, doc, gold))
    assert s["platform_mentions_found"]["rate"] == 1.0 and s["feature_statements_found"]["rate"] == 1.0
    assert s["relationships_correct"]["rate"] == 1.0 and s["relationships_platform_only_named_in_gold"] == 0
    for o in doc["observations"]:                                    # a relationship the gold does not hold is counted as wrong
        o["relations"] = [{"event_id": gold["events"][0]["event_id"], "relationship": "Carried_Out_Through", "cue": "on", "basis": "x"}]
    assert summarize_observations(score_observations(gold, doc, gold))["relationships_correct"]["rate"] < 1.0
