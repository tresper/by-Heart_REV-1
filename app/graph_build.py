"""Graph A — the Build Pipeline (blueprint §4).

    [provenance_gate] --admit--> [prosody_analysis] --> [curriculum_plan] --> Course
            └-----------refuse----------> (halt)

All three nodes are now real. ``provenance_gate`` (gate) admits only allowlisted
public-domain poems; ``prosody_analysis`` (a Gemini LLM agent grounded by the
Prosody MCP) reasons over deterministic phonetic ground truth and commits its
anchor-word judgment; ``curriculum_plan`` (§13.4) applies the deterministic
Crutch-Removal Policy and has Gemini author a per-session Deletion Rationale.

Data flow note: the masking schedule must run on PRISTINE phonetic ground truth
(blueprint §8 — LLM output is a proposal, never trusted raw), so ``curriculum_plan``
re-derives the structural map deterministically from the admitted poem text (stashed
in session state by the gate). The genuine LLM dependency that §4 calls for is the
*anchor words* from ``prosody_analysis``, which feed the rung-3 deletions.

API note (verified against installed google-adk 2.3.0): a workflow node is an
async function taking ``(ctx, node_input)``. ``output_schema`` and ``tools`` coexist
on an Agent (tools run in the thought loop; structure is enforced on the final
reply). A ``@node`` may write ``ctx.state[...]`` and, when declared
``rerun_on_resume=True``, may ``await ctx.run_node(agent, ...)`` to invoke a model
mid-graph and get its (schema-validated) output back.
"""

from __future__ import annotations

import sys
from typing import Any

from google.adk.agents import Agent
from google.adk.events.event import Event
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.adk.workflow import START, Workflow, node
from mcp import StdioServerParameters
from pydantic import BaseModel

from app.curriculum.policy import plan_course
from app.curriculum.types import Course
from app.models import gemini
from app.prosody.analysis import analyze_poem
from app.provenance import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_MANIFEST_PATH,
    evaluate_provenance,
    load_manifest,
)


def _as_poem_id(node_input: Any) -> str:
    """Normalize the gate's input to a poem id.

    The id may arrive as a bare string, a dict carrying ``poem_id``, or — when the
    pipeline is driven by a Runner — the user message as a ``Content`` (whose text
    parts hold the id). All three collapse to the id string here.
    """
    if isinstance(node_input, str):
        return node_input.strip()
    if isinstance(node_input, dict):
        return str(node_input.get("poem_id", "")).strip()
    parts = getattr(node_input, "parts", None)
    if parts:
        return "".join(p.text for p in parts if getattr(p, "text", None)).strip()
    return str(node_input).strip()


@node(name="provenance_gate")
async def provenance_gate(ctx, node_input: Any):
    """Admit ONLY poems on the signed public-domain allowlist; else refuse.

    Input: a poem id (string / dict / Runner ``Content`` — see ``_as_poem_id``).
    Emits the structured ``ProvenanceResult`` and routes ``"admit"`` / ``"refuse"``.
    On admission the verified poem id + text are stashed in session state so a
    downstream node can re-derive prosody ground truth without re-loading the file.
    """
    poem_id = _as_poem_id(node_input)
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)
    result = evaluate_provenance(
        poem_id, manifest=manifest, corpus_root=DEFAULT_CORPUS_ROOT
    )
    if result.admitted:
        ctx.state["poem_id"] = result.poem_id
        ctx.state["poem_text"] = result.text
    yield Event(output=result, route="admit" if result.admitted else "refuse")


class ProsodyAnalysis(BaseModel):
    """The structured judgment ``prosody_analysis`` commits (its load-bearing output).

    Only the anchor-word judgment is trusted from the LLM; the phonetic facts
    (rhyme/stress) stay deterministic ground truth derived from the MCP elsewhere.
    """

    anchor_words: list[str]
    notes: str = ""


# prosody_analysis: a Gemini LLM node grounded by the Prosody MCP (§4/§5/§8). It
# calls the MCP's deterministic tools (analyze_poem / scan_line / pronounce), reasons
# over that phonetic ground truth, and emits its anchor-word judgment (validated by
# ``output_schema``; also written to state under ``output_key``). The toolset launches
# the local stdio server on demand; no API key is needed at construction time.
_prosody_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable, args=["-m", "app.prosody.server"]
        ),
        timeout=20.0,
    ),
)

prosody_analysis = Agent(
    name="prosody_analysis",
    model=gemini(),
    instruction=(
        "You analyze a single public-domain poem's prosody. Call the prosody MCP "
        "tools to get DETERMINISTIC ground truth — use `analyze_poem` on the full "
        "poem text for the rhyme scheme, rhyme-partner map, slant rhymes, and "
        "per-line stress. Never guess pronunciations; rely on the tools. Then "
        "identify the ANCHOR WORDS: the high-information content words a learner "
        "leans on to reconstruct a line (concrete nouns, vivid verbs — not function "
        "words). Return ONLY JSON matching the schema: an `anchor_words` list (the "
        "anchor surface forms, as they appear in the poem) and a short `notes` string "
        "explaining your choices."
    ),
    tools=[_prosody_toolset],
    output_schema=ProsodyAnalysis,
    output_key="prosody",
)


class Rationales(BaseModel):
    """One Deletion Rationale per session, in session order."""

    rationales: list[str]


