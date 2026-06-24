"""Graph B — the Recall Session Loop (blueprint §4), human-in-the-loop and now LIVE.

    [present_masked_line] -> (RequestInput: learner recall) -> [adjudicate]
        -> advance ----> [memory_update]
        -> scaffold --> [memory_update]
    ...looping per attempt via RequestInput pause/resume.

This is the §13.6 build: ``adjudicate`` grades semantically and emits the real
crutch-dependence tag, ``scaffold`` gives a graduated minimum hint, and
``present_masked_line`` renders an actual masked line from the persisted Course. That
closes the §13.5 adaptive loop: real tags land in Learner Memory, so the *next* Build
Pipeline run strips a *different* crutch (DoD §11 #3/#4).

The §8 hybrid is preserved one layer down: the LLM (``_adjudicator``) grades and
*proposes* which crutch a correct recall leaned on; a pure validator
(``_validate_adjudication``) accepts that tag only if the cue was actually still
VISIBLE for this word — facts computed deterministically by ``present_masked_line``
from the structural map + the session's masks. A miss leans on nothing. So the tag is
never trusted raw, and the deterministic half is unit-testable without a key. Graph B
calls no MCP (the cue facts are already in the structural map), which keeps a single
stdio MCP session from being reused across event loops (the §13.4 invariant).

The human-in-the-loop pause is modeled with ``RequestInput`` (yielded from
``present_masked_line``): the run pauses for the learner's typed recall and resumes
with it, flowing into ``adjudicate``. The §4 loop is realized ACROSS invocations
(RequestInput pause/resume), so ``memory_update`` is terminal here, not a back-edge.
Nodes that call ``ctx.run_node`` after the resume are declared ``rerun_on_resume=True``
(the same ADK contract ``curriculum_plan`` uses in Graph A).
"""

from __future__ import annotations

from typing import Any

from google.adk.agents import Agent
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Workflow, node
from pydantic import BaseModel

from app.curriculum.memory import Attempt, LearnerMemory, load_course
from app.curriculum.policy import is_metrically_regular
from app.curriculum.types import SessionPlan, line_tokens, render_masked_line
from app.models import gemini
from app.prosody.analysis import _STOPWORDS, analyze_poem

# The Adjudicator's grade vocabulary (blueprint §4). "hit"/"variant" are successes (a
# meaning-preserving variant still counts as recalled); "near_miss"/"miss" are not.
_VALID_OUTCOMES = ("hit", "near_miss", "variant", "miss")
_SUCCESS = frozenset({"hit", "variant"})


# ---------------------------------------------------------------------------
# The LLM nodes (no tools — the cue facts are handed to them as data, §8).
# ---------------------------------------------------------------------------

class Adjudication(BaseModel):
    """The Adjudicator's structured proposal — graded semantically, validated after.

    ``crutch_dependence`` is the money-shot tag (§4): which still-visible cue a CORRECT
    recall most plausibly leaned on. It is a proposal: ``_validate_adjudication`` keeps
    it only if that cue was actually available, and clears it on any non-success.
    """

    outcome: str  # hit | near_miss | variant | miss
    crutch_dependence: str = "none"  # rhyme_partner | metrical_regularity | syntactic_momentum | none
    note: str = ""  # one-line, human-readable crutch-dependence tag


class Hint(BaseModel):
    """The Scaffolding Coach's minimum-effective hint (§3 graduated cue withdrawal)."""

    hint_level: int  # 1 rhyme cue, 2 first letter, 3 meaning gloss
    hint: str


# adjudicate: a Gemini node that grades the recall against the expected word
# SEMANTICALLY (never a string compare, §2) and names the leaned-on crutch. It is
# given the list of cues that were still VISIBLE for this word, so it can only credit a
# real one; the validator enforces that afterwards.
_adjudicator = Agent(
    name="adjudicate",
    model=gemini(),
    instruction=(
        "You grade a learner's attempt to recall ONE masked word in a stanza of poetry. "
        "You are given the expected word, the stanza as the learner saw it (with one or "
        "more blanks — you are grading the blank that holds the expected word), their "
        "typed recall, and `available_cues` — the structural cues that were still visible "
        "and could have helped them. Grade SEMANTICALLY, never by exact string: "
        "`hit` = the expected word (allow spelling/case/inflection); `variant` = a "
        "different word that preserves the line's meaning acceptably; `near_miss` = close "
        "but wrong (right sound or sense, wrong word); `miss` = wrong or blank. THEN, only "
        "if the outcome is a success (hit or variant), set `crutch_dependence` to the ONE "
        "entry of `available_cues` the recall most plausibly leaned on — or `none` if they "
        "clearly knew it or no cue applies. On any non-success, `crutch_dependence` must be "
        "`none`. Write `note` as one short sentence naming the dependence, e.g. \"got "
        "'sun' only because its rhyme partner 'done' was still visible.\" Return JSON "
        "matching the schema."
    ),
    output_schema=Adjudication,
)

# scaffold: a Gemini node that gives the MINIMUM hint for where the learner stalled,
# escalating only as needed. The rhyme cue (level 1) and first-letter (level 2) facts
# are provided deterministically; the coach picks the lowest level that helps and, at
# level 3, authors a one-line meaning gloss WITHOUT revealing the word.
_scaffold_coach = Agent(
    name="scaffold",
    model=gemini(),
    instruction=(
        "You are a memorization coach giving the SMALLEST hint that will unstick a "
        "learner on one masked word — never the word itself. You are given the line with "
        "the gap, their (wrong or blank) recall, a ready-made `rhyme_cue` (level 1) and "
        "`first_letter_hint` (level 2), the hidden `expected_word`, and `prior_hint_level` "
        "(the strongest hint already given for this word, 0 if none). Choose the lowest "
        "level above `prior_hint_level` that fits where they stalled: level 1 if rhyme "
        "would jog them, level 2 if they need the letter, level 3 only when 1-2 are spent "
        "— then write a one-line meaning gloss of the word that does NOT contain or "
        "obviously spell the word. Return `hint_level` (1-3) and the `hint` text."
    ),
    output_schema=Hint,
)


# ---------------------------------------------------------------------------
# Deterministic helpers — the key-free, unit-testable half (§8/§11).
# ---------------------------------------------------------------------------

def _recall_text(node_input: Any) -> str:
    """Normalize the learner's resumed recall (str / dict / Runner ``Content``) to text."""
    if isinstance(node_input, str):
        return node_input.strip()
    if isinstance(node_input, dict):
        return str(node_input.get("recall", node_input.get("text", ""))).strip()
    parts = getattr(node_input, "parts", None)
    if parts:
        return "".join(p.text for p in parts if getattr(p, "text", None)).strip()
    return str(node_input or "").strip()


def _partners_for(stanza: dict[str, Any], line_idx: int) -> list[dict]:
    """The rhyme partners of a line; tolerant of int or str map keys (post-JSON)."""
    rpm = stanza.get("rhyme_partner_map", {}) or {}
    return rpm.get(line_idx) or rpm.get(str(line_idx)) or []


def _visible_cues(
    target: dict[str, Any],
    masked_positions: set[tuple[int, int, int]],
    structural_map: dict[str, Any],
) -> dict[str, Any]:
    """Which structural cues were still available to lean on for the target word.

    A rhyme partner counts as a cue only if it is NOT itself masked this session (so
    rung 1 — partner visible — offers it, rung 2 — both masked — does not). Metrical
    regularity is available in a regular stanza; syntactic momentum for a function word.
    """
    stanza = next(
        (s for s in structural_map.get("stanzas", []) if s["index"] == target["stanza_idx"]),
        None,
    )
    rhyme_partner_visible = False
    partner_word = ""
    metrically_regular = False
    if stanza is not None:
        for p in _partners_for(stanza, target["line_idx"]):
            p_line = int(p["line"])
            p_word_idx = len(line_tokens(stanza["lines"][p_line])) - 1
            if (target["stanza_idx"], p_line, p_word_idx) not in masked_positions:
                rhyme_partner_visible = True
                partner_word = str(p.get("word", ""))
                break
        metrically_regular = is_metrically_regular(stanza.get("stress_by_line", []))
    return {
        "rhyme_partner_visible": rhyme_partner_visible,
        "partner_word": partner_word,
        "metrically_regular": metrically_regular,
        "is_stopword": target["word"].lower() in _STOPWORDS,
    }


def _available_cues(target: dict[str, Any], cues: dict[str, Any]) -> set[str]:
    """The crutch classes the learner could legitimately have leaned on for this word."""
    available: set[str] = set()
    if target["crutch_class"] == "rhyme_partner" and cues["rhyme_partner_visible"]:
        available.add("rhyme_partner")
    if cues["metrically_regular"]:
        available.add("metrical_regularity")
    if cues["is_stopword"]:
        available.add("syntactic_momentum")
    return available


def _select_target(session: SessionPlan, requested: Any):
    """The masked word to quiz: an explicit request, else the first word this session adds."""
    if isinstance(requested, dict) and all(
        k in requested for k in ("stanza_idx", "line_idx", "word_idx")
    ):
        want = (int(requested["stanza_idx"]), int(requested["line_idx"]), int(requested["word_idx"]))
        for m in session.masks:
            if (m.stanza_idx, m.line_idx, m.word_idx) == want:
                return m
    newly = [m for m in session.masks if m.rung == session.rung]
    pool = newly or list(session.masks)
    return pool[0] if pool else None


def _target_context(course, structural_map: dict[str, Any], ctx) -> dict[str, Any] | None:
    """Everything ``adjudicate``/``scaffold`` need: the rendered line + visible-cue facts.

    Deterministic: selects the current session and target word, renders the masked line,
    and computes which cues were still visible — the ground truth the LLM is constrained by.
    """
    if not course.sessions:
        return None
    session_index = int(ctx.state.get("session_index", 0))
    session_index = max(0, min(session_index, len(course.sessions) - 1))
    session = course.sessions[session_index]
    span = _select_target(session, ctx.state.get("target"))
    if span is None:
        return None

    target = {
        "stanza_idx": span.stanza_idx,
        "line_idx": span.line_idx,
        "word_idx": span.word_idx,
        "word": span.word,
        "crutch_class": span.crutch_class,
    }
    masked_positions = {(m.stanza_idx, m.line_idx, m.word_idx) for m in session.masks}
    cues = _visible_cues(target, masked_positions, structural_map)

    stanza = next(
        (s for s in structural_map.get("stanzas", []) if s["index"] == span.stanza_idx), None
    )
    # Render the whole STANZA (not just the target line): the rhyme-partner crutch lives
    # ACROSS lines, so the grader must see the still-visible partner to judge whether the
    # learner leaned on it. Each line carries its own session masks; the target word is
    # one of the blanks, identified to the grader by ``word``.
    lines = stanza["lines"] if stanza else []
    rendered_lines = [
        render_masked_line(
            line,
            [m for m in session.masks if m.stanza_idx == span.stanza_idx and m.line_idx == li],
        )
        for li, line in enumerate(lines)
    ]
    line = lines[span.line_idx] if lines else ""
    target_line_masks = [
        m for m in session.masks if m.stanza_idx == span.stanza_idx and m.line_idx == span.line_idx
    ]
    return {
        **target,
        "session_index": session_index,
        "rendered_line": render_masked_line(line, target_line_masks),
        "rendered_stanza": "\n".join(rendered_lines),
        "cues": cues,
        "available_cues": sorted(_available_cues(target, cues)),
    }


def _validate_adjudication(raw: Any, target_context: dict[str, Any]) -> dict[str, Any]:
    """Accept the LLM grade only as far as the ground truth allows (§8 fail-safe).

    Unknown outcome → ``miss``. The crutch-dependence tag survives only on a success AND
    only if it names a cue that was actually available; otherwise it is ``none`` (you
    cannot have leaned on a cue that was not there, or when you did not recall the word).
    """
    data = raw if isinstance(raw, dict) else {}
    outcome = data.get("outcome")
    if outcome not in _VALID_OUTCOMES:
        outcome = "miss"
    dependence = data.get("crutch_dependence", "none")
    if outcome not in _SUCCESS or dependence not in set(target_context.get("available_cues", [])):
        dependence = "none"
    return {
        "outcome": outcome,
        "crutch_dependence": dependence,
        "note": str(data.get("note", "")).strip(),
    }


