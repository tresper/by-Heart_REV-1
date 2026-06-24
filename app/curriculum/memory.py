"""Learner Memory + deterministic pattern aggregation (blueprint §4/§13.5).

This is the substrate for the adaptation "money shot": a per-learner record of
recall attempts, reduced to a falsifiable **crutch-dependence profile** that the
Architect (``curriculum_plan``) reasons over to decide which cue to strip next.

Two halves, deliberately split:

- ``LearnerMemory`` — a tiny JSON-backed append log of ``Attempt`` rows. JSON (not
  SQLite) is chosen because it is the simplest thing to *demo*: human-readable, no
  schema/migration, and it matches the ``to_dict``/``from_dict`` convention used
  throughout the package. Minimal-PII (§8): the only identity stored is an opaque
  ``learner_id`` — no real names. The store lives under a gitignored runtime dir so
  learner data never reaches the public repo.
- ``profile_from_attempts`` — a **deterministic** reduction ("diagnose the pattern").
  It counts, per crutch class, how often the learner *succeeded while leaning on it*
  (``relied_on``) and *missed at its positions* (``missed_at``), and ranks the
  classes by how much the learner leans on each. The counts are ground truth the LLM
  reads; the LLM never invents them. This keeps the §4-step-4 "infers/chooses" an
  LLM act while its evidence stays testable without a key.

The crutch-dependence *tag* that makes ``relied_on`` meaningful is emitted by
``adjudicate`` (§13.6, not yet built); until then ``crutch_dependence`` defaults to
``"none"`` and the profile is dominated by ``missed_at``. The machinery here is
exercised now on seeded history; the live loop closes in §13.6.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

from app.curriculum.types import CrutchClass

# The crutch classes that name a *real* cue to strip (everything but "none"), in a
# stable tie-break order. Ranking and aggregation ignore "none": there is no support
# to remove from a word the learner never leaned on.
_REAL_CRUTCHES: tuple[CrutchClass, ...] = tuple(
    c for c in get_args(CrutchClass) if c != "none"
)

# A correct recall (the learner produced the line) vs. a failure to. "variant" is an
# acceptable alternative wording, so it counts as success; "near_miss"/"miss" do not.
_SUCCESS_OUTCOMES = frozenset({"hit", "variant"})

# var/ is already gitignored; BY_HEART_STATE_DIR overrides it for tests/deploys.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_STATE_DIR = _REPO_ROOT / "var"
_STORE_FILENAME = "learner_memory.json"


@dataclass(frozen=True)
class Attempt:
    """One recorded recall attempt at one masked word.

    ``crutch_class`` is the cue the *word* structurally leans on (from its
    ``MaskedSpan``); ``crutch_dependence`` is the Adjudicator's judgment of the cue
    the *learner's recall* actually relied on (§13.6 — e.g. "got 'sun' only because
    'done' was visible"). They differ, and the profile uses each differently.
    """

    learner_id: str
    poem_id: str
    session_index: int
    stanza_idx: int
    line_idx: int
    word_idx: int
    word: str
    crutch_class: CrutchClass
    outcome: str  # hit | near_miss | variant | miss
    crutch_dependence: CrutchClass = "none"
    ts: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "learner_id": self.learner_id,
            "poem_id": self.poem_id,
            "session_index": self.session_index,
            "stanza_idx": self.stanza_idx,
            "line_idx": self.line_idx,
            "word_idx": self.word_idx,
            "word": self.word,
            "crutch_class": self.crutch_class,
            "outcome": self.outcome,
            "crutch_dependence": self.crutch_dependence,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Attempt:
        return cls(
            learner_id=d["learner_id"],
            poem_id=d["poem_id"],
            session_index=d["session_index"],
            stanza_idx=d["stanza_idx"],
            line_idx=d["line_idx"],
            word_idx=d["word_idx"],
            word=d["word"],
            crutch_class=d["crutch_class"],
            outcome=d["outcome"],
            crutch_dependence=d.get("crutch_dependence", "none"),
            ts=d.get("ts", 0.0),
        )


class LearnerMemory:
    """A JSON append log of attempts, keyed by ``(learner_id, poem_id)``.

    Tolerant by design: a missing or empty store reads as "no history" (cold start),
    so the very first session never errors. Writes are atomic (temp file + replace)
    so a crash mid-write cannot corrupt prior attempts.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else _default_store_path()

    def _load(self) -> list[Attempt]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        data = json.loads(raw) if raw.strip() else {}
        return [Attempt.from_dict(a) for a in data.get("attempts", [])]

    def _save(self, attempts: list[Attempt]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"attempts": [a.to_dict() for a in attempts]}, indent=2, ensure_ascii=False
        )
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)

    def record(self, attempt: Attempt) -> None:
        """Append one attempt, stamping ``ts`` if the caller left it unset."""
        if not attempt.ts:
            attempt = Attempt.from_dict({**attempt.to_dict(), "ts": time.time()})
        attempts = self._load()
        attempts.append(attempt)
        self._save(attempts)

    def attempts_for(self, learner_id: str, poem_id: str) -> list[Attempt]:
        """Every recorded attempt for one learner on one poem, in insertion order."""
        return [
            a
            for a in self._load()
            if a.learner_id == learner_id and a.poem_id == poem_id
        ]


