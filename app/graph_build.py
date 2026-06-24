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

from app.curriculum.memory import LearnerMemory, profile_from_attempts
from app.curriculum.policy import plan_course
from app.curriculum.types import AdaptationDirective, Course
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
        "recall becomes more unaided. If an `adaptation` block is present, the schedule "
        "was PERSONALIZED to this learner — weave its diagnosis into the session where "
        "that crutch is stripped (why we now remove the cue THIS learner leaned on). "
        "Do not invent words beyond those given. Return JSON "
        '{"rationales": [...]} with exactly one rationale per session, in order.'
    ),
    output_schema=Rationales,
)


class AdaptationProposal(BaseModel):
    """The adaptive overlay's structured choice (§13.5) — the Architect's one decision.

    A proposal, not the schedule: ``_validate_directive`` checks the named class is
    actually present in this poem before the deterministic policy applies it (§8).
    """

    prioritized_crutch: str  # rhyme_partner | metrical_regularity | syntactic_momentum
    diagnosis: str = ""
    target_stanza: int | None = None


# The adaptive Architect (§4 step 4 — the money shot): a focused Gemini node, no
# tools. Invoked from ``curriculum_plan`` with the learner's crutch-dependence
# profile, it CHOOSES which crutch to strip next — the reasoning a ``for`` loop can't
# do (§2). Its choice is validated and applied deterministically; it never authors masks.
_adaptive_planner = Agent(
    name="adaptive_planner",
    model=gemini(),
    instruction=(
        "You are the curriculum Architect adapting a poem's memorization schedule to "
        "ONE learner. You are given their crutch-dependence profile: per crutch class, "
        "`relied_on` (times they recalled a word correctly only because that cue was "
        "still present) and `missed_at` (times they failed at that cue's words), plus "
        "`dominant` (classes ranked by how much they lean on each). Choose the ONE "
        "crutch class to strip next: the support this learner most leans on, so recall "
        "becomes less aided. Prefer the dominant class; for a miss-heavy pattern target "
        "where they repeatedly fail — do NOT merely re-queue exact misses. Return JSON "
        "matching the schema: `prioritized_crutch` (exactly one of rhyme_partner, "
        "metrical_regularity, syntactic_momentum), a short `diagnosis` naming the "
        "pattern and why you strip that cue, and `target_stanza` (an integer) only if "
        "the pattern is confined to one stanza, else null."
    ),
    output_schema=AdaptationProposal,
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


def _rationale_payload(
    course: Course,
    structural_map: dict[str, Any],
    directive: AdaptationDirective | None = None,
) -> dict[str, Any]:
    """The compact, LLM-facing view of the schedule: what each session removes.

    When the schedule was personalized (§13.5), the validated ``directive`` rides
    along so the rationale can name *why this learner* gets that cue stripped now.
    """
    sessions = []
    for s in course.sessions:
        removing = [
            {"word": m.word, "crutch": m.crutch_class}
            for m in s.masks
            if m.rung == s.rung  # the words newly removed at this session's rung
        ]
        sessions.append({"session": s.index, "rung": s.rung, "removing": removing})
    payload: dict[str, Any] = {"poem_id": course.poem_id, "sessions": sessions}
    if directive is not None:
        payload["adaptation"] = {
            "prioritized_crutch": directive.prioritized_crutch,
            "diagnosis": directive.diagnosis,
        }
    return payload


def _validate_directive(
    raw: Any, present_classes: set[str]
) -> AdaptationDirective | None:
    """Accept the LLM's adaptation only if it names a crutch this poem actually has.

    Blueprint §8: the model's choice is a proposal the policy validates, never trusted
    raw. A class the poem doesn't exhibit — or a malformed reply — yields ``None``, so
    the schedule falls back to the deterministic §13.4 base plan (fail safe).
    """
    if not isinstance(raw, dict):
        return None
    cls = raw.get("prioritized_crutch")
    if cls not in present_classes:
        return None
    stanza = raw.get("target_stanza")
    return AdaptationDirective(
        prioritized_crutch=cls,
        diagnosis=str(raw.get("diagnosis", "")).strip(),
        target_stanza=stanza if isinstance(stanza, int) else None,
    )


def _resolve_learner_id(ctx) -> str:
    """The opaque learner id for memory lookup (minimal-PII, §8); ``"demo"`` default."""
    return str(ctx.state.get("learner_id") or "demo")


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
    """Plan the crutch-removal schedule, adapt it to the learner, then author rationale.

    Three layers, in blueprint order: (1) the deterministic Crutch-Removal Policy on
    pristine ground truth + the LLM's anchor words (§13.4); (2) the §13.5 adaptive
    overlay — if this learner has a history, Gemini CHOOSES which crutch to strip
    sooner (validated, then applied deterministically); (3) the LLM Deletion Rationale,
    now personalized. The masking schedule is deterministic at every step; only the
    *choice* and the *prose* are model-generated. Emits the Course as a JSON dict.
    """
    poem_id = ctx.state.get("poem_id") or ""
    poem_text = ctx.state.get("poem_text") or ""
    structural_map = (
        analyze_poem(poem_text) if poem_text else {"stanzas": [], "anchor_candidates": []}
    )
    anchors = _resolve_anchors(node_input, ctx, structural_map)

    # Layer 1: the deterministic base plan (and the crutch classes this poem exhibits).
    base_course = plan_course(structural_map, anchors, poem_id)
    present = {m.crutch_class for s in base_course.sessions for m in s.masks}

    # Layer 2: the adaptive overlay (§13.5). Only when the learner's history shows a
    # lean signal do we ask Gemini which crutch to strip sooner; validate, then re-plan.
    learner_id = _resolve_learner_id(ctx)
    profile = profile_from_attempts(
        poem_id, LearnerMemory().attempts_for(learner_id, poem_id)
    )
    directive: AdaptationDirective | None = None
    if profile.dominant:
        proposal = await ctx.run_node(_adaptive_planner, node_input=profile.to_dict())
        directive = _validate_directive(proposal, present)
    course = (
        plan_course(structural_map, anchors, poem_id, adaptation=directive)
        if directive
        else base_course
    )

    # Layer 3: the visible Deletion Rationale, personalized when an adaptation applied.
    raw = await ctx.run_node(
        _rationale_agent,
        node_input=_rationale_payload(course, structural_map, directive),
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
