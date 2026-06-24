"""Course data shapes for the crutch-removal curriculum (blueprint §4/§13.4).

The Course is the Build Pipeline's product: a multi-session masking schedule whose
difficulty escalates by CRUTCH REMOVAL — stripping the prosodic cue a learner leans
on — plus a per-session, human-readable Deletion Rationale. These are plain frozen
dataclasses (matching ``ProvenanceResult`` / ``Pronunciation``) with dict
(de)serialization so the node can emit JSON-friendly output that the Recall graph
reconstructs and renders.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

# Which prosodic cue a masked word leans on (blueprint §4 step 2). "none" = no
# strong crutch (a short, low-information word with nothing to lean on).
CrutchClass = Literal[
    "rhyme_partner", "metrical_regularity", "syntactic_momentum", "none"
]

# The policy<->renderer contract: a line's alphabetic tokens are indexed under THIS
# regex (identical to app.prosody.analysis's), so ``word_idx`` always lands on the
# exact word the policy chose to mask. A unit test cross-checks it against the
# prosody scanner to guard against drift.
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


@dataclass(frozen=True)
class AdaptationDirective:
    """The adaptive overlay's single instruction to the deletion ladder (§4 step 4).

    This is the *only* thing the LLM contributes to the schedule: which crutch class
    the learner most leans on, so the policy strips it sooner. The phonetic ground
    truth and the concrete masks stay deterministic — the directive merely re-orders
    which cue goes first (blueprint §8: an LLM proposal the policy validates and
    applies, never trusted to author masks itself). ``diagnosis`` is the LLM's short
    reason; ``target_stanza`` optionally narrows the adaptation to one stanza when the
    pattern is localized (``None`` = poem-wide).
    """

    prioritized_crutch: CrutchClass
    diagnosis: str = ""
    target_stanza: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prioritized_crutch": self.prioritized_crutch,
            "diagnosis": self.diagnosis,
            "target_stanza": self.target_stanza,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AdaptationDirective:
        return cls(
            prioritized_crutch=d["prioritized_crutch"],
            diagnosis=d.get("diagnosis", ""),
            target_stanza=d.get("target_stanza"),
        )


def line_tokens(line: str) -> list[str]:
    """The alphabetic tokens of a line, in order (the maskable words)."""
    return _WORD_RE.findall(line)


@dataclass(frozen=True)
class MaskedSpan:
    """One masked word in the schedule, tagged with why it is being removed."""

    stanza_idx: int
    line_idx: int  # index of the line WITHIN its stanza (matches analyze_poem)
    word_idx: int  # token index within the line (see ``_WORD_RE``)
    word: str  # surface form — lets the renderer size the gap and the grader compare
    crutch_class: CrutchClass
    rung: int  # 1..4: the ladder rung that first introduced this mask

    def to_dict(self) -> dict[str, Any]:
        return {
            "stanza_idx": self.stanza_idx,
            "line_idx": self.line_idx,
            "word_idx": self.word_idx,
            "word": self.word,
            "crutch_class": self.crutch_class,
            "rung": self.rung,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MaskedSpan:
        return cls(
            stanza_idx=d["stanza_idx"],
            line_idx=d["line_idx"],
            word_idx=d["word_idx"],
            word=d["word"],
            crutch_class=d["crutch_class"],
            rung=d["rung"],
        )


@dataclass(frozen=True)
class SessionPlan:
    """One study session: the cumulative set of words masked, and the rationale."""

    index: int  # 0-based session number
    rung: int  # the dominant crutch-removal rung this session reaches
    masks: tuple[MaskedSpan, ...]
    rationale: str = ""  # the LLM Deletion Rationale; "" straight from the policy

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "rung": self.rung,
            "masks": [m.to_dict() for m in self.masks],
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SessionPlan:
        return cls(
            index=d["index"],
            rung=d["rung"],
            masks=tuple(MaskedSpan.from_dict(m) for m in d["masks"]),
            rationale=d.get("rationale", ""),
        )

    def with_rationale(self, rationale: str) -> SessionPlan:
        """Return a copy with the Deletion Rationale filled in (dataclass is frozen)."""
        return SessionPlan(self.index, self.rung, self.masks, rationale)


@dataclass(frozen=True)
class Course:
    """The full multi-session memorization course for one poem."""

    poem_id: str
    stanza_count: int
    sessions: tuple[SessionPlan, ...]
    rungs_used: tuple[int, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "poem_id": self.poem_id,
            "stanza_count": self.stanza_count,
            "sessions": [s.to_dict() for s in self.sessions],
            "rungs_used": list(self.rungs_used),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Course:
        return cls(
            poem_id=d["poem_id"],
            stanza_count=d["stanza_count"],
            sessions=tuple(SessionPlan.from_dict(s) for s in d["sessions"]),
            rungs_used=tuple(d.get("rungs_used", [])),
        )


def render_masked_line(line: str, masks: Iterable[MaskedSpan]) -> str:
    """Render a line with the session's masks applied (the Recall graph's view).

    Masked tokens become an underscore gap sized to the hidden word; everything
    else — punctuation, spacing, unmasked words — is preserved verbatim, so the
    "near-whole-line with only scaffolding punctuation" rung reads correctly.
    """
    masked_idx = {m.word_idx for m in masks}
    out: list[str] = []
    last = 0
    for i, match in enumerate(_WORD_RE.finditer(line)):
        out.append(line[last : match.start()])
        token = match.group()
        out.append("_" * len(token) if i in masked_idx else token)
        last = match.end()
    out.append(line[last:])
    return "".join(out)
