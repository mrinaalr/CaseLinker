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
    assert feats("He ran a website and uploaded the files to cloud storage.") == [
        ("distribution_infrastructure", "uploaded"), ("distribution_infrastructure", "cloud storage")]   # a bare "website" is not a feature


def test_two_spellings_of_one_service_are_one_platform(tmp_path):
    E.write_page("alias_case", "sof", 1, "STATEMENT OF FACTS. He wrote to her on Kik Messenger. She answered on Kik the next day.", tmp_path)
    (tmp_path / "alias_case" / "sources.json").write_text(json.dumps({"case_id": "alias_case", "documents": [
        {"doc_id": "sof", "doc_type": "statement_of_facts", "sha256": "x", "pages": [{"pdf_page": 1, "text_method": "text_layer"}]}]}), encoding="utf-8")
    doc = O.observe("alias_case", tmp_path)
    assert [(o["platform"], o["named_as"]) for o in doc["observations"]] == [("Kik", "Kik Messenger"), ("Kik", "Kik")]
    assert O.summary(doc)["platforms"] == {"Kik": 2} and O.check(doc, tmp_path) == []


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


@pytest.mark.parametrize("kind,sentence,term,expected", [
    ("platform", "The defendant sent Minor Victim 1 threats, and her mother reported the account to Kitebox.", "Kitebox", None),      # recipient, another subject
    ("platform", "The defendant stored the images on his phone, and agents served a warrant on Kitebox.", "Kitebox", None),         # someone else's act
    ("platform", "The defendant denied that he had ever asked Minor Victim 1 for images through Kitebox.", "Kitebox", None),        # a denial
    ("platform", "The defendant told Minor Victim 1 to download Kitebox and delete her messages.", "Kitebox", None),                # an infinitive, not a means
    ("feature", "The defendant asked Minor Victim 1 for images after she used a fake name to open her account.", "fake name", None),   # the victim's use
    ("feature", "Minor Victim 1 used a fake name when she replied to the defendant.", "fake name", None),                          # an opening clause about the victim
    ("feature", "An undercover agent used a fake profile to chat with the defendant on Kitebox.", "fake profile", None),            # the agent's feature
    ("platform", "Agents served a search warrant on Kitebox for the account the defendant had created.", "Kitebox", None),          # an opening clause with no offender in it
    ("platform", "Agents used Dropbox to store the images the defendant had sent to Minor Victim 1.", "Dropbox", None),
    ("feature", "The defendant, who used no VPN, was identified by his address.", "VPN", None),                                     # negation between cue and term
    ("feature", "The defendant sent messages that were not encrypted.", "encrypted", None),
    ("feature", "The defendant created an account without a fake name.", "fake name", None),
    ("platform", "Agents learned that the defendant contacted Minor Victim 1 through Kitebox.", "Kitebox", "Carried_Out_Through"),  # reported, but the offender's act
    ("feature", "The defendant used a fake name to open the account.", "fake name", "Supports_Action"),
    ("platform", "The defendant first contacted Minor Victim 1 on Kitebox.", "Kitebox", "Carried_Out_Through"),
    ("platform", "The defendant uploaded the images to Kitebox.", "Kitebox", "Carried_Out_Through"),
    ("platform", "The defendant told Minor Victim 1 to continue their conversation on Kitebox.", "Kitebox", "Moved_To"),
    ("platform", "Minor Victim 1 then sent the defendant three images over Kitebox.", "Kitebox", "Carried_Out_Through"),
    ("platform", "The defendant first contacted her in May, when Minor Victim 1 wrote back to him via Kitebox.", "Kitebox", "Carried_Out_Through"),   # both sides of a conversation
])
def test_the_means_must_be_stated_in_the_offenders_own_clause(kind, sentence, term, expected):
    o = {"kind": kind, "named_as": term, "platform": term, "feature_term": term}
    got = O._means(kind, sentence, o)
    assert (got and got[0]) == expected


