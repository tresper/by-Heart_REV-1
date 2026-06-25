"""Key-free smoke for the web trainer (mirrors tests/integration/test_demo_runner.py).

Keeps the trunk green and the service bisectable WITHOUT a Gemini key: the provenance
refusal, the static graph topology, the node-transition envelope, and the SSE stream
opening are all exercised with no model call. The live build/recall/grade path is the
manual, key-bearing demo — deliberately out of the always-green gate, the same §13.4
reason the live eval sweep stays out of pytest.

The TestClient-based checks ``importorskip('httpx')`` so that when this file is collected
by the root ``uv run pytest`` (whose shared venv may not carry the web dev deps) they skip
cleanly instead of erroring; the dedicated ``uv run --package by-heart-web pytest web/tests``
run installs httpx and exercises them fully.
"""

from __future__ import annotations

import asyncio
import json
import types

import pytest
from by_heart_web import viz

from app.graph_build import build_pipeline
from app.graph_recall import recall_session

# --- pure unit checks (no server, no key, no httpx) -------------------------

def test_topology_matches_the_real_graphs() -> None:
    build = viz.topology(build_pipeline)
    recall = viz.topology(recall_session)
    assert set(build["nodes"]) == {
        "__START__", "provenance_gate", "prosody_analysis", "refuse", "curriculum_plan"
    }
    assert set(recall["nodes"]) == {
        "__START__", "present_masked_line", "adjudicate", "advance", "scaffold", "memory_update"
    }
    # The routed branches the visualization lights up must be present and labeled.
    assert any(
        e["from"] == "provenance_gate" and e["to"] == "refuse" and e["route"] == "refuse"
        for e in build["edges"]
    )
    assert any(
        e["from"] == "adjudicate" and e["to"] == "scaffold" and e["route"] == "scaffold"
        for e in recall["edges"]
    )


def _fake_event(name, *, path="recall_session@1/x@1", route=None, waiting=False):
    return types.SimpleNamespace(
        node_info=types.SimpleNamespace(name=name, path=path),
        actions=types.SimpleNamespace(route=route),
        long_running_tool_ids={"id"} if waiting else None,
        timestamp=1.0,
    )


def test_node_transition_envelope() -> None:
    tr = viz._node_transition(_fake_event("adjudicate", route="scaffold"))
    assert tr == {
        "kind": "node", "node": "adjudicate", "path": "recall_session@1/x@1",
        "route": "scaffold", "waiting": False, "ts": 1.0,
    }
    waiting = viz._node_transition(_fake_event("present_masked_line", waiting=True))
    assert waiting["waiting"] is True and waiting["route"] is None
    # An event with no node identity (e.g. the seeding user message) is skipped.
    assert viz._node_transition(types.SimpleNamespace(node_info=None)) is None


def test_structured_stanza_flags_the_target_blank() -> None:
    """The structured stanza marks exactly the quizzed blank, sizes it to the hidden word,
    and never emits the answer word as text (it stays server-side until earned)."""
    from by_heart_web.drive import _structured_stanza

    from app.curriculum.types import Course, MaskedSpan, SessionPlan

    poem = "Whose woods these are I think I know.\nHis house is in the village though;"
    course = Course(
        poem_id="t", stanza_count=1,
        sessions=(SessionPlan(index=0, rung=1,
                  masks=(MaskedSpan(0, 0, 7, "know", "rhyme_partner", 1),)),),
    )
    ctx = {"stanza_idx": 0, "line_idx": 0, "word_idx": 7, "session_index": 0}
    lines = _structured_stanza(poem, course, ctx)
    assert lines is not None and len(lines) == 2
    blanks = [s for s in lines[0] if s["t"] == "blank"]
    assert len(blanks) == 1 and blanks[0]["target"] is True and blanks[0]["len"] == 4
    # Each blank carries its position so the page can keep already-solved words filled in.
    assert blanks[0]["stanza_idx"] == 0 and blanks[0]["line_idx"] == 0 and blanks[0]["word_idx"] == 7
    text0 = "".join(s["v"] for s in lines[0] if s["t"] == "text")
    assert "know" not in text0                       # the answer is never sent as text
    text1 = "".join(s["v"] for s in lines[1] if s["t"] == "text")
    assert "though" in text1                          # unmasked line stays fully visible


def test_reveal_after_miss_discloses_only_on_request() -> None:
    """The answer is held server-side and only surfaced by the explicit reveal action; the
    consumed pause is cleared on grading but the context survives so a miss can be retried
    or revealed."""
    from by_heart_web.drive import reveal_recall
    from by_heart_web.sessions import create_web_session

    ws = create_web_session("reveal-learner")
    assert reveal_recall(ws)["ok"] is False           # nothing presented yet

    ws.target_context = {"word": "though", "stanza_idx": 0, "line_idx": 1, "word_idx": 6}
    ws.adk_session_id, ws.interrupt_id = "adk-1", "int-1"

    # Grading consumes the pause but must KEEP the context (so retry/reveal still work).
    ws.clear_pause()
    assert ws.adk_session_id is None and ws.interrupt_id is None
    assert ws.target_context is not None

    revealed = reveal_recall(ws)
    assert revealed["ok"] is True
    assert revealed["revealed_word"] == "though"
    assert revealed["target"] == {"stanza_idx": 0, "line_idx": 1, "word_idx": 6}

    # A full reset (new word) drops the context entirely.
    ws.clear_recall()
    assert ws.target_context is None and reveal_recall(ws)["ok"] is False


# --- endpoint checks (skip if httpx/TestClient unavailable) -----------------

@pytest.fixture
def client():
    pytest.importorskip("httpx")
    from by_heart_web.server import app
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_provenance_refusal_endpoint(client) -> None:
    r = client.get("/api/provenance", params={"poem_id": "plath-daddy"})
    assert r.status_code == 200
    body = r.json()
    assert body["admitted"] is False
    assert "allowlist" in body["reason"].lower()


def test_graphs_endpoint(client) -> None:
    body = client.get("/api/graphs").json()
    assert set(body["build"]["nodes"]) >= {"provenance_gate", "curriculum_plan"}
    assert set(body["recall"]["nodes"]) >= {"present_masked_line", "adjudicate", "memory_update"}
    assert body["default_poem_id"] == "frost-stopping-by-woods"


def test_sse_generator_yields_hello_then_transition() -> None:
    """Drive the SSE generator directly (the stream is infinite, so never via TestClient):
    it opens with a hello frame, then forwards each queued node transition as a ``data:``
    line whose body is the valid-JSON envelope the page consumes."""
    from by_heart_web.server import _sse
    from by_heart_web.sessions import create_web_session

    async def run() -> str:
        ws = create_web_session("smoke-learner")
        gen = _sse(ws)
        hello = await gen.__anext__()
        assert hello.startswith("event: hello")
        ws.queue.put_nowait({"kind": "node", "node": "adjudicate", "route": "scaffold", "waiting": False})
        frame = await gen.__anext__()
        await gen.aclose()
        return frame

    frame = asyncio.run(run())
    assert frame.startswith("data:")
    payload = json.loads(frame[len("data:"):].strip())
    assert payload["node"] == "adjudicate" and payload["route"] == "scaffold"
