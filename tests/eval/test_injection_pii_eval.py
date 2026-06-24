"""The injection/PII eval, under pytest (§13.7) — so ``uv run pytest`` is the single gate.

This gate carries the DETERMINISTIC core (containment / sanitizer / PII-minimization): the
falsifiable security artifact, key-free and always-green on any clone. Every check must
pass, proving an injected recall cannot escape the validated-proposal clamp and a recall's
PII cannot reach the store.

The LIVE model sweep — driving the real Adjudicator and Coach over every injection scenario
— lives in the standalone harness ``evals/injection_pii_eval.py`` (the DoD §11 #5 artifact a
judge runs by hand). It is deliberately NOT in this gate: the harness runs its calls on one
shared event loop, whereas the suite's per-test synchronous Runners each spin a new loop, and
piling more live model calls into the gate trips ADK's "Event loop is closed" teardown race
(the §13.4 constraint). Keeping live coverage in the harness keeps ``main`` reliably green.
"""

from __future__ import annotations

from evals.injection_pii_eval import deterministic_checks


def test_deterministic_security_checks_all_pass() -> None:
    checks = deterministic_checks()
    assert checks, "the eval must produce checks"
    failures = [c for c in checks if not c.passed]
    assert not failures, "failed: " + "; ".join(f"{c.name} ({c.detail})" for c in failures)


def test_containment_clamps_every_injection_to_a_safe_grade() -> None:
    """The signature guarantee: a swayed model still yields outcome=miss, dependence=none."""
    containment = [c for c in deterministic_checks() if c.name.startswith("containment[")]
    assert containment
    assert all(c.passed for c in containment)


def test_no_pii_scenario_reaches_the_store() -> None:
    pii = [c for c in deterministic_checks() if c.name.startswith("pii-not-persisted[")]
    assert pii
    assert all(c.passed for c in pii)