def test_a_sentence_several_acts_cite_ties_its_platform_to_none(tmp_path):
    E.write_page("two_acts", "sof", 1, "STATEMENT OF FACTS. The defendant first wrote to Minor Victim 1 through Kitebox and later drove to her home.", tmp_path)
    docs = [{"doc_id": "sof", "doc_type": "statement_of_facts", "sha256": "x", "pages": [{"pdf_page": 1, "text_method": "text_layer"}]}]
    (tmp_path / "two_acts" / "sources.json").write_text(json.dumps({"case_id": "two_acts", "documents": docs}), encoding="utf-8")
    page = E.normalize("STATEMENT OF FACTS. The defendant first wrote to Minor Victim 1 through Kitebox and later drove to her home.")
    a, b = page.index("The defendant"), len(page)
    act = lambda eid, code: {"event_id": eid, "action": code, "support": [{"passage_id": "q1", "facet": "action", "status": "DIRECT"}]}
    bundle = {"case_id": "two_acts", "documents": docs, "passages": [{"passage_id": "q1", "doc_id": "sof", "pdf_page": 1, "char_start": a, "char_end": b}],
              "events": [act("e1", "INITIATE_CONTACT"), act("e2", "TRAVEL_TO_MEET")]}
    doc = O.relate(O.observe("two_acts", tmp_path), bundle, tmp_path)
    assert [o["relations"] for o in doc["observations"]] == [[]] and doc["observations"][0]["several_acts"] == 2
    bundle["events"] = bundle["events"][:1]                               # one act cites it: the means is that act's
    assert O.relate(O.observe("two_acts", tmp_path), bundle, tmp_path)["observations"][0]["relations"][0]["event_id"] == "e1"
    assert [n for n, _, _ in O.platforms_in("He wrote to her on the Signal Messenger app and on the WhatsApp Messenger app.")] == ["Signal", "WhatsApp"]


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
    features = [o for o in plain["observations"] if o["kind"] == "feature"]
    assert {o["feature_term"] for o in features} >= {"public group", "private direct messages"}
    g = rdflib.Graph().parse(data=serialize(observation_graph(bundle, plain)), format="json-ld")
    OA, CLT = rdflib.Namespace("http://www.w3.org/ns/oa#"), rdflib.Namespace("https://w3id.org/caselinker/trajectory#")
    obs = set(g.subjects(OA.motivatedBy, OA.classifying))
    assert len(obs) == len(features) and all((a, CLT.derivationRule, rdflib.Literal(O.RULE_VERSION)) in g for a in obs)
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
    flipped = json.loads(json.dumps(doc))                            # the right platform in the wrong way is not correct
    for o in flipped["observations"]:
        for r in o["relations"]:
            if o["kind"] == "platform":
                r["relationship"] = "Moved_To" if r["relationship"] == "Carried_Out_Through" else "Carried_Out_Through"
    f = summarize_observations(score_observations(gold, flipped, gold))
    assert f["relationships_right_platform_wrong_kind"] > 0 and f["relationships_correct"]["rate"] < 1.0
    for o in doc["observations"]:                                    # a relationship the gold does not hold is counted as wrong
        o["relations"] = [{"event_id": gold["events"][0]["event_id"], "relationship": "Carried_Out_Through", "cue": "on", "basis": "x"}]
    assert summarize_observations(score_observations(gold, doc, gold))["relationships_correct"]["rate"] < 1.0


