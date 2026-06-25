# Demo Script — the ≤5:00 video

A shot-by-shot plan for the capstone video, mapped to the blueprint §7 beats. Open on the
payoff, not the setup. Every command below is verified to run; the live steps need a Gemini key
in `.env` (see the README **Setup**). Record continuously, not at the end.

**Before recording:** `uv sync`, put a Gemini key in `.env`, and do one warm-up run of
`uv run python -m app.demo --reset` so the model/MCP are cached and the take is fast. The runner
prints a clean transcript to **stdout**; the Deletion Rationale and MCP logs go to **stderr** — for
a clean screen, you can hide stderr with `2>/dev/null`, or show it to prove the MCP tool calls.

---

## 0:00–0:30 · Hook (open on the payoff)

- **On screen:** the line *"The NYT needed an editorial team and a week to build one memorization
  course — with a fixed path and self-grading."* Then cut straight to By Heart building a course
  live (the `[2/5]` Deletion Rationale streaming).
- **Narration:** "Memorizing a poem changes how you hold it. The New York Times proved millions
  want to — but it took a team a week to build one course, with a fixed path. By Heart's agents
  build one for *any* poem, adapt it to *any* learner, and grade recall themselves — in minutes."
- **Command (rolling under the cut):**
  ```
  uv run python -m app.demo --reset
  ```

## 0:30–1:15 · Problem + why agents

- **On screen:** the §2 contrast table (NYT fixed-path / self-graded / one poem  vs.  By Heart
  crutch-removal / semantic grading / any poem, any learner).
- **Narration:** "Progressive masking on a fixed schedule is a `for` loop — no intelligence
  needed. Three things *do* need judgment: designing the curriculum from a poem's scansion and
  rhyme; noticing a learner only 'knew' a word because the rhyme partner gave it away, and
  stripping *that* crutch next; and grading recall by meaning, not string match. Those are the
  agents."

## 1:15–2:00 · Architecture (the two graphs)

- **On screen:** the two-graph diagram from the README (Build Pipeline → Course; Recall Loop with
  the human-in-the-loop `RequestInput`). Highlight the Prosody MCP feeding `prosody_analysis`, and
  the crutch-dependence tag flowing from `adjudicate` back into `curriculum_plan`.
- **Narration:** "Two ADK 2.0 graphs over a shared learner store. Graph A vets the poem, grounds
  scansion in a custom **Prosody MCP**, and plans a crutch-removal schedule. Graph B presents a
  masked line, takes the learner's recall, grades it semantically, and tags the crutch it leaned
  on. That tag is what re-plans the next session."

## 2:00–4:00 · Live demo, ending on the money shot

Drive this from the one-command runner; narrate over its streaming `[n/5]` blocks. (For the
"learner types a recall" beat, you can optionally cut to the `agents-cli playground`
`present_masked_line` prompt for a human-typing visual — see the README.)

- **2:00–2:25 · the gate (`[1/5]`).** On screen: the runner refusing `plath-daddy`.
  Narration: "Only vetted public-domain poems get in — a modern, in-copyright poem is refused at
  the gate. That's the copyright guarantee *and* an input-validation control."
- **2:25–3:05 · build the course (`[2/5]`).** On screen: the four-session **Deletion Rationale**
  streaming for Dickinson's "Because I could not stop for Death." Narration: "The agents read the
  rhyme-partner map and meter, then plan four sessions — strip rhyme partners first, then meter,
  then the syntactic glue — and **explain each step in plain language**. Show the reasoning, not
  just the masking."
- **3:05–3:35 · recall + the crutch tag (`[3/5]`).** On screen: the recall attempts —
  `recalled 'Immortality' → outcome=hit, crutch=rhyme_partner`. Narration: "The learner recalls
  the line — and the Adjudicator notices the win leaned on the *visible rhyme partner*. It grades
  by meaning and tags the crutch."
- **3:35–4:00 · the money shot (`[4/5]`).** On screen: the **re-planned** Deletion Rationale —
  *"…to address your diagnosed reliance exclusively on rhyme partners for successful recall.
  Removing this dominant crutch forces you to retrieve these line endings independently…"* — plus
  the `rationale changed for session(s): [0, 1, 2, 3]` line. Narration: "Next session, the plan is
  **different for this learner**: it strips the rhyme cue they were leaning on, first — and even
  inserts a consolidation session. The course adapted itself."

## 4:00–5:00 · The build, told straight

- **On screen:** quick cuts — `.claude/skills/` (the authored `SKILL.md` files), the Prosody MCP
  (`app/prosody/server.py`), and the security eval passing:
  ```
  uv run python -m evals.injection_pii_eval
  ```
- **Narration:** "Built by agentic vibe coding with **Claude Code** — two **ADK 2.0** graphs on
  **Gemini**, a custom **Prosody MCP** for phonetic ground truth, authored **Agent Skills**, and a
  STRIDE threat model with an injection/PII eval that passes. The 'good': a teacher can generate an
  evidence-based memorization course for any poem in their curriculum, free and open-source — the
  NYT-quality experience, for everyone." Close on the one-liner: *"By Heart — what an editorial
  team did by hand for one poem, agents do for any poem and any learner."*

---

## Reference — the exact commands

| Beat | Command | Needs key |
|---|---|---|
| Full live loop (spine of the demo) | `uv run python -m app.demo --reset` | yes (steps 2–4) |
| Security eval (its own shot) | `uv run python -m evals.injection_pii_eval` | partial (live scenarios) |
| Playground (optional, for the typing visual) | `uvx google-agents-cli playground` | yes |
| Tests green (B-roll, optional) | `uv run pytest -q` | no |

The video, cover image, and YouTube upload are produced from this script — they are not part of
the repository.