def _route_for(outcome: str) -> str:
    """Mastered → advance; otherwise scaffold (fail safe — assume more support is needed)."""
    return "advance" if outcome in _SUCCESS else "scaffold"


def _attempt_payload(target_context: dict[str, Any], adjudication: dict[str, Any]) -> dict[str, Any]:
    """The exact field contract ``_attempt_from`` records (graph stays loosely coupled)."""
    return {
        "word": target_context["word"],
        "stanza_idx": target_context["stanza_idx"],
        "line_idx": target_context["line_idx"],
        "word_idx": target_context["word_idx"],
        "crutch_class": target_context["crutch_class"],
        "session_index": target_context["session_index"],
        "outcome": adjudication["outcome"],
        "crutch_dependence": adjudication["crutch_dependence"],
        "note": adjudication["note"],
    }


def _candidate_hints(target_context: dict[str, Any]) -> dict[int, str]:
    """The deterministic level-1/2 hints handed to the coach (rhyme cue, first letter)."""
    word = target_context.get("word", "")
    partner = target_context.get("cues", {}).get("partner_word") or ""
    rhyme = f"It rhymes with “{partner}.”" if partner else "Recall the line's rhyme sound."
    first_letter = f"It starts with “{word[0]}.”" if word else ""
    return {1: rhyme, 2: first_letter}


def _validate_hint(raw: Any, prior_level: int, candidates: dict[int, str]) -> dict[str, Any]:
    """Clamp the coach's hint to 1..3, forbid regressing below an already-given hint.

    A malformed reply (or an empty level-1/2 hint) falls back to the deterministic
    candidate, so scaffolding never returns nothing.
    """
    data = raw if isinstance(raw, dict) else {}
    try:
        level = int(data.get("hint_level"))
    except (TypeError, ValueError):
        level = prior_level + 1
    floor = min(3, prior_level + 1 if prior_level > 0 else 1)
    level = min(3, max(floor, level))
    hint = str(data.get("hint", "")).strip()
    if level < 3 and not hint:
        hint = candidates.get(level, "")
    if not hint:
        hint = candidates.get(level) or candidates.get(2) or candidates.get(1) or "Try the line again."
    return {"hint_level": level, "hint": hint}


# ---------------------------------------------------------------------------
# The graph nodes.
# ---------------------------------------------------------------------------

@node(name="present_masked_line")
async def present_masked_line(ctx, node_input: Any):
    """Render the current masked line from the persisted Course, then pause for recall.

    Loads this learner's Course (the §4 shared-store seam, written by Graph A), rebuilds
    the prosody structural map from the admitted poem text, selects the target word, and
    stashes the visible-cue ``target_context`` for ``adjudicate``. Yields ``RequestInput``
    — the ADK human-in-the-loop pause. If no Course/text is seeded yet (cold start before
    Graph A), it degrades to a bare prompt and records nothing downstream.
    """
    poem_text = ctx.state.get("poem_text") or ""
    poem_id = str(ctx.state.get("poem_id") or "")
    learner_id = str(ctx.state.get("learner_id") or "demo")

    course = load_course(poem_id, learner_id) if poem_id else None
    context = (
        _target_context(course, analyze_poem(poem_text), ctx)
        if course is not None and poem_text
        else None
    )
    ctx.state["target_context"] = context
    if context is None:
        yield RequestInput(message="Recall the masked line:")
        return
    yield RequestInput(
        message=f"Recall the stanza — fill the blanks (we're checking one word):\n{context['rendered_stanza']}"
    )


