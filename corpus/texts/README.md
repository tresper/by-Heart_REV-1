# corpus/texts/ — canonical poem texts

Each poem on the allowlist in `../manifest.yaml` has its canonical public-domain
text stored here as a UTF-8 `.txt` file, keyed by the manifest `id`:

| manifest `id` | file |
|---|---|
| `frost-stopping-by-woods` | `frost-stopping-by-woods.txt` |
| `dickinson-because-i-could-not-stop-for-death` | `dickinson-because-i-could-not-stop-for-death.txt` |
| `whitman-o-captain-my-captain` | `whitman-o-captain-my-captain.txt` |
| `lazarus-the-new-colossus` | `lazarus-the-new-colossus.txt` |
| `kilmer-trees` | `kilmer-trees.txt` |

## Integrity contract
The manifest records each file's `text_file` (relative to `corpus/`) and its
`sha256`. The `provenance_gate` node refuses any poem whose file is missing or
whose bytes don't match the recorded hash (tamper detection). See
`.claude/skills/provenance-gate/SKILL.md`.

## Adding / updating a text
1. Paste the canonical public-domain text into the file (no editorial notes or
   typeset apparatus that could carry its own copyright).
2. Recompute the hash: `shasum -a 256 corpus/texts/<file>` (or
   `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" corpus/texts/<file>`).
3. Update that entry's `sha256` in `manifest.yaml`.
