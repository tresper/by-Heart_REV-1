"""Tests for the provenance policy (the public-domain guarantee).

Each test builds a self-contained corpus under ``tmp_path`` (a known manifest +
text file with a freshly computed sha256), so the suite is deterministic and
neither depends on the pasted seed corpus nor mutates real files. The policy is
``app.provenance.evaluate_provenance`` — a pure function the ``provenance_gate``
node wraps.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.provenance import evaluate_provenance


def _make_corpus(
    tmp_path: Path,
    *,
    poem_id: str = "p",
    text: str = "Whose woods these are I think I know.\n",
    first_published: int = 1923,
) -> tuple[dict, Path]:
    """Write a one-poem corpus and return its (manifest, corpus_root)."""
    (tmp_path / "texts").mkdir(exist_ok=True)
    rel = f"texts/{poem_id}.txt"
    (tmp_path / rel).write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    manifest = {
        poem_id: {
            "id": poem_id,
            "first_published": first_published,
            "text_file": rel,
            "sha256": sha,
        }
    }
    return manifest, tmp_path


def test_valid_corpus_poem_is_admitted(tmp_path: Path) -> None:
    """(a) An on-allowlist poem with a matching hash and a valid year is admitted."""
    text = "Whose woods these are I think I know.\n"
    manifest, corpus_root = _make_corpus(tmp_path, text=text)

    result = evaluate_provenance("p", manifest=manifest, corpus_root=corpus_root)

    assert result.admitted is True
    assert result.text == text
    assert result.entry is not None


def test_unknown_id_is_refused(tmp_path: Path, capsys) -> None:
    """(b) An id absent from the manifest is refused (fail closed), logged to stderr."""
    manifest, corpus_root = _make_corpus(tmp_path)

    result = evaluate_provenance("not-a-real-id", manifest=manifest, corpus_root=corpus_root)

    assert result.admitted is False
    assert "allowlist" in result.reason
    # Refusals must go to stderr, never stdout.
    captured = capsys.readouterr()
    assert "REFUSE" in captured.err
    assert captured.out == ""


def test_altered_text_is_refused_on_sha_mismatch(tmp_path: Path) -> None:
    """(c) A corpus poem whose text file was altered fails the sha256 check."""
    manifest, corpus_root = _make_corpus(tmp_path, poem_id="p")
    # Tamper: overwrite the file with different bytes after the hash was recorded.
    (corpus_root / "texts" / "p.txt").write_text("Whose woods these are I do NOT know.\n", encoding="utf-8")

    result = evaluate_provenance("p", manifest=manifest, corpus_root=corpus_root)

    assert result.admitted is False
    assert "sha256" in result.reason


def test_poem_after_1930_is_refused(tmp_path: Path) -> None:
    """Bonus: the bright-line year test — first_published after 1930 is refused."""
    manifest, corpus_root = _make_corpus(tmp_path, first_published=1931)

    result = evaluate_provenance("p", manifest=manifest, corpus_root=corpus_root)

    assert result.admitted is False
    assert "1930" in result.reason


def test_real_seed_corpus_all_admit() -> None:
    """Integration smoke test: every poem in the shipped manifest admits.

    Guards the real corpus — each entry must have a valid year, an existing
    text file, and a matching sha256. Skips cleanly until the texts are pasted.
    """
    from app.provenance import (
        DEFAULT_CORPUS_ROOT,
        DEFAULT_MANIFEST_PATH,
        load_manifest,
    )

    manifest = load_manifest(DEFAULT_MANIFEST_PATH)
    incomplete = [pid for pid, e in manifest.items() if "sha256" not in e]
    if incomplete:
        import pytest

        pytest.skip(f"corpus texts not yet wired in: {incomplete}")

    for poem_id in manifest:
        result = evaluate_provenance(
            poem_id, manifest=manifest, corpus_root=DEFAULT_CORPUS_ROOT
        )
        assert result.admitted is True, f"{poem_id} refused: {result.reason}"
