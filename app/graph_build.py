"""Graph A — the Build Pipeline (blueprint §4).

    [provenance_gate] --admit--> [prosody_analysis] --> [curriculum_plan] --> Course
            └-----------refuse----------> (halt)

Only ``provenance_gate`` is implemented in this phase; ``prosody_analysis`` and
``curriculum_plan`` are explicit stubs that pass their input through with a TODO
marker so the graph constructs and is walkable without faking poem analysis.

API note (verified against installed google-adk 2.3.0): a workflow node is an
async function taking ``(ctx, node_input)`` — a parameter literally named
``node_input`` receives the upstream node's output. A node emits a value and an
optional route via ``Event(output=..., route=...)``; routing-map dicts on an
edge select the next node by that route value.
"""

from __future__ import annotations

from typing import Any

from google.adk.events.event import Event
from google.adk.workflow import START, Workflow, node

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


@node(name="prosody_analysis")
async def prosody_analysis(ctx, node_input: Any):
    """STUB (§13.3). Will call the Prosody MCP for meter/stress, rhyme scheme,
    the rhyme-partner map, and anchor words. For now: passthrough + TODO marker."""
    yield Event(output={"todo": "prosody_analysis not implemented", "admitted": node_input})


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
