"""FastAPI service — the browser front-end over the existing By Heart ADK graphs.

Endpoints are a thin HTTP skin over ``drive.py`` (which drives the real
``build_pipeline`` / ``recall_session``). The page draws both graphs from the static
topology (``GET /api/graphs``) and highlights the live node transitions streamed over
SSE (``GET /api/session/{id}/stream``) while a human builds the course and recalls the
poem. Provenance, semantic grading, the crutch-removal schedule, and minimal-PII all
remain enforced in ``app/`` — this layer only presents them.

Run locally:   uv run uvicorn by_heart_web.server:app --reload  (from web/)
On Cloud Run:  uvicorn by_heart_web.server:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.graph_build import build_pipeline
from app.graph_recall import recall_session

from . import drive
from .sessions import create_web_session, get_web_session, new_learner_id
from .viz import topology

# The web trainer is anchored on the Frost poem (on the public-domain allowlist), but
# every endpoint is poem_id-parameterized and still passes through the provenance gate,
# so only allowlisted corpus poems are ever processed.
DEMO_POEM_ID = "frost-stopping-by-woods"
_LEARNER_COOKIE = "byheart_learner"
_STATIC_DIR = Path(__file__).parent / "static"


class _NoCacheStaticFiles(StaticFiles):
    """Serve the front-end with revalidation forced on every load.

    The demo is a single static page + ``app.js``; a stale cached copy silently renders
    old UI against a live (new) backend — exactly the confusing failure to avoid mid-demo.
    ``no-cache`` keeps the fast ETag revalidation (304s) but guarantees the browser never
    *uses* a cached asset without first checking it is current.
    """

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="By Heart — Web Trainer", version="0.1.0")
app.mount("/static", _NoCacheStaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Request bodies.
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    web_session_id: str
    poem_id: str = DEMO_POEM_ID


class StartRequest(BaseModel):
    web_session_id: str
    poem_id: str = DEMO_POEM_ID
    session_index: int = 0
    target: dict[str, int] | None = None
    # The strongest scaffold hint already given for this word (0 = first attempt); a retry
    # passes it so the scaffold ladder climbs instead of restarting at level 1.
    prior_hint_level: int = 0


class SubmitRequest(BaseModel):
    web_session_id: str
    recall: str


def _require_session(web_session_id: str):
    ws = get_web_session(web_session_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="unknown or expired web session")
    return ws


# ---------------------------------------------------------------------------
# Page + static topology.
# ---------------------------------------------------------------------------

@app.get("/")
async def index() -> FileResponse:
    # no-cache so a refresh always revalidates — never render a stale page against a live backend.
    return FileResponse(str(_STATIC_DIR / "index.html"), headers={"Cache-Control": "no-cache"})


@app.get("/api/graphs")
async def graphs() -> dict[str, Any]:
    """The static node/edge shape of both graphs (drawn once; key-free)."""
    return {
        "build": topology(build_pipeline),
        "recall": topology(recall_session),
        "default_poem_id": DEMO_POEM_ID,
    }


# ---------------------------------------------------------------------------
# Web session lifecycle + the SSE viz stream.
# ---------------------------------------------------------------------------

@app.post("/api/session")
async def open_session(request: Request, response: Response) -> dict[str, Any]:
    """Open a browser's web session (its viz channel). Learner id persists via cookie."""
    learner_id = request.cookies.get(_LEARNER_COOKIE) or new_learner_id()
    ws = create_web_session(learner_id)
    response.set_cookie(_LEARNER_COOKIE, learner_id, httponly=True, samesite="lax")
    return {
        "web_session_id": ws.id,
        "learner_id": learner_id,
        "default_poem_id": DEMO_POEM_ID,
        "stream_url": f"/api/session/{ws.id}/stream",
    }


async def _sse(ws) -> Any:
    """Yield SSE frames: an initial hello, then each node/tool transition; heartbeats keep
    the connection alive through proxies (e.g. Cloud Run idle timeout)."""
    yield "event: hello\ndata: {}\n\n"
    while True:
        try:
            item = await asyncio.wait_for(ws.queue.get(), timeout=15.0)
        except TimeoutError:
            yield ": keepalive\n\n"
            continue
        yield f"data: {json.dumps(item)}\n\n"


@app.get("/api/session/{web_session_id}/stream")
async def stream(web_session_id: str) -> StreamingResponse:
    ws = _require_session(web_session_id)
    return StreamingResponse(
        _sse(ws),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Graph A — build the course (live).
# ---------------------------------------------------------------------------

@app.post("/api/course/build")
async def course_build(body: BuildRequest) -> dict[str, Any]:
    ws = _require_session(body.web_session_id)
    return await drive.run_build(ws, body.poem_id)


@app.get("/api/course")
async def course_get(web_session_id: str, poem_id: str = DEMO_POEM_ID) -> dict[str, Any]:
    """The persisted Course summary (+ the per-session target list the UI steps through)."""
    ws = _require_session(web_session_id)
    summary = drive.load_course_summary(poem_id, ws.learner_id)
    if summary is None:
        return {"ok": False, "course": None}
    from app.curriculum.memory import load_course

    course = load_course(poem_id, ws.learner_id)
    targets_by_session = {
        s["index"]: drive.session_targets(course, s["index"]) for s in summary["sessions"]
    }
    return {"ok": True, "course": summary, "targets": targets_by_session}


# ---------------------------------------------------------------------------
# Graph B — present a masked word, then grade the typed recall.
# ---------------------------------------------------------------------------

@app.post("/api/recall/start")
async def recall_start(body: StartRequest) -> dict[str, Any]:
    ws = _require_session(body.web_session_id)
    return await drive.start_recall(
        ws, body.poem_id, body.session_index, body.target, body.prior_hint_level
    )


@app.post("/api/recall/submit")
async def recall_submit(body: SubmitRequest) -> dict[str, Any]:
    ws = _require_session(body.web_session_id)
    return await drive.resume_recall(ws, body.recall)


@app.post("/api/recall/reveal")
async def recall_reveal(body: SubmitRequest) -> dict[str, Any]:
    """Disclose the current word after a miss (the explicit "I give up" action). Reuses the
    ``SubmitRequest`` body — only ``web_session_id`` is needed; ``recall`` is ignored."""
    ws = _require_session(body.web_session_id)
    return drive.reveal_recall(ws)


# ---------------------------------------------------------------------------
# Learner memory + the key-free provenance check.
# ---------------------------------------------------------------------------

@app.get("/api/memory")
async def memory(web_session_id: str, poem_id: str = DEMO_POEM_ID) -> dict[str, Any]:
    ws = _require_session(web_session_id)
    return drive.memory_snapshot(poem_id, ws.learner_id)


@app.get("/api/provenance")
async def provenance(poem_id: str) -> dict[str, Any]:
    """Key-free gate check — proves the allowlist refuses a non-corpus poem."""
    return drive.provenance_check(poem_id)
