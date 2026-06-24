"""The Crutch-Removal Deletion Policy (blueprint §4) — deterministic and key-free.

This is the project's technical signature, made falsifiable. Given the prosody
structural map (deterministic ground truth from the Prosody MCP) and the anchor
words (the LLM's judgment from ``prosody_analysis``), it builds a multi-session
masking schedule that escalates by *stripping the cue a learner leans on*, not by
masking a fixed ratio:

  Rung 1  mask the LATER word of each rhyme pair, partner still visible — the
          learner can still lean on the rhyme crutch.
  Rung 2  mask BOTH members of each rhyme pair — rhyme can no longer bridge.
  Rung 3  add the anchor (content) words — meter/meaning alone is now insufficient.
  Rung 4  near-whole-line — only scaffolding punctuation remains.

Masks are cumulative across sessions; each is tagged with the crutch class it
removes and the rung that introduced it. The prose Deletion Rationale is authored
by the LLM node downstream; nothing here calls a model, so the schedule is a
deterministic, unit-testable artifact (blueprint §8/§11). ``history`` is a typed
seam for the §13.5 adaptive overlay (re-order which crutch is stripped next based
on the learner's error patterns); it is accepted and documented but unused now.
"""

from __future__ import annotations

from typing import Any

from app.curriculum.types import Course, CrutchClass, MaskedSpan, SessionPlan, line_tokens
from app.prosody.analysis import _STOPWORDS

_N_RUNGS = 4


def is_metrically_regular(stress_by_line: list[str]) -> bool:
    """True if a stanza's lines are predominantly alternating-stress.

    Accentual-syllabic meter (common/iambic meter, the corpus baseline) makes a
    word's stress slot predictable — the "metrical regularity" crutch. We treat a
    stanza as regular when a majority of its lines' stress strings mostly alternate.
    """
    if not stress_by_line:
        return False
    regular = sum(1 for s in stress_by_line if _is_alternating(s))
    return regular >= (len(stress_by_line) + 1) // 2


def _is_alternating(stress: str, *, min_len: int = 4) -> bool:
    """A stress string mostly alternates between stressed/unstressed digits."""
    if len(stress) < min_len:
        return False
    alternations = sum(1 for a, b in zip(stress, stress[1:]) if a != b)
    return alternations >= (len(stress) - 1) * 0.6


def _rhyme_pairs(stanza: dict[str, Any]) -> list[tuple[int, int]]:
    """Distinct (earlier_line, later_line) rhyme pairs within a stanza.

    Both full and slant partners count: a visible slant partner is still a crutch
    the learner can lean on. Keyed off the deterministic ``rhyme_partner_map``.
    """
    seen: set[frozenset[int]] = set()
    pairs: list[tuple[int, int]] = []
    for i, partners in stanza.get("rhyme_partner_map", {}).items():
        for p in partners:
            key = frozenset({int(i), int(p["line"])})
            if len(key) == 2 and key not in seen:
                seen.add(key)
                pairs.append((min(key), max(key)))
    return pairs


def classify_crutches(
    stanza: dict[str, Any], anchors: set[str]
) -> dict[tuple[int, int], CrutchClass]:
    """Tag every token position in a stanza with the dominant crutch it leans on.

    Precedence (strongest cue first): a line-final word in a rhyme pair leans on
    its rhyme partner; an anchor (content) word leans on metrical regularity; a
    function/stop word rides syntactic momentum; anything else has no strong crutch.
    """
    rhyme_lines = {ln for pair in _rhyme_pairs(stanza) for ln in pair}
    out: dict[tuple[int, int], CrutchClass] = {}
    for line_idx, line in enumerate(stanza["lines"]):
        tokens = line_tokens(line)
        last = len(tokens) - 1
        for word_idx, tok in enumerate(tokens):
            lw = tok.lower()
            if line_idx in rhyme_lines and word_idx == last:
                cls: CrutchClass = "rhyme_partner"
            elif lw in anchors:
                cls = "metrical_regularity"
            elif lw in _STOPWORDS:
                cls = "syntactic_momentum"
            else:
                cls = "none"
            out[(line_idx, word_idx)] = cls
    return out


def _stanza_spans(
    stanza: dict[str, Any], stanza_idx: int, anchors: set[str]
) -> list[MaskedSpan]:
    """Assign every maskable word in a stanza to its crutch-removal rung."""
    cls_map = classify_crutches(stanza, anchors)
    tokens_by_line = [line_tokens(line) for line in stanza["lines"]]

    rung_of: dict[tuple[int, int], int] = {}
    for earlier, later in _rhyme_pairs(stanza):
        rung_of[(later, len(tokens_by_line[later]) - 1)] = 1  # later member first
        rung_of.setdefault((earlier, len(tokens_by_line[earlier]) - 1), 2)  # then both
    for pos, cls in cls_map.items():  # anchors removed next (rung 3)
        if pos not in rung_of and cls == "metrical_regularity":
            rung_of[pos] = 3
    for pos in cls_map:  # everything else fills in at rung 4 (near-whole-line)
        rung_of.setdefault(pos, _N_RUNGS)

    spans: list[MaskedSpan] = []
    for (line_idx, word_idx), rung in rung_of.items():
        spans.append(
            MaskedSpan(
                stanza_idx=stanza_idx,
                line_idx=line_idx,
                word_idx=word_idx,
                word=tokens_by_line[line_idx][word_idx],
                crutch_class=cls_map[(line_idx, word_idx)],
                rung=rung,
            )
        )
    return spans


def plan_course(
    structural_map: dict[str, Any],
    anchors: list[str],
    poem_id: str,
    *,
    history: Any | None = None,  # SEAM for §13.5 adaptive overlay; unused now
    n_sessions: int = _N_RUNGS,
) -> Course:
    """Build the multi-session crutch-removal Course for one poem.

    Each session reaches one rung higher; its masks are the cumulative union of
    every word introduced at or below that rung (so a session can be presented
    standalone). When two rungs would mask the same word, the lower (earlier) rung
    wins, so a rhyme word stays tagged ``rhyme_partner`` rather than being relabeled
    when the near-whole-line rung sweeps everything.
    """
    stanzas = structural_map.get("stanzas", [])
    anchor_set = {a.lower() for a in anchors}

    # All spans across the poem, deduplicated by position keeping the lowest rung.
    introduced: dict[tuple[int, int, int], MaskedSpan] = {}
    for stanza in stanzas:
        for span in _stanza_spans(stanza, stanza["index"], anchor_set):
            pos = (span.stanza_idx, span.line_idx, span.word_idx)
            if pos not in introduced or span.rung < introduced[pos].rung:
                introduced[pos] = span

    sessions: list[SessionPlan] = []
    for k in range(n_sessions):
        rung = min(k + 1, _N_RUNGS)
        masks = tuple(
            sorted(
                (s for s in introduced.values() if s.rung <= rung),
                key=lambda s: (s.stanza_idx, s.line_idx, s.word_idx),
            )
        )
        sessions.append(SessionPlan(index=k, rung=rung, masks=masks))

    rungs_used = tuple(sorted({s.rung for s in sessions}))
    return Course(
        poem_id=poem_id,
        stanza_count=len(stanzas),
        sessions=tuple(sessions),
        rungs_used=rungs_used,
    )