@node(name="adjudicate", rerun_on_resume=True)
async def adjudicate(ctx, node_input: Any):
    """Grade the recall semantically and emit the crutch-dependence tag (§4/§13.6).

    The LLM grade is a proposal; ``_validate_adjudication`` constrains it to the cues
    that were actually visible. Routes ``advance`` on mastery, else ``scaffold``.
    """
    recall = _recall_text(node_input)
    ctx.state["last_recall"] = recall
    context = ctx.state.get("target_context")
    if not context:
        # Nothing was presented (cold start) — grade nothing, fail safe to scaffold.
        yield Event(output={"todo": "no target presented", "recall": recall}, route="scaffold")
        return

    raw = await ctx.run_node(
        _adjudicator,
        node_input={
            "expected_word": context["word"],
            "masked_stanza": context["rendered_stanza"],
            "learner_recall": recall,
            "available_cues": context["available_cues"],
        },
    )
    adjudication = _validate_adjudication(raw, context)
    attempt = _attempt_payload(context, adjudication)
    yield Event(output=attempt, route=_route_for(adjudication["outcome"]))


@node(name="advance")
async def advance(ctx, node_input: Any):
    """Learner mastered this line; forward the graded attempt to be recorded."""
    yield Event(output=node_input)


@node(name="scaffold", rerun_on_resume=True)
async def scaffold(ctx, node_input: Any):
    """Give the minimum-effective hint where the learner stalled (§3), then record.

    Deterministic rhyme/first-letter cues are handed to the coach; it picks the lowest
    level above any already given and authors a gloss only when those are spent. The
    graded attempt (``node_input``) rides through to ``memory_update`` under ``attempt``.
    """
    context = ctx.state.get("target_context")
    if not context:
        yield Event(output={"attempt": node_input})
        return

    candidates = _candidate_hints(context)
    prior = int(ctx.state.get("hint_level", 0))
    raw = await ctx.run_node(
        _scaffold_coach,
        node_input={
            "masked_line": context["rendered_line"],
            "learner_recall": str(ctx.state.get("last_recall", "")),
            "rhyme_cue": candidates.get(1, ""),
            "first_letter_hint": candidates.get(2, ""),
            "expected_word": context["word"],
            "prior_hint_level": prior,
        },
    )
    hint = _validate_hint(raw, prior, candidates)
    ctx.state["hint_level"] = hint["hint_level"]
    yield Event(output={"attempt": node_input, "hint": hint["hint"], "hint_level": hint["hint_level"]})


def _attempt_from(ctx, node_input: Any) -> Attempt | None:
    """Build an ``Attempt`` from the adjudication outcome, if it carries one.

    Reads the attempt fields either at the top level (the ``advance`` path) or nested
    under ``"attempt"`` (the ``scaffold`` path). The learner id and poem id come from
    session state (minimal-PII, §8). A payload without word + position records nothing,
    so a cold-start run never poisons the store with noise.
    """
    data = node_input if isinstance(node_input, dict) else {}
    src = data.get("attempt") if isinstance(data.get("attempt"), dict) else data
    if not all(k in src for k in ("word", "stanza_idx", "line_idx", "word_idx")):
        return None
    return Attempt(
        learner_id=str(ctx.state.get("learner_id") or "demo"),
        poem_id=str(ctx.state.get("poem_id") or src.get("poem_id") or ""),
        session_index=int(src.get("session_index", 0)),
        stanza_idx=int(src["stanza_idx"]),
        line_idx=int(src["line_idx"]),
        word_idx=int(src["word_idx"]),
        word=str(src["word"]),
        crutch_class=src.get("crutch_class", "none"),
        outcome=str(src.get("outcome", "miss")),
        crutch_dependence=src.get("crutch_dependence", "none"),
    )


@node(name="memory_update")
async def memory_update(ctx, node_input: Any):
    """Persist the graded attempt to Learner Memory (§13.5) — the data the adaptive
    overlay re-plans on next session. Terminal for a single attempt; the next attempt
    re-invokes the workflow (the loop is realized across RequestInput resume cycles, not
    a literal back-edge). Now that ``adjudicate`` emits a real crutch-dependence tag, the
    recorded attempts feed ``profile_from_attempts`` and close the adaptive loop."""
    attempt = _attempt_from(ctx, node_input)
    if attempt is not None:
        LearnerMemory().record(attempt)
    yield Event(
        output={
            "recorded": attempt.to_dict() if attempt is not None else None,
            "outcome": node_input,
        }
    )


# Per-attempt graph. The loop in §4 is across invocations (RequestInput pause/resume),
# so ``memory_update`` is terminal here rather than a back-edge.
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
