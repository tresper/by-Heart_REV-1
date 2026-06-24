"""The Scaffolding Coach's deterministic half (§13.6, no key).

Graduated cue withdrawal (§3): the rhyme cue (level 1) and first letter (level 2) are
deterministic facts handed to the coach; the validator clamps the chosen level to 1..3,
forbids regressing below a hint already given, and falls back to the deterministic cue
when the LLM reply is empty/malformed — so scaffolding never returns nothing.
"""

from __future__ import annotations

from app.graph_recall import _candidate_hints, _validate_hint


def test_candidate_hints_surface_rhyme_partner_and_first_letter() -> None:
    hints = _candidate_hints({"word": "sun", "cues": {"partner_word": "done"}})
    assert "done" in hints[1]
    assert "starts with" in hints[2] and "s" in hints[2]


def test_candidate_rhyme_cue_degrades_without_a_partner() -> None:
    hints = _candidate_hints({"word": "grain", "cues": {"partner_word": ""}})
    assert "rhyme" in hints[1].lower()


def test_malformed_reply_falls_back_to_the_next_level_cue() -> None:
    cand = {1: "rhyme cue", 2: "letter cue"}
    out = _validate_hint(None, prior_level=0, candidates=cand)
    assert out == {"hint_level": 1, "hint": "rhyme cue"}


def test_level_is_clamped_to_three() -> None:
    cand = {1: "r", 2: "f"}
    assert _validate_hint({"hint_level": 99, "hint": "x"}, 0, cand)["hint_level"] == 3


def test_no_regression_below_an_already_given_hint() -> None:
    """A learner already shown level 2 gets at least level 3 next — hints only escalate."""
    cand = {1: "r", 2: "f"}
    assert _validate_hint({"hint_level": 1, "hint": "x"}, prior_level=2, candidates=cand)["hint_level"] == 3


def test_empty_level1_hint_uses_the_deterministic_cue() -> None:
    cand = {1: "rhyme cue", 2: "letter cue"}
    out = _validate_hint({"hint_level": 1, "hint": ""}, 0, cand)
    assert out["hint"] == "rhyme cue"


def test_authored_gloss_is_preserved_at_level_three() -> None:
    cand = {1: "r", 2: "f"}
    out = _validate_hint({"hint_level": 3, "hint": "the daytime star"}, 0, cand)
    assert out == {"hint_level": 3, "hint": "the daytime star"}
