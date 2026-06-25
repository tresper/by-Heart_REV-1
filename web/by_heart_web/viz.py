"""Real-time graph visualization — the live signal behind the browser's SVG.

Two halves, both read straight from ADK so nothing can drift from the real graphs:

* ``topology(wf)`` extracts the static node/edge shape from ``Workflow.graph`` — the
  same object the runtime executes — so the page draws exactly the graph that runs
  (Graph A: 5 nodes/4 edges; Graph B: 6 nodes/6 edges, with the routed branches).

* ``NodeTransitionPlugin`` is an ADK ``BasePlugin`` registered on a per-web-session
  ``Runner(plugins=[...])``. Its ``on_event_callback`` fires for every event before
  persistence; we pull the *clean active-node name* (``event.node_info.name`` — a
  computed property, verified on the installed ADK), the *branch taken*
  (``event.actions.route``), and the *human-in-the-loop pause* flag
  (``bool(event.long_running_tool_ids)``) and push a compact transition onto an
  ``asyncio.Queue`` the SSE endpoint drains. ``before_tool_callback`` surfaces each
  Prosody MCP call (``pronounce`` / ``scan_line`` / ``analyze_poem``) so the page can
  show the MCP firing during the build. The plugin only observes — every hook returns
  ``None`` and never mutates an event.
"""

from __future__ import annotations

import asyncio
from typing import Any

from google.adk.plugins.base_plugin import BasePlugin

# The dynamic LLM/tool child nodes ADK schedules under a node (e.g. the Adjudicator
# agent under ``adjudicate``, the rationale/adaptive planners under ``curriculum_plan``)
# carry their own ``node_info.name``. We forward them as sub-steps; the page maps the
# canonical graph nodes below to circles and shows the rest as a reasoning log.
CANONICAL_NODES: dict[str, tuple[str, ...]] = {
    "build": ("__START__", "provenance_gate", "prosody_analysis", "refuse", "curriculum_plan"),
    "recall": ("__START__", "present_masked_line", "adjudicate", "advance", "scaffold", "memory_update"),
}

# The actual Prosody MCP tools (app/prosody/server.py). We surface ONLY these as "MCP
# calls" — ADK's internal structured-output plumbing (e.g. ``set_model_response``) also
# arrives via the tool hook, but it is not the MCP and would mislead the showcase.
_MCP_TOOLS = frozenset({"pronounce", "scan_line", "analyze_poem"})


def topology(wf: Any) -> dict[str, Any]:
    """The static node/edge shape of a Workflow, for the page to draw once at load.

    Reads ``wf.graph`` (the compiled graph the runner executes), so the drawing is the
    real topology — including each edge's ``route`` (``None`` for an unconditional edge,
    or ``admit``/``refuse``/``advance``/``scaffold`` for a conditional branch).
    """
    g = wf.graph
    return {
        "nodes": [n.name for n in g.nodes],
        "edges": [
            {"from": e.from_node.name, "to": e.to_node.name, "route": e.route}
            for e in g.edges
        ],
    }


def _node_transition(event: Any) -> dict[str, Any] | None:
    """Translate one ADK event into a compact transition, or ``None`` to skip it.

    Skips events with no node identity (e.g. the seeding user message). The clean node
    name is ``node_info.name``; ``node_info.path`` keeps the hierarchy so the page can
    tell a top-level graph node from a dynamic child step.
    """
    ni = getattr(event, "node_info", None)
    name = getattr(ni, "name", None) if ni is not None else None
    if not name:
        return None
    actions = getattr(event, "actions", None)
    route = getattr(actions, "route", None) if actions is not None else None
    long_running = getattr(event, "long_running_tool_ids", None)
    return {
        "kind": "node",
        "node": name,
        "path": getattr(ni, "path", None),
        "route": route,
        "waiting": bool(long_running),
        "ts": getattr(event, "timestamp", None),
    }


class NodeTransitionPlugin(BasePlugin):
    """Observe-only ADK plugin that streams node + MCP-tool transitions to a queue.

    One instance per web session, bound to that session's ``asyncio.Queue``; the same
    instance is attached to every ``Runner`` the web session spins up (build, then each
    recall start/resume), so a single open SSE stream sees the whole arc. ``graph`` is a
    soft label (``"build"``/``"recall"``) the server sets before each run so the page
    knows which diagram to light up.
    """

    def __init__(self, queue: asyncio.Queue[dict[str, Any]], name: str = "node-transition") -> None:
        super().__init__(name=name)
        self._queue = queue
        self.graph = ""  # current graph label, set by the server before a run

    def _emit(self, payload: dict[str, Any]) -> None:
        payload.setdefault("graph", self.graph)
        # Non-blocking: an unbounded queue never rejects; a slow client just buffers.
        self._queue.put_nowait(payload)

    async def on_event_callback(self, *, invocation_context: Any, event: Any) -> None:
        transition = _node_transition(event)
        if transition is not None:
            self._emit(transition)
        return None

    async def before_tool_callback(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any
    ) -> None:
        # Make the Prosody MCP visible: a call to one of its tools is the build graph
        # grounding its scansion in the MCP server. Internal ADK tooling is ignored so
        # the "MCP firing" signal stays honest.
        name = getattr(tool, "name", "")
        if name in _MCP_TOOLS:
            self._emit({"kind": "tool", "tool": name, "ts": None})
        return None
