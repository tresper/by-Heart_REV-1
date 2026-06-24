"""The By Heart security eval — the runnable proof of the §8/§13.7 controls.

``scenarios`` holds the synthetic adversarial corpus (injection + PII probes) as
readable data; ``injection_pii_eval`` runs them as a one-command PASS/FAIL harness
(``python -m evals.injection_pii_eval``) and is also imported by the pytest suite, so
``uv run pytest`` stays the single green gate. The deterministic core needs no API key;
the live adjudicator/coach scenarios run only when a Gemini key is present.
"""
