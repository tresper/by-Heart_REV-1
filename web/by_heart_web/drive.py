"""Thin async driver over the two existing ADK graphs.

Every function here imports and drives the *real* graphs by reference
(``app.graph_build.build_pipeline`` / ``app.graph_recall.recall_session``) using the
same ``Runner`` + ``RequestInput`` pause/resume mechanics ``app/demo.py`` established —
it adds no behavior the graphs don't already have. It does NOT import ``app.demo`` (the
CLI runner stays untouched); it re-expresses that pattern for a long-running, per-request
web server, with the web session's ``NodeTransitionPlugin`` attached so each run streams
its node transitions to the open SSE stream.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from google.adk.runners import Runner
from google.genai import types

from app.curriculum.memory import (
    LearnerMemory,
    load_course,
    profile_from_attempts,
)
from app.curriculum.types import _WORD_RE, Course
from app.graph_build import build_pipeline
from app.graph_recall import recall_session
from app.prosody.analysis import analyze_poem
from app.provenance import evaluate_provenance, load_manifest
from app.security.recall_input import sanitize_recall

from .sessions import SESSION_SERVICE, WebSession

APP_NAME = "by-heart"
# ADK's human-in-the-loop request_input function-call name; the resume FunctionResponse
# is matched back to the paused node by this name + the interrupt id (see app/demo.py).
_REQUEST_INPUT_FC = "adk_request_input"


# ---------------------------------------------------------------------------
# Message + resume helpers (mirror app/demo.py:94-119).
# ---------------------------------------------------------------------------

def _user_message(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


def _recall_resume(interrupt_id: str, recall: str) -> types.Content:
    """A FunctionResponse that resumes the paused recall node with the learner's text."""
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=interrupt_id, name=_REQUEST_INPUT_FC, response={"recall": recall}
                )
            )
        ],
    )


def _event_output(event: Any) -> Any:
    return getattr(event, "output", None)


# ---------------------------------------------------------------------------
# Course shaping for the UI (no answer words ever leave the server).
# ---------------------------------------------------------------------------

def _course_summary(course: Course) -> dict[str, Any]:
    """The Course as the page shows it: per-session rung, rationale, and mask counts.

    The Deletion Rationale (the §4 visible reasoning artifact) is surfaced verbatim; the
    actual masked *words* are never included — only counts — so the answers stay server-side.
    """
    return {
        "poem_id": course.poem_id,
        "stanza_count": course.stanza_count,
        "rungs_used": list(course.rungs_used),
        "sessions": [
            {
                "index": s.index,
                "rung": s.rung,
                "rationale": s.rationale,
                "mask_count": len(s.masks),
                "new_masks": sum(1 for m in s.masks if m.rung == s.rung),
            }
            for s in course.sessions
        ],
    }


def session_targets(course: Course, session_index: int) -> list[dict[str, Any]]:
    """The words this session newly asks the learner to recall (positions + lengths only).

    Matches ``present_masked_line``'s target pool: the masks introduced at this session's
    rung. Only the word *length* is exposed (to size the blank), never the word itself.
    """
    if not course.sessions:
        return []
    session_index = max(0, min(session_index, len(course.sessions) - 1))
    session = course.sessions[session_index]
    newly = [m for m in session.masks if m.rung == session.rung] or list(session.masks)
    return [
        {
            "stanza_idx": m.stanza_idx,
            "line_idx": m.line_idx,
            "word_idx": m.word_idx,
            "word_len": len(m.word),
            "crutch_class": m.crutch_class,
        }
        for m in newly
    ]


@lru_cache(maxsize=8)
def _analyzed(poem_text: str) -> dict[str, Any]:
    """Cache the (pure, key-free) prosody structural map per poem — the recall graph
    rebuilds it each pause, so caching here avoids re-scanning for every quizzed word."""
    return analyze_poem(poem_text)


