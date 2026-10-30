import json
from pathlib import Path

import pytest

from volunteer_desk.rules import EMERGENCY_TERMS, Route, fold, route

CASES = [
    json.loads(line)
    for line in (Path(__file__).parent / "data" / "routing_cases.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line
]
ROUTED = [c for c in CASES if not c.get("known_gap")]
GAPS = [c for c in CASES if c.get("known_gap")]


def test_set_covers_several_languages_and_all_routes():
    assert {c["lang"] for c in CASES} == {"en", "tr", "de", "fr", "es", "ar"}
    assert {c["expected"] for c in CASES} == {r.value for r in Route}
    assert len(CASES) >= 100


@pytest.mark.parametrize("case", ROUTED, ids=lambda c: f"{c['lang']}-{c['text'][:30]}")
def test_routing(case):
    assert route(case["text"]).route.value == case["expected"]


@pytest.mark.parametrize("case", GAPS, ids=lambda c: f"{c['lang']}-{c['text'][:30]}")
def test_known_gaps_are_still_gaps(case):
    # These pin the README's stated limits. If one starts passing, move it to the routed set.
    assert route(case["text"]).route.value != case["expected"]


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("YANGIN", "yangin"),
        ("yangın", "yangin"),
        ("Yangin", "yangin"),
        ("İSTANBUL", "istanbul"),
        ("NIÑO  perdido", "nino perdido"),
        ("Fußgänger", "fussganger"),
        ("can’t", "can't"),
        ("إسعاف", "اسعاف"),
    ],
)
def test_fold(raw, folded):
    assert fold(raw) == folded


@pytest.mark.parametrize("text", ["YANGIN VAR", "yangın var", "yangin var", "Yangında kaldık"])
def test_turkish_emergency_survives_case_and_missing_diacritics(text):
    assert route(text).route is Route.EMERGENCY


def test_turkish_acil_does_not_match_open_verb():
    # Regression: "açılıyor" folds to acil-; a prefix rule routed door times to the safety lead.
    assert route("Kapılar saat kaçta açılıyor?").route is Route.MODEL
    assert route("Acil yardım lazım").route is Route.EMERGENCY


@pytest.mark.parametrize("text", ["The firewall is down", "He was fired", "firefly", "Gunther"])
def test_word_boundaries(text):
    assert route(text).route is Route.MODEL


def test_most_serious_route_wins_and_all_hits_are_kept():
    decision = route("My badge is on fire, urgent")
    assert decision.route is Route.EMERGENCY
    assert {h.route for h in decision.hits} == {Route.EMERGENCY, Route.URGENT, Route.PERSONAL}
    assert decision.language == "en"


def test_contact_details_never_go_to_the_model():
    assert route("yaz bana: someone@example.com").route is Route.PERSONAL
    assert route("Bana 0555 000 00 00 yazın").route is Route.PERSONAL
    assert route("Hall 12 opens at 09:00").route is Route.MODEL


def test_every_emergency_language_has_terms():
    assert all(len(terms) >= 20 for terms in EMERGENCY_TERMS.values())