@dataclass(frozen=True)
class CrutchProfile:
    """The learner's crutch-dependence pattern for one poem (the LLM's evidence).

    ``by_class`` maps each real crutch to ``{"relied_on", "missed_at"}`` counts;
    ``dominant`` ranks the classes by how much the learner leans on each (most first),
    so ``dominant[0]`` is the cue the adaptive overlay should strip next.
    """

    poem_id: str
    by_class: dict[str, dict[str, int]] = field(default_factory=dict)
    dominant: list[str] = field(default_factory=list)
    total_attempts: int = 0

    def is_empty(self) -> bool:
        return self.total_attempts == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "poem_id": self.poem_id,
            "by_class": self.by_class,
            "dominant": self.dominant,
            "total_attempts": self.total_attempts,
        }


def profile_from_attempts(poem_id: str, attempts: list[Attempt]) -> CrutchProfile:
    """Reduce raw attempts to a crutch-dependence profile (deterministic).

    Per real crutch class: ``relied_on`` counts *successful* recalls the learner
    leaned on that cue for (the Adjudicator's dependence tag); ``missed_at`` counts
    *failed* recalls at words of that class. Classes are ranked by the sum of the two
    (lean signal), tie-broken by ``relied_on`` then the stable class order, and only
    classes with a non-zero signal appear in ``dominant`` — so an empty or
    no-signal history yields no adaptation and the §13.4 base plan stands.
    """
    by_class: dict[str, dict[str, int]] = {
        c: {"relied_on": 0, "missed_at": 0} for c in _REAL_CRUTCHES
    }
    for a in attempts:
        succeeded = a.outcome in _SUCCESS_OUTCOMES
        if succeeded and a.crutch_dependence in by_class:
            by_class[a.crutch_dependence]["relied_on"] += 1
        elif not succeeded and a.crutch_class in by_class:
            by_class[a.crutch_class]["missed_at"] += 1

    order = {c: i for i, c in enumerate(_REAL_CRUTCHES)}
    scored = [
        (c, v["relied_on"] + v["missed_at"], v["relied_on"])
        for c, v in by_class.items()
    ]
    dominant = [
        c
        for c, total, _ in sorted(
            scored, key=lambda t: (-t[1], -t[2], order[t[0]])
        )
        if total > 0
    ]
    return CrutchProfile(
        poem_id=poem_id,
        by_class=by_class,
        dominant=dominant,
        total_attempts=len(attempts),
    )


def _default_store_path() -> Path:
    """``$BY_HEART_STATE_DIR/learner_memory.json``, else under the gitignored ``var/``."""
    base = os.environ.get("BY_HEART_STATE_DIR")
    root = Path(base) if base else _DEFAULT_STATE_DIR
    return root / _STORE_FILENAME
