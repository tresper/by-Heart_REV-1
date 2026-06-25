"""By Heart Web — a FastAPI trainer that drives the existing ADK graphs live.

This package adds NO pedagogy. It is a thin async driver over the same two ADK 2.0
graphs (``app.graph_build.build_pipeline`` and ``app.graph_recall.recall_session``) and
the Prosody MCP the rest of By Heart already ships — imported by reference, never forked
or modified. Its only new capability is presentation: serving a browser UI, feeding the
``RequestInput`` human-in-the-loop pause from a web form, and streaming each ADK node
transition to the page so a human watches the graphs execute as they memorize the poem.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
