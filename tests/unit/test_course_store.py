"""The Course store (§13.6, no key) — the §4 "Course ──► Session/Memory store" seam.

Graph A persists the per-learner adapted Course; Graph B loads it to know what to mask.
A round-trip must be lossless, and a missing file must read as "no course yet" (None) so
Graph B never errors before Graph A has run.
"""

from __future__ import annotations

import pathlib

from app.curriculum.memory import load_course, save_course
from app.curriculum.policy import plan_course
from app.prosody.analysis import analyze_poem

_DICKINSON = pathlib.Path(
    "corpus/texts/dickinson-because-i-could-not-stop-for-death.txt"
).read_text(encoding="utf-8")
_MAP = analyze_poem(_DICKINSON)
_POEM_ID = "dickinson-because-i-could-not-stop-for-death"


def test_course_round_trips_through_the_store(tmp_path) -> None:
    course = plan_course(_MAP, _MAP["anchor_candidates"], _POEM_ID)
    path = tmp_path / "course.json"
    save_course(course, "L1", path=path)
    loaded = load_course(_POEM_ID, "L1", path=path)
    assert loaded is not None
    assert loaded.to_dict() == course.to_dict()


def test_missing_course_reads_as_none(tmp_path) -> None:
    assert load_course(_POEM_ID, "L1", path=tmp_path / "absent.json") is None
