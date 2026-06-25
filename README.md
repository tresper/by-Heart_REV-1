# By Heart

**An agentic tutor that turns any public-domain poem into a personalized, prosody-aware
memorization course — doing autonomously, for any poem and any learner, what the New York
Times Poetry Challenge did by hand for a single one.**

## The problem, and why it needs agents

The NYT Poetry Challenge (2025) proved that millions of people want to memorize poems — but it
took an editorial team to build **one** course for **one** poem, with a **fixed** masking path
and **self-graded** recall. Progressive masking on a fixed schedule needs no intelligence; a
`for` loop does it. What *can't* be a `for` loop is the judgment By Heart automates:

- **Curriculum design** — reading a poem's scansion and rhyme structure to plan a multi-session
  course.
- **Crutch-removal** — noticing that a learner only "knew" a word because its rhyme partner gave
  it away, and stripping *that* support next.
- **Semantic grading** — scoring a recall as hit / near-miss / meaningful-variant / miss, never a
  string compare.

By Heart generalizes all three axes — any vetted poem, any learner, graded and re-planned by the
agents themselves — built as a two-graph **Google ADK 2.0** multi-agent system on **Gemini**.

## Architecture (two ADK graphs)

> **New to agentic systems?** For a narrative, concept-by-concept walkthrough — with one-line
> definitions of ADK, MCP, Gemini, nodes, graphs, and conditional routing as they come up — read
> **[How By Heart uses an agentic workflow](docs/HOW_THIS_APP_USES_AGENTIC_WORKFLOW.md)**. The
> sections below are the terse reference version. For how the project itself was built with an AI
> coding assistant — phases, recovery-friendly git, TDD, a living decision log, and multi-agent
> review — see **[How this app was built](docs/HOW_THIS_APP_WAS_BUILT.md)**.

**Build Pipeline (Graph A)** — runs once per poem:
`provenance_gate` (admits only allowlisted public-domain poems) → `prosody_analysis`
(a Gemini agent grounded by the **Prosody MCP** — CMU dict + g2p — that commits the
anchor words) → `curriculum_plan` (the **Crutch-Removal Policy**: a deterministic,
multi-session masking schedule that escalates by stripping the cue a learner leans on
— visible rhyme partner → metrical regularity → syntactic momentum — plus a
per-session, human-readable **Deletion Rationale**).

```
[provenance_gate]  admit ONLY poems on the public-domain allowlist; else refuse
       │ admit
       ▼
[prosody_analysis] ──MCP──► Prosody MCP server   meter/stress, rhyme scheme,
       │                                         rhyme-partner map, anchor words
       ▼
[curriculum_plan]  Crutch-Removal Policy + this learner's history →
       │           masking schedule + a human-readable DELETION RATIONALE
       ▼
   Course  ──►  per-learner Course store
```

