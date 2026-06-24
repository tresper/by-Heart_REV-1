"""The Adjudicator's deterministic half (§13.6, no key) — the gradeable artifact.

The LLM grades semantically (key-gated, tested in the integration suite); here we prove
the ground-truth machinery it is constrained by: which cues were still VISIBLE for a
masked word, and the validator that keeps the crutch-dependence tag honest (a cue you
could not have leaned on, or a recall you missed, leans on nothing). All key-free.

The signature stanza is Dickinson's "played / done / grain / sun" (done~sun is a full
rhyme): at session 0 only the later rhyme word `sun` is masked, so its partner `done`
is still visible — the learner can lean on the rhyme. By session 1 both are masked, so
that crutch is gone. The validator must reflect exactly that shift.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

from app.curriculum.policy import plan_course
from app.graph_recall import (
    _available_cues,
    _route_for,
    _target_context,
    _validate_adjudication,
    _visible_cues,
)
from app.prosody.analysis import analyze_poem

_DICKINSON = pathlib.Path(
    "corpus/texts/dickinson-because-i-could-not-stop-for-death.txt"
).read_text(encoding="utf-8")
_MAP = analyze_poem(_DICKINSON)
_ANCHORS = _MAP["anchor_candidates"]
_POEM_ID = "dickinson-because-i-could-not-stop-for-death"
_COURSE = plan_course(_MAP, _ANCHORS, _POEM_ID)


def _ctx(**state) -> SimpleNamespace:
    return SimpleNamespace(state=state)


def _span(session_index: int, word: str):
    return next(m for m in _COURSE.sessions[session_index].masks if m.word == word)


def _target_state(session_index: int, word: str) -> SimpleNamespace:
    m = _span(session_index, word)
    return _ctx(
        session_index=session_index,
        target={"stanza_idx": m.stanza_idx, "line_idx": m.line_idx, "word_idx": m.word_idx},
    )


def test_rhyme_partner_is_visible_at_rung1() -> None:
    """Session 0 masks `sun` only; its partner `done` is unmasked → rhyme cue available."""
    ctx = _target_state(0, "sun")
    context = _target_context(_COURSE, _MAP, ctx)
    assert context["word"] == "sun"
    assert context["crutch_class"] == "rhyme_partner"
    assert context["cues"]["rhyme_partner_visible"] is True
    assert context["cues"]["partner_word"].lower() == "done"
    assert "rhyme_partner" in context["available_cues"]


def test_rhyme_partner_hidden_once_both_are_masked() -> None:
    """Session 1 masks both `sun` and `done` → the rhyme can no longer bridge."""
    context = _target_context(_COURSE, _MAP, _target_state(1, "sun"))
    assert context["cues"]["rhyme_partner_visible"] is False
    assert "rhyme_partner" not in context["available_cues"]


def test_default_target_is_a_word_this_session_adds() -> None:
    """With no explicit target, the quiz word is one newly removed at this session's rung."""
    context = _target_context(_COURSE, _MAP, _ctx(session_index=0))
    span = _span(0, context["word"])
    assert span.rung == _COURSE.sessions[0].rung


def test_visible_cues_flags_stopword_momentum() -> None:
    target = {"stanza_idx": 0, "line_idx": 0, "word_idx": 0, "word": "the", "crutch_class": "none"}
    cues = _visible_cues(target, set(), _MAP)
    assert cues["is_stopword"] is True
    assert "syntactic_momentum" in _available_cues(target, cues)


def test_validate_keeps_an_available_dependence_on_success() -> None:
    tc = {"available_cues": ["rhyme_partner"]}
    out = _validate_adjudication({"outcome": "hit", "crutch_dependence": "rhyme_partner"}, tc)
    assert out == {"outcome": "hit", "crutch_dependence": "rhyme_partner", "note": ""}


def test_validate_clears_an_unavailable_dependence() -> None:
    """§8 fail-safe: you cannot have leaned on a cue that was not there for this word."""
    tc = {"available_cues": ["rhyme_partner"]}
    out = _validate_adjudication({"outcome": "variant", "crutch_dependence": "metrical_regularity"}, tc)
    assert out["crutch_dependence"] == "none"


def test_validate_clears_dependence_on_a_miss() -> None:
    tc = {"available_cues": ["rhyme_partner"]}
    out = _validate_adjudication({"outcome": "miss", "crutch_dependence": "rhyme_partner"}, tc)
    assert out["crutch_dependence"] == "none"


def test_validate_coerces_unknown_or_malformed_to_miss() -> None:
    tc = {"available_cues": []}
    assert _validate_adjudication({"outcome": "banana"}, tc)["outcome"] == "miss"
    bad = _validate_adjudication(None, tc)
    assert bad == {"outcome": "miss", "crutch_dependence": "none", "note": ""}


def test_outcome_routes_advance_or_scaffold() -> None:
    assert _route_for("hit") == "advance"
    assert _route_for("variant") == "advance"
    assert _route_for("near_miss") == "scaffold"
    assert _route_for("miss") == "scaffold"
