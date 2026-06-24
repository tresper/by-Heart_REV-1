"""Graph B — the Recall Session Loop (blueprint §4), human-in-the-loop.

    [present_masked_line] -> (RequestInput: learner recall) -> [adjudicate]
        -> advance ----> [memory_update]
        -> scaffold --> [memory_update]
    ...looping per attempt via RequestInput pause/resume.

All nodes here are STUBS for this phase — the real grading, scaffolding, and
crutch-dependence tagging arrive in §13.5–13.6. The graph exists now so the
two-graph architecture (§4) is in place and importable. The human-in-the-loop
pause is modeled with ``RequestInput`` (yielded from ``present_masked_line``),
which is the idiomatic ADK 2.0 mechanism: the run pauses for the learner's typed
recall and resumes with it.
"""

from __future__ import annotations

from typing import Any

from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Workflow, node

from app.curriculum.memory import Attempt, LearnerMemory


@node(name="present_masked_line")
async def present_masked_line(ctx, node_input: Any):
    """STUB. Will present the line with crutch-removal masking applied, then
    pause for the learner's recall. Yields ``RequestInput`` (human-in-the-loop).

    When wired (§13.6) this renders a ``SessionPlan`` from the Course via
    ``app.curriculum.types.render_masked_line`` — masks land on words by the shared
    token-index contract — so the Build graph's schedule drives what the learner sees.
    """
    yield RequestInput(message="Recall the masked line:")


@node(name="adjudicate")
async def adjudicate(ctx, node_input: Any):
    """STUB (§13.6). Will grade semantically (hit / near-miss / variant / miss),
    never a string compare, and emit a crutch-dependence tag. Routes advance |
    scaffold; defaults to scaffold (fail safe — assume more support is needed)."""
    yield Event(
        output={"todo": "adjudicate not implemented", "recall": node_input},
        route="scaffold",
    )


@node(name="advance")
async def advance(ctx, node_input: Any):
    """STUB. Learner mastered this line; advance the schedule. Passthrough."""
    yield Event(output={"todo": "advance not implemented", "adjudication": node_input})


@node(name="scaffold")
async def scaffold(ctx, node_input: Any):
    """STUB (§13.6). Will give the minimum hint: rhyme cue -> first letter ->
    gloss, based on where the learner stalled. Passthrough."""
    yield Event(output={"todo": "scaffold not implemented", "adjudication": node_input})


def _attempt_from(ctx, node_input: Any) -> Attempt | None:
    """Build an ``Attempt`` from the adjudication outcome, if it carries one.

    Tolerant of the current `adjudicate` stub: only a payload with explicit word +
    position fields becomes a recorded attempt; anything else persists nothing. The
    learner id and poem id come from session state (minimal-PII, §8). When §13.6's
    `adjudicate` emits a real grade + crutch-dependence tag, those fields ride through
    here unchanged — this is the persistence half of the Learner Memory loop (§13.5).
    """
    data = node_input if isinstance(node_input, dict) else {}
    src = data.get("attempt") if isinstance(data.get("attempt"), dict) else data
    if not all(k in src for k in ("word", "stanza_idx", "line_idx", "word_idx")):
        return None
    return Attempt(
        learner_id=str(ctx.state.get("learner_id") or "demo"),
        poem_id=str(ctx.state.get("poem_id") or src.get("poem_id") or ""),
        session_index=int(src.get("session_index", 0)),
        stanza_idx=int(src["stanza_idx"]),
        line_idx=int(src["line_idx"]),
        word_idx=int(src["word_idx"]),
        word=str(src["word"]),
        crutch_class=src.get("crutch_class", "none"),
        outcome=str(src.get("outcome", "miss")),
        crutch_dependence=src.get("crutch_dependence", "none"),
    )


@node(name="memory_update")
async def memory_update(ctx, node_input: Any):
    """Persist the attempt to Learner Memory (§13.5) — the data the adaptive overlay
    re-plans on next session. Terminal for a single attempt; the next attempt
    re-invokes the workflow (the loop is realized across RequestInput resume cycles,
    not a literal back-edge). The crutch-dependence tag is filled by `adjudicate` in
    §13.6; until then only well-formed attempts are recorded (stub outcomes are
    ignored, not persisted as noise)."""
    attempt = _attempt_from(ctx, node_input)
    if attempt is not None:
        LearnerMemory().record(attempt)
    yield Event(
        output={
            "recorded": attempt.to_dict() if attempt is not None else None,
            "outcome": node_input,
        }
    )


# Per-attempt graph. The loop in §4 is across invocations (RequestInput
# pause/resume), so ``memory_update`` is terminal here rather than a back-edge.
recall_session = Workflow(
    name="recall_session",
    edges=[
        (START, present_masked_line),
        (present_masked_line, adjudicate),
        (adjudicate, {"advance": advance, "scaffold": scaffold}),
        (advance, memory_update),
        (scaffold, memory_update),
    ],
)
