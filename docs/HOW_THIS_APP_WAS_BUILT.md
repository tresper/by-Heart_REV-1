# How This App Was Built with an AI Coding Assistant

*Audience: computer-science students and working coders who want to see how an AI coding assistant
is used in practice — not a feature tour of any one product, but the **techniques** that make
AI-assisted engineering reliable. By Heart is the worked example; the practices are tool-agnostic.*

---

## Starting observation: the assistant is itself an agent

An AI coding assistant is an **agentic system** pointed at a repository. It runs a **reason → act
loop**: it holds the task in a **context window**, **plans** multi-step work, and uses **tools** —
reading and editing files, running shell commands, searching the codebase, running the tests — then
observes the results and decides the next step. So this project is doubly agentic: an agentic *app*
built by an agentic *assistant*. The same primitives — planning, tool use, human-in-the-loop,
multi-agent orchestration, verification — appear on both sides, which makes the build a good way to
*see* those ideas in action.

This particular project was built with **Claude Code**, but nothing below depends on it: the
workflow is the point, and a capable peer assistant such as **Google Antigravity** or **OpenAI
Codex** would run the same loop just as well. Treat the product name as interchangeable and the
practices as the lesson.

## 1. Give the assistant a constitution (persistent project instructions)

The single highest-leverage move is to write the project's rules down where the assistant reads them
every session. Here that lives in a checked-in `CLAUDE.md` (peer tools use their own equivalent) — a
small "constitution" that **overrides the model's defaults**:

- **Non-negotiables** — secrets only in a gitignored `.env`; process only allowlisted public-domain
  poems; meet the rubric, don't gold-plate.
- **Tech stack, conventions, and the git workflow** — stated once, applied consistently.
- **An authoritative spec to read before planning** — the design blueprint. The model's pretrained
  knowledge is a *starting point*; the spec is the *source of truth*.

This is **grounding**: the quality of AI-assisted work tracks the quality of the context you supply.
Encode the rules once instead of re-explaining them — and re-explaining them inconsistently — every
session.

## 2. Plan before touching code

Use the assistant's **plan mode**: have it read the spec, lay out a step-by-step plan, and get human
sign-off *before* it writes code. A wrong plan costs a paragraph to fix; wrong code costs a rewrite.
Planning also surfaces hidden assumptions early, where they're cheap.

A guiding rule from the spec shaped every plan: **one working end-to-end loop before breadth.** Build
the spine first (ingest → build a course → run one recall → grade it → record it), prove it runs, then
widen. This keeps the project demoable at every step instead of "almost done" for a long time.

## 3. Work in small phases with recovery-friendly git

The unit of work is a **phase**, and git is treated as a safety net, not an afterthought:

- **One short-lived branch per phase** (`phase/NN-slug`), branched from an **always-green `main`**.
- **Merge with `--no-ff`**, so each phase boundary is a visible merge commit while the granular
  commits beneath it stay intact for `git bisect`. **Never squash** — that destroys the per-step
  history troubleshooting relies on.
- **Annotated tags at each green checkpoint** are **recovery anchors**: `git checkout` a known-good
  state, or `git bisect` between two tags to localize a regression to a single small commit.
- **`main` is the recovery baseline** — a fresh clone of it must run, and work never lands on it
  unless the tests pass.
- **The human owns the irreversible step.** The assistant prepares every commit, merge, and tag
  locally and then hands off the exact `git push` line for the human to run from their own terminal.
  Pushing is outward-facing and hard to undo, so it's a deliberate **approval gate** — a clean
  example of **human-in-the-loop** control over the one action you can't quietly take back.

For a deadline-driven project this discipline pays for itself the first time something breaks:
every state is restorable and every regression is bisectable.

## 4. Test-driven — and keep `main` green *without secrets*

- **Test the parts where correctness is subtle**, not the trivial ones. Here that meant the
  crutch-removal deletion policy and the semantic adjudicator (which must *never* be a string
  compare) — the places a plausible-looking implementation can be quietly wrong.
- **Key-free smoke tests** form the always-green gate: they run with no API key, so a fresh clone,
  CI, and `git bisect` all work without secrets, while the live model-dependent path is exercised
  separately. The trunk stays bisectable for anyone.
- **Lint and the security eval run before each commit milestone.**
- The assistant **runs the tests itself and reports failures honestly** — "green" is claimed only
  when the suite actually passes, with the output to back it up.

## 5. Document decisions while the reasoning is fresh

