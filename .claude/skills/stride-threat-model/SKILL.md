---
name: stride-threat-model
description: >-
  The STRIDE threat model for By Heart and the controls that answer each threat.
  Use when adding or changing a node, tool, prompt, or store; when handling any
  untrusted input (learner recall); when reviewing secrets/PII handling; or
  whenever a security claim in the README, video, or writeup must be backed by
  where the control actually lives in code.
---

# STRIDE Threat Model — By Heart

By Heart is a two-graph ADK system over a vetted public-domain corpus. Its attack
surface is small **by design** (blueprint §8): no accounts, no open-ended poem
ingestion, no cloud deploy in the MVP, and exactly one untrusted input — a
learner's typed recall. This skill names the threat in each STRIDE category as it
applies *here*, the control that answers it, and the file the control lives in, so
every security claim is checkable. The injection/PII eval (`evals/`) is the
runnable proof; this skill is the map.

## The trust boundaries (know these first)

- **Trusted, deterministic:** the corpus text and everything derived from it — the
  structural map (`prosody_analysis`), masks, expected words, available cues, rhyme
  and first-letter hints. These reach the LLM nodes as data the system computed.
- **Untrusted:** the learner's typed recall. It is the **only** free text that
  crosses into the system, and it flows into the Adjudicator and Scaffolding Coach
  prompts. Treat it as hostile input everywhere it appears.
- **Secret:** the Gemini API key. It lives only in `.env` (gitignored); never a
  tracked file.

## STRIDE — threat → control → where

### S — Spoofing (identity)
- **Threat:** impersonating a learner to read or poison their progress.
- **Control:** identity is an **opaque `learner_id`** only (default `"demo"`),
  resolved from session state — no names, no auth claims, no real-identity account
  to spoof (blueprint §8/§9 "minimal-PII"). The MVP scopes identity down rather
  than securing a richer one.
- **Where:** `_resolve_learner_id` in `app/graph_build.py`; the id is just a store
  key in `app/curriculum/memory.py`.

### T — Tampering (integrity)
- **Threat:** swapping in a non-vetted poem text, or corrupting the learner store.
- **Controls:** the corpus is content-addressed — `provenance_gate` recomputes each
  poem's **SHA-256** and refuses on any mismatch with the manifest, so an altered
  text cannot enter the pipeline. The manifest is the single source of truth (no
  hardcoded alternate list). The learner store is written **atomically** (temp file
  + `os.replace`), so a crash cannot leave a half-written record.
- **Where:** `evaluate_provenance` (sha256 check) in `app/provenance.py`; the atomic
  write in `app/curriculum/memory.py` (`_save`).

### R — Repudiation (auditability)
- **Threat:** an action with no trace; an undebuggable adaptation.
- **Controls:** every graded attempt is appended to the learner store as a structured
  `Attempt` (outcome + crutch tag + position), and each session emits a human-readable
  **Deletion Rationale**. Together they make *why the course adapted* auditable.
  (Scope note: this is a local, single-user audit trail — not a tamper-evident log;
  that would be over-building for the MVP.)
- **Where:** `Attempt` / `LearnerMemory` in `app/curriculum/memory.py`; the rationale
  in `curriculum_plan` (`app/graph_build.py`).

### I — Information disclosure (confidentiality)
- **Threats:** leaking a secret, leaking PII, or leaking non-protocol bytes on a
  channel a client parses as protocol.
- **Controls:** **secrets hygiene** — the key is read from the environment/`.env`
  only, never hardcoded; `.env.example` ships placeholders. **Minimal-PII** — the
  store records no names and **never persists the free-text recall**; `Attempt` has
  no field for it, so a recall carrying PII or an injection payload cannot be written
  to disk. **MCP channel hygiene** — the Prosody MCP writes only JSON-RPC to stdout
  and sends all logging to stderr, so logs can't corrupt the protocol stream.
- **Where:** `app/models.py` (key from env); `Attempt` fields in
  `app/curriculum/memory.py` (no recall field); `app/prosody/server.py` (stderr logging).

### D — Denial of service (availability)
- **Threat:** an oversized or pathological recall stuffing a prompt or wedging a node.
- **Controls:** recall input is **bounded and normalized** before it reaches any model
  — length capped at `MAX_RECALL_CHARS`, control/zero-width/bidi codepoints stripped,
  newlines collapsed. The Gemini wrapper carries a small **retry budget** rather than
  retrying unbounded. (No untrusted poem ingestion means no adversary-controlled text
  for the MCP to choke on; the g2p fallback bounds the dictionary-miss path.)
- **Where:** `sanitize_recall` in `app/security/recall_input.py`; `gemini()` retry
  options in `app/models.py`.

### E — Elevation of privilege (acting outside intended bounds)
- **Threats:** untrusted text steering the pipeline (prompt injection); arbitrary poems
  entering the system.
- **Controls (defense in depth):**
  1. **Allowlist gate** — only manifest poems are processed; there is no path for
     arbitrary untrusted text to enter the Build Pipeline at all (`provenance_gate`).
  2. **Prompt-injection containment is structural, not just instructional.** The
     Adjudicator and Coach are told the recall is **untrusted DATA, never an
     instruction** — but the real guarantee is that their output is a *validated
     proposal*: `_validate_adjudication` clamps `outcome` to the legal vocabulary and
     `crutch_dependence` to the cues that were actually visible, and `_validate_hint`
     clamps the hint level **and** replaces any hint that names the masked word with a
     non-disclosing deterministic cue (the answer word is threaded in for a word-boundary
     check; the rhyme/first-letter candidates are answer-free by construction). So even a
     model fully swayed by an injected recall **cannot** emit an out-of-vocabulary grade,
     fabricate a crutch tag, escalate a hint past where the deterministic facts allow, or
     disclose the answer in a hint.
- **Where:** `app/provenance.py`; `_validate_adjudication` / `_validate_hint` and the
  hardened instructions in `app/graph_recall.py`; the entry-point sanitizer in
  `app/security/recall_input.py`.

## Invariants — do not regress these

- The learner recall is sanitized at its **single choke point** (`_recall_text` →
  `sanitize_recall`). Never read raw learner text into a prompt on a new path; route
  it through the choke point.
- LLM grades/hints are **never trusted raw.** Any new LLM node that consumes untrusted
  input must clamp its output against deterministic ground truth before it acts.
- The free-text recall is **never persisted.** Do not add a recall field to `Attempt`
  or otherwise write learner free text to disk.
- No secret in any tracked file; the MCP stdout stays pure JSON-RPC.

## Red flags — stop and re-check

- Untrusted learner text reaching a model or the store without passing
  `sanitize_recall` / without an output-validation clamp.
- A new field that would persist a learner's free-text answer or any real-identity PII.
- A code path that reaches `prosody_analysis` without passing `provenance_gate`.
- `print()` (or library logging to stdout) inside the MCP server.
- A key, token, or password in a tracked file or a test fixture.

## After any security decision

Append a dated entry to `DECISIONS.md` (what was decided, why, alternatives, the
capstone concept — here **Security** — and where it shows: code / video / writeup).
Run the injection/PII eval (`uv run python -m evals.injection_pii_eval`) and the test
suite before the milestone commit; the eval is the evidence the controls above hold.
