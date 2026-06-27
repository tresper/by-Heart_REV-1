"""The Scaffolding Coach's deterministic half (§13.6, no key).

Graduated cue withdrawal (§3): the rhyme cue (level 1) and first letter (level 2) are
deterministic facts handed to the coach; the validator clamps the chosen level to 1..3,
forbids regressing below a hint already given, and falls back to the deterministic cue
when the LLM reply is empty/malformed — so scaffolding never returns nothing.
"""

from __future__ import annotations

from app.graph_recall import _candidate_hints, _validate_hint
from app.security.recall_input import contains_word


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


def test_hint_naming_the_answer_is_scrubbed_at_every_level() -> None:
    """A coach swayed into naming the masked word is replaced with a deterministic cue
    that cannot — so answer non-disclosure is structural, not merely instructed."""
    cand = {1: "It rhymes with “done.”", 2: "It starts with “s.”"}
    # Levels 1 and 2: a leaked answer is swapped for the answer-free deterministic cue.
    for level in (1, 2):
        out = _validate_hint(
            {"hint_level": level, "hint": "the answer is sun"}, 0, cand, expected_word="sun"
        )
        assert "sun" not in out["hint"].lower()
    # A level-3 gloss that leaks falls back to the first-letter cue, keeping the level.
    out3 = _validate_hint(
        {"hint_level": 3, "hint": "a sun over the field"},
        prior_level=2,
        candidates=cand,
        expected_word="sun",
    )
    assert out3["hint_level"] == 3
    assert "sun" not in out3["hint"].lower()


def test_answer_guard_is_fail_safe_for_a_non_leaking_gloss() -> None:
    """The scrub only fires on an actual leak: a legitimate gloss is left untouched even
    when the expected word is supplied (no false-trip on an unrelated token)."""
    cand = {1: "r", 2: "f"}
    out = _validate_hint(
        {"hint_level": 3, "hint": "the daytime star"}, 0, cand, expected_word="sun"
    )
    assert out == {"hint_level": 3, "hint": "the daytime star"}


def test_single_letter_answer_is_not_leaked_by_the_first_letter_cue() -> None:
    """A single-letter masked word ("I", masked at rung 4) makes the first-letter cue equal
    the answer, so the scrub must keep falling back to a cue that doesn't name it."""
    cand = {1: "It rhymes with “sky.”", 2: "It starts with “I.”"}  # first-letter cue IS "I"
    out = _validate_hint(
        {"hint_level": 2, "hint": "the word is I"}, 0, cand, expected_word="I"
    )
    assert not contains_word("I", out["hint"])   # the rhyme cue is chosen, not the leaking one


def test_scrub_falls_back_to_a_length_blank_when_every_cue_would_leak() -> None:
    """If even the deterministic cues would name a (single-letter) answer, the scrub returns
    a bare length blank — no word tokens, so it can never disclose the word."""
    cand = {1: "the answer is a", 2: "a"}  # contrived: both cues name the answer "a"
    out = _validate_hint(
        {"hint_level": 3, "hint": "it is a"}, prior_level=2, candidates=cand, expected_word="a"
    )
    assert not contains_word("a", out["hint"])
    assert set(out["hint"]) == {"_"}             # the guaranteed-safe length-blank terminal
