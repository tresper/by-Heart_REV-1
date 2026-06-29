# How By Heart Uses an Agentic Workflow

*Audience: computer-science students who can program but haven't built an agentic system.
This is a narrative, concept-by-concept walkthrough — it uses By Heart as the running example
and defines each tool and term inline the first time it appears. For the terse reference
version of the same architecture, see the [README](../README.md); for the rationale behind each
design decision, see [`DECISIONS.md`](../DECISIONS.md).*

---

## The premise

By Heart turns a public-domain poem into a personalized course for memorizing it. You could
imagine writing this as a normal program: blank out every Nth word, check the user's typing with
`==`, repeat. That version works, but it can't make the two judgments that actually matter:
*which* word to hide next for **this** learner, and whether a typed answer that isn't
character-identical is still *right* ("morn" for "morning", a synonym that preserves the line).
Those are judgment calls, not string operations — which is exactly the line where you reach for
an **agentic workflow**.

> **Agentic workflow** — a program whose control flow is driven in part by a language model's
> *decisions* (what to do next, how to grade something) rather than entirely by hard-coded logic.
> The model reasons; the surrounding code routes, validates, and persists.

The guiding design rule in this project: *every model-powered step must do reasoning a `for` loop
couldn't.* If a node could be replaced by an `if` statement, it shouldn't be a model call. That
rule is what keeps an "agentic" system from being theater.

## The building blocks (defined once)

- **LLM / Google Gemini** — a large language model maps a prompt to text or structured output;
  **Gemini** is Google's LLM family, and it's the "reasoning engine" inside each smart node here.
- **Google ADK (Agent Development Kit)** — a framework for building LLM systems as a **graph** of
  steps, with typed routing between them, shared state, and built-in support for pausing to ask a
  human.
- **Node** — one step in the graph. A node takes an input, optionally calls Gemini (or a tool, or
  just runs plain Python), and emits an **event** carrying its output and an optional `route` label.
- **Graph / Workflow** — the directed graph that wires nodes together. ADK's `Workflow` object
  *is* the graph: you declare its edges, and the runtime walks it.
- **Edge / conditional routing** — an edge connects one node to a successor. A *conditional* edge
  chooses the successor from the `route` a node emits (e.g. `advance` vs. `scaffold`), so the
  model's output literally steers the program counter.
- **MCP (Model Context Protocol)** — an open protocol for exposing tools and data to LLM apps over
  a standard JSON-RPC interface, usually as a separate process. It's "USB-C for tools": instead of
  hard-wiring a capability into your app, you stand up an MCP server and any agent can call it.
