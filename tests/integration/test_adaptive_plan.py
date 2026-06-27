"""Adaptive overlay wiring + the §13.5 directive (the money-shot decision).

Key-free: the adaptive planner is a no-tools LlmAgent, `curriculum_plan` still resumes,
and the validator fails closed on a class this poem lacks (blueprint §8). Key-gated:
drive the planner over a seeded rhyme-heavy profile and assert it CHOOSES a valid crutch
with a real diagnosis — the §4-step-4 agentic choice (grounding check, not string-equal).
We isolate the planner the way §13.4 isolates the rationale agent, so no single test
process reuses one stdio MCP session across two event loops.
"""

from __future__ import annotations

import json
import os

import pytest

from app.curriculum.memory import Attempt, profile_from_attempts, recent_evidence
from app.graph_build import _adaptive_planner, _validate_directive, curriculum_plan


def test_adaptive_planner_is_wired_as_a_no_tools_chooser() -> None:
    assert type(_adaptive_planner).__name__ == "LlmAgent"
    assert _adaptive_planner.name == "adaptive_planner"
    assert list(_adaptive_planner.tools) == []  # it decides; it does not call tools
    assert _adaptive_planner.output_schema is not None
    assert getattr(curriculum_plan, "rerun_on_resume", False) is True


def test_validate_directive_fails_closed_on_absent_class() -> None:
    """§8: the LLM's choice is a proposal validated against the poem, never trusted raw."""
    present = {"rhyme_partner", "metrical_regularity"}
    assert _validate_directive({"prioritized_crutch": "syntactic_momentum"}, present) is None
    assert _validate_directive("not a dict", present) is None
    ok = _validate_directive(
        {"prioritized_crutch": "rhyme_partner", "diagnosis": "leans on the rhyme"},
        present,
    )
    assert ok is not None and ok.prioritized_crutch == "rhyme_partner"


def test_validate_directive_applies_a_non_dominant_but_present_class() -> None:
    """The pipeline honors whatever valid class the Architect picks — not just the
    count-ranked dominant one — so a recency/miss-driven choice is applied, not overridden
    back to argmax. Here rhyme_partner would be count-dominant, yet the chosen
    metrical_regularity (also present) is accepted as-is."""
    present = {"rhyme_partner", "metrical_regularity"}
    ok = _validate_directive(
        {"prioritized_crutch": "metrical_regularity", "diagnosis": "recent misses there"},
        present,
    )
    assert ok is not None and ok.prioritized_crutch == "metrical_regularity"


def _final_text(events) -> str:
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
def test_adaptive_planner_chooses_a_grounded_crutch() -> None:
    """A learner who keeps nailing rhyme words (partner visible) → the Architect picks
    a real crutch to strip next and explains why. The choice is validated, not parsed."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    attempts = [
        Attempt(
            "L",
            "dickinson",
            0,
            0,
            0,
            3,
            "sun",
            crutch_class="rhyme_partner",
            outcome="hit",
            crutch_dependence="rhyme_partner",
        )
        for _ in range(4)
    ]
    profile = profile_from_attempts("dickinson", attempts)
    # Feed exactly what curriculum_plan sends: the aggregate profile + raw recent attempts.
    planner_input = {**profile.to_dict(), "recent_attempts": recent_evidence(attempts)}

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="t", app_name="by-heart")
    runner = Runner(
        agent=_adaptive_planner, session_service=session_service, app_name="by-heart"
    )
    message = types.Content(
        role="user", parts=[types.Part.from_text(text=json.dumps(planner_input))]
    )
    events = list(runner.run(new_message=message, user_id="t", session_id=session.id))

    proposal = json.loads(_final_text(events))
    assert proposal["prioritized_crutch"] in (
        "rhyme_partner",
        "metrical_regularity",
        "syntactic_momentum",
    )
    assert str(proposal.get("diagnosis", "")).strip(), "the choice must carry a reason"