Every non-trivial design, architecture, security, or dependency choice gets a dated entry in a
living `DECISIONS.md`: *what* was decided, *why*, the *alternatives considered*, and where it shows
up. The bar is **substance** — a real alternative, a non-obvious trade-off, a constraint that shaped
the design — not routine mechanics already visible in the diff.

Why it matters: an assistant's reasoning is otherwise trapped in an ephemeral chat that scrolls away.
A decision log makes that reasoning **durable, reviewable, and publishable** — on this project it
became the raw material for the writeup. Capture it in the same change that makes the decision, not
as an end-of-project chore.

## 6. Verify; don't trust the model's say-so

Generated code that *looks* right is not the same as code that *works*. Three habits close the gap:

- **Live, end-to-end runs.** Stand up the real service and drive it with a script, rather than
  assuming the code is correct. Real bugs on this project — a recalled word not persisting on screen,
  and a missing "try again" path — were found exactly because the running app was exercised, not just
  read.
- **Probe unknown APIs empirically before designing on them.** The live graph-visualization feature
  was built only after probing the framework's event objects to learn the *actual* field names; a
  confident guess would have shipped a broken feature.
- **Read before you edit or delete.** Look at the target first; if it contradicts how it was
  described, stop and surface that instead of plowing ahead.

## 7. Use the assistant's own agentic muscles for the hard checks

For a high-stakes change, an AI assistant can review its own work with **multi-agent orchestration**:

- **Fan-out review.** Spin up several **subagents in parallel**, each auditing a different dimension
  of a diff — answer-leakage/security, logical correctness, UI state-machine soundness,
  regression/scope — so no single pass has to hold everything at once.
- **Adversarial verification.** Feed each finding to a second pass that tries to *refute* it before
  it's accepted — **LLM-as-judge** with a skeptical prior, which filters out plausible-but-wrong
  claims a lone reviewer would wave through.

This project's riskiest diff went through exactly that review before it was merged. And the design
lesson the *app* teaches applies to the *build* itself: **use models for judgment, and deterministic
code — tests, linters, type checks — for everything that can be checked mechanically.**

## 8. Build reusable capabilities: skills and memory

- **Skills** — authored, on-demand procedures (here, `SKILL.md` files) that package project-specific
  know-how, such as enforcing the public-domain allowlist or walking a STRIDE threat model. They make
  expert moves repeatable instead of re-derived (and inconsistently) each time.
- **Persistent memory** — durable notes that survive across sessions (preferences, hard constraints),
  so the assistant doesn't relearn the same context every time you return.

## 9. Guardrails, and where the human stays in charge

- **Guardrails** are encoded as non-negotiables the assistant enforces under instruction: secrets
  never leave `.env`; the provenance gate **fails closed** on any poem off the allowlist; untrusted
  user input is sanitized at a single choke point. The assistant is told to refuse to cross these
  lines, even when a change would be easier without them.
- **The human stays in the loop where judgment and irreversibility live**: scope and taste calls
  ("meet the rubric, don't over-build"), approving pushes and other outward-facing actions, and final
  acceptance. The assistant *proposes and prepares*; the human *decides and triggers*.

## The fundamentals, distilled

Tool-agnostic, and portable to any capable agentic coding assistant:

1. **A written constitution + an authoritative spec** — ground the assistant in your project's rules.
2. **Plan, get sign-off, then build** — and build one end-to-end loop before breadth.
3. **Small phases on recovery-friendly git** — green `main`, `--no-ff` merges, tags as recovery
   anchors, never squash.
4. **Green-by-default TDD** — test the subtle logic; keep the trunk runnable without secrets.
5. **A living decision log** — capture the *why* and the alternatives while they're fresh.
6. **Verify, don't trust** — run it live, probe real APIs, read before you edit.
7. **Multi-agent adversarial review** — fan-out plus refutation for high-stakes diffs.
8. **Reusable skills and persistent memory** — package know-how; don't relearn it.
9. **Guardrails enforced; humans in the loop** on irreversible and scope decisions.

None of these are features of one product. They are an engineering *discipline* for working with an
agentic assistant — and the same reason→act-with-tools loop that builds the software is the one the
software itself runs on its users.

---

### Further reading

- [README](../README.md) — what By Heart is, its architecture, and how to run the demo.
- [How By Heart uses an agentic workflow](HOW_THIS_APP_USES_AGENTIC_WORKFLOW.md) — the agentic
  design of the app itself (the companion to this build-process doc).
- [`DECISIONS.md`](../DECISIONS.md) — the living decision log referenced throughout.
