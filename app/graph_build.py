"""Graph A — the Build Pipeline (blueprint §4).

    [provenance_gate] --admit--> [prosody_analysis] --> [curriculum_plan] --> Course
            └-----------refuse----------> (halt)

``provenance_gate`` (gate) and ``prosody_analysis`` (Gemini LLM agent grounded by
the Prosody MCP) are implemented; ``curriculum_plan`` remains a stub (§13.4).

API note (verified against installed google-adk 2.3.0): a workflow node is an
async function taking ``(ctx, node_input)`` — a parameter literally named
``node_input`` receives the upstream node's output. A node emits a value and an
optional route via ``Event(output=..., route=...)``; routing-map dicts on an
edge select the next node by that route value. An ``Agent`` is also a valid node.
"""

from __future__ import annotations

import sys
from typing import Any

from google.adk.agents import Agent
from google.adk.events.event import Event
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.adk.workflow import START, Workflow, node
from mcp import StdioServerParameters

from app.models import gemini
from app.provenance import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_MANIFEST_PATH,
    evaluate_provenance,
    load_manifest,
)


@node(name="provenance_gate")
async def provenance_gate(ctx, node_input: Any):
    """Admit ONLY poems on the signed public-domain allowlist; else refuse.

    Input: a poem id (string), or a dict carrying ``poem_id``. Emits the
    structured ``ProvenanceResult`` as output and routes ``"admit"`` /
    ``"refuse"``. All policy + stderr logging lives in ``evaluate_provenance``.
    """
    poem_id = node_input["poem_id"] if isinstance(node_input, dict) else node_input
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)
    result = evaluate_provenance(
        poem_id, manifest=manifest, corpus_root=DEFAULT_CORPUS_ROOT
    )
    yield Event(output=result, route="admit" if result.admitted else "refuse")


# prosody_analysis: a Gemini LLM node grounded by the Prosody MCP (§4/§5/§8).
# It calls the MCP's deterministic tools (analyze_poem / scan_line / pronounce)
# and reasons over that phonetic ground truth to emit the structural map +
# anchor words. The toolset launches the local stdio server on demand; nothing
# is spawned and no API key is needed at construction time (only when it runs).
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
        "per-line stress. Never guess pronunciations; rely on the tools. Then emit "
        "the structural map and identify the anchor words (the high-information "
        "content words a learner leans on), explaining your choices briefly."
    ),
    tools=[_prosody_toolset],
)


@node(name="curriculum_plan")
async def curriculum_plan(ctx, node_input: Any):
    """STUB (§13.4). Will apply the Crutch-Removal Policy + learner history to
    emit a masking schedule and a human-readable Deletion Rationale. Passthrough."""
    yield Event(output={"todo": "curriculum_plan not implemented", "prosody": node_input})


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
