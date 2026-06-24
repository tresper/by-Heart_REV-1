"""Curriculum planning — the crutch-removal deletion policy and its adaptive overlay.

``policy`` builds the deterministic multi-session masking schedule (blueprint §4/§13.4);
``memory`` records per-learner recall attempts and reduces them to a crutch-dependence
profile that drives the §13.5 adaptive re-planning (strip the cue the learner most leans
on next); ``types`` holds the shared Course / directive data shapes.
"""
