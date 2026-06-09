"""Tests for the pure clinical-note extraction logic in domain.extract.

These exercise only pure functions over plain strings — no Flask, no DB,
no I/O. This file is the TDD spec for Task 3 (entity extraction + token
classification).
"""

import pytest

from domain import extract


# Sample discharge note fixture (UTF-8: contains en-dash —, en-dash – and ²).
NOTE = """DISCHARGE SUMMARY — Bangalore City Hospital
Patient: Rajan Menon, 54M   |  MRN: PT-2024-001   |  Date: 2024-06-03
Attending: Dr. Priya Sharma, MD Endocrinology

PRESENTING COMPLAINT:
Patient presented with a 4-day history of polydipsia, polyuria, and blurred
vision. He also reported fatigue and mild lower-limb tingling over 3 weeks.
Known case of Type 2 Diabetes Mellitus, poorly controlled.

EXAMINATION:
BP: 148/92 mmHg. HR: 88 bpm. SpO2: 98% on room air. Weight: 84 kg.
Bilateral pedal oedema (1+). Fundoscopy shows early background retinopathy.

INVESTIGATIONS:
Fasting glucose: 182 mg/dL (ref: 70–99). HbA1c: 8.9% (ref: <5.7%).
Urine microalbumin: 42 mg/g creatinine (borderline elevated).
CBC: WBC 7.8, Hb 13.2, platelets 215K — all within normal limits.
Creatinine: 1.1 mg/dL. eGFR: 68 mL/min/1.73m² (G2 — mildly decreased).

ASSESSMENT & PLAN:
1. Type 2 Diabetes Mellitus (E11.65) — hyperglycaemia with hyperlipidaemia.
   Increased Metformin to 1000mg BD. Added Glipizide 5mg OD.
2. Diabetic nephropathy — early stage (N08). Monitor eGFR quarterly.
3. Hypertension (I10): continue Amlodipine 5mg OD, add Ramipril 2.5mg.

FOLLOW-UP: 4 weeks with Dr. Sharma. Repeat HbA1c in 3 months.
DIET: Low glycaemic index diet. Avoid processed foods and refined sugar.
"""


# The 8 classifier cases from the Exercise 1B contract.
CLASSIFIER_CASES = [
    ("BP: 148/92 mmHg", "mixed"),
    ("Patient presented with a 4-day history of polydipsia and polyuria.", "unstructured"),
    ("HbA1c: 8.9%", "structured"),
    ("E11.65", "structured"),
    ("Bilateral pedal oedema (1+). Fundoscopy shows early retinopathy.", "unstructured"),
    ("WBC 7.8, Hb 13.2, platelets 215K", "structured"),
    ("Low glycaemic index diet. Avoid processed foods and refined sugar.", "unstructured"),
    ("eGFR: 68 mL/min", "structured"),
]


# ── extract_entities ────────────────────────────────────────────────────────

def _labels_to_values(entities):
    """Group entity values by label for convenient assertions."""
    out = {}
    for ent in entities:
        out.setdefault(ent["label"], []).append(ent["value"])
    return out


def test_extract_entities_offsets_are_valid():
    """Generic offset-validity invariant: text[start:end] contains value."""
    entities = extract.extract_entities(NOTE)
    assert entities, "expected at least one entity from the sample note"
    for ent in entities:
        assert set(ent) >= {"label", "value", "start", "end"}
        assert isinstance(ent["start"], int)
        assert isinstance(ent["end"], int)
        assert 0 <= ent["start"] <= ent["end"] <= len(NOTE)
        assert ent["value"] in NOTE[ent["start"]:ent["end"]]


# Each required label and a substring that must appear in one of its values.
ENTITY_CASES = [
    ("BP", "148/92"),
    ("HR", "88"),
    ("Weight", "84"),
    ("Blood Glucose", "182"),
    ("HbA1c", "8.9"),
    ("ICD-10", "E11.65"),
    ("Creatinine", "1.1"),
    ("SpO2", "98"),
    ("eGFR", "68"),
    ("Platelets", "215"),
    ("Microalbumin", "42"),
]


@pytest.mark.parametrize("label,substr", ENTITY_CASES)
def test_extract_entities_finds_label(label, substr):
    values = _labels_to_values(extract.extract_entities(NOTE))
    assert label in values
    assert any(substr in v for v in values[label])


def test_extract_entities_icd10_is_case_sensitive():
    """Lowercase parentheticals must NOT be picked up as ICD-10 codes."""
    values = _labels_to_values(extract.extract_entities("the variant (a12) was noted"))
    assert "ICD-10" not in values


def test_extract_entities_empty_string_returns_empty_list():
    assert extract.extract_entities("") == []


def test_extract_entities_no_match_returns_empty_list():
    assert extract.extract_entities("hello world, nothing clinical here") == []


# ── classify_token ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("token,expected", CLASSIFIER_CASES)
def test_classify_token(token, expected):
    assert extract.classify_token(token) == expected
