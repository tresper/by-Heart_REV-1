"""memory_update's attempt extraction (§13.5) — tolerant of the §13.6 adjudicate stub.

``_attempt_from`` is the seam between Graph B and the Learner Memory store: a
well-formed adjudication becomes a recorded ``Attempt``; the current stub payload
(no word/position) records nothing, so a stub run never poisons the store with noise.
Pure (no I/O), so it asserts the contract without touching the JSON file.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph_recall import _attempt_from


def _ctx(**state) -> SimpleNamespace:
    return SimpleNamespace(state=state)


def test_stub_payload_records_nothing() -> None:
    payload = {"todo": "advance not implemented", "adjudication": {"recall": "..."}}
    assert _attempt_from(_ctx(poem_id="dickinson"), payload) is None


def test_well_formed_attempt_is_extracted() -> None:
    payload = {
        "word": "sun",
        "stanza_idx": 0,
        "line_idx": 0,
        "word_idx": 3,
        "crutch_class": "rhyme_partner",
        "outcome": "hit",
        "crutch_dependence": "rhyme_partner",
        "session_index": 1,
    }
    a = _attempt_from(_ctx(poem_id="dickinson", learner_id="L9"), payload)
    assert a is not None
    assert (a.learner_id, a.poem_id, a.word, a.outcome) == ("L9", "dickinson", "sun", "hit")
    assert a.crutch_dependence == "rhyme_partner"


def test_attempt_nested_under_attempt_key_with_defaults() -> None:
    payload = {"attempt": {"word": "done", "stanza_idx": 1, "line_idx": 2, "word_idx": 0}}
    a = _attempt_from(_ctx(poem_id="p"), payload)
    assert a is not None and a.word == "done"
    assert a.outcome == "miss" and a.crutch_dependence == "none"  # safe defaults
