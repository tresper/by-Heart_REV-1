"""Recall-input validation — the one untrusted input, hardened at the choke point.

A learner's typed recall is the only untrusted text in either graph: everything else the
LLM nodes reason over (the expected word, the masked stanza, the available cues, the
rhyme/first-letter hints) is derived deterministically from a vetted public-domain poem.
That recall flows into the Adjudicator and Scaffolding Coach prompts, so it is the system's
prompt-injection surface (blueprint §8).

``sanitize_recall`` neutralizes the *mechanical* injection/obfuscation vectors — unbounded
length, control characters, invisible zero-width/bidirectional codepoints, and embedded
newlines that could fake prompt structure — while preserving every legitimate poetic token
(apostrophes in ``o'er``, hyphens, accents in ``café``). It is deliberately NON-rejecting:
a recall is judged on *content* by the validated-proposal pipeline (``_validate_adjudication``
clamps the grade to the legal vocabulary and the crutch tag to cues that were actually
visible — the real containment), so this layer only strips characters that can never be
part of a genuine one-line answer. Pure and key-free, hence unit-testable in isolation.
"""

from __future__ import annotations

import re
import unicodedata

# A recall is one masked word or a short line — never a paragraph. Bounding the length
# caps the injection payload a single answer can carry (also a context-stuffing / DoS guard).
MAX_RECALL_CHARS = 200

# Collapse any run of whitespace — including the newlines a learner cannot meaningfully type
# into a one-line answer but an injection would use to fake a system/role turn — to one space.
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_recall(text: str) -> str:
    """Return a single-line, bounded, control-free version of a learner's recall.

    Drops Unicode *format* characters (category ``Cf`` — zero-width spaces/joiners, the
    bidirectional overrides and isolates, soft hyphen, BOM): invisible vectors that never
    belong in a real answer. Converts other control characters (``Cc`` etc. — newlines,
    tabs, NULs) to spaces, collapses whitespace, trims, and truncates to
    ``MAX_RECALL_CHARS``. Legitimate tokens survive unchanged. Never raises; coerces
    non-``str`` input first.
    """
    s = text if isinstance(text, str) else str(text or "")
    cleaned: list[str] = []
    for ch in s:
        category = unicodedata.category(ch)
        if category == "Cf":
            continue  # invisible format/zero-width/bidi codepoint — remove, don't space-split
        cleaned.append(" " if category[0] == "C" else ch)  # other control chars → boundary
    collapsed = _WHITESPACE_RE.sub(" ", "".join(cleaned)).strip()
    return collapsed[:MAX_RECALL_CHARS].strip()


def contains_word(word: str, text: str) -> bool:
    """True if ``word`` appears as a standalone token (case-insensitive) in ``text``.

    The answer-leak predicate shared by the Scaffolding Coach's hint guard
    (``_validate_hint``) and the live injection eval: a hint may cite the rhyme partner
    or a first letter, but never the masked word itself. Word-boundary (not substring)
    matching so a longer word that merely contains the answer — or an unrelated token —
    does not false-trip. Empty ``word`` matches nothing.
    """
    if not word:
        return False
    return re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE) is not None
