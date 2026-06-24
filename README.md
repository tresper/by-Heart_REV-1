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
- [`stride-threat-model`](.claude/skills/stride-threat-model/SKILL.md) — the STRIDE threat
  model for the two graphs: each category mapped to By Heart's concrete control and where it
  lives in code

## Security

The attack surface is small **by design** (no accounts, no open-ended poem ingestion, no cloud
deploy) and the controls are explicit and tested:

- **Threat model.** [`stride-threat-model`](.claude/skills/stride-threat-model/SKILL.md) walks
  each STRIDE category and names the control and its code location.
- **Recall-input validation.** A learner's typed recall is the one untrusted input. It is
  sanitized at a single choke point ([`app/security/recall_input.py`](app/security/recall_input.py))
  before any model sees it — length-bounded, control/zero-width/bidi codepoints stripped,
  newlines collapsed — while legitimate poetic tokens (`o'er`, `café`) survive.
- **Prompt-injection containment is structural.** The Adjudicator and Coach are told the recall
  is untrusted data, but the guarantee is that their output is a *validated proposal*: the grade
  is clamped to the legal vocabulary and the crutch tag to cues that were actually visible. A
  model fully swayed by an injected recall still cannot emit an illegal grade, fabricate a tag,
  or over-escalate a hint.
- **Minimal-PII + secrets hygiene.** Identity is an opaque `learner_id`; the free-text recall is
  **never persisted** (the attempt record has no field for it). The Gemini key lives only in
  `.env` (gitignored); `.env.example` ships placeholders.

**Run the injection/PII eval** (blueprint DoD #5):

```
uv run python -m evals.injection_pii_eval
```

It prints a per-scenario PASS/FAIL table — injection containment, the input sanitizer, and
PII-minimization — and exits non-zero on any failure. The deterministic checks need no API key;
the live model scenarios run when a Gemini key is present. The same checks run under
`uv run pytest`.