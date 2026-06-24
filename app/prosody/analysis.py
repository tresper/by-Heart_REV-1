"""Scansion + rhyme analysis — the deterministic structural map (blueprint §4/§8).

Pure functions over poem lines, built on the PronunciationResolver. Produces the
ground truth the LLM nodes reason over: per-line stress, rhyme scheme, the
rhyme-partner map, slant-rhyme detection, and anchor-word candidates. Rhyme
analysis runs WITHIN stanzas (split on blank lines), as rhyme conventionally does.
"""

from __future__ import annotations

import re

from app.prosody.pronounce import ARPABET_VOWELS, Pronunciation, PronunciationResolver

_resolver = PronunciationResolver()

# Coarse near-vowel groups for slant rhyme (ARPAbet, stress-stripped). Same group
# = phonetically near (e.g. the high-front IY/IH/EY cluster that makes Dickinson's
# "away/civility" and "day/eternity" slant-rhyme).
_NEAR_VOWEL_GROUPS = [
    {"IY", "IH", "EY"}, {"EH", "AE"}, {"AA", "AO", "AH"},
    {"UW", "UH", "OW"}, {"ER"}, {"AW"}, {"AY"}, {"OY"},
]

_STOPWORDS = frozenset(
    "the a an and or but of to in on at by for with as is was are were be been "
    "i you he she it we they me my his her its our their that this these those "
    "not no so if then than too s t".split()
)


def _bare(phone: str) -> str:
    """Strip the stress digit from an ARPAbet phone (EH1 -> EH)."""
    return phone[:-1] if phone and phone[-1].isdigit() else phone


def final_word(line: str) -> str:
    """The last alphabetic token of a line (rhyme-bearing word)."""
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", line)
    return words[-1] if words else ""


def rhyme_key(pron: Pronunciation) -> tuple[str, ...]:
    """The exact-rhyme tail: phones from the last primary-stressed vowel, bare."""
    idx = max(
        (i for i, p in enumerate(pron.phones) if p.endswith("1")), default=None
    )
    if idx is None:  # no primary stress: fall back to last vowel
        idx = max(
            (i for i, p in enumerate(pron.phones) if p[:2] in ARPABET_VOWELS),
            default=0,
        )
    return tuple(_bare(p) for p in pron.phones[idx:])


def _end_vowel(pron: Pronunciation) -> str:
    return next(
        (_bare(p) for p in reversed(pron.phones) if p[:2] in ARPABET_VOWELS), ""
    )


def _coda(pron: Pronunciation) -> tuple[str, ...]:
    """Consonants trailing the final vowel (empty for open syllables)."""
    tail: list[str] = []
    for p in reversed(pron.phones):
        if p[:2] in ARPABET_VOWELS:
            break
        tail.append(_bare(p))
    return tuple(reversed(tail))


def _near(v1: str, v2: str) -> bool:
    return v1 == v2 or any(v1 in g and v2 in g for g in _NEAR_VOWEL_GROUPS)


def is_full_rhyme(p1: Pronunciation, p2: Pronunciation) -> bool:
    """True exact rhyme: identical stressed tails, different words."""
    return p1.word.lower() != p2.word.lower() and rhyme_key(p1) == rhyme_key(p2)


def is_slant_rhyme(p1: Pronunciation, p2: Pronunciation) -> bool:
    """Near rhyme: not a full rhyme, but near vowel + matching coda (assonance
    on open syllables, or consonance), e.g. away/civility, me/Immortality."""
    if not p1.phones or not p2.phones or is_full_rhyme(p1, p2):
        return False
    if p1.word.lower() == p2.word.lower():
        return False
    return _coda(p1) == _coda(p2) and _near(_end_vowel(p1), _end_vowel(p2))


def scan_line(line: str) -> dict:
    """Per-word pronunciation + the line's stress pattern (the scansion)."""
    words = [
        _resolver.pronounce(w) for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", line)
    ]
    return {
        "line": line,
        "stress": "".join(p.stress for p in words),
        "words": [
            {"word": p.word, "phones": list(p.phones), "stress": p.stress, "source": p.source}
            for p in words
        ],
    }


def _finals(lines: list[str]) -> list[Pronunciation]:
    return [_resolver.pronounce(final_word(ln)) for ln in lines if final_word(ln)]


def rhyme_scheme(lines: list[str]) -> list[str]:
    """Assign rhyme letters (a, b, c, …) by exact rhyme over line-final words."""
    finals = _finals(lines)
    labels: list[str] = []
    reps: list[Pronunciation] = []
    for pron in finals:
        for i, rep in enumerate(reps):
            if pron.word.lower() == rep.word.lower() or rhyme_key(pron) == rhyme_key(rep):
                labels.append(chr(ord("a") + i))
                break
        else:
            labels.append(chr(ord("a") + len(reps)))
            reps.append(pron)
    return labels


def rhyme_partner_map(lines: list[str]) -> dict[int, list[dict]]:
    """For each line index, its rhyme partners (full or slant) with the type."""
    finals = _finals(lines)
    out: dict[int, list[dict]] = {}
    for i, a in enumerate(finals):
        partners = []
        for j, b in enumerate(finals):
            if i == j:
                continue
            kind = "full" if is_full_rhyme(a, b) else "slant" if is_slant_rhyme(a, b) else None
            if kind:
                partners.append({"line": j, "word": b.word, "type": kind})
        if partners:
            out[i] = partners
    return out


def slant_rhymes(lines: list[str]) -> list[dict]:
    """All slant (near-but-not-exact) rhyme pairs among line-final words."""
    finals = _finals(lines)
    pairs = []
    for i in range(len(finals)):
        for j in range(i + 1, len(finals)):
            if is_slant_rhyme(finals[i], finals[j]):
                pairs.append({"a": finals[i].word, "b": finals[j].word, "lines": [i, j]})
    return pairs


def anchor_candidates(lines: list[str]) -> list[str]:
    """Content-word heuristic (the LLM node refines this later)."""
    seen: list[str] = []
    for ln in lines:
        for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", ln):
            lw = w.lower()
            if len(lw) >= 4 and lw not in _STOPWORDS and lw not in [s.lower() for s in seen]:
                seen.append(w)
    return seen


def _stanzas(text: str) -> list[list[str]]:
    """Split a poem into stanzas on blank lines; keep nonblank lines."""
    out, cur = [], []
    for raw in text.splitlines():
        if raw.strip():
            cur.append(raw)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def analyze_poem(text: str) -> dict:
    """The full structural map: rhyme + scansion, computed within stanzas."""
    stanzas = _stanzas(text)
    result_stanzas = []
    for s_idx, lines in enumerate(stanzas):
        result_stanzas.append(
            {
                "index": s_idx,
                "lines": lines,
                "rhyme_scheme": rhyme_scheme(lines),
                "rhyme_partner_map": rhyme_partner_map(lines),
                "slant_rhymes": slant_rhymes(lines),
                "stress_by_line": [scan_line(ln)["stress"] for ln in lines],
            }
        )
    return {
        "stanza_count": len(stanzas),
        "stanzas": result_stanzas,
        "anchor_candidates": anchor_candidates([ln for s in stanzas for ln in s]),
    }