def _structured_stanza(
    poem_text: str, course: Course, target_ctx: dict[str, Any]
) -> list[list[dict[str, Any]]] | None:
    """The presented stanza as per-line segments, with the ONE quizzed blank flagged.

    Mirrors ``render_masked_line`` exactly (same ``_WORD_RE``, same session masks) but
    emits structure instead of a flat string, so the page can highlight the *specific*
    target blank among the stanza's other blanks and fill it in on a correct recall. Each
    segment is ``{"t": "text", "v": str}`` or ``{"t": "blank", "len": int, "target": bool,
    "stanza_idx", "line_idx", "word_idx"}``. The position lets the page keep words the
    learner has already earned (or revealed) filled in as it re-renders the stanza for the
    next word. The answer word is never included — only its length sizes the blank.
    """
    try:
        sx = int(target_ctx["stanza_idx"])
        tline = int(target_ctx["line_idx"])
        twi = int(target_ctx["word_idx"])
        si = int(target_ctx.get("session_index", 0))
    except (KeyError, TypeError, ValueError):
        return None
    if not course.sessions:
        return None
    stanza = next(
        (s for s in _analyzed(poem_text).get("stanzas", []) if s.get("index") == sx), None
    )
    if stanza is None:
        return None
    si = max(0, min(si, len(course.sessions) - 1))
    masked = {
        (m.line_idx, m.word_idx) for m in course.sessions[si].masks if m.stanza_idx == sx
    }
    lines_out: list[list[dict[str, Any]]] = []
    for li, line in enumerate(stanza.get("lines", [])):
        segs: list[dict[str, Any]] = []
        last = 0
        for i, mo in enumerate(_WORD_RE.finditer(line)):
            if mo.start() > last:
                segs.append({"t": "text", "v": line[last:mo.start()]})
            token = mo.group()
            if (li, i) in masked:
                segs.append({
                    "t": "blank",
                    "len": len(token),
                    "target": li == tline and i == twi,
                    "stanza_idx": sx,
                    "line_idx": li,
                    "word_idx": i,
                })
            else:
                segs.append({"t": "text", "v": token})
            last = mo.end()
        if last < len(line):
            segs.append({"t": "text", "v": line[last:]})
        lines_out.append(segs)
    return lines_out


# ---------------------------------------------------------------------------
# Graph A — build the Course (live, on demand).
# ---------------------------------------------------------------------------

async def run_build(ws: WebSession, poem_id: str) -> dict[str, Any]:
    """Drive the Build Pipeline once, streaming node transitions, and return the Course.

    The provenance gate runs inside the graph (so a non-corpus poem lights up
    ``provenance_gate → refuse`` live and key-free). An admitted poem then needs a Gemini
    key for ``prosody_analysis`` (Prosody MCP) and ``curriculum_plan``; if the key is
    missing the run raises, which we report as a friendly notice rather than a crash.
    """
    ws.plugin.graph = "build"
    admitted = evaluate_provenance(poem_id, manifest=load_manifest())

    session = await SESSION_SERVICE.create_session(
        app_name=APP_NAME, user_id=ws.learner_id, state={"learner_id": ws.learner_id}
    )
    runner = Runner(
        agent=build_pipeline,
        session_service=SESSION_SERVICE,
        app_name=APP_NAME,
        plugins=[ws.plugin],
    )
    error: str | None = None
    try:
        async for _ in runner.run_async(
            user_id=ws.learner_id, session_id=session.id, new_message=_user_message(poem_id)
        ):
            pass
    except Exception as exc:  # surfaced to the UI, not swallowed silently
        error = f"{type(exc).__name__}: {exc}"

    course = load_course(poem_id, ws.learner_id)
    if course is None:
        return {
            "ok": False,
            "admitted": admitted.admitted,
            "reason": admitted.reason,
            "error": error,
            "needs_key": admitted.admitted and error is not None,
            "course": None,
        }
    return {
        "ok": True,
        "admitted": True,
        "reason": admitted.reason,
        "error": None,
        "needs_key": False,
        "course": _course_summary(course),
    }


def load_course_summary(poem_id: str, learner_id: str) -> dict[str, Any] | None:
    course = load_course(poem_id, learner_id)
    return _course_summary(course) if course is not None else None


# ---------------------------------------------------------------------------
# Graph B — present a masked word (run to the RequestInput pause).
# ---------------------------------------------------------------------------

