# by-Heart_REV-1

By Heart turns a vetted public-domain poem into a personalized, prosody-aware
memorization course using a multi-agent **Google ADK 2.0** system on Gemini.

## Architecture (two ADK graphs)

**Build Pipeline (Graph A)** — runs once per poem:
`provenance_gate` (admits only allowlisted public-domain poems) → `prosody_analysis`
(a Gemini agent grounded by the **Prosody MCP** — CMU dict + g2p — that commits the
anchor words) → `curriculum_plan` (the **Crutch-Removal Policy**: a deterministic,
multi-session masking schedule that escalates by stripping the cue a learner leans on
— visible rhyme partner → metrical regularity → syntactic momentum — plus a
per-session, human-readable **Deletion Rationale**).

**Recall Session Loop (Graph B)** — per study session, human-in-the-loop via
`RequestInput`: `present_masked_line` (renders the masked stanza from the persisted
Course) → learner recall → `adjudicate` (a Gemini node that grades **semantically** —
hit / near-miss / variant / miss, never a string compare — and tags **which still-visible
crutch the recall leaned on**) → advance / `scaffold` (a graduated minimum hint: rhyme
cue → first letter → meaning gloss) → `memory_update`. The crutch-dependence tag is the
Adjudicator's *proposal*, validated against the cues that were actually visible for that
word (a cue that wasn't shown, or a missed recall, leans on nothing) — so the tag stays
honest and the deterministic half is unit-testable without a key.

**Adaptive re-planning (the money shot).** `memory_update` records each attempt to a
small **Learner Memory** store (`app/curriculum/memory.py`); a deterministic
reduction turns that history into a crutch-dependence profile, and `curriculum_plan`
has Gemini **choose which crutch to strip next** for *this* learner. The choice is
validated against the poem and applied deterministically, so the masking schedule
stays falsifiable while the Deletion Rationale personalizes — e.g. *"because you have
developed a strong reliance on the poem's metrical cadence, we strip that cue now."*
The masking schedule is deterministic at every step; only the *choice* and the
*prose* are model-generated (see [`DECISIONS.md`](DECISIONS.md)).

The loop is now **closed end-to-end**: `adjudicate` emits the real crutch-dependence
tag, `memory_update` persists it, the profile picks it up, and the *next* Build run
strips a *different* crutch — play a session and watch the schedule adapt. The demo
runs in the `agents-cli` local playground (no custom UI needed).

## Agent Skills

This project demonstrates the course's **Agent skills** concept via authored `SKILL.md`
files that Claude Code loads during development. They live in [`.claude/skills/`](.claude/skills/):

- [`provenance-gate`](.claude/skills/provenance-gate/SKILL.md) — enforces the public-domain
  corpus allowlist when adding poems and maintaining the provenance_gate node