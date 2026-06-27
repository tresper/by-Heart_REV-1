# By Heart — Capstone Blueprint (Second Draft)
### Target: 1st place, *Agents for Good* track — AI Agents: Intensive Vibe Coding Capstone
### Hard deadline: **Mon, July 6, 2026, 11:59 PM PT** (≈ 9:59 AM EAT, Tue July 7). One submission only — no iteration.

**Working principles**
- **Judge-legibility first.** Design the code and the Kaggle Writeup so a judge can find and score each rubric element fast. Lead every artifact with the value, not the setup.
- **Google-first *runtime* stack; transparent *build* tooling.** The product runs on Google's stack — **ADK 2.0**, **Gemini** as the agent model, a custom **MCP** server, `agents-cli` for the dev lifecycle. The *coding agent* is **Claude Code (Opus 4.8 + Sonnet)**, used openly: Google's own course codelabs name Claude Code as a first-class member of the `SKILL.md` agent-skills ecosystem (alongside Antigravity, Cursor, Cline, Copilot), so there is nothing to hide and a "Build" story that is honest scores better than a coy one. We are **not** using Antigravity; we rest on four concepts (ADK + MCP + Skills + Security).
- **Meet the spec; don't exceed it.** Land every criterion, banked in the place the rubric assesses it. Enhancements are deferred to later revisions. Prioritize the criteria most likely to move a judge.
- **Write instructions that are clear to Claude Code.** Every build step below is phrased to hand off cleanly.

*Working title: **By Heart**. Anchor poem and homage: **"Recuerdo"** (Edna St. Vincent Millay, 1919) — the very poem the NYT hand-built its 2025 memorization challenge around; Spanish for "I remember." Agents may carry literary names.*

---

## 1. The one-sentence pitch

> **By Heart is an agentic tutor that turns any public-domain poem into a personalized, prosody-aware memorization course — doing autonomously, for any poem and any learner, what the New York Times Poetry Challenge did by hand for a single one.**

This framing is the whole strategy. It exists to defeat the one failure mode that sinks every poetry-cloze submission: *a judge mentally replacing your "agent" with a `for` loop.* Progressive masking on a fixed schedule needs no intelligence. **Curriculum design, adaptive crutch-removal, and semantic grading do.** Every decision below keeps the agents irreducible and visible.

---

## 2. The strategic reframe (why this wins vs. a "cloze app")

The sharp, factually precise contrast (verified): the NYT challenge (launched Apr 28, 2025; authors A.O. Scott & Aliza Aufrichtig) used a **fixed step sequence** and **self-graded** recall for **one** poem. By Heart generalizes all three axes.

| Ordinary submission / the NYT challenge | *By Heart* |
|---|---|
| Masks words on a fixed schedule | Agents perform **crutch-removal deletion** — progressively stripping the prosodic cues a learner is *leaning on*, grounded in real scansion and rhyme analysis, so recall becomes genuinely unaided |
| Self-graded / exact-string checking | A **Recall Adjudicator** grades semantically (hit / near-miss / meaningful-variant / miss) **and names which crutch the recall relied on** |
| One hand-built poem | Ingests **any vetted public-domain poem** and **generates the full multi-session course** |
| Same path for everyone | A per-learner memory store **diagnoses error *patterns*** and re-plans which crutch-class to strip next |
| "An app" | A demonstrable **two-graph ADK 2.0 multi-agent system** with tool-grounded reasoning, a human-in-the-loop recall node, and persistent state |

Headline for video + writeup: *"The NYT needed an editorial team and a week to build one memorization course, with a fixed path and self-grading. By Heart's agents build one for any poem, adapt it to any learner, and grade recall themselves — in minutes."*

---

## 3. The pedagogy, made legible (scores Core Concept + Writeup)

Foreground the evidence base and map each principle to an **agent behavior**, so the science is visibly *implemented*, not cited.

