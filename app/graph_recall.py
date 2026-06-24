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


@node(name="present_masked_line")
async def present_masked_line(ctx, node_input: Any):
    """STUB. Will present the line with crutch-removal masking applied, then
    pause for the learner's recall. Yields ``RequestInput`` (human-in-the-loop)."""
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


@node(name="memory_update")
async def memory_update(ctx, node_input: Any):
    """STUB (§13.5). Will persist the attempt, error pattern, crutch dependence,
    and mastery. Terminal for a single attempt; the next attempt re-invokes the
    workflow (the loop is realized across RequestInput resume cycles, not a
    literal back-edge)."""
    yield Event(output={"todo": "memory_update not implemented", "outcome": node_input})


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
