---
name: provenance-gate
description: >-
  Enforce the public-domain corpus allowlist for By Heart. Use when adding or
  editing poems in corpus/manifest.yaml, when reviewing the provenance_gate
  node, or whenever a poem's copyright/public-domain status must be vetted
  before the Build Pipeline may process it.
---

# Provenance Gate

By Heart processes **only** poems on the public-domain allowlist in
`corpus/manifest.yaml`. The `provenance_gate` node is the first node of the
Build Pipeline and MUST refuse any poem not on that allowlist. This skill is the
checklist for keeping that guarantee true whenever the corpus or the gate
changes.

## The rule (non-negotiable)

- **Allowlist only.** A poem is eligible **iff** it has an entry in
  `corpus/manifest.yaml`. No open-ended or "paste-your-own-poem" ingestion in
  the MVP.
- **US works first published in or before 1930.** This is the bright-line test
  for the MVP. If you cannot cite a first-publication year **≤ 1930** from a
  verifiable source, the poem does not go in the manifest.
- **The gate refuses by default.** Any title/author not matched in the manifest
  → reject and stop the pipeline. Fail closed, never open.

## Manifest entry contract

Each poem in `corpus/manifest.yaml` should carry enough provenance to be
auditable by a reviewer who does not trust us:

```yaml
poems:
  - id: frost-stopping-by-woods          # stable slug, used as the poem key
    title: "Stopping by Woods on a Snowy Evening"
    author: "Robert Frost"
    first_published: 1923                 # MUST be an integer year ≤ 1930
    source_url: "https://www.gutenberg.org/..."   # verifiable public-domain host
    rights: public-domain-US              # why it is in the clear
    notes: "First published in New Hampshire (1923)."
```

Required fields: `id`, `title`, `author`, `first_published`, `source_url`,
`rights`. Reject the entry in review if any are missing or if
`first_published > 1930`.

## When adding a poem — checklist

1. **Verify the date.** Confirm first US publication is **≤ 1930** from a
   primary or reputable secondary source (Project Gutenberg, HathiTrust, a
   scholarly edition). Record the source in `source_url`.
2. **Confirm US public-domain status**, not merely "old" or "free to read
   online." Being on a website is not provenance.
3. **Add one manifest entry** with all required fields and a stable `id`.
4. **Do not** paste the poem body from a paywalled, annotated, or
   recently-typeset edition whose layout/notes may carry their own copyright.
   Use the public-domain source text.
5. **Update tests/eval** if you add a poem the provenance tests assert against.

## When editing the `provenance_gate` node — invariants

- The node loads the allowlist from `corpus/manifest.yaml` (single source of
  truth) — it must never hardcode an alternate list.
- Matching is by stable `id` (or an exact normalized title+author), not a fuzzy
  string compare that could admit a near-title.
- On a miss: refuse, emit a clear reason, and **halt** the Build Pipeline. Do
  not fall through to `prosody_analysis`.
- On a hit: pass the validated manifest entry forward so downstream nodes
  inherit verified provenance rather than re-deriving it.

## Red flags — stop and re-check

- A `first_published` year after 1930, or one you cannot source.
- A poem present in code/tests but **absent** from `corpus/manifest.yaml`.
- Any code path that lets a poem reach `prosody_analysis` without passing
  through `provenance_gate`.
- "It's probably fine / everyone uses it" reasoning in place of a cited date.

## After any provenance decision

Append a dated entry to `DECISIONS.md` (what was decided, why, alternatives,
the capstone concept — here **Security / public-domain compliance** — and where
it shows). The public-domain guarantee is a graded rubric item; its reasoning
must be visible.
