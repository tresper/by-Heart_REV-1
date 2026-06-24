"""curriculum_plan wiring + the §13.4 Deletion Rationale.

The key-free tests prove the node is the intended hybrid: a deterministic schedule
(`curriculum_plan`, a FunctionNode) plus a no-tools Gemini rationale writer, with
`prosody_analysis` now committing a structured anchor judgment. The live test drives
the real rationale agent over the deterministic Dickinson schedule and asserts a
grounded Deletion Rationale per session — the visible, judge-facing artifact. (The
full provenance->prosody(MCP)->curriculum pipeline is exercised end-to-end by the
manual run in the phase verification; here we isolate the new LLM behavior so a
single test process doesn't reuse one stdio MCP session across two event loops.)
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from app.graph_build import (
    _rationale_agent,
    _rationale_payload,
    curriculum_plan,
    prosody_analysis,
)


def test_curriculum_plan_is_wired_as_hybrid() -> None:
    """Deterministic node + a no-tools rationale agent; the node can call a model."""
    assert type(curriculum_plan).__name__ == "FunctionNode"
    assert getattr(curriculum_plan, "rerun_on_resume", False) is True
    assert type(_rationale_agent).__name__ == "LlmAgent"
    assert _rationale_agent.name == "deletion_rationale"
    assert list(_rationale_agent.tools) == []  # rationale only — no tool calls
    assert _rationale_agent.output_schema is not None


def test_prosody_analysis_commits_anchor_judgment() -> None:
    """prosody_analysis stays MCP-grounded but now also emits structured anchors —
    the load-bearing dependency curriculum_plan consumes for rung-3 deletions (§4)."""
    assert prosody_analysis.output_schema is not None
    assert prosody_analysis.output_key == "prosody"
    assert prosody_analysis.tools  # still grounded by the Prosody MCP toolset


def _final_text(events) -> str:
    """The last model text across an Agent run (the rationale agent's JSON reply)."""
    texts = [
        p.text
        for e in events
        if e.content and e.content.parts
        for p in e.content.parts
        if getattr(p, "text", None)
    ]
    return texts[-1] if texts else ""


@pytest.mark.skipif(
    not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
    reason="live LLM run requires GOOGLE_API_KEY or GEMINI_API_KEY in the environment",
)
def test_rationale_agent_authors_grounded_rationale_per_session() -> None:
    """The §13.4 deliverable: Gemini writes one Deletion Rationale per session,
    over the real deterministic Dickinson schedule, naming the crutch removed."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app.curriculum.policy import plan_course
    from app.prosody.analysis import analyze_poem

    text = pathlib.Path(
        "corpus/texts/dickinson-because-i-could-not-stop-for-death.txt"
    ).read_text(encoding="utf-8")
    structural_map = analyze_poem(text)
    course = plan_course(
        structural_map, structural_map["anchor_candidates"], "dickinson"
    )
    payload = _rationale_payload(course, structural_map)

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="t", app_name="by-heart")
    runner = Runner(
        agent=_rationale_agent, session_service=session_service, app_name="by-heart"
    )
    message = types.Content(
        role="user", parts=[types.Part.from_text(text=json.dumps(payload))]
    )
    events = list(
        runner.run(new_message=message, user_id="t", session_id=session.id)
    )

    rationales = json.loads(_final_text(events))["rationales"]
    assert len(rationales) == len(course.sessions) >= 4
    assert all(str(r).strip() for r in rationales), "every session has a rationale"
    blob = " ".join(map(str, rationales)).lower()
    assert any(
        term in blob for term in ("rhyme", "meter", "metrical", "stress", "syntactic")
    ), "the rationale should name the crutch being removed"
