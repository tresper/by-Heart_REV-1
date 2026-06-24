"""Deterministic crutch-removal policy tests — the §13.4 gradeable artifact (no key).

Proves the escalating ladder on the real Dickinson seed poem: rung 1 removes a
rhyme word while its partner is still visible; rung 2 removes both members so the
rhyme can't bridge; rung 3 removes the anchor content words; rung 4 nears the whole
line. The schedule is deterministic, so this is the falsifiable signature a judge
can run without a model. The signature stanza is "played / done / grain / sun"
(done~sun is a full rhyme).
"""

from __future__ import annotations

import pathlib

from app.curriculum.policy import is_metrically_regular, plan_course
from app.curriculum.types import (
    AdaptationDirective,
    Course,
    line_tokens,
    render_masked_line,
)
from app.prosody.analysis import analyze_poem, scan_line

_DICKINSON = pathlib.Path(
    "corpus/texts/dickinson-because-i-could-not-stop-for-death.txt"
).read_text(encoding="utf-8")
_MAP = analyze_poem(_DICKINSON)
_ANCHORS = _MAP["anchor_candidates"]
_POEM_ID = "dickinson-because-i-could-not-stop-for-death"


def _course() -> Course:
    return plan_course(_MAP, _ANCHORS, _POEM_ID)


def _words(session) -> set[str]:
    return {m.word for m in session.masks}


def _positions(session) -> set[tuple[int, int, int]]:
    return {(m.stanza_idx, m.line_idx, m.word_idx) for m in session.masks}


def test_rung1_removes_later_rhyme_word_with_partner_visible() -> None:
    """Session 0 masks `sun` (later in the pair) but leaves its partner `done`."""
    s0 = _course().sessions[0]
    assert "sun" in _words(s0)
    assert "done" not in _words(s0)  # the visible rhyme partner is still the crutch
    span = next(m for m in s0.masks if m.word == "sun")
    assert span.crutch_class == "rhyme_partner" and span.rung == 1


def test_rung2_removes_both_rhyme_members() -> None:
    """Session 1 adds the partner `done`, so rhyme can no longer bridge."""
    s1 = _course().sessions[1]
    assert {"sun", "done"} <= _words(s1)


def test_rung3_removes_anchor_word_with_metrical_class() -> None:
    """Session 2 newly removes an anchor content word, tagged metrical_regularity."""
    course = _course()
    assert "grain" not in _words(course.sessions[1])  # not yet at rung 2
    s2 = course.sessions[2]
    span = next(m for m in s2.masks if m.word == "grain")
    assert span.crutch_class == "metrical_regularity" and span.rung == 3


def test_rung4_nears_whole_line_and_keeps_punctuation() -> None:
    """The final session masks every alphabetic token; punctuation is untouched."""
    final = _course().sessions[-1]
    by_line: dict[tuple[int, int], set[int]] = {}
    for m in final.masks:
        by_line.setdefault((m.stanza_idx, m.line_idx), set()).add(m.word_idx)
    for stanza in _MAP["stanzas"]:
        for li, line in enumerate(stanza["lines"]):
            masked = by_line.get((stanza["index"], li), set())
            assert masked == set(range(len(line_tokens(line))))  # every word gone
    # A line ending in ',' still ends in ',' after rendering (only words are gapped).
    line = _MAP["stanzas"][2]["lines"][0]
    spans = [m for m in final.masks if m.stanza_idx == 2 and m.line_idx == 0]
    assert render_masked_line(line, spans).rstrip().endswith(",")


def test_masks_are_cumulative() -> None:
    """Each session's masked positions are a superset of the previous session's."""
    sessions = _course().sessions
    for prev, nxt in zip(sessions, sessions[1:]):
        assert _positions(prev) <= _positions(nxt)


def test_word_idx_round_trips_through_the_scanner() -> None:
    """The policy<->renderer token contract: word_idx indexes the same tokens the
    prosody scanner produces, so masks land on the intended words."""
    final = _course().sessions[-1]
    for m in final.masks:
        line = _MAP["stanzas"][m.stanza_idx]["lines"][m.line_idx]
        assert scan_line(line)["words"][m.word_idx]["word"] == m.word


def test_adaptation_directive_strips_the_prioritized_crutch_sooner() -> None:
    """The §13.5 overlay: prioritizing metrical_regularity pulls the anchor `grain`
    from its base rung-3 session (2) into the rung-2 session (1) — stripped sooner."""
    base = _course()
    adapted = plan_course(
        _MAP,
        _ANCHORS,
        _POEM_ID,
        adaptation=AdaptationDirective(prioritized_crutch="metrical_regularity"),
    )
    assert "grain" not in _words(base.sessions[1])  # base: not until rung 3 (session 2)
    assert "grain" in _words(adapted.sessions[1])  # adapted: now at rung 2 (session 1)


def test_no_adaptation_reproduces_the_base_plan() -> None:
    """Cold start (no directive) is byte-for-byte the §13.4 schedule."""
    cold = plan_course(_MAP, _ANCHORS, _POEM_ID, adaptation=None)
    assert cold.to_dict() == _course().to_dict()


def test_none_crutch_directive_is_a_no_op() -> None:
    """A directive naming no real crutch leaves the deterministic plan untouched."""
    adapted = plan_course(
        _MAP,
        _ANCHORS,
        _POEM_ID,
        adaptation=AdaptationDirective(prioritized_crutch="none"),
    )
    assert adapted.to_dict() == _course().to_dict()


def test_course_dict_round_trip() -> None:
    course = _course()
    assert Course.from_dict(course.to_dict()).to_dict() == course.to_dict()


def test_is_metrically_regular_heuristic() -> None:
    assert is_metrically_regular(["01010", "10101", "01010", "10101"])
    assert not is_metrically_regular(["111", "00"])
    assert not is_metrically_regular([])


def test_render_masked_line_sizes_gap_and_preserves_text() -> None:
    """A masked word becomes an equal-length gap; unmasked words/punctuation stay."""
    line = "Their lessons scarcely done;"
    course = _course()
    # session 1 masks `done` (rung 2) in that line; render shows the gap, keeps ';'.
    spans = [
        m
        for m in course.sessions[1].masks
        if line_tokens(line) and m.word == "done"
    ]
    rendered = render_masked_line(line, [s for s in spans])
    assert rendered.startswith("Their lessons scarcely ")
    assert rendered.rstrip().endswith(";")
    assert "____" in rendered  # 'done' -> four underscores
