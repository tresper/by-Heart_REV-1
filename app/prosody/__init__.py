"""Prosody: deterministic phonetic ground truth for By Heart (blueprint §8).

CMU-primary pronunciation with a poetic-elision normalizer and a gruut g2p
fallback, plus scansion and rhyme analysis. Pure Python, import-light, and
stdout-silent so it can back the Prosody MCP server without corrupting its
JSON-RPC channel.
"""
