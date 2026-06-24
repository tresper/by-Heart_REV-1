"""Recall-loop wiring + the §13.6 live grade/scaffold (the closed adaptive loop).

Key-free: the Adjudicator and Scaffolding Coach are no-tools LlmAgents with a structured
schema, the recall graph keeps its edges, and Graph B uses NO MCP toolset — so a single
test process never reuses one stdio MCP session across two event loops (the §13.4
invariant). Key-gated: drive the Adjudicator over a near-miss recall and assert it returns
a valid grade and a dependence tag drawn only from the visible cues; drive the Coach and
assert a non-empty hint at a valid level. Grounding checks, not string-equality.
"""

from __future__ import annotations

import json
import os

import pytest

from app.graph_recall import _adjudicator, _scaffold_coach, adjudicate, recall_session, scaffold


def test_adjudicator_is_wired_as_a_no_tools_grader() -> None:
    assert type(_adjudicator).__name__ == "LlmAgent"
    assert _adjudicator.name == "adjudicate"
    assert list(_adjudicator.tools) == []  # it grades; it does not call tools (no MCP in Graph B)
    assert _adjudicator.output_schema is not None
    assert getattr(adjudicate, "rerun_on_resume", False) is True


def test_scaffold_coach_is_wired_as_a_no_tools_hinter() -> None:
    assert type(_scaffold_coach).__name__ == "LlmAgent"
    assert _scaffold_coach.name == "scaffold"
    assert list(_scaffold_coach.tools) == []
    assert _scaffold_coach.output_schema is not None
    assert getattr(scaffold, "rerun_on_resume", False) is True


def test_recall_graph_keeps_its_edges() -> None:
    """The §4 shape is intact: present → adjudicate → {advance|scaffold} → memory_update."""
    assert recall_session.name == "recall_session"
    node_names = {
        n.name
        for edge in recall_session.edges
        for n in edge
        if hasattr(n, "name")
    }
    assert {"present_masked_line", "adjudicate", "advance", "scaffold", "memory_update"} <= node_names


def _final_text(events) -> str:
    texts = [
        p.text
        for e in events
        if e.content and e.content.parts
        for p in e.content.parts
        if getattr(p, "text", None)
    ]
    return texts[-1] if texts else ""


def _run(agent, payload: dict) -> dict:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="t", app_name="by-heart")
    runner = Runner(agent=agent, session_service=session_service, app_name="by-heart")
    message = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(payload))])
    events = list(runner.run(new_message=message, user_id="t", session_id=session.id))
    return json.loads(_final_text(events))


@pytest.mark.skipif(
    not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
    reason="live LLM run requires GOOGLE_API_KEY or GEMINI_API_KEY in the environment",
)
def test_adjudicator_grades_and_tags_within_the_visible_cues() -> None:
    """Expected `sun` while its rhyme partner `done` is visible: any success it credits
    must be the rhyme cue (the only available one); the grade is a valid label."""
    grade = _run(
        _adjudicator,
        {
            "expected_word": "sun",
            "masked_stanza": (
                "We passed the School, where Children strove\n"
                "At Recess - in the Ring -\n"
                "We passed the Fields of Gazing Grain -\n"
                "We passed the Setting _____ -"
            ),
            "learner_recall": "sun",
            "available_cues": ["rhyme_partner"],
        },
    )
    assert grade["outcome"] in ("hit", "near_miss", "variant", "miss")
    assert grade.get("crutch_dependence", "none") in ("rhyme_partner", "none")


@pytest.mark.skipif(
    not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
    reason="live LLM run requires GOOGLE_API_KEY or GEMINI_API_KEY in the environment",
)
def test_coach_returns_a_minimum_hint_at_a_valid_level() -> None:
    hint = _run(
        _scaffold_coach,
        {
            "masked_line": "We passed the Setting _____ -",
            "learner_recall": "moon",
            "rhyme_cue": "It rhymes with “done.”",
            "first_letter_hint": "It starts with “s.”",
            "expected_word": "sun",
            "prior_hint_level": 0,
        },
    )
    assert hint["hint_level"] in (1, 2, 3)
    assert str(hint.get("hint", "")).strip()
