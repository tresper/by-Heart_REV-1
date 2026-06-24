"""Security — the runtime input-validation controls for By Heart (blueprint §8/§13.7).

``recall_input`` sanitizes the one untrusted input in either graph — a learner's typed
recall — at its single choke point, before it reaches the Adjudicator and Scaffolding
Coach prompts. The threat model these controls answer is documented in
``.claude/skills/stride-threat-model/SKILL.md``; the injection/PII eval (``evals/``)
proves them.
"""