**Recall Session Loop (Graph B)** — per study session, human-in-the-loop via
`RequestInput`: `present_masked_line` (renders the masked stanza from the persisted
Course) → learner recall → `adjudicate` (a Gemini node that grades **semantically** —
hit / near-miss / variant / miss, never a string compare — and tags **which still-visible
crutch the recall leaned on**) → advance / `scaffold` (a graduated minimum hint: rhyme
cue → first letter → meaning gloss) → `memory_update`. The crutch-dependence tag is the
Adjudicator's *proposal*, validated against the cues that were actually visible for that
word (a cue that wasn't shown, or a missed recall, leans on nothing) — so the tag stays
honest and the deterministic half is unit-testable without a key.

```
[present_masked_line] ──► [RequestInput: learner types recall] ──► [adjudicate]
                                                                        │ hit/near-miss/
                                                                        │ variant/miss
                                                  ┌── advance ──────────┤ + CRUTCH-
                                                  │                     │   DEPENDENCE TAG
                                                  ▼                     └── scaffold (min hint)
                                            [memory_update]  persist attempt + crutch tag
                                                  │
                              re-planned by Graph A next session ◄──────┘
```

**Adaptive re-planning (the money shot).** `memory_update` records each attempt to a
small **Learner Memory** store (`app/curriculum/memory.py`); a deterministic
reduction turns that history into a crutch-dependence profile, and `curriculum_plan`
has Gemini **choose which crutch to strip next** for *this* learner. The choice is
validated against the poem and applied deterministically, so the masking schedule
stays falsifiable while the Deletion Rationale personalizes — e.g. *"because you have
developed a strong reliance on the poem's rhyme partners, we strip that cue now."*
The masking schedule is deterministic at every step; only the *choice* and the
*prose* are model-generated (see [`DECISIONS.md`](DECISIONS.md)).

The loop is **closed end-to-end**: `adjudicate` emits the real crutch-dependence
tag, `memory_update` persists it, the profile picks it up, and the *next* Build run
strips a *different* crutch — play a session and watch the schedule adapt.

### Agent / node / tool / services taxonomy

- **Orchestration = the two `Workflow` graphs themselves** — there is no separate
  "director" LLM; the graphs are the agents.
- **LLM nodes** (each does reasoning a `for` loop cannot): `prosody_analysis`,
  `curriculum_plan`, `adjudicate`, `scaffold`.
- **Tool**: the **Prosody MCP server** (`app/prosody/server.py`) — CMU Pronouncing
  Dictionary + a grapheme-to-phoneme fallback so every archaic/poetic token resolves —
  called at runtime to provide deterministic phonetic ground truth the LLM nodes reason over.
- **Services / data**: ADK **Session & Memory** for learner state, the **provenance
  allowlist** (the public-domain guarantee), and small local JSON stores for the Course
  and attempts (`var/`, gitignored).

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

The injection/PII eval (blueprint DoD #5) proves these controls — see **Run the demo** below.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.11–3.13.

```
uv sync                 # install dependencies from the committed lockfile
cp .env.example .env     # then add a Gemini API key: https://aistudio.google.com/apikey
```

The key is read from `.env` (either `GOOGLE_API_KEY` or `GEMINI_API_KEY`). The Provenance Gate
and the deterministic security eval run **without** a key; the Gemini nodes (prosody, planning,
grading, scaffolding) need one.

## Run the demo

**One command, the full five-step Definition-of-Done walkthrough:**

```
uv run python -m app.demo --reset
```

It drives, in order: **[1]** the Provenance Gate refusing a poem that isn't on the public-domain
allowlist → **[2]** the Build Pipeline generating a Course with a printed **Deletion Rationale** →
**[3]** a Recall session grading typed recall semantically with a **crutch-dependence tag** →
**[4]** an adaptive **re-plan** that strips a *different* crutch based on the recorded pattern (the
money shot) → **[5]** the injection/PII security eval. With no Gemini key it prints the key-free
spine (steps 1 and 5) and exits cleanly; with a key it runs the whole adaptive loop.

**The security eval on its own** (DoD #5 — *run the injection/PII eval and see it pass*):

```
uv run python -m evals.injection_pii_eval
```

It prints a per-scenario PASS/FAIL table — injection containment, the input sanitizer, and
PII-minimization — and exits non-zero on any failure. The deterministic checks need no API key;
the live model scenarios run when a Gemini key is present. The same checks run under `uv run pytest`.

**The agents-cli playground** (the visual path for the Build Pipeline):

```
uvx google-agents-cli playground
```

Select `build_pipeline` and enter a poem id — a corpus id such as `frost-stopping-by-woods`
builds a Course (watch the Deletion Rationale on stderr); any other id is refused by the gate. The
full recall + re-plan loop seeds session state and feeds the `RequestInput` pauses, which the
one-command runner above does for you.

### Corpus

By Heart processes only the vetted public-domain poems on its allowlist
([`corpus/manifest.yaml`](corpus/manifest.yaml)); provenance and the public-domain rationale for
each are in [`PUBLIC_DOMAIN.md`](PUBLIC_DOMAIN.md).

| Poem id | Poem | Author | First published |
|---|---|---|---|
| `dickinson-because-i-could-not-stop-for-death` | "Because I could not stop for Death" | Emily Dickinson | 1890 |
| `frost-stopping-by-woods` | "Stopping by Woods on a Snowy Evening" | Robert Frost | 1923 |
| `whitman-o-captain-my-captain` | "O Captain! My Captain!" | Walt Whitman | 1865 |
