"""Prosody MCP server — a local stdio MCP exposing deterministic prosody tools.

This is the custom MCP server of blueprint §5/§8: it wraps the CMU dict + gruut
g2p resolver and the scansion/rhyme analysis as MCP tools that `prosody_analysis`
(and later `adjudicate`) call at runtime for phonetic ground truth.

stdout hygiene (CLAUDE.md / §8): the stdio transport owns stdout for JSON-RPC, so
this module must write NOTHING else to stdout. All diagnostics go to stderr. Run:
    python -m app.prosody.server
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from app.prosody.analysis import analyze_poem as _analyze_poem
from app.prosody.analysis import scan_line as _scan_line
from app.prosody.pronounce import PronunciationResolver

# Logs to stderr only — never pollute the JSON-RPC stdout channel.
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

mcp = FastMCP("prosody")
_resolver = PronunciationResolver()


@mcp.tool()
def pronounce(word: str) -> dict:
    """ARPAbet pronunciation of a word (CMU → elision → gruut g2p fallback).

    Returns phones, the stress pattern (digits 0/1/2), and `source`
    (cmu | normalized | g2p) so the caller can see how it was resolved.
    """
    p = _resolver.pronounce(word)
    return {"word": p.word, "phones": list(p.phones), "stress": p.stress, "source": p.source}


@mcp.tool()
def scan_line(line: str) -> dict:
    """Scansion of one line: per-word pronunciation + the line stress pattern."""
    return _scan_line(line)


@mcp.tool()
def analyze_poem(text: str) -> dict:
    """The structural map for a whole poem: per-stanza rhyme scheme, rhyme-partner
    map, slant-rhyme detection, per-line stress, and anchor-word candidates."""
    return _analyze_poem(text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
