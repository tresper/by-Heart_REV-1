"""Provenance policy — the public-domain guarantee, made executable.

By Heart processes ONLY poems on the vetted allowlist in ``corpus/manifest.yaml``
(US works first published in or before 1930). This module is the single source
of that policy: a pure, synchronous decision function the ``provenance_gate``
node wraps. Keeping the logic here — not in the async node — is what lets the
guarantee be unit-tested without an ADK runtime or a model key.

Design (per .claude/skills/provenance-gate/SKILL.md): **fail closed.** A poem is
admitted only when every check passes; anything else is refused, with the reason
logged to stderr (stdout is reserved for protocol/JSON elsewhere in the system).
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# The bright-line MVP test: US works first published in or before this year.
MAX_FIRST_PUBLISHED_YEAR = 1930

# corpus/ lives at the repo root, one level above this package.
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS_ROOT = _REPO_ROOT / "corpus"
DEFAULT_MANIFEST_PATH = DEFAULT_CORPUS_ROOT / "manifest.yaml"


@dataclass(frozen=True)
class ProvenanceResult:
    """Structured admit/refuse decision returned by the gate.

    ``entry`` and ``text`` are populated only on admission, so downstream nodes
    inherit verified provenance + the loaded poem rather than re-deriving them.
    """

    admitted: bool
    poem_id: str
    reason: str
    entry: dict[str, Any] | None = None
    text: str | None = None


def load_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    """Load the corpus manifest as an ``{id: entry}`` allowlist.

    The manifest is the single source of truth; the gate never hardcodes an
    alternate list. Entries without an ``id`` are skipped (they can't be keyed).
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    poems = data.get("poems") or []
    return {entry["id"]: entry for entry in poems if "id" in entry}


def _refuse(poem_id: str, reason: str) -> ProvenanceResult:
    """Build a refusal and log it to stderr (never stdout)."""
    print(f"[provenance_gate] REFUSE {poem_id!r}: {reason}", file=sys.stderr)
    return ProvenanceResult(admitted=False, poem_id=poem_id, reason=reason)


def evaluate_provenance(
    poem_id: str,
    *,
    manifest: dict[str, dict[str, Any]],
    corpus_root: str | Path = DEFAULT_CORPUS_ROOT,
) -> ProvenanceResult:
    """Decide whether ``poem_id`` may enter the Build Pipeline. Refuse by default.

    Ordered checks, each a refusal on failure:
      1. ``poem_id`` is on the allowlist (present in the manifest).
      2. ``first_published`` is an int <= 1930.
      3. the entry names a ``text_file`` that exists on disk.
      4. the file's sha256 matches the recorded ``sha256`` (tamper detection).
    Only if all pass is the poem admitted, with its entry and text attached.
    """
    entry = manifest.get(poem_id)
    if entry is None:
        return _refuse(poem_id, "not on the public-domain allowlist (corpus/manifest.yaml)")

    year = entry.get("first_published")
    if not isinstance(year, int) or year > MAX_FIRST_PUBLISHED_YEAR:
        return _refuse(
            poem_id,
            f"first_published {year!r} missing or after {MAX_FIRST_PUBLISHED_YEAR}",
        )

    text_file = entry.get("text_file")
    if not text_file:
        return _refuse(poem_id, "manifest entry has no text_file")
    text_path = Path(corpus_root) / text_file
    if not text_path.is_file():
        return _refuse(poem_id, f"text file not found: {text_file}")

    recorded_sha = entry.get("sha256")
    if not recorded_sha:
        return _refuse(poem_id, "manifest entry has no recorded sha256")

    raw = text_path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != recorded_sha:
        return _refuse(
            poem_id,
            f"sha256 mismatch (recorded {recorded_sha[:12]}…, actual {actual_sha[:12]}…)",
        )

    return ProvenanceResult(
        admitted=True,
        poem_id=poem_id,
        reason="on allowlist; first_published <= 1930; sha256 verified",
        entry=entry,
        text=raw.decode("utf-8"),
    )
