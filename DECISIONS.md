# DECISIONS.md — By Heart implementation decision log

**Purpose:** an append-only record of key implementation decisions and their rationale. This is the **raw material for the Kaggle Writeup** ("Journey & key decisions"), and it feeds the `README.md` and the video's "The Build" segment.

**Rules**
- Append-only; newest at top. Date every entry.
- Keep it **factual engineering rationale** — this repo will be public (and CC-BY if it wins). No secrets; no "how to impress the judges" language.
- For each decision, name the **capstone concept** it serves and **where it will show** (code / video / writeup).

**Entry template**
```
## YYYY-MM-DD — <short title>
- Decision: <what was decided>
- Why: <reasoning>
- Alternatives considered: <options + why rejected>
- Concept served: <ADK | MCP | Agent skills | Security | Deployability>
- Shows in: <code | video | writeup>
```

---

## 2026-06-24 — Corpus text canonicalization: body-only, and which edition the hash pins
- Decision: store each poem as **body-only** (no title line) UTF-8 with a single trailing newline and single blank lines between stanzas; the manifest `sha256` then binds those exact bytes. Where a poem has competing editions, the committed text matches the **public-domain source we recorded in `source_url`**, not the modern critical edition. Concretely: Dickinson is the regularized **1890 "The Chariot"** text from Gutenberg #12242 — five stanzas, omitting the "Or rather, he passed us" stanza and using "children played / Their lessons scarcely done" — *not* the 6-stanza Franklin/Johnson text. Frost and Whitman are likewise the bodies of their recorded sources (Whitman = deathbed-edition).
- Why: body-only keeps the unit of masking (Graph B) equal to a line of verse, with no title to special-case. Pinning the hash to the *recorded source's* edition keeps `source_url` honest — the cited page actually contains these bytes — and makes the corpus reproducible. The editorial-variant note matters: someone diffing our Dickinson against a modern anthology will see "missing stanza" and "wrong stanza 3," and that is correct-by-design, not corruption.
- Process note: each pasted text was proofed line-by-line before hashing; this caught a missing "a" in the Frost title (moot once title-dropped) and a stray double space in Dickinson's "centuries; but each". Small edits change the hash, so they were settled before the manifest recorded `sha256`.
- Alternatives considered: include the title line (rejected — adds a non-verse line the masking logic must exempt); use the modern critical edition for Dickinson (rejected — it doesn't match the 1890 `source_url`, breaking the provenance chain the gate asserts); normalize/reformat pasted text (rejected — store exactly what the source prints, so the hash means "this edition," not "our reflow").
- Concept served: Security / Agent skills.
- Shows in: code, writeup.

## 2026-06-24 — ADK scaffold: agents-cli prototype, trimmed to a no-cloud core
- Decision: scaffold with `agents-cli create -a adk --prototype` (per blueprint §13.1), then relocate the minimal project to the repo root and **trim** the generated `pyproject.toml` to `google-adk>=2.0.0,<3.0.0` + `pyyaml` (dropping the `[gcp]` extra and the `google-cloud-*` / `opentelemetry` / `gcsfs` deps). Kept `agents-cli-manifest.yaml` so the lifecycle commands (lint/eval/playground) still recognize the project. Build the two graphs with the real graph API — `google.adk.workflow` (`Workflow`, `@node`, `START`, routing-map edges) + `RequestInput` — **not** the `Agent`+`App` ReAct sample the template ships.
- Why: the template targets Vertex AI / Cloud Run and pulls a heavy GCP stack the MVP doesn't use (blueprint §9: no cloud deploy). Trimming keeps a clean-clone setup small and avoids GCP-auth-at-import (the sample `agent.py` calls `google.auth.default()` on import). Crucially, the installed-package API was read on disk before writing any node code: confirmed **google-adk 2.3.0**, async-generator nodes taking `(ctx, node_input)`, conditional fan-out via `Event(output=..., route=...)`.
- Alternatives considered: a fully hand-rolled `uv init` project (lighter, but skips the official scaffold and its eval wiring — and §13.1 explicitly says use agents-cli); keeping the template's `Agent`+`App` ReAct code (rejected — the project is two graph Workflows, not a single ReAct agent); assuming the ADK API from memory (rejected — verified against the installed 2.3.0 source instead).
- Concept served: Agent / multi-agent (ADK) / Agent skills.
- Shows in: code, writeup.

## 2026-06-24 — Provenance gate: sha256 content integrity + pure, testable policy
- Decision: split the gate into a pure synchronous policy (`app/provenance.py::evaluate_provenance`) and a thin async ADK node that wraps it. The policy fails closed through ordered checks: on the allowlist → `first_published <= 1930` → text file present → **sha256 of the file bytes matches the manifest's recorded `sha256`** (tamper detection) → admit. The manifest gains `text_file` + `sha256` per entry; canonical texts live in `corpus/texts/<id>.txt`. Refusals are logged to **stderr**, never stdout.
- Why: separating policy from the node lets the public-domain guarantee be unit-tested without an ADK runtime or a model key (4 pytest cases: admit, unknown-id, tampered-text, post-1930). The sha256 check is the concrete answer to the prior entry's "a present-but-wrong source is the failure mode" — content is verified at gate time, not assumed. Stderr-only logging matches the MCP stdout-hygiene convention used elsewhere.
- Alternatives considered: putting logic directly in the async node (rejected — forces an async/ADK harness into every test); trusting the file's presence without hashing (rejected — that is exactly the tamper/swap hole); a string-compare of the poem text (rejected — hashing is O(1) to store and compare, and is the standard integrity primitive).
- Concept served: Security.
- Shows in: code, writeup.

## 2026-06-24 — Seed corpus + source_url verification
- Decision: seed `corpus/manifest.yaml` with three vetted entries — Frost, "Stopping by Woods on a Snowy Evening" (1923); Dickinson, "Because I could not stop for Death" (1890); Whitman, "O Captain! My Captain!" (1865) — each carrying `id`, `title`, `author`, `first_published`, `source_url`, `rights`. Every `source_url` was fetched and confirmed to resolve to the named work before commit.
- Why: provenance is only real if the cited source actually holds the cited text. Verification caught a wrong link — the Frost `source_url` initially pointed at Gutenberg #58018, an unrelated 1817 religious tract; the correct *New Hampshire* (1923) collection is #58611. This is exactly the skill's "being on a website is not provenance" red flag, observed in practice.
- Implication for the gate: the `provenance_gate` node should validate that each `source_url` resolves to the named work, not merely that the field is populated. A present-but-wrong URL is the failure mode to guard against.
- Alternatives considered: trusting plausible-looking Gutenberg IDs without fetching (rejected — that is what produced the bad Frost link); deferring all corpus content to the build phase (rejected — a seeded corpus lets the demo run end-to-end immediately).
- Concept served: Security / Agent skills.
- Shows in: code, writeup.

## 2026-06-24 — Git hygiene: ignore runtime state, commit the seed corpus
- Decision: extend `.gitignore` to drop `.DS_Store`, `.claude/settings.local.json`, all `*.db`/`*.sqlite`/`*.sqlite3` files and their transient sidecars (`-wal`, `-shm`, `-journal`) — but re-include `corpus/*.db|*.sqlite|*.sqlite3` so the pre-seeded public-domain corpus ships in-repo. Convention: committed corpus data lives under `corpus/`; learner runtime state (attempts, mastery, sessions) lives elsewhere and stays untracked.
- Why: keeps secret-adjacent and machine-specific files out of a public repo, prevents accidental commits of learner attempt data, and guarantees the demo clones with data already present. The location-based exemption is more robust than per-file negation as the corpus grows.
- Alternatives considered: blanket `*.db` ignore (would block the seed corpus); committing runtime state too (privacy noise, churn, and it's regenerable); relying on the user's global `~/.config/git/ignore` for `.claude/settings.local.json` (not portable to collaborators or CI on a public repo).
- Concept served: Security.
- Shows in: code.

## 2026-06-24 — Coding toolchain: Claude Code, used transparently
- Decision: build with Claude Code (Opus 4.8 + Sonnet); the runtime stack stays Google (ADK 2.0 + Gemini).
- Why: Claude Code is a recognized member of the `SKILL.md` agent-skills ecosystem the course teaches; an honest "Build" story scores better than obscuring the tool.
- Alternatives considered: Antigravity (course default — adds a 5th video concept, but unnecessary and we prefer transparency); being coy about the tool (rejected as evasive).
- Concept served: Agent skills.
- Shows in: video, writeup.

## 2026-06-24 — Public-domain enforcement: corpus-only MVP + Provenance Gate
- Decision: the MVP processes only poems listed in a vetted `corpus/manifest.yaml` (US, first published in or before 1930); the `provenance_gate` node refuses anything else; no open-ended uploads.
- Why: structurally eliminates copyright risk, and doubles as an allowlist security control and an authored skill.
- Alternatives considered: open ingestion with an attestation gate (reintroduces copyright + prompt-injection surface; deferred to a gated stretch).
- Concept served: Security.
- Shows in: code, writeup.

## 2026-06-24 — Deletion theory: "removing crutches"
- Decision: the deletion policy strips the prosodic cue a learner is currently relying on (visible rhyme partner, metrical regularity, syntactic momentum), escalating by removing cues rather than masking a fixed ratio.
- Why: rhyme and meter are retrieval scaffolds; durable recall requires unaided retrieval (Bjork's desirable difficulties). Inferring which crutch supported a given recall is a judgment a regex cannot make.
- Alternatives considered: fixed-ratio cloze (the reducible-to-a-loop baseline); "exploit cues" (mask rhyme words first for easy wins — rejected because it trains reliance, not durability).
- Concept served: Agent / multi-agent (ADK).
- Shows in: code, video, writeup.

## 2026-06-24 — Prosody MCP coverage: CMU dict + g2p fallback
- Decision: the Prosody MCP resolves stress/phonemes via the CMU Pronouncing Dictionary, with a grapheme-to-phoneme fallback for out-of-dictionary tokens (archaic/poetic vocabulary, proper nouns, contractions).
- Why: the corpus is exactly the vocabulary CMU under-covers; the fallback closes the gap so every word resolves and scansion is grounded, not hallucinated.
- Alternatives considered: CMU-only (gaps on "morn", "o'er", proper nouns); LLM-only pronunciation (hallucinates — admissible only as proposals validated against the dict/g2p).
- Concept served: MCP server.
- Shows in: code, writeup.