# The Deletion Rationale writer (§4 step 5): a focused Gemini node, no tools. It is
# invoked from inside ``curriculum_plan`` via ``ctx.run_node`` with the deterministic
# schedule, and authors the visible, judge-facing reasoning — the one place the LLM's
# reasoning becomes the surfaced artifact. The schedule itself is NOT model-generated.
_rationale_agent = Agent(
    name="deletion_rationale",
    model=gemini(),
    instruction=(
        "You are given a poem's per-session crutch-removal masking schedule. Each "
        "session lists the words removed THIS session and which crutch each leans on: "
        "`rhyme_partner` (a visible rhyme partner gives the word away), "
        "`metrical_regularity` (the meter lets you reconstruct it), or "
        "`syntactic_momentum` (a function word the syntax auto-fills). For EACH "
        "session, in order, write ONE short Deletion Rationale (2-3 sentences) that "
        "names the crutch being stripped and why the learner was leaning on it, so "
        "recall becomes more unaided. Do not invent words beyond those given. Return "
        'JSON {"rationales": [...]} with exactly one rationale per session, in order.'
    ),
    output_schema=Rationales,
)


_RUNG_BLURB = {
    1: "Removes a rhyme word while its partner stays visible, so recall still leans "
    "on the rhyme crutch.",
    2: "Removes both members of each rhyme pair, so the rhyme can no longer give the "
    "word away.",
    3: "Removes the anchor content words, so metrical regularity alone is no longer "
    "enough to reconstruct the line.",
    4: "Removes nearly the whole line, leaving only scaffolding punctuation for fully "
    "unaided recall.",
}


def _resolve_anchors(node_input: Any, ctx, structural_map: dict[str, Any]) -> list[str]:
    """The LLM's anchor judgment (the §4 dependency), with a deterministic fallback.

    Reads ``prosody_analysis``'s validated output from the node input, then session
    state, and falls back to the deterministic anchor heuristic if the LLM produced
    none — so the schedule is always well-formed, key or no key.
    """
    for src in (node_input, ctx.state.get("prosody")):
        if isinstance(src, dict) and src.get("anchor_words"):
            return list(src["anchor_words"])
    return list(structural_map.get("anchor_candidates", []))


def _rationale_payload(course: Course, structural_map: dict[str, Any]) -> dict[str, Any]:
    """The compact, LLM-facing view of the schedule: what each session removes."""
    sessions = []
    for s in course.sessions:
        removing = [
            {"word": m.word, "crutch": m.crutch_class}
            for m in s.masks
            if m.rung == s.rung  # the words newly removed at this session's rung
        ]
        sessions.append({"session": s.index, "rung": s.rung, "removing": removing})
    return {"poem_id": course.poem_id, "sessions": sessions}


def _attach_rationales(course: Course, raw: Any) -> Course:
    """Fill each session's Deletion Rationale from the LLM reply, fallback per rung."""
    rationales = raw.get("rationales") if isinstance(raw, dict) else None
    sessions = []
    for i, s in enumerate(course.sessions):
        text = ""
        if isinstance(rationales, list) and i < len(rationales):
            text = str(rationales[i]).strip()
        sessions.append(s.with_rationale(text or _RUNG_BLURB.get(s.rung, "")))
    return Course(course.poem_id, course.stanza_count, tuple(sessions), course.rungs_used)


def print_deletion_rationale(course: Course) -> None:
    """Surface the Deletion Rationale on stderr (stdout stays protocol-clean)."""
    print(f"[curriculum_plan] Deletion Rationale for {course.poem_id!r}:", file=sys.stderr)
    for s in course.sessions:
        print(f"  Session {s.index} (rung {s.rung}): {s.rationale}", file=sys.stderr)


@node(name="curriculum_plan", rerun_on_resume=True)
async def curriculum_plan(ctx, node_input: Any):
    """Apply the Crutch-Removal Policy, then have Gemini author the rationale (§13.4).

    The masking *schedule* is deterministic (re-derived on the admitted poem text +
    the LLM's anchor words); the per-session *Deletion Rationale* is the LLM's
    reasoning artifact. Emits the Course as a JSON-friendly dict.
    """
    poem_id = ctx.state.get("poem_id") or ""
    poem_text = ctx.state.get("poem_text") or ""
    structural_map = (
        analyze_poem(poem_text) if poem_text else {"stanzas": [], "anchor_candidates": []}
    )
    anchors = _resolve_anchors(node_input, ctx, structural_map)
    course = plan_course(structural_map, anchors, poem_id)
    raw = await ctx.run_node(
        _rationale_agent, node_input=_rationale_payload(course, structural_map)
    )
    course = _attach_rationales(course, raw)
    print_deletion_rationale(course)
    yield Event(output=course.to_dict())


@node(name="refuse")
async def refuse(ctx, node_input: Any):
    """Terminal node for the refuse route — the Build Pipeline halts here.
    Input is the refusing ``ProvenanceResult`` (it carries the reason)."""
    yield Event(output=node_input)


# The graph. ``provenance_gate`` fans out by route; admit continues the pipeline,
# refuse dead-ends at ``refuse`` (fail closed).
build_pipeline = Workflow(
    name="build_pipeline",
    edges=[
        (START, provenance_gate),
        (provenance_gate, {"admit": prosody_analysis, "refuse": refuse}),
        (prosody_analysis, curriculum_plan),
    ],
)
