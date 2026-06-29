**INTRODUCTION**

The "By Heart" application turns any vetted public-domain poem into a personalized, prosody-aware memorization trainer. It exercises a valuable and increasingly rare cognitive skill: committing meaningful literature to one's own memory. We risk losing that skill in an age of instant answers from the internet, our mobile phones, and LLM chatbots.

"By Heart" is inspired by the New York Times Poetry Challenge\*, where in 2025 the paper's creative staff spent weeks developing a memorization tool for a single poem. In contrast, this application's agentic workflow scales to many poems with no new code: the same five Gemini agents that build a course for one poem build it for the next. Adding a poem is a matter of vetting its provenance, not hand-crafting a course. And beyond extending the corpus, the real benefit of "By Heart" is that it adapts to each learner's effort in a way that is reminiscent of a tutor's guidance. A fixed, deterministic script could never do that. This application builds a valuable skill, deepens an appreciation of literature, and thankfully it is enjoyable to use.

**HOW TO LAUNCH**

The "By Heart" workflow relies on five Gemini agents and two Google ADK graphs.

From a browser: [https://by-heart-web-596572954271.us-east1.run.app](https://by-heart-web-596572954271.us-east1.run.app)

To run locally:
Clone the Git repo: [https://github.com/tresper/by-Heart_REV-1](https://github.com/tresper/by-Heart_REV-1)
`$ cd web && uv run --package by-heart-web uvicorn by_heart_web.server:app --reload --port 8000`
Note:  a local run needs a Gemini API key in a `.env` file. (For reference, please see file `.env.example`) 

Once the application is launched: pick a poem from the dropdown and click **Build my course** to watch the Build Pipeline run and read the Deletion Rationale it produces. Typically, this takes less than 30 seconds. Then click **Start session** and fill in the blanked-out words. When you make an error, a Coach offers the smallest hint that will help; when you finish, click **Re-plan from my pattern** and watch the curriculum rewrite itself around the cue you lean on most.

**A NOTE ON THE LEARNING METHOD**

The teaching method is to show the text with words progressively removed and ask the learner to recall by filling in the \_\_\_\_. This requires the learner to *reconstruct* the missing words rather than memorize by repeated re-reading — this is **retrieval practice**, and decades of cognitive-science research finds it builds far more durable recall than simply reading again. The technique, though age-old, was carefully documented by Wilson Taylor\* as the "cloze" procedure. (Relatedly, computer science uses a similar approach called Masked Language Modeling, notably in Google's BERT language model\*.) While "By Heart" implements well-supported principles of how memory consolidates, we do acknowledge a limitation. Namely, we have not run a controlled learning study of its efficacy.

**HOW THE "BY HEART" APPLICATION WORKS**

Progressive masking on a fixed schedule needs no intelligence. Conceivably, an ordinary `for` loop could blank out every third word. What *cannot* be relegated is the judgment a good tutor brings: reading a poem to decide what to teach first, noticing *why* a learner actually remembered a word, and grading a recall by meaning rather than spelling. "By Heart" confines its five Gemini agents to exactly those judgments and keeps everything else deterministic. That single design decision is the core of the application.

![ADK two-graph architecture: Graph A (Build Pipeline) and Graph B (Recall Loop)](https://raw.githubusercontent.com/tresper/by-Heart_REV-1/main/docs/ADK_Graphs.png)
> *Figure 1 — The two ADK graphs, drawn live from the compiled topology so the picture cannot drift from the executed graph: Graph A forks on provenance (admit / refuse), Graph B on the grade (advance / scaffold).*

The orchestration is two Google ADK graphs. The graphs themselves are the director. There is no separate "controller" model deciding what runs next.

The **Build Pipeline** (Graph A) runs once per poem. Its first node is a *provenance gate* that admits a poem only if it is on our public-domain allowlist, was first published in or before 1930, and matches a recorded SHA-256 hash of its text; anything else is refused and the pipeline halts. An admitted poem flows to a **prosody-analysis agent**, grounded by a **Prosody MCP server** — a small, local Model Context Protocol (MCP) service (built with FastMCP) that resolves each word's pronunciation and stress through the CMU Pronouncing Dictionary, falling back to grapheme-to-phoneme synthesis for archaic or unusual words. Phonetics is exactly the kind of fact a language model will unintentionally yet confidently hallucinate. So we made that the one thing the model never guesses. The pipeline ends at a **curriculum-planning node** that is itself deterministic Python, orchestrating two further Gemini sub-agents: one **chooses which "crutch"** the learner should be weaned off next, and one **writes a short Deletion Rationale** explaining the choice. The masking schedule it builds is computed, not generated. Because nothing in this pipeline is hand-tuned to a particular poem, the same workflow produces a visibly different scansion* and a different Deletion Rationale for Frost's tetrameter and for Lazarus's sonnet. You can observe this as you demo the application for yourself.

That schedule is the pedagogical core, and it is where "By Heart" differs from an ordinary fill-in-the-blanks drill. Rather than hiding a fixed ratio of words, it strips the specific prosodic crutch a learner is leaning on, such as a visible rhyme partner, the regularity of the stress pattern, or the syntactic momentum of a phrase. It escalates the challenge by *removing cues*, not by blanking more text. Stripping the cue a learner leans on is a direct application of Bjork's principle of **desirable difficulties**\* — the counter-intuitive finding that making retrieval harder, in the right way, makes memory stronger. The Deletion Rationale ("because you have come to rely on the poem's rhyme partners, we take that cue away now") is reasoning the learner can read at every step.

The **Recall Loop** (Graph B) is where the learner sits down to study, with a genuine human-in-the-loop pause built on ADK's `RequestInput`. A node presents the masked line and the graph *waits*; the learner types what they remember; an **adjudicator agent** then grades that recall *semantically*. The grades are:  hit, near-miss, meaningful variant, or miss. Note that this is never by string comparison, so "morn" for "morning" is understood rather than failed. This, by the way, also quietly serves ESL learners and imperfect spellers. The same agent tags which still-visible crutch the recall leaned on. On success the learner advances; on a miss a **scaffolding agent** offers the minimum hint that will help, climbing a ladder from a rhyme cue to a first letter to a meaning gloss only as far as needed. Here is the *method of vanishing cues*. Every attempt is then recorded by a memory-update node.

This is what closes the loop, and it is the part we are proudest of. The crutch-dependence tag from grading is saved to a small learner-memory store, reduced into a profile of how *this particular person* fails, and read back by the planner the next time a course is built. So the next schedule takes a different cue away first. Play one session and the curriculum rewrites itself around your own weaknesses. That feedback path (not the masking) is the "agentic" part of the system. The agentic heart of "By Heart."

A word on rigor, because it matters for a tool that touches learners. Every model output that could change what the learner sees is treated as a *proposal* that deterministic code validates before it is allowed to act: the grade is clamped to its four legal values, the crutch tag is checked against the cues that were actually on screen, and the hint is bounded so it can never blurt out the answer. The masking the learner experiences is therefore deterministic and unit-tested without any API key at all. The model is swayable, but it cannot emit an illegal grade, invent a tag, over-escalate a hint, or leak the answer word. The application also collects no names and never stores the text a learner types. This is privacy by design of the data schema, not by after-the-fact scrubbing.

A note on the model: all five agents run on **Gemini Flash** (`gemini-flash-latest`). One can substitute a new model by changing one line of code. Gemini Flash is a deliberate choice, not a cost compromise. Because the deterministic policy carries correctness and each agent is confined to a narrow, well-scoped judgment, a fast, inexpensive, free-tier-eligible model is exactly the right tool. It is also what lets the hosted demo run within a free quota, and what would let "By Heart" stay free for a classroom.

Taken together, the application puts four of the capstone's course concepts into working code: a multi-agent **ADK** system with conditional routing and human-in-the-loop, a real **MCP** server, a **security** posture of validated-proposal containment, and authored **Agent Skills** that encode the project's own rules. (We did not use Antigravity, and want to mention that explicitly.) By a *meaningful* agent we mean exactly the interdependence shown above: remove any one of the five and the product degrades. This is not a thin wrapper around a single prompt. Not a trivial exercise that can be simply done with an LLM chatbot.

**WHO THIS IS FOR — AND WHY IT'S "FOR GOOD"**

We submit "By Heart" in the **Agents for Good** track. We believe it can achieve an educational objective while fostering an appreciation of literature.

Picture a teacher in an under-resourced classroom, or an adult-literacy or ESL program: with "By Heart" they stand up an evidence-based memorization unit for a poem already in their curriculum in minutes, virtually free, running locally, collecting no student data. Effectively doing what the New York Times needed an editorial team and weeks for a single poem. That **cost asymmetry is the good**: "By Heart" democratizes expert editorial labor, rather than simply asserting that poetry is good for you.

Our responsible-AI posture is structural, as manifested in the repository: 

- **Public-domain only, and fail-closed.** The provenance gate admits a poem only after an allowlist check, a first-published-by-1930 check, and a SHA-256 match. In an age of scrape-everything models, an agent whose very first node refuses anything it cannot prove is free to use is itself part of the "good."
- **Minimal personal data by design.** The stored record has no field for the free text a learner types, and identity is an opaque id. There are no names to leak, by schema rather than by redaction. That makes it safe for classrooms and for minors.
- **Explainable by design.** The Deletion Rationale tells the learner *why* a cue is being taken away, so the system is transparent rather than a black box.

"By Heart" is released under **CC BY 4.0** because this is the license this Kaggle competition requires, and ships a `NOTICE` inventory of its dependencies' licenses; the poems themselves are public domain. None of this need be taken on faith: a judge can clone the repository and, **with no API key at all**, run `uv run python -m evals.injection_pii_eval` to watch the output-containment and PII-minimization checks pass. Security is a runnable artifact, not a paragraph. Alternatively, simply open the hosted demo and play.

**HOW THIS APPLICATION WAS BUILT**

This application was built largely through "vibe coding" with an agentic coding assistant (Claude Code): we described intent in plain language and let the assistant plan, write, test, and refactor. The running system stays entirely on Google's stack, ADK 2.0 graphs on Gemini models. 

The work proceeded in small, recoverable phases. Each phase lived on its own short-lived branch, merged into an always-green trunk only when its tests passed, and was marked with an annotated tag. Any good checkpoint can be restored and any regression can be bisected. That discipline was deliberate insurance that we baked into the vibe coding sessions.

Throughout, we kept a running decision log in `DECISIONS.md`. Every non-trivial choice (for example, why the masking schedule is deterministic rather than model-generated, why the corpus is a closed allowlist, why the recall graph deliberately does *not* call the MCP) was recorded as it was made, along with the alternatives we rejected and the reasoning. It kept the project coherent across many sessions, and it became the raw material for this very writeup. A living log of decisions, we found, is one of the most useful artifacts an agentic build can produce.

**FUTURE DEVELOPMENT**

Several directions would extend the application without changing its character.

The most obvious is breadth of corpus. Because the pipeline runs unchanged on any vetted poem, growing the library from five poems spanning Frost, Dickinson, Whitman, Lazarus, and Kilmer is mostly a matter of provenance vetting rather than engineering. The grapheme-to-phoneme fallback already resolves archaic and proper-noun vocabulary, so a wide range of heritage poetry is within reach.

A second direction is learning from real use. With learners' (anonymous) outcomes in hand, we could tune the crutch-removal policy and the scaffolding ladder against what actually helps, and wire ADK's `MemoryService` to carry personalization and spaced review across longer stretches of time. Currently, the durable record is a simple local JSON store.

A third is cost and latency. The system reads its model from configuration, so as newer and more efficient Gemini models arrive they can be dropped in to make each session faster and cheaper. This is important for a tool meant to be free and friendly to a classroom. Natural further steps include an audio path for read-aloud and spoken recall, and a spacing scheduler that brings a poem back days later when recall is hardest, and therefore most durable.

**CONCLUSION**

This project was designed as an example of an "Agent for Good," aspiring to advance education through an appreciation of literature. In developing this application we set out to show how an agentic solution can be built to scale while retaining the personal touch that guides a learner building a cognitive skill. Our conviction is simple: a system that is honest about where intelligence is genuinely needed (and rigorous, deterministic, and verifiable everywhere else) can deliver genuine value.

**CITATIONS**

\* New York Times Poetry Challenge — [https://www.nytimes.com/interactive/2025/books/edna-st-vincent-millay-recuerdo-poem-challenge.html](https://www.nytimes.com/interactive/2025/books/edna-st-vincent-millay-recuerdo-poem-challenge.html), by A.O. Scott and Aliza Aufrichtig, April 28, 2025.

\* Cloze procedure (Wilson Taylor) — [https://en.wikipedia.org/wiki/Cloze_test](https://en.wikipedia.org/wiki/Cloze_test)

\* BERT (language model) — [https://en.wikipedia.org/wiki/BERT_(language_model)](https://en.wikipedia.org/wiki/BERT_\(language_model\))

\* Retrieval practice / the testing effect — [https://en.wikipedia.org/wiki/Testing_effect](https://en.wikipedia.org/wiki/Testing_effect)

\* Desirable difficulties (Robert A. Bjork) — [https://en.wikipedia.org/wiki/Desirable_difficulty](https://en.wikipedia.org/wiki/Desirable_difficulty); the graduated-hint Coach follows the *method of vanishing cues* (Glisky, Schacter & Tulving, 1986).

Scansion:  the metrical rhythm and pattern of a line of poetry
