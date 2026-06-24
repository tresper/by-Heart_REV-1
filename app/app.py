"""Entry point exposing By Heart's two ADK 2.0 graphs (blueprint §4).

Graph A (Build Pipeline) turns a vetted public-domain poem into a Course;
Graph B (Recall Session Loop) runs the human-in-the-loop study session. Both are
imported here so tooling (and later the agents-cli playground) has one place to
find them. Model/runtime wiring is deferred until an LLM node is implemented.
"""

from __future__ import annotations

from app.graph_build import build_pipeline
from app.graph_recall import recall_session

__all__ = ["build_pipeline", "recall_session"]