def test_validation_sample_covers_every_relationship_and_feature_and_scores_apart(tmp_path):
    from state_machines.observations import validation as V2
    docs = _store(tmp_path)
    bundle = _bundle(tmp_path, docs, [("e1", "SOLICIT_IMAGERY", "On May 2, 2020"), ("e4", "SOLICIT_IMAGERY", "He used the disappearing-message")])
    doc = O.relate(O.observe(CASE, tmp_path), bundle, tmp_path)
    root = tmp_path / "rel"
    (root / "observations").mkdir(parents=True)
    (root / "observations" / f"{CASE}.json").write_text(json.dumps(doc), encoding="utf-8")
    items = V2.sample(root)
    assert [i["item_id"] for i in items] == [i["item_id"] for i in V2.sample(root)]                 # the same release, the same items
    tied = {f"{CASE}:{o['observation_id']}" for o in doc["observations"] if o["relations"]}
    assert {i["item_id"] for i in items if i["stratum"] == "relationship"} == tied and len(tied) == 3
    assert {i["item_id"] for i in items} == {f"{CASE}:{o['observation_id']}" for o in doc["observations"]}   # a small case: all of it
    page = V2.packet("rel", root, tmp_path, tmp_path / "out").read_text()
    assert "<mark>Kitebox</mark>" in page and "http" not in page.replace("http-equiv", "")           # local text, no network
    decisions = {"reviewer": "MR", "reviewed_on": "2026-11-18", "decisions": {
        i["item_id"]: {"stratum": i["stratum"], "grounding": "yes", "meaning": "no" if i["stratum"] == "feature" else "yes"} for i in items}}
    s = V2.score(root, decisions)["strata"]
    assert s["relationship"]["meaning_yes"] == 3 and s["feature"]["meaning_no"] == s["feature"]["reviewed"] and s["platform"]["grounded"] == s["platform"]["reviewed"]
    assert "sentence" not in json.dumps(V2.score(root, decisions))                                   # answers only
    del decisions["decisions"][items[0]["item_id"]]
    with pytest.raises(SystemExit, match="unanswered"):
        V2.score(root, decisions)
    assert V2.wilson(9, 10) == [0.596, 0.982]


def test_a_placeholder_label_is_observed_as_a_platform_whose_name_is_withheld(tmp_path, monkeypatch):
    labels = lambda s: [n for n, _, _ in O.withheld_in(s)]
    assert labels("He administered Website A and posted on Website B; Website A had many users.") == ["Website A", "Website B"]
    assert labels("He used a social media application and an online service.") == []          # a description, no label
    assert labels("The U.S. Secret Service I contacted, and Exhibit A, and Count 2.") == []    # not a service label
    assert labels("He posted on Web- site B and on WEBSITE 12.") == ["Website B", "Website 12"]   # a line break; capitals
    for ordinary in ("On the Website I saw images.", "Agents searched Site 1 and Site 2.", "The warrant Application 2 was granted.",
                     "He posted on the Forum A user saw it.", "See Website A-1 and Platform 9.", "the website a user visits"):
        assert labels(ordinary) == [], ordinary                                               # only "Website" + a letter or number
    monkeypatch.setitem(PAGES, ("sof", 1), "The defendant sent the files to other members through Website A. "
                                           "He did not post on Website B. Agents later seized Website A.")
    docs = _store(tmp_path)
    doc = O.observe(CASE, tmp_path)
    got = [(o["platform"], o["named_as"], o.get("withheld")) for o in doc["observations"]]
    assert got == [("Website A (name withheld)", "Website A", True), ("Website B (name withheld)", "Website B", True),
                   ("Website A (name withheld)", "Website A", True)]
    bundle = _bundle(tmp_path, docs, [("e1", "DISTRIBUTE_MATERIAL", "The defendant sent"), ("e2", "DISTRIBUTE_MATERIAL", "He did not post")])
    O.relate(doc, bundle, tmp_path)
    assert [[(r["event_id"], r["relationship"]) for r in o["relations"]] for o in doc["observations"]] == [
        [("e1", "Carried_Out_Through")], [], []]                                             # the denial and the seizure tie nothing
    assert O.check(doc, tmp_path, bundle) == []
    bad = copy.deepcopy(doc)
    bad["observations"][0]["platform"] = "Somebody's Site (name withheld)"                   # free text is refused
    assert any("placeholder" in p for p in O.check(bad, tmp_path, bundle))
    from state_machines.observations.table import case_observed
    seen = case_observed(doc)["platforms"]
    assert seen["Website A (name withheld)"] == {"mentions": 2, "standing": {"ADMITTED": 2}, "withheld": True}
    from state_machines.graphs.emit import observation_graph, serialize
    g = rdflib.Graph().parse(data=serialize(observation_graph(bundle, doc)), format="json-ld")
    nodes = {str(n) for n, _, name in g if str(name) == "Website A (name withheld)"}
    assert len(nodes) == 1 and "/resource/platform/" not in next(iter(nodes))                # stays inside the case