| Principle | Source | Implemented as |
|---|---|---|
| Retrieval practice / testing effect | Roediger & Karpicke, 2006 | The core recall-not-reread loop |
| Cloze deletion | Taylor, 1953 | But **crutch-removal** deletion, not fixed-ratio |
| Desirable difficulties; retrieval vs. storage strength | Bjork & Bjork | Recall must be **effortful and unaided** to build durable memory — the rationale for removing crutches |
| Graduated cue withdrawal / method of vanishing cues | Glisky, Schacter & Tulving, 1986; Wood, Bruner & Ross, 1976 (scaffolding) | The **Scaffolding Coach's** minimum-effective hint, withdrawn as mastery grows |
| Spacing effect | Ebbinghaus, 1885 → present | Lines and stripped cues resurface across sessions on a spaced schedule |

**The chosen theory — "removing crutches."** In poetry, rhyme and meter are built-in retrieval scaffolds. A learner often *appears* fluent only because the rhyme partner gives away the word, or the metrical regularity reconstructs the line. That is retrieval strength borrowed from the poem's structure, not durable storage strength of one's own. By Heart's deletion policy therefore escalates by **stripping the specific cue a learner is currently relying on**, forcing unaided retrieval. This is both pedagogically defensible (Bjork) and, crucially, **agentic**: inferring *which* crutch supported a given correct recall is a judgment a regex cannot make — and it is the reasoning we will surface to judges (§4).

**Prior-art paragraph (for the Writeup).** State plainly that this is decades-to-centuries-old, unprotectable prior art: cloze (1953), retrieval practice (1970s–present), "vanishing text" recitation pedagogy older still. You are independently implementing unencumbered pedagogy, not copying anyone's expression. This preempts any "isn't this just the NYT thing?" reaction.

---

## 4. Agent architecture — ADK 2.0 graphs (scores Technical Implementation, 50 pts)

Two ADK 2.0 **graph workflows** over a shared learner-memory store, grounded by a custom MCP tool and gated by a provenance check. We use ADK 2.0 idioms explicitly: `Workflow`, `@node`, conditional routing, and `RequestInput` for human-in-the-loop.

### What is an agent vs. a node vs. a tool (state this in the README)
- **Orchestration = the graphs themselves** (the "Curriculum Director" is the two Workflows, not a separate LLM).
- **LLM nodes** (each does reasoning a `for` loop cannot): `prosody_analysis`, `curriculum_plan`, `adjudicate`, `scaffold`, and the optional `literary_companion`.
- **Tool**: the **Prosody MCP server** (called at runtime by `prosody_analysis`, and by `adjudicate` for rhyme-aware grading).
- **Services / data**: ADK **Session & Memory** (learner state — the Day-3 Context Engineering concept made concrete) and the **Provenance allowlist** (the public-domain guarantee, §8).

### Graph A — Build Pipeline (runs once per poem → emits a Course)
```
[provenance_gate]            admit ONLY poems on the signed PD allowlist; else refuse
        │
        ▼
[prosody_analysis] ──MCP──► Prosody MCP server   produces the structural map:
        │                                        meter/stress, rhyme scheme,
        │                                        RHYME-PARTNER MAP, anchor words
        ▼
[curriculum_plan]            applies the Crutch-Removal Policy (§ below) + learner
        │                    history → multi-session masking schedule
        │                    + emits a human-readable DELETION RATIONALE per session
        ▼
   Course object  ──►  Session/Memory store
```

### Graph B — Recall Session Loop (per study session; human-in-the-loop)
```
        ┌─────────────────────────────────────────────┐
        ▼                                             │
[present_masked_line]                                 │
        │                                             │
        ▼                                             │
[RequestInput]  ◄── learner types recall (HUMAN-IN-THE-LOOP, ADK RequestInput)
        │                                             │
        ▼                                             │
[adjudicate] ──► hit / near-miss / variant / miss     │
        │        + CRUTCH-DEPENDENCE TAG               │
        │        ("got 'friends' only because rhyme    │
        │         partner 'ends' was visible")         │
        ▼                                             │
   route ─── mastered ──► [advance] ──────────────────┘
        │
        └─ stall/miss ──► [scaffold]  minimum hint: rhyme cue → first letter → gloss
                              │
                              ▼
                         [memory_update]  persist attempt, error PATTERN, crutch
                              │            dependence, mastery → loop
                              ▼
                          (loop or end)
```