async def start_recall(
    ws: WebSession,
    poem_id: str,
    session_index: int,
    target: dict[str, int] | None,
    prior_hint_level: int = 0,
) -> dict[str, Any]:
    """Seed Graph B, run to the ``present_masked_line`` pause, and return the masked view.

    Stashes the paused ADK ``session_id`` + ``interrupt_id`` + the presented
    ``target_context`` on the web session so ``resume_recall`` can finish the attempt on
    the next request. The target word's surface form never leaves the server — only the
    underscore-blanked stanza/line and the word length do.

    ``prior_hint_level`` carries the strongest scaffold hint already given for THIS word on
    a previous failed attempt. Each retry is a fresh ADK session, so seeding it as the
    session's ``hint_level`` lets the existing ``scaffold`` node climb the §3 cue-withdrawal
    ladder (1 rhyme → 2 first letter → 3 gloss) across retries instead of restarting at 1.
    """
    ws.plugin.graph = "recall"
    admitted = evaluate_provenance(poem_id, manifest=load_manifest())
    if not admitted.admitted or not admitted.text:
        return {"ok": False, "reason": admitted.reason}

    state: dict[str, Any] = {
        "poem_id": poem_id,
        "poem_text": admitted.text,
        "learner_id": ws.learner_id,
        "session_index": session_index,
    }
    if prior_hint_level and prior_hint_level > 0:
        state["hint_level"] = int(prior_hint_level)
    if target is not None:
        state["target"] = {
            "stanza_idx": int(target["stanza_idx"]),
            "line_idx": int(target["line_idx"]),
            "word_idx": int(target["word_idx"]),
        }

    session = await SESSION_SERVICE.create_session(
        app_name=APP_NAME, user_id=ws.learner_id, state=state
    )
    runner = Runner(
        agent=recall_session,
        session_service=SESSION_SERVICE,
        app_name=APP_NAME,
        plugins=[ws.plugin],
    )
    interrupt_id: str | None = None
    try:
        async for event in runner.run_async(
            user_id=ws.learner_id, session_id=session.id, new_message=_user_message(poem_id)
        ):
            ids = getattr(event, "long_running_tool_ids", None)
            if ids:
                interrupt_id = next(iter(ids))
    except Exception as exc:
        # A transient model/tool failure while presenting the word: surface it instead of a
        # 500. No pause has been committed yet (ws.* are set only after this loop), so there
        # is nothing to clear — the learner can simply try the word again.
        return {
            "ok": False,
            "reason": "the tutor model is temporarily unavailable — please try again",
            "error": f"{type(exc).__name__}: {exc}",
        }
    if interrupt_id is None:
        return {"ok": False, "reason": "no masked word was presented (build the course first)"}

    live = await SESSION_SERVICE.get_session(
        app_name=APP_NAME, user_id=ws.learner_id, session_id=session.id
    )
    context = (live.state or {}).get("target_context") or {}

    ws.adk_session_id = session.id
    ws.interrupt_id = interrupt_id
    ws.poem_id = poem_id
    ws.target_context = context

    course = load_course(poem_id, ws.learner_id)
    stanza_lines = _structured_stanza(admitted.text, course, context) if course is not None else None

    word = str(context.get("word", ""))
    return {
        "ok": True,
        "rendered_stanza": context.get("rendered_stanza", ""),
        "rendered_line": context.get("rendered_line", ""),
        "stanza_lines": stanza_lines,
        "available_cues": context.get("available_cues", []),
        "crutch_class": context.get("crutch_class", "none"),
        "word_len": len(word),
        "target": {
            "stanza_idx": context.get("stanza_idx"),
            "line_idx": context.get("line_idx"),
            "word_idx": context.get("word_idx"),
        },
    }


# ---------------------------------------------------------------------------
# Graph B — grade a typed recall (resume the paused node).
# ---------------------------------------------------------------------------

