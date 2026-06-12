"""Tests for the pure intake validation logic in domain.intake.

These are the TDD spec for the Register-Patient / Record-Result forms:
`validate_patient` and `validate_result` take the raw JSON payload from the
browser and return `(clean, errors)` — `clean` is the normalized dict the
blueprint can persist as-is, `errors` maps field name → human message (empty
when valid). `next_patient_id` / `next_mrn` mint the next sequential ids from
a passed-in list (the blueprint supplies it from SQL — no DB in here).
"""

from datetime import date, timedelta

import pytest

from domain import intake


# ── validate_patient: happy path ─────────────────────────────────────────────

def good_patient():
    return {
        "full_name": "  Asha Kumar ",
        "dob": "1995-12-30",
        "gender": "f",
        "blood_type": "O+",
        "phone": "9876501234",
        "city": "Bangalore",
    }


def test_valid_patient_has_no_errors_and_normalizes():
    clean, errors = intake.validate_patient(good_patient())
    assert errors == {}
    assert clean["full_name"] == "Asha Kumar"      # stripped
    assert clean["dob"] == date(1995, 12, 30)      # parsed to a date
    assert clean["gender"] == "F"                  # uppercased
    assert clean["blood_type"] == "O+"
    assert clean["city"] == "Bangalore"


def test_patient_optional_fields_default_empty():
    clean, errors = intake.validate_patient(
        {"full_name": "Ravi Rao", "dob": "1980-01-01", "gender": "M"}
    )
    assert errors == {}
    assert clean["blood_type"] == ""
    assert clean["phone"] == ""
    assert clean["city"] == ""


# ── validate_patient: rejections ─────────────────────────────────────────────

@pytest.mark.parametrize("field,value", [
    ("full_name", ""),            # required
    ("full_name", "X"),           # too short
    ("dob", ""),                  # required
    ("dob", "not-a-date"),
    ("dob", "12/30/1995"),        # wrong format
    ("gender", ""),
    ("gender", "X"),
    ("blood_type", "C+"),         # not an ABO/Rh group
    ("phone", "abc"),             # not a phone
])
def test_patient_field_rejections(field, value):
    payload = good_patient()
    payload[field] = value
    _, errors = intake.validate_patient(payload)
    assert field in errors


def test_patient_dob_must_be_in_the_past():
    payload = good_patient()
    payload["dob"] = (date.today() + timedelta(days=1)).isoformat()
    _, errors = intake.validate_patient(payload)
    assert "dob" in errors


def test_patient_collects_multiple_errors():
    _, errors = intake.validate_patient({"full_name": "", "dob": "", "gender": ""})
    assert {"full_name", "dob", "gender"} <= set(errors)


# ── validate_result ──────────────────────────────────────────────────────────

def test_valid_result_normalizes_and_enriches_from_catalog():
    clean, errors = intake.validate_result(
        {"loinc_code": "4548-4", "value": "9.1", "obs_date": "2026-06-12"}
    )
    assert errors == {}
    assert clean["value"] == 9.1                   # parsed float
    assert clean["display_name"] == "HbA1c"        # enriched from catalog
    assert clean["unit"] == "%"
    assert clean["obs_date"] == date(2026, 6, 12)


def test_result_date_defaults_to_today():
    clean, errors = intake.validate_result({"loinc_code": "2708-6", "value": 97})
    assert errors == {}
    assert clean["obs_date"] == date.today()


@pytest.mark.parametrize("payload,field", [
    ({"loinc_code": "", "value": 5}, "loinc_code"),          # required
    ({"loinc_code": "0000-0", "value": 5}, "loinc_code"),    # unknown test
    ({"loinc_code": "4548-4", "value": ""}, "value"),        # required
    ({"loinc_code": "4548-4", "value": "high"}, "value"),    # not a number
    ({"loinc_code": "4548-4", "value": 250}, "value"),       # implausible HbA1c
    ({"loinc_code": "2708-6", "value": 30}, "value"),        # implausible SpO2
    ({"loinc_code": "4548-4", "value": 7, "obs_date": "tomorrowish"}, "obs_date"),
])
def test_result_rejections(payload, field):
    _, errors = intake.validate_result(payload)
    assert field in errors


def test_result_date_must_not_be_future():
    future = (date.today() + timedelta(days=2)).isoformat()
    _, errors = intake.validate_result(
        {"loinc_code": "4548-4", "value": 7, "obs_date": future}
    )
    assert "obs_date" in errors


# ── id minting ───────────────────────────────────────────────────────────────

def test_next_patient_id_continues_the_sequence():
    assert intake.next_patient_id(["PT-001", "PT-002", "PT-008"]) == "PT-009"


def test_next_patient_id_handles_gaps_and_noise():
    assert intake.next_patient_id(["PT-003", "PT-011", "WEIRD-9"]) == "PT-012"


def test_next_patient_id_empty_registry():
    assert intake.next_patient_id([]) == "PT-001"


def test_next_mrn_continues_the_sequence():
    assert intake.next_mrn(["MRN-10001", "MRN-10008"]) == "MRN-10009"


def test_next_mrn_empty_registry():
    assert intake.next_mrn([]) == "MRN-10001"