- **Session / State / Memory** — ADK gives each run a state dictionary that nodes read and write to
  pass data along the graph, plus a durable memory store for things that must outlive a single run
  (here, the learner's history).

By Heart is built as **two graphs**: one that *builds* the course, and one that *runs* a study
session. Keeping them separate is a deliberate pattern — a mostly-automated pipeline vs. an
interactive, human-in-the-loop loop.

## Graph A — the Build Pipeline

This graph ingests a poem id and emits a Course (an ordered schedule of which words to hide in
which session).

```
START → provenance_gate ──admit──→ prosody_analysis → curriculum_plan → (Course)
                        └─refuse──→ refuse
```

- **`provenance_gate`** is a *deterministic* node — no model. It checks the requested poem against
  an allowlist of works published in or before 1930 and emits `route="admit"` or `route="refuse"`.
  This is the conditional edge in its purest form: a plain check decides which branch the graph
  takes. (It's also a security control — the system will only ever process vetted, public-domain
  text.)
- **`prosody_analysis`** is where the **MCP** appears. To decide which words are "easy" because of
  rhyme or meter, you first need to know how each word is *pronounced and stressed* — and an LLM
  shouldn't guess phonetics. So this node calls the **Prosody MCP**, a small local server that
  resolves stress and phonemes using the **CMU Pronouncing Dictionary**, with a
  grapheme-to-phoneme fallback for words the dictionary doesn't have (archaic/poetic vocabulary).
  The MCP exposes tools like `pronounce`, `scan_line`, and `analyze_poem`; it speaks only JSON-RPC
  on stdout (logs go to stderr) so the protocol stream stays clean. The node combines those hard
  phonetic facts with Gemini's reading of the poem's structure.
- **`curriculum_plan`** is a Gemini node that does the genuinely agentic work: given the prosodic
  map, it decides the order in which to strip the learner's "crutches" and writes a short,
  human-readable **Deletion Rationale** explaining why. This rationale is the *visible reasoning
  artifact* — the thing that proves a model made a judgment rather than a loop counting to N.

The pedagogy worth noting: instead of hiding a fixed fraction of words, By Heart removes the
specific *prosodic crutch* a learner is leaning on — the visible rhyme partner, the regular meter,
the syntactic momentum of a function word. Deciding which crutch is in play is, again, a judgment
a regex can't make.

## Graph B — the Recall Session Loop

This is the interactive graph, and it's where the **human-in-the-loop** machinery lives.

```
START → present_masked_line → [PAUSE for human] → adjudicate ──advance──→ memory_update
                                                              └─scaffold─→ memory_update
```

- **`present_masked_line`** renders the stanza with one word blanked, then yields a
  **`RequestInput`** — ADK's primitive for pausing a run to wait for external input. The graph
  literally *suspends mid-execution*; the process is free to do other things until the answer
  arrives.

  > **RequestInput** — a node yields it to pause the workflow and wait for a human (or external)
  > response, which is later fed back in to *resume* the run from exactly where it stopped.

- **`adjudicate`** runs after the human's answer comes back. It calls Gemini to grade the recall
  **semantically** — `hit`, `near_miss`, `variant`, or `miss` — never a string compare, so a
  meaning-preserving synonym can count. It also *proposes* which crutch the learner leaned on. Then
  it emits `route="advance"` (mastered) or `route="scaffold"` (needs help), and that route picks
  the next node.
- **`advance`** / **`scaffold`** — the two branches. `scaffold` is another Gemini node that gives
  the *minimum* effective hint and escalates only as needed: a rhyme cue, then a first letter, then
  a meaning gloss — graduated help rather than just showing the answer.
- **`memory_update`** persists the graded attempt to the durable memory store and ends this turn.
  Note there's **no back-edge** drawn in the graph: the loop in "Recall *Loop*" is realized
  *across* invocations — each attempt is one `present → pause → grade → record` arc, and the next
  attempt re-enters the graph. The pause/resume cycle *is* the loop.

## Two engineering patterns to take away

**1. The hybrid "LLM proposes, code disposes" pattern.** A model's output is never trusted raw. In
`adjudicate`, Gemini proposes an outcome and a crutch tag, but a deterministic validator keeps the
crutch tag *only* if that cue was actually still visible for this word, and discards it on any
non-success — you can't have leaned on a cue that wasn't there. The `scaffold` node is the same:
the model picks a hint level, but plain code clamps it to 1–3 and forbids it from regressing. This
split — a probabilistic core wrapped in a deterministic, unit-testable shell — is how you get the
model's judgment without inheriting its unreliability.

**2. The adaptive feedback loop = emergent personalization.** Because every attempt's crutch tag
lands in memory, the *next* run of the Build Pipeline can read that history and strip a *different*
crutch earlier for a learner who's over-relying on it. No node "knows" the learner; the
personalization **emerges** from one graph writing state that another graph reads. That
data-coupling-through-shared-state is the multi-agent design at work.

## The serving layer: driving the graphs live

The same two graphs run unchanged behind a **FastAPI** web app (a Python framework for HTTP
services). Two details are instructive:

- A single recall **spans two HTTP requests** — one to drive Graph B to its `RequestInput` pause
  (and stash the suspended session id), and a second to resume it with the typed answer. The web
  server's single event loop holds many such suspended runs at once; HTTP maps naturally onto ADK's
  pause/resume.
- The UI visualizes the graph executing in real time. ADK lets you register a **plugin** that fires
  a callback on every event the runtime emits; from each event you can read the active node's name,
  the branch it routed to, and whether it's paused waiting for input. The app pushes those onto a
  queue and streams them to the browser over **SSE (Server-Sent Events)** — a one-way
  server→client stream over plain HTTP — so a student watching can literally see
  `provenance_gate → prosody_analysis → curriculum_plan` light up, the Prosody MCP get called, and
  the recall loop pause on a human. The topology it draws isn't hand-maintained — it's read
  straight from the `Workflow` graph object, so the picture can't drift from the code.

## The one-paragraph summary

By Heart is two ADK **graphs** of **nodes**. Deterministic nodes (the provenance gate, the
validators) handle anything an `if` can decide; **Gemini** nodes handle the judgments — what to
teach next, whether an answer is *really* right, the minimum hint to give. An **MCP** server
supplies the hard phonetic facts the model shouldn't guess. **Conditional edges** let a model's
output choose the program's next step; **`RequestInput`** lets a graph pause for a human and
resume; **shared state and memory** let one graph's output reshape another's future behavior.
That's the whole anatomy of an agentic workflow: models for judgment, code for everything else, a
graph to wire them together, and state to make it adapt.

---

### Further reading

- [README](../README.md) — the reference architecture, setup, and run-the-demo steps.
- [`DECISIONS.md`](../DECISIONS.md) — the dated design-decision log (why each choice was made).
