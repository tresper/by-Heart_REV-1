"""Deterministic prosody tests — the §13.3/§12 gate (no API key needed).

Proves the Prosody MCP's ground truth on the real Dickinson seed poem: the
rhyme-partner map (full rhymes) and slant-rhyme detection, plus that the
CMU→elision→g2p resolver leaves no word unresolved.
"""

from __future__ import annotations

import pathlib

from app.prosody.analysis import (
    analyze_poem,
    is_full_rhyme,
    is_slant_rhyme,
    scan_line,
)
from app.prosody.pronounce import PronunciationResolver

_DICKINSON = pathlib.Path(
    "corpus/texts/dickinson-because-i-could-not-stop-for-death.txt"
).read_text(encoding="utf-8")


def _slant_pairs(text: str) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    for stanza in analyze_poem(text)["stanzas"]:
        for p in stanza["slant_rhymes"]:
            pairs.add(frozenset({p["a"].lower(), p["b"].lower()}))
    return pairs


def test_dickinson_slant_rhymes_detected() -> None:
    """The poem's signature slant rhymes are detected (not exact-string equal)."""
    pairs = _slant_pairs(_DICKINSON)
    assert frozenset({"me", "immortality"}) in pairs
    assert frozenset({"away", "civility"}) in pairs
    assert frozenset({"day", "eternity"}) in pairs


def test_dickinson_full_rhymes_classified() -> None:
    """The exact rhymes resolve as full, and a slant pair is NOT full."""
    r = PronunciationResolver()
    assert is_full_rhyme(r.pronounce("done"), r.pronounce("sun"))
    assert is_full_rhyme(r.pronounce("ground"), r.pronounce("mound"))
    assert not is_full_rhyme(r.pronounce("away"), r.pronounce("civility"))
    assert is_slant_rhyme(r.pronounce("away"), r.pronounce("civility"))


def test_rhyme_partner_map_pairs_exact_rhymes() -> None:
    """In a common-meter stanza, the rhyme-partner map links the b-lines."""
    stanza = next(
        s for s in analyze_poem(_DICKINSON)["stanzas"]
        if "done" in " ".join(s["lines"]).lower()
    )
    # lines: 0 played, 1 done, 2 grain, 3 sun  -> 1 and 3 are full-rhyme partners
    partners = stanza["rhyme_partner_map"]
    assert any(p["type"] == "full" for p in partners.get(1, []))
    assert {p["line"] for p in partners.get(1, []) if p["type"] == "full"} == {3}


def test_every_word_resolves_no_oov() -> None:
    """The resolver leaves no token unresolved across the whole poem (§8)."""
    for stanza in analyze_poem(_DICKINSON)["stanzas"]:
        for line in stanza["lines"]:
            for w in scan_line(line)["words"]:
                assert w["source"] != "none", f"unresolved: {w['word']}"
                assert w["phones"], f"no phones: {w['word']}"


def test_resolver_sources_cmu_normalized_g2p() -> None:
    """Each resolution path is exercised by representative words."""
    r = PronunciationResolver()
    assert r.pronounce("death").source == "cmu"
    assert r.pronounce("o'er").source == "normalized"  # elision -> CMU "over"
    assert r.pronounce("anchor'd").source == "normalized"
    cornice = r.pronounce("cornice")  # truly out-of-dictionary -> g2p
    assert cornice.source == "g2p" and cornice.phones
    recuerdo = r.pronounce("Recuerdo")  # proper noun -> g2p predicts it
    assert recuerdo.source == "g2p" and recuerdo.phones
