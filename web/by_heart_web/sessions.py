"""Per-browser web sessions and the one shared ADK session service.

A *web session* is the browser's live channel: it owns an ``asyncio.Queue`` and the
``NodeTransitionPlugin`` bound to it, so a single open SSE stream sees every graph run
the browser triggers (the build, then each recall start/resume). It also remembers the
in-flight recall (the paused ADK ``session_id`` + ``interrupt_id`` + the presented
``target_context``) between the two HTTP requests a recall takes (start → pause,
submit → resume).

The ADK ``InMemorySessionService`` is a process-wide singleton (mirroring
``app/demo.py``): one event loop (FastAPI's), many concurrent requests as coroutines —
which satisfies the §13.4 single-loop invariant. Per-browser isolation comes from a
distinct ADK ``session_id`` (and an opaque ``learner_id``) per web session; the durable
learner record stays in the existing ``LearnerMemory`` store, not here.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.sessions import InMemorySessionService

from .viz import NodeTransitionPlugin

# One ADK session service for the whole process (one event loop). Recall start and
# recall submit must share it so the paused session is found again on resume.
SESSION_SERVICE = InMemorySessionService()


@dataclass
class WebSession:
    """One browser's viz channel + in-flight recall state."""

    id: str
    learner_id: str
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    plugin: NodeTransitionPlugin | None = None
    # In-flight recall (set by start_recall, consumed by resume_recall):
    adk_session_id: str | None = None
    interrupt_id: str | None = None
    poem_id: str | None = None
    target_context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.plugin is None:
            self.plugin = NodeTransitionPlugin(self.queue)

    def clear_recall(self) -> None:
        """Drop the in-flight recall once it has been graded."""
        self.adk_session_id = None
        self.interrupt_id = None
        self.target_context = None


_SESSIONS: dict[str, WebSession] = {}
# A soft cap so a long-lived process can't accumulate sessions without bound; the demo
# is single-user, so this only matters as a leak guard.
_MAX_SESSIONS = 512


def new_learner_id() -> str:
    """An opaque, minimal-PII learner id (no real identity)."""
    return f"web-{uuid.uuid4().hex[:12]}"


def create_web_session(learner_id: str) -> WebSession:
    """Mint a web session (and its queue + plugin) for a browser."""
    if len(_SESSIONS) >= _MAX_SESSIONS:
        # Evict the oldest insertion (dicts preserve order) — best-effort GC.
        _SESSIONS.pop(next(iter(_SESSIONS)), None)
    ws = WebSession(id=uuid.uuid4().hex, learner_id=learner_id)
    _SESSIONS[ws.id] = ws
    return ws


def get_web_session(web_session_id: str) -> WebSession | None:
    return _SESSIONS.get(web_session_id)