async def resume_recall(ws: WebSession, recall_text: str) -> dict[str, Any]:
    """Sanitize the typed recall, resume the paused node, and return the graded result.

    The recall is the one untrusted input: it passes ``sanitize_recall`` here, at the web
    boundary, *before* it enters the FunctionResponse and reaches any model (the graph
    sanitizes again internally — defense in depth). The authoritative outcome + crutch tag
    are read back from the LearnerMemory store (as ``app/demo.py`` does); any scaffold hint
    is lifted from the terminal ``memory_update`` event.
    """
    if not ws.adk_session_id or not ws.interrupt_id or ws.poem_id is None:
        return {"ok": False, "reason": "no recall is awaiting an answer"}

    clean = sanitize_recall(recall_text)
    runner = Runner(
        agent=recall_session,
        session_service=SESSION_SERVICE,
        app_name=APP_NAME,
        plugins=[ws.plugin],
    )
    hint: str | None = None
    hint_level: int | None = None
    try:
        async for event in runner.run_async(
            user_id=ws.learner_id,
            session_id=ws.adk_session_id,
            new_message=_recall_resume(ws.interrupt_id, clean),
        ):
            ni = getattr(event, "node_info", None)
            if ni is not None and getattr(ni, "name", None) == "memory_update":
                out = _event_output(event)
                inner = out.get("outcome") if isinstance(out, dict) else None
                if isinstance(inner, dict) and "hint" in inner:
                    hint = inner.get("hint")
                    hint_level = inner.get("hint_level")
    except Exception as exc:
        # A transient model failure mid-grade must not wedge the attempt. Drop the consumed
        # pause so the learner can re-present and retry THIS word cleanly (clear_pause keeps
        # target_context for exactly that retry), and return a friendly error rather than a
        # 500 that leaves the half-consumed FunctionResponse stuck.
        ws.clear_pause()
        return {
            "ok": False,
            "reason": "the tutor model is temporarily unavailable — please try again",
            "error": f"{type(exc).__name__}: {exc}",
        }

    attempts = LearnerMemory().attempts_for(ws.learner_id, ws.poem_id)
    recorded = attempts[-1].to_dict() if attempts else {}
    outcome = recorded.get("outcome", "miss")
    advanced = outcome in ("hit", "variant")

    # Reveal the poem's word ONLY once the learner has earned it (a success) — so the
    # page can fill the blank in green. On a miss the word stays server-side (the answer
    # isn't given away, and a future retry isn't spoiled).
    revealed = str((ws.target_context or {}).get("word", "")) if advanced else None

    # Drop the consumed pause (no double-submit), but keep ``target_context``: a miss can
    # still be retried (re-presents the same word) or revealed (the learner gives up), and
    # both read the answer that is still held server-side.
    ws.clear_pause()
    return {
        "ok": True,
        "outcome": outcome,
        "crutch_dependence": recorded.get("crutch_dependence", "none"),
        "advanced": advanced,
        "revealed_word": revealed,
        "hint": hint,
        "hint_level": hint_level,
    }


def reveal_recall(ws: WebSession) -> dict[str, Any]:
    """Reveal the current word's surface form — the explicit "I give up" action.

    The answer is held server-side until earned; this surfaces it only on a deliberate
    learner request (after a miss), so the page can fill the blank in and move on. The
    attempt was already graded a miss on the failed submit, so revealing records nothing
    new — it just discloses what the learner stopped trying to recall.
    """
    context = ws.target_context or {}
    word = str(context.get("word", ""))
    if not word:
        return {"ok": False, "reason": "no word is awaiting recall"}
    return {
        "ok": True,
        "revealed_word": word,
        "target": {
            "stanza_idx": context.get("stanza_idx"),
            "line_idx": context.get("line_idx"),
            "word_idx": context.get("word_idx"),
        },
    }


# ---------------------------------------------------------------------------
# Learner memory + the adaptive profile (the re-plan signal).
# ---------------------------------------------------------------------------

def memory_snapshot(poem_id: str, learner_id: str) -> dict[str, Any]:
    """Recorded attempts + the diagnosed crutch profile that re-plans the next course."""
    attempts = LearnerMemory().attempts_for(learner_id, poem_id)
    profile = profile_from_attempts(poem_id, attempts)
    return {
        "attempts": [
            {
                "session_index": a.session_index,
                "word_len": len(a.word),
                "crutch_class": a.crutch_class,
                "outcome": a.outcome,
                "crutch_dependence": a.crutch_dependence,
            }
            for a in attempts
        ],
        "profile": {
            "dominant": profile.dominant,
            "by_class": profile.by_class,
            "total_attempts": profile.total_attempts,
        },
    }


def provenance_check(poem_id: str) -> dict[str, Any]:
    """Key-free gate check (used by the refusal demo + the smoke test)."""
    result = evaluate_provenance(poem_id, manifest=load_manifest())
    return {"poem_id": poem_id, "admitted": result.admitted, "reason": result.reason}


def list_poems() -> list[dict[str, Any]]:
    """The selectable corpus — every poem on the public-domain allowlist.

    Drawn from the *same* manifest the provenance gate enforces, so the picker is
    closed to allowlisted poems by construction: there is no open-text path, and a
    build of any listed id still passes through ``provenance_gate``. Manifest order
    is preserved (the seed Frost poem stays first, matching ``DEMO_POEM_ID``)."""
    return [
        {
            "id": pid,
            "title": entry.get("title", pid),
            "author": entry.get("author", ""),
            "first_published": entry.get("first_published"),
        }
        for pid, entry in load_manifest().items()
    ]
