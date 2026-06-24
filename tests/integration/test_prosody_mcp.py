"""Integration tests for the Prosody MCP server over real stdio JSON-RPC.

A successful client round-trip is itself the stdout-hygiene assertion: any stray
write to the server's stdout would corrupt the JSON-RPC stream and break the
client. We also assert the server module imports with a silent stdout.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_MINI_POEM = "away\nhaste\ntoo\ncivility"  # away ~ civility is a slant rhyme


async def _call(tool: str, args: dict) -> dict:
    params = StdioServerParameters(command=sys.executable, args=["-m", "app.prosody.server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            return json.loads(result.content[0].text)


def test_server_lists_and_calls_tools_over_stdio() -> None:
    """The server exposes the prosody tools and analyze_poem returns the map.

    The round-trip succeeding proves stdout carried only valid JSON-RPC.
    """
    data = asyncio.run(_call("analyze_poem", {"text": _MINI_POEM}))
    stanza = data["stanzas"][0]
    slant = {frozenset({p["a"].lower(), p["b"].lower()}) for p in stanza["slant_rhymes"]}
    assert frozenset({"away", "civility"}) in slant


def test_pronounce_tool_resolves_oov_over_stdio() -> None:
    data = asyncio.run(_call("pronounce", {"word": "cornice"}))
    assert data["source"] == "g2p" and data["phones"]


def test_server_import_is_stdout_silent() -> None:
    """Importing the server module must print nothing to stdout (MCP hygiene)."""
    out = subprocess.run(
        [sys.executable, "-c", "import app.prosody.server"],
        capture_output=True, text=True, cwd=".",
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout == "", f"unexpected stdout: {out.stdout!r}"