### The Crutch-Removal Deletion Policy (the technical signature — specify it, don't assert it)
A concrete, ordered, falsifiable rule set that `curriculum_plan` executes:
1. **Read cue structure** from the Prosody MCP: rhyme scheme, rhyme-partner map, meter/stress regularity, anchor words.
2. **Define the crutches**: (i) a *visible rhyme partner* that makes a masked rhyme word inferable; (ii) *strong metrical regularity* that lets stress/syllable count reconstruct a word; (iii) *syntactic/collocational momentum* that auto-fills function words.
3. **Escalate by stripping crutches**: low-crutch words first → then **both** members of a rhyme pair (so rhyme can't bridge) → then anchor + adjacent content words (so meter alone is insufficient) → near-whole-line with only scaffolding punctuation.
4. **Adaptive overlay (the money shot)**: the Architect *infers which crutch a prior correct recall relied on* (from the Adjudicator's crutch-dependence tag) and removes **that** support next; for misses it diagnoses the *pattern* (rhyme-position misses? one stanza? confusable synonyms?) and chooses which crutch-class to strip — it does **not** merely re-queue exact misses.
5. **Emit the reasoning**: one short natural-language **Deletion Rationale** per session. This is the visible, judge-facing artifact that proves the adaptation is reasoning, not bookkeeping.

**Why this reads as "meaningful use of agents":** remove any LLM node and the product degrades in a way a `for` loop cannot repair. `curriculum_plan` *depends on* `prosody_analysis` and the learner's error patterns; `adjudicate` *cannot* be a string compare and feeds the crutch tag back into planning; `scaffold` *depends on* where the learner stalled. That interdependence — and the surfaced rationale — is the signature a judge cannot dismiss as an LLM wrapper.

---

## 5. Course-concept coverage (need ≥3; we deliver 4, Deployability optional 5th)

| Key concept | Where shown | How |
|---|---|---|
| **Agent / Multi-agent (ADK)** | Code | Two ADK 2.0 graph workflows + five LLM nodes + human-in-the-loop `RequestInput` (§4) |
| **MCP Server** | Code | Custom **Prosody MCP** (CMU dict **+ g2p fallback**, §below) wrapping scansion + rhyme analysis; called at runtime. "Clever usage of existing toolsets" is explicitly rewarded |
| **Agent skills (`SKILL.md` / `agents-cli`)** | Code/Video | Author real `SKILL.md` skills consumed by Claude Code during the build: **`scansion`**, **`crutch-removal-deletion`**, **`stride-threat-model`**; use `agents-cli` for the scaffold/lint/test/**eval** lifecycle. (Claude Code is in the course's named skills ecosystem.) |
| **Security features** | Code/Video | STRIDE skill + prompt-injection & PII eval + the Provenance/PD gate + recall-input validation + secrets hygiene + minimal-PII store (§8) |

*Deployability (Cloud Run / Agent Runtime) remains an optional **stretch** that banks a 5th concept on video — only after the MVP and README are solid. **Antigravity is intentionally not used.***

---

## 6. Sharpening "the Good" (scores Core Concept & Value, 10 pts)

Make the social value concrete and named:
- **Educational equity (primary):** a teacher generates an evidence-based memorization unit for *any* poem in their curriculum in minutes — the NYT-quality experience, free and open-source, for under-resourced classrooms with no editorial team.
- **Lifelong & older learners:** poetry memorization as cognitive engagement and enrichment. *(Frame as enrichment — no clinical or medical claims.)*
- **Accessibility (stretch):** an audio-first recall path (TTS + spoken recall via STT) for low-vision and auditory learners.
- **Cultural preservation (stretch):** any public-domain poem with a pronunciation resource → heritage-poetry memorization.

Throughline: *By Heart democratizes a high-craft, evidence-based learning experience that until now required expert editorial labor.* Open-source (CC-BY, which winning requires anyway) and a public-domain corpus reinforce the accessibility story rather than fighting it.

---

## 7. Rubric-by-rubric battle plan

### Pitch — 30 pts
- **Core Concept & Value (10):** the reframe (autonomous, adaptive curriculum generator), agents demonstrably central, track-copy fit. Lead every artifact with the NYT-team-vs-agents contrast.
- **YouTube Video (10):** 5:00 hard cap. **Open on the payoff, not the setup.**
  1. *0:00–0:30* — Hook: "Memorizing a poem changes how you hold it. The NYT proved millions want to — but it took a team a week to build one course, with a fixed path." Cut to By Heart building a course live.
  2. *0:30–1:15* — Problem + **Why agents?** (curriculum design, crutch-removal, and semantic grading require judgment).
  3. *1:15–2:00* — Architecture image (the two graphs from §4) with tight narration of node interplay.
  4. *2:00–4:00* — **Live demo, ending on the money shot:** pick a vetted poem → agents generate the course → learner attempts a session → Adjudicator handles a near-miss and **shows the crutch-dependence tag** → next session the **Deletion Rationale** explains *why* it strips that exact cue → learner now recalls unaided. *Show the reasoning, not just the masking.*
  5. *4:00–5:00* — **The Build, told straight:** agentic vibe coding with **Claude Code**, **ADK 2.0** graphs on **Gemini**, the **Prosody MCP**, authored **`SKILL.md`** skills; the "Good"; close on the one-liner.
- **Writeup (10):** ≤2,500 words. Structure: Problem → Why agents → Architecture (embed the two-graph diagram) → Pedagogy & the crutch-removal theory → Concept coverage → **Provenance & safety posture** → Journey & key decisions (honest toolchain). The prior-art depth and the provenance rigor are your differentiators.

### Implementation — 70 pts
- **Technical Implementation (50):** clean ADK 2.0 graphs; real runtime tool use via the Prosody MCP; the crutch-removal policy + pattern-based adaptive memory as the signature; the visible Deletion Rationale; comments tied to *design and behavior*, not syntax; **no API keys or passwords in code** (rubric reminder — and a free Security demo). If you deploy, include reproducible deployment docs.
- **Documentation (20) — near-free points, do not skip:** `README.md` with problem, solution, the two-graph architecture diagram, the agent/node/tool taxonomy, setup, `.env.example`, run-the-demo steps, and a link to `PUBLIC_DOMAIN.md`. Write it *before* the final night.

---

## 8. Provenance, copyright & safety posture (the strongest PD fix; feeds Security + Writeup)

**Decision: the MVP is corpus-only. This *structurally* eliminates copyright risk — protected work cannot be misused if protected work cannot enter the system.**

- **Frozen, vetted corpus.** The only poems the MVP ever processes are a hand-checked seed set of public-domain works shipped in-repo. No open-ended ingestion in the MVP.
- **Public-domain standard (US, precise).** As of **January 1, 2026**, US works **published in or before 1930** are in the public domain. Every seed poem satisfies this with margin.
- **Provenance manifest** (`corpus/manifest.yaml`): per poem — title, author, year of first publication, source edition/URL (e.g., Project Gutenberg / Poetry Foundation PD text), and the PD rationale. Summarized in **`PUBLIC_DOMAIN.md`**.
- **Provenance Gate** (`provenance_gate` node + a `SKILL.md`): admits **only** poems present in the signed allowlist/manifest; anything else is refused. This is simultaneously the copyright guarantee, an **allowlist input-validation security control**, and a third authored skill — one component, three rubric reinforcements.
- **Security (Day-4 material, anchored in the MVP, not the stretch):** a **STRIDE threat-model `SKILL.md`**; a small **prompt-injection + PII eval** run via `agents-cli` and the course's eval skill (synthetic scenarios: injection attempts in a recall answer, PII leakage); **input validation** on learner recall input; **secrets hygiene** (`.env.example` only, never a committed key); a **minimal-PII** learner store (an opaque local learner id + attempts; no real names required).
- **CC-BY winner license:** winning forces open-sourcing, so never ship an in-copyright poem and never attach a private Kaggle resource you aren't ready to make public.

**Proposed seed corpus (~6; all published ≤1930; chosen for prosodic variety and to exercise the MCP):**

| Poem | Author | First pub. | Why it's useful |
|---|---|---|---|
| Sonnet 18 ("Shall I compare thee…") | Shakespeare | 1609 | Iambic pentameter, ENF rhyme — the regular baseline |
| "The Tyger" | William Blake | 1794 | Trochaic, AABB — strong, simple rhyme pairs |
| "On First Looking into Chapman's Homer" | John Keats | 1816 | Petrarchan sonnet — a different rhyme topology |
| "Because I could not stop for Death" | Emily Dickinson | 1890 | Common meter + **slant rhyme** — deliberately stresses the g2p/near-rhyme path |
| "Recuerdo" | Edna St. Vincent Millay | 1919 | AABB with a refrain — the NYT homage and demo anchor |
| "Pied Beauty" (*optional/showcase*) | Gerard Manley Hopkins | 1918 | **Sprung rhythm** — advanced stress case; include only if the MCP handles it cleanly |

### Prosody MCP — eliminating the coverage risk (point 4, the strongest fix)
The CMU Pronouncing Dictionary has real gaps on archaic/poetic vocabulary, proper nouns, and contractions ("morn," "o'er," "thou," "Recuerdo"), which is exactly this corpus's vocabulary. Fix:
- **Primary:** CMU dict lookup for stress + phonemes.
- **Fallback (closes the gap):** a grapheme-to-phoneme (g2p) model for any out-of-dictionary token, so **every** word resolves.
- **Validation:** treat LLM-suggested pronunciations (if ever used) as proposals to be *validated against* the dict/g2p, never trusted raw.
- **Framing:** the MCP provides **deterministic phonetic ground truth** (stress, rhyme scheme, rhyme-partner map, slant-rhyme detection) that the LLM nodes reason over — not "a dictionary behind a wrapper." That is what makes it clever tool use and what stops scansion hallucination.

---

## 9. Scope discipline — what actually wins (and what we are NOT building)

Judges reward one working, well-documented loop over a sprawling half-built platform. Build bottom-up; ascend only when the tier below is solid **and the README reflects it.**

**MVP — must land (demonstrates all four concepts):**
1. **Provenance Gate** + vetted PD corpus manifest (the safety/copyright floor, built first).
2. **Prosody MCP** (CMU + g2p fallback) → anchor words, rhyme-partner map, slant-rhyme.
3. **Build Pipeline graph** → `curriculum_plan` produces a multi-session **crutch-removal** schedule + **Deletion Rationale**.
4. **Recall Session Loop graph** with `RequestInput` human-in-the-loop.
5. **Recall Adjudicator** → semantic grading + **crutch-dependence tag**.
6. **Scaffolding Coach** → graduated minimum hints.
7. **Learner Memory** → **pattern-based** re-planning across sessions (the demo's money shot).
8. **STRIDE skill + injection/PII eval** + recall-input validation + secrets hygiene.
9. Minimal demo UI (the `agents-cli` local web playground is sufficient).

**Stretch — only after MVP + README are solid:**
- Literary Companion in full Socratic mode.
- Audio: TTS playback + spoken recall via STT.
- Cloud Run / Agent Runtime deployment (banks Deployability on video).
- Spaced scheduling across multiple poems and days.

**Explicitly NOT building (protects scope and the PD guarantee):**
- ✗ Open-ended "paste your own poem" ingestion *(reintroduces copyright + injection surface; if ever added later it needs an attestation + publication-year gate + untrusted-input handling + an in-copyright refusal guardrail).*
- ✗ Antigravity integration.
- ✗ User accounts / real-identity auth beyond an opaque learner id.
- ✗ Audio and cloud deployment in the MVP.

---

## 10. Tech stack (for a clean Claude Code hand-off)

- **Framework:** Google **ADK 2.0** (graph `Workflow`, `@node`, `RequestInput`).
- **Model (runtime):** **Gemini** via Gemini API key (course-aligned; stored in `.env`, never committed).
- **Lifecycle tooling:** **`agents-cli`** (`uvx google-agents-cli`) for scaffold / lint / test / **eval** / local playground.
- **MCP:** Python MCP SDK (e.g., FastMCP) wrapping CMU dict + a g2p library; exposes scansion/rhyme tools.
- **State:** ADK Session & Memory service for learner state; a small local store (e.g., SQLite/JSON) for the corpus manifest, attempts, and mastery if simpler.
- **Skills:** authored `SKILL.md` files in the repo (`scansion`, `crutch-removal-deletion`, `stride-threat-model`, `provenance-gate`).
- **Dev agent:** **Claude Code (Opus 4.8 + Sonnet)**, used transparently.
- **Package mgmt:** `uv` (with a lockfile for reproducibility).

---

## 11. Definition of Done (MVP)

A judge can clone the repo, follow the README, and: (1) see the Provenance Gate refuse a non-corpus poem; (2) watch the Build Pipeline generate a course for a corpus poem with a printed Deletion Rationale; (3) run a Recall session, get semantically graded with a crutch-dependence tag; (4) re-run and see the next session strip a *different* crutch based on their pattern; (5) run the injection/PII eval and see it pass. The README documents the two graphs, the agent/node/tool taxonomy, and setup. No secrets in the repo.

---

## 12. Schedule to July 6 (≈12 days; protect the deliverables)

The video + writeup are **30%** of the score and are routinely under-budgeted. **Freeze code July 3.**

- **Days 1–2:** Provenance Gate + corpus manifest; Prosody MCP (CMU + g2p) with the slant-rhyme case (Dickinson) passing.
- **Days 3–5:** Build Pipeline graph + crutch-removal policy + Deletion Rationale on one poem end-to-end.
- **Days 6–7:** Learner Memory + pattern-based re-planning (the money shot); record rough demo clips as you go.
- **Days 8–9:** Adjudicator (crutch tag) + Scaffolding Coach; generalize across the corpus.
- **Day 10:** STRIDE skill + injection/PII eval + input validation; secrets sweep.
- **~July 3 (code freeze):** lock the MVP.
- **July 4–6:** README, ≤2,500-word Writeup, record + edit + upload the ≤5-min YouTube video, cover image.

**Pre-submit checklist (one submission only):** writeup < 2,500 words ✓ · Track = Agents for Good selected ✓ · cover image attached ✓ · YouTube link public ✓ · repo public + setup verified **on a clean clone** ✓ · **no secrets committed** ✓ · provenance manifest complete ✓.

---

## 13. Immediate next builds (priority order, Claude-Code-ready)

1. Scaffold the ADK 2.0 project with `agents-cli`; stub **Graph A** and **Graph B** as graph workflows (nodes named exactly as §4).
2. Build the **Provenance Gate** node + `corpus/manifest.yaml` + `PUBLIC_DOMAIN.md`; ship the seed corpus.
3. Stand up the **Prosody MCP** (CMU + g2p fallback); wire `prosody_analysis` to it; verify rhyme-partner map + slant rhyme on Dickinson.
4. Implement the **crutch-removal policy** in `curriculum_plan` end-to-end on one poem, including the printed **Deletion Rationale**.
5. Add **Learner Memory** + the **pattern-based** re-planning loop (the adaptation proof point).
6. Layer **`adjudicate`** (with the crutch-dependence tag) and **`scaffold`**.
7. Author the **STRIDE `SKILL.md`** and the **injection/PII eval**; add recall-input validation.
8. Write the **README** and record the **demo** continuously — never at the end.

---

### Open decision points flagged for your input (do not block the build)
- **Seed corpus:** swap any poem; in particular, keep Hopkins's "Pied Beauty" only if the MCP handles sprung rhythm cleanly — otherwise drop it and keep the set regular.
- **Runtime model:** set to **Gemini** for course alignment; confirm, or name a specific Gemini variant.
- **Demo UI:** the `agents-cli` local playground is the low-effort default; say if you'd prefer a thin custom front-end for the video.
- **State store:** ADK Session/Memory vs. a small SQLite/JSON — I defaulted to "whichever is simpler to demo"; flag if you have a preference.

