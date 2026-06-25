"""The one-command demo runner (§13 build item 8) — key-free smoke.

Keeps ``main`` green and the runner bisectable WITHOUT a Gemini key: the runner's two
key-free steps (the provenance refusal and the deterministic security eval) must pass,
and ``main`` must exit 0 on the key-free spine when no key is present (steps 2-4, which
need a model, are skipped). The live build/recall/re-plan path is exercised by hand via
``uv run python -m app.demo`` with a key — deliberately not in the always-green gate, the
same §13.4 reason the live eval sweep is kept out of pytest.
"""

from __future__ import annotations

from app import demo


def test_provenance_refusal_step_refuses_a_non_corpus_poem() -> None:
    assert demo.step1_provenance_refusal() is True


def test_security_eval_step_passes_key_free() -> None:
    assert demo.step5_security_eval() is True


def test_main_exits_zero_on_the_key_free_spine(monkeypatch) -> None:
    """No key → steps 2-4 are skipped, steps 1 and 5 run, and the runner still exits 0."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert demo.main(["--poem-id", "frost-stopping-by-woods"]) == 0
