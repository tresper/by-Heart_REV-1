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
