# Public-Domain Provenance

By Heart processes **only** poems on a frozen, hand-vetted allowlist. This is a deliberate
copyright-safety decision (blueprint §8): protected work cannot be misused if protected work
cannot enter the system. There is **no** open-ended "paste your own poem" ingestion.

## The standard

As of **January 1, 2026**, US works **first published in or before 1930** are in the public
domain. Every poem in the corpus satisfies this with margin (the most recent was first
published in 1923).

## How the guarantee is enforced

- **Single source of truth.** [`corpus/manifest.yaml`](corpus/manifest.yaml) is the allowlist.
  Each entry records `id`, `title`, `author`, `first_published`, `source_url`, `rights`, the
  `text_file`, and a `sha256` of that text.
- **The Provenance Gate fails closed.** The `provenance_gate` node
  ([`app/provenance.py`](app/provenance.py)) admits a poem **iff** it is on the allowlist, its
  text file exists, and its SHA-256 matches the manifest. Anything else is refused — so the gate
  is simultaneously the copyright guarantee and an allowlist input-validation control. See the
  [`provenance-gate`](.claude/skills/provenance-gate/SKILL.md) skill.
- **Integrity.** The recorded `sha256` detects any drift between the manifest's provenance claim
  and the bytes actually fed to the pipeline.

## The corpus

| Poem | Author | First published | Source | Public-domain rationale |
|---|---|---|---|---|
| "Stopping by Woods on a Snowy Evening" | Robert Frost | 1923 | [Gutenberg 58611](https://www.gutenberg.org/ebooks/58611) | US work first published 1923 (in the collection *New Hampshire*), ≤ 1930 → PD. |
| "Because I could not stop for Death" | Emily Dickinson | 1890 | [Gutenberg 12242](https://www.gutenberg.org/ebooks/12242) | Written c. 1863; first published (as "The Chariot") in *Poems by Emily Dickinson*, ed. Higginson & Todd, 1890, ≤ 1930 → PD. |
| "O Captain! My Captain!" | Walt Whitman | 1865 | [Gutenberg 1322](https://www.gutenberg.org/ebooks/1322) | First published 1865 in *Sequel to Drum-Taps*; later collected in *Leaves of Grass*, ≤ 1930 → PD. |
| "The New Colossus" | Emma Lazarus | 1883 | [Wikisource](https://en.wikisource.org/wiki/The_New_Colossus) | US work first published 1883 (written for the Bartholdi Pedestal Fund; later cast on a plaque inside the Statue of Liberty), ≤ 1930 → PD. |
| "Trees" | Joyce Kilmer | 1913 | [Wikisource](https://en.wikisource.org/wiki/Trees_(Kilmer)) | US work first published 1913 in *Poetry* magazine; collected in *Trees and Other Poems* (1914), ≤ 1930 → PD. |

Each text in [`corpus/texts/`](corpus/texts/) is a body-only transcription of the cited
public-domain edition (titles omitted; see each manifest entry's `notes` for edition details).

## Licensing note

By Heart is released under CC-BY (the capstone's winning license requirement). Shipping only
public-domain poems keeps the repository safely open-sourceable — no in-copyright text is ever
committed or processed.
