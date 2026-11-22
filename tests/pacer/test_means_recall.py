"""The recall lexicon and the dependency instrument detector, both off by default."""
from __future__ import annotations

import pytest

from state_machines.coding.coreference import make_inventory
from state_machines.observations.means_parse import compare, instrument_means, refuse_corpus_path
from state_machines.observations.observe import _means, features_in

PAREN = "The defendant utilized virtual private networks (VPNs) to conceal his IP address."
THEY = "The defendant opened an account and they sent files via an encrypted channel."
ON = "The defendant and the facilitator communicated on an encrypted messaging application."
TOR = "Tor is a browser that routes packets through virtual private networks."
WINDOW = "He used the disappearing-message feature on Kitebox to ask Minor Victim 1 for more images."


def _tok(text, start, head, deprel, pos=""):
    return {"text": text, "start": start, "end": start + len(text), "head": head, "deprel": deprel, "pos": pos}


def _paren_tokens():
    s = PAREN
    # utilized is the verb; networks is its object; VPNs is an apposition inside parentheses.
    i_util = s.index("utilized")
    i_net = s.index("networks")
    i_vpn = s.index("VPNs")
    i_def = s.index("defendant")
    return [
        _tok("defendant", i_def, 1, "nsubj"),
        _tok("utilized", i_util, 1, "ROOT", "VERB"),
        _tok("networks", i_net, 1, "dobj"),
        _tok("VPNs", i_vpn, 2, "appos"),
    ]


def _they_tokens():
    s = THEY
    return [
        _tok("they", s.index("they"), 1, "nsubj"),
        _tok("sent", s.index("sent"), 1, "ROOT", "VERB"),
        _tok("via", s.index("via"), 1, "prep"),
        _tok("encrypted", s.index("encrypted"), 4, "amod"),
        _tok("channel", s.index("channel"), 2, "pobj"),
    ]


def _tor_tokens():
    s = TOR
    return [
        _tok("Tor", s.index("Tor"), 1, "nsubj"),
        _tok("is", s.index("is"), 1, "ROOT", "VERB"),
        _tok("routes", s.index("routes"), 1, "relcl", "VERB"),
        _tok("through", s.index("through"), 2, "prep"),
        _tok("networks", s.index("networks"), 3, "pobj"),
    ]


def test_default_rule_does_not_gain_the_recall_phrases_or_the_on_cue(monkeypatch):
    monkeypatch.delenv("CASELINKER_MEANS_RULE", raising=False)
    monkeypatch.delenv("CASELINKER_MEANS_PARSER", raising=False)
    monkeypatch.delenv("CASELINKER_COREFERENCE", raising=False)
    # The spelled-out form is absent from the phrase list, so the rule emits nothing.
    # Handing that phrase to the word window still ties "utilized"; that window is unchanged.
    assert features_in(PAREN) == []
    assert _means("feature", PAREN, {"feature_term": "virtual private networks"}) == ("Supports_Action", "utilized")
    assert _means("feature", ON, {"feature_term": "encrypted"}) is None
    assert _means("feature", WINDOW, {"feature_term": "disappearing-message"}) == ("Supports_Action", "used")
    assert instrument_means(PAREN, {"feature_term": "VPNs"}, _paren_tokens()) is None


def test_parenthetical_vpn_is_an_instrument_when_the_parser_is_on(monkeypatch):
    monkeypatch.setenv("CASELINKER_MEANS_PARSER", "dep")
    hit = instrument_means(PAREN, {"feature_term": "VPNs"}, _paren_tokens(), actors=make_inventory())
    assert hit["method"] == "dep"
    assert hit["crossed_parentheses"] is True
    assert hit["cue"] == "utilized"
    both = compare(PAREN, {"feature_term": "virtual private networks"}, _paren_tokens(), actors=make_inventory())
    assert both["window"] == ("Supports_Action", "utilized")


def test_they_is_the_offender_only_when_coreference_resolves_it(monkeypatch):
    monkeypatch.setenv("CASELINKER_MEANS_PARSER", "dep")
    monkeypatch.delenv("CASELINKER_COREFERENCE", raising=False)
    actors = make_inventory()
    assert instrument_means(THEY, {"feature_term": "encrypted"}, _they_tokens(), actors=actors) is None
    monkeypatch.setenv("CASELINKER_COREFERENCE", "1")
    hit = instrument_means(THEY, {"feature_term": "encrypted"}, _they_tokens(), actors=actors)
    assert hit["cue"] == "via"
    assert hit["method"] == "dep"


def test_on_is_a_feature_cue_only_under_the_recall_rule(monkeypatch):
    monkeypatch.delenv("CASELINKER_MEANS_RULE", raising=False)
    assert _means("feature", ON, {"feature_term": "encrypted"}) is None
    monkeypatch.setenv("CASELINKER_MEANS_RULE", "1.4-recall")
    phrases = [phrase for _, phrase, _, _ in features_in(PAREN)]
    assert phrases == ["virtual private networks", "VPNs"]
    assert _means("feature", ON, {"feature_term": "encrypted"}) == ("Supports_Action", "on")


def test_a_tor_explainer_is_not_an_act(monkeypatch):
    monkeypatch.setenv("CASELINKER_MEANS_RULE", "1.4-recall")
    monkeypatch.setenv("CASELINKER_MEANS_PARSER", "dep")
    assert "virtual private networks" in [phrase for _, phrase, _, _ in features_in(TOR)]
    assert _means("feature", TOR, {"feature_term": "virtual private networks"}) is None
    assert instrument_means(TOR, {"feature_term": "virtual private networks"}, _tor_tokens(),
                            actors=make_inventory()) is None


def test_the_detector_refuses_a_corpus_path():
    with pytest.raises(SystemExit):
        refuse_corpus_path("state_machines/data/pacer-v1")
    with pytest.raises(SystemExit):
        refuse_corpus_path("local/pacer_text")
    with pytest.raises(SystemExit):
        refuse_corpus_path("caselinker_oxigraph/store")
