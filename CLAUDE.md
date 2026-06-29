# CLAUDE.md — By Heart

By Heart is an agentic poetry-memorization tutor: it turns a vetted public-domain poem into a personalized, prosody-aware memorization course using a multi-agent **Google ADK 2.0** system. This is a Kaggle capstone submission (*Agents for Good* track).

**Before planning any build phase, read the Capstone Blueprint (`docs/By_Heart_Capstone_Blueprint_Second_Draft.md`, a local working doc kept out of the published repo) — it is the authoritative spec.** Build in the priority order in its §13: one working end-to-end loop before breadth.

## Non-negotiables
- **Secrets:** never commit secrets. The Gemini API key lives only in `.env` (gitignored). Ship `.env.example` with placeholders. No keys, tokens, or passwords in any tracked file.
- **Public-domain only:** the system processes ONLY poems listed in `corpus/manifest.yaml` (US works first published **in or before 1930**). The `provenance_gate` node MUST refuse any poem not on that allowlist. No open-ended / "paste-your-own-poem" ingestion in the MVP.
- **Scope:** meet the capstone rubric; do not gold-plate. Defer everything in the blueprint's "Stretch" and "NOT building" lists — no Antigravity, no user accounts, no audio, no cloud deploy in the MVP.
- **Meaningful agents:** every LLM node must do reasoning a `for` loop cannot. Preserve the agent interdependence in blueprint §4.

## Tech stack
- **Framework:** Google ADK 2.0 — graph `Workflow`, `@node`, conditional routing, `RequestInput` (human-in-the-loop).
- **Runtime model:** Gemini (key from `.env`).
- **Lifecycle:** `agents-cli` (`uvx google-agents-cli`) for scaffold / lint / test / eval / local playground.
- **MCP:** a local Python stdio server (e.g. FastMCP) — the **Prosody MCP** (CMU Pronouncing Dictionary + grapheme-to-phoneme fallback). It MUST write only JSON-RPC to stdout; send all logging to stderr.
- **Deps:** `uv`, with a committed lockfile.
- **State:** ADK Session for in-graph state; a small local JSON store for the corpus manifest, the learner-memory attempts, and mastery (ADK `MemoryService` is not wired — the durable learner record is the JSON store).
- **Skills:** author project skills under `.claude/skills/<name>/SKILL.md`.

## Architecture (see blueprint §4 for full detail)
Two graphs:
- **Build Pipeline:** `provenance_gate` → `prosody_analysis` (calls the Prosody MCP) → `curriculum_plan` → emit a Course.
- **Recall Session Loop:** `present_masked_line` → `RequestInput` (learner recall) → `adjudicate` → route advance / `scaffold` → `memory_update` → loop.

Key behaviors:
- Deletion policy = **crutch removal**: strip the prosodic cue the learner is currently relying on (visible rhyme partner, metrical regularity, syntactic momentum); escalate by removing cues, not by masking a fixed ratio.
- `curriculum_plan` emits a short, human-readable **Deletion Rationale** each session — this is the visible reasoning artifact; surface it in logs/UI.
- `adjudicate` grades semantically (hit / near-miss / variant / miss) and emits a **crutch-dependence tag** that feeds back into planning. Never a string compare.

## Conventions
- Comments explain **design and behavior**, not syntax.
- Write tests for the deletion policy and the adjudicator; run `agents-cli` lint and the injection/PII eval before each commit milestone.
- Keep `README.md` current: problem, solution, the two-graph architecture, setup, and run-the-demo steps.

## Git workflow
Build in phase increments with recovery-friendly history (this is a one-submission deadline — keep `main` clean and everything backed up off-machine).
- **`main` is the always-green trunk.** Work never lands on `main` unless its tests pass; a fresh clone of `main` must run. `main` is the recovery baseline.
- **One short-lived branch per phase**, named `phase/NN-slug` (e.g. `phase/02-prosody-mcp`), branched from `main`.
- **Merge to `main` with `--no-ff`** when the phase is green, so the phase boundary is a visible merge commit while the granular commits underneath stay intact for `git bisect`. Do **not** squash — it destroys the per-step history that troubleshooting relies on.
- **Tag each green checkpoint** with an annotated tag matching the branch slug: `git tag -a phase-NN-slug -m "…"`. Tags are the recovery anchors — `git checkout phase-NN-…` for a known-good state; `git bisect` between two tags to localize a regression.
- **Push after each phase — run by the human from their terminal.** `origin` is SSH, which works in the terminal; the assistant's sandboxed shell has no access to the SSH key, so the assistant prepares all commits/merges/tags locally and hands off the exact push line, e.g. `git push origin main && git push origin <phase-branch> && git push origin <tag>`. The off-machine copy is the deadline insurance.
- End-of-phase checklist: tests green → merge `--no-ff` to `main` → annotated tag → **hand off the push line; human pushes** `main` + tag → cut the next `phase/NN-slug`.
- History so far: phase 1 is tagged `phase-01-provenance-gate` on `main`; active branch is `phase/02-prosody-mcp`.

## Decision log (important)
After any non-trivial design, architecture, security, or dependency decision, **append a dated entry to `DECISIONS.md`**: what was decided, why, the alternatives considered, the capstone concept it serves (ADK / MCP / Skills / Security), and where it will show (code / video / writeup). This is the raw material for the Writeup's "Journey & key decisions" section. Keep it factual and publishable — the repo will be public.

**Keep `DECISIONS.md` current as you build — treat it as a living log, not an end-of-project chore.** Capture a decision while the reasoning is fresh, ideally in the same change that makes it. At natural checkpoints (finishing a build phase, before a milestone commit), pause and ask "what did we decide here that a future reader — or the Writeup — would want the reasoning for?" and record it. The bar is **substance**: log a choice when there was a real alternative, a non-obvious trade-off, a surprise, or a constraint that shaped the design. Do **not** log routine mechanics already visible in the diff or git history (renames, dependency bumps, "added a test"). When nothing substantive happened, it is fine to add nothing — say so rather than padding the log.
