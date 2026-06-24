"""prosody_analysis wiring + the ADK↔MCP integration (mostly key-free).

The deterministic tests prove the §5 story — the Prosody MCP is consumed through
ADK's own toolset machinery — without a Gemini key. The live test (skipped
without a key) exercises the full LLM agent end-to-end.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from app.graph_build import _prosody_toolset, prosody_analysis


def test_prosody_analysis_is_wired() -> None:
    """prosody_analysis is an LLM agent grounded by the Prosody MCP toolset."""
    assert type(prosody_analysis).__name__ == "LlmAgent"
    assert prosody_analysis.name == "prosody_analysis"
    assert _prosody_toolset in prosody_analysis.tools


def test_adk_mcp_toolset_connects_and_lists_tools() -> None:
    """ADK's McpToolset launches the stdio server and exposes the prosody tools
    — the §5 'MCP consumed by the agent framework' path, no Gemini key needed."""
    async def _run() -> list[str]:
        try:
            tools = await _prosody_toolset.get_tools()
            return sorted(t.name for t in tools)
        finally:
            await _prosody_toolset.close()

    assert asyncio.run(_run()) == ["analyze_poem", "pronounce", "scan_line"]


@pytest.mark.skipif(
    not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
    reason="live LLM run requires GOOGLE_API_KEY or GEMINI_API_KEY in the environment",
)
def test_prosody_analysis_live() -> None:
    """End-to-end: the agent reasons over the MCP tools to analyze a poem."""
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    poem = "away\nhaste\ntoo\ncivility"
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="t", app_name="by-heart")
    runner = Runner(
        agent=prosody_analysis, session_service=session_service, app_name="by-heart"
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"Analyze the prosody of this poem:\n{poem}")],
    )
    events = list(
        runner.run(
            new_message=message,
            user_id="t",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    assert any(
        e.content and e.content.parts and any(p.text for p in e.content.parts)
        for e in events
    ), "expected the agent to produce text"