def _case(tmp_path, case, text, acts=()):
    """One statement-of-facts page for ``case`` with offender acts located by their opening words."""
    E.write_page(case, "sof", 1, text, tmp_path)
    page = E.normalize(text)
    docs = [{"doc_id": "sof", "doc_type": "statement_of_facts", "sha256": E.sha256_text(case),
             "pages": [{"pdf_page": 1, "text_method": "text_layer", "page_text_sha256": E.sha256_text(page)}]}]
    (tmp_path / case / "sources.json").write_text(json.dumps({"case_id": case, "documents": docs}), encoding="utf-8")
    passages, events = [], []
    for eid, action, words, end in acts:
        a = page.index(words)
        passages.append({"passage_id": f"q{eid}", "doc_id": "sof", "pdf_page": 1, "char_start": a, "char_end": page.index(end, a) + len(end)})
        events.append({"event_id": eid, "action": action, "support": [{"passage_id": f"q{eid}", "facet": "action", "status": "DIRECT"}],
                       "platform_interactions": [], "affordances": []})
    bundle = {"case_id": case, "documents": docs, "passages": passages, "events": events}
    return O.relate(O.observe(case, tmp_path), bundle, tmp_path), bundle


@pytest.mark.parametrize("text, words, end", [
    # the coder's splitter reads "A." as an initial, so the act's cited passage runs across both sentences
    ("Another user contacted Minor Victim 1 through Website A. The defendant distributed the files to other members in March 2020.",
     "Another user", "2020."),
    ("The defendant told Minor Victim 1 about Website A. Another user then uploaded the files through Kitebox.", "The defendant told", "Kitebox."),
])
def test_a_passage_that_runs_across_sentences_ties_only_what_the_observations_own_sentence_states(tmp_path, text, words, end):
    doc, bundle = _case(tmp_path, "runon", text, [("e1", "DISTRIBUTE_MATERIAL", words, end)])
    assert [r for o in doc["observations"] for r in o["relations"]] == []       # which sentence is the act's own is unknown
    assert all(o["act_passage_runs_on"] for o in doc["observations"] if o["kind"] == "platform")
    assert O.check(doc, tmp_path, bundle) == []


