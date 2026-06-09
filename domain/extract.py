"""Pure clinical-note entity extraction + token classification.

Ported (and lightly expanded) from the Module 2 hands-on exercise
(`module2_hands_on_exercise.py`, Exercise 1 — Structured vs Unstructured,
and the regex-based entity extraction).

This module is intentionally PURE: module-level data plus pure functions
over plain strings. No Flask, no database access, no network/file I/O.
"""

import re

# ═══════════════════════════════════════════════════════════════════════════
# Entity patterns — (label, compiled regex). Each regex captures the value
# of interest in group(1); the matched value's offsets come from that group
# so callers get real character spans into the source text.
#
# Labels are stable and human-readable: Task 4 (blueprint/UI) colour-codes
# by these exact label strings, so don't rename them casually.
# ═══════════════════════════════════════════════════════════════════════════

_PATTERNS = [
    ("BP",            re.compile(r"BP[:\s]+(\d{2,3}/\d{2,3})\s*mmHg",   re.IGNORECASE)),
    ("HR",            re.compile(r"HR[:\s]+(\d{2,3})\s*bpm",            re.IGNORECASE)),
    ("Weight",        re.compile(r"Weight[:\s]+(\d{2,3})\s*kg",        re.IGNORECASE)),
    ("Blood Glucose", re.compile(r"glucose[:\s]+(\d{2,4})\s*mg/dL",    re.IGNORECASE)),
    ("HbA1c",         re.compile(r"HbA1c[:\s]+([\d.]+%)",             re.IGNORECASE)),
    # ICD-10 codes are uppercase by definition — NOT IGNORECASE, or the
    # uppercase [A-Z] would also match lowercase parentheticals (gene
    # variants, footnote refs) and yield false positives.
    ("ICD-10",        re.compile(r"\(([A-Z]\d{2}(?:\.\d{1,3})?)\)")),
    ("Creatinine",    re.compile(r"Creatinine[:\s]+([\d.]+)\s*mg/dL", re.IGNORECASE)),
    ("SpO2",          re.compile(r"SpO2[:\s]+(\d{2,3})\s*%",          re.IGNORECASE)),
    ("eGFR",          re.compile(r"eGFR[:\s]+(\d{2,3})",              re.IGNORECASE)),
    ("Platelets",     re.compile(r"platelets\s+(\d+)K",               re.IGNORECASE)),
    ("Microalbumin",  re.compile(r"microalbumin[:\s]+(\d+)",          re.IGNORECASE)),
]

# Compound-vital pattern used by classify_token to detect "mixed" tokens
# (e.g. a "148/92" blood-pressure reading embedded in narrative-ish text).
_COMPOUND_VITAL = re.compile(r"\d+/\d+")


# ═══════════════════════════════════════════════════════════════════════════
# Entity extraction
# ═══════════════════════════════════════════════════════════════════════════

def extract_entities(text: str) -> list[dict]:
    """Extract clinical entities from `text`.

    Returns a list of dicts ``{"label", "value", "start", "end"}`` where
    ``start``/``end`` are character offsets such that
    ``text[start:end]`` contains ``value``. Uses ``re.finditer`` so the
    offsets are the real spans of the captured value group.

    Results are sorted by start offset for stable, document-order output.
    An empty / no-match input yields an empty list.
    """
    entities: list[dict] = []
    for label, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            entities.append({
                "label": label,
                "value": m.group(1),
                "start": m.start(1),
                "end": m.end(1),
            })
    entities.sort(key=lambda e: (e["start"], e["end"]))
    return entities


# ═══════════════════════════════════════════════════════════════════════════
# Token classification (Exercise 1B)
# ═══════════════════════════════════════════════════════════════════════════

def classify_token(token: str) -> str:
    """Classify a token as ``"structured"``, ``"unstructured"`` or ``"mixed"``.

    Heuristic (counts only alphabetic-only words so that data-dense tokens
    like ``"WBC 7.8, Hb 13.2, platelets 215K"`` are NOT mistaken for prose):

    * > 4 alphabetic-only words           -> ``"unstructured"`` (narrative)
    * contains a compound vital (``d/d``) -> ``"mixed"``
    * contains any digit                  -> ``"structured"``
    * otherwise                           -> ``"unstructured"``
    """
    alpha_words = [w for w in token.split() if w.isalpha()]

    if len(alpha_words) > 4:
        return "unstructured"

    if _COMPOUND_VITAL.search(token):
        return "mixed"

    if any(ch.isdigit() for ch in token):
        return "structured"

    return "unstructured"
