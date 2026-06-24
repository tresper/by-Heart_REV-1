"""Learner Memory store + the deterministic crutch-dependence profile (§13.5, no key).

These are the falsifiable half of the adaptation: a JSON append log and a pure
reduction over it. A learner who keeps nailing rhyme words only because the partner
was still visible should surface ``rhyme_partner`` as the cue to strip next — the
signal the LLM Architect then acts on. No model runs here, so this needs no key.
"""

from __future__ import annotations

from app.curriculum.memory import Attempt, LearnerMemory, profile_from_attempts


def _attempt(**kw) -> Attempt:
    base = dict(
        learner_id="L1",
        poem_id="dickinson",
        session_index=0,
        stanza_idx=0,
        line_idx=0,
        word_idx=3,
        word="sun",
        crutch_class="rhyme_partner",
        outcome="hit",
        crutch_dependence="rhyme_partner",
    )
    base.update(kw)
    return Attempt(**base)


def test_store_round_trips_and_filters_by_learner_and_poem(tmp_path) -> None:
    store = LearnerMemory(tmp_path / "mem.json")
    store.record(_attempt(word="sun"))
    store.record(_attempt(word="done", learner_id="L2"))  # other learner
    store.record(_attempt(word="grain", poem_id="other"))  # other poem
    got = store.attempts_for("L1", "dickinson")
    assert [a.word for a in got] == ["sun"]


def test_record_stamps_a_timestamp(tmp_path) -> None:
    store = LearnerMemory(tmp_path / "mem.json")
    store.record(_attempt(ts=0.0))
    assert store.attempts_for("L1", "dickinson")[0].ts > 0


def test_missing_store_reads_as_cold_start(tmp_path) -> None:
    store = LearnerMemory(tmp_path / "absent.json")
    assert store.attempts_for("L1", "dickinson") == []


def test_profile_ranks_the_relied_on_crutch_first() -> None:
    """relied_on (success leaning on a cue) + missed_at (failure at it) rank the cues."""
    attempts = [
        _attempt(crutch_dependence="rhyme_partner"),
        _attempt(crutch_dependence="rhyme_partner"),
        _attempt(crutch_dependence="rhyme_partner"),
        _attempt(outcome="miss", crutch_class="metrical_regularity", crutch_dependence="none"),
    ]
    profile = profile_from_attempts("dickinson", attempts)
    assert profile.dominant[0] == "rhyme_partner"
    assert profile.by_class["rhyme_partner"]["relied_on"] == 3
    assert profile.by_class["metrical_regularity"]["missed_at"] == 1
    assert profile.total_attempts == 4


def test_empty_history_yields_an_empty_profile() -> None:
    profile = profile_from_attempts("dickinson", [])
    assert profile.is_empty()
    assert profile.dominant == []


def test_none_dependence_is_not_a_strippable_cue() -> None:
    """A correct recall that leaned on no cue contributes no lean signal."""
    profile = profile_from_attempts(
        "dickinson", [_attempt(outcome="hit", crutch_dependence="none")]
    )
    assert profile.dominant == []  # nothing to strip
    assert profile.total_attempts == 1