def test_generic_service_descriptions_are_cited_phrases_and_nothing_more(tmp_path):
    def terms(s):
        names = [m.span() for _, pat in O._NAME_PATTERNS for m in pat.finditer(s)] + [m.span() for m in O._WITHHELD.finditer(s)]
        return [t for t, _, _ in O.descriptions_in(s, names)]
    assert terms("He met her on a social media application and an online chat room.") == ["social media application", "online chat room"]
    assert terms("He used peer to peer file sharing software and Social-Networking Sites.") == ["peer-to-peer file-sharing software", "social networking site"]
    for none in ("the forum selection clause", "the dating of the application", "a social media account", "the website", "an application",
                 "a notice on the bulletin board", "an encrypted messaging application he denied", "social media"):
        assert terms(none) in ([], ["messaging application"]) and "encrypted" not in " ".join(terms(none)), none
    assert terms("the forum selection clause and the website and social media") == []
    assert terms("the Kitebox messaging application") == [] and terms("a messaging app called Kitebox") == []   # the named service's own descriptor
    assert terms("the file-sharing website Website A") == []
    text = ("The defendant asked Minor Victim 2 for images through a social media application. "
            "He used a file-sharing website to send them. He also used the Kitebox messaging application.")
    doc, bundle = _case(tmp_path, "generic", text, [("e1", "SOLICIT_IMAGERY", "The defendant asked", "application.")])
    kinds = [(o["kind"], o.get("service_term") or o.get("feature_term") or o.get("platform")) for o in doc["observations"]]
    assert kinds == [("service_description", "social media application"), ("service_description", "file-sharing website"),
                     ("feature", "file-sharing"), ("platform", "Kitebox")]
    assert all(o["relations"] == [] for o in doc["observations"] if o["kind"] == "service_description")   # never tied to an act
    assert O.check(doc, tmp_path, bundle) == []
    bad = copy.deepcopy(doc)
    bad["observations"][0]["service_term"] = "somebody's private site"
    assert any("fixed grammar" in p for p in O.check(bad, tmp_path, bundle))
    bad = copy.deepcopy(doc)
    bad["observations"][0]["relations"] = [{"event_id": "e1", "relationship": "Carried_Out_Through", "cue": "through", "basis": "x"}]
    assert any("tied to an act" in p for p in O.check(bad, tmp_path, bundle))
    from state_machines.observations.table import case_observed
    seen = case_observed(doc)
    assert seen["service_descriptions"] == {"file-sharing website": 1, "social media application": 1}
    assert list(seen["platforms"]) == ["Kitebox"] and seen["features"] == {"distribution_infrastructure": {"file-sharing": 1}}
    from state_machines.graphs.emit import observation_graph, serialize
    g = rdflib.Graph().parse(data=serialize(observation_graph(bundle, doc)), format="json-ld")
    OA = rdflib.Namespace("http://www.w3.org/ns/oa#")
    described = list(g.subjects(OA.motivatedBy, OA.describing))
    assert len(described) == 2
    for a in described:
        body = g.value(a, OA.hasBody)
        assert (body, rdflib.RDF.type, OA.TextualBody) in g and str(g.value(body, rdflib.RDF.value)) in seen["service_descriptions"]
    names = {str(o) for o in g.objects(None, rdflib.URIRef("https://ontology.unifiedcyberontology.org/uco/core/name"))}
    assert names == {"Kitebox"}                                # a description is not a platform entity


def test_queries_keep_cases_and_kinds_apart(tmp_path):
    from state_machines.graphs.emit import observation_graph, serialize
    from state_machines.observations.queries import QUERIES
    ds = rdflib.Dataset()
    for case, text, words in [
        ("case_one", "The defendant sent the files to other members through Website A, he admitted. He had a chat room open.", "The defendant sent"),
        ("case_two", "The defendant posted the images on Website A, she said. The defendant, who was a member of a group chat, asked "
                     "Minor Victim 1 for images through the Kitebox application.", "The defendant posted")]:
        doc, bundle = _case(tmp_path, case, text, [("e1", "DISTRIBUTE_MATERIAL", words, "."), ] + (
            [("e2", "SOLICIT_IMAGERY", "The defendant, who", "application.")] if case == "case_two" else []))
        g = ds.graph(rdflib.URIRef(f"urn:caselinker:pacer:{case}:observations"))
        g.parse(data=serialize(observation_graph(bundle, doc)), format="json-ld")
        ev = ds.graph(rdflib.URIRef(f"urn:caselinker:pacer:{case}:evidence"))
        for e in bundle["events"]:
            ev.add((next(s for s in g.subjects() if str(s).endswith(e["event_id"])), rdflib.URIRef("https://w3id.org/caselinker/trajectory#actionCode"),
                    rdflib.Literal(e["action"])))
    rows = lambda name: [[str(v) for v in r] for r in ds.query(QUERIES[name]["sparql"])]
    assert rows("documented") == [["Kitebox", "1", "1"]]                                   # no placeholder among listed platforms
    assert rows("withheld") == [["case_one", "Website A (name withheld)", "1"], ["case_two", "Website A (name withheld)", "1"]]
    assert rows("described") == [["chat room", "1", "1"]]
    supported = {(r[0], r[4]) for r in rows("supported")}
    assert supported == {("case_one", "Website A (name withheld)"), ("case_two", "Website A (name withheld)"), ("case_two", "Kitebox")}   # not "group chat"
