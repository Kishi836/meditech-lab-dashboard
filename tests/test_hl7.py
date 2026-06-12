"""Tests for the pure HL7 v2.5 message builder in domain.hl7.

These exercise only pure functions — no Flask, no DB, no network/file I/O.
This file is the TDD spec for Task 6 (HL7 v2.5 message builder, ported from
`../hl7_sender.py`'s `buildHL7`).
"""

from datetime import date, datetime

import pytest

from domain import hl7


# Fixed datetime so MSH timestamps / control ids are deterministic.
FIXED_NOW = datetime(2024, 6, 3, 14, 30, 5)
FIXED_TS = "20240603143005"


@pytest.fixture
def patient():
    """Sample patient with >=2 observations and >=2 medications."""
    return {
        "patient_id": "PT-001",
        "name": "Rajan Menon",
        "dob": "19700412",
        "gender": "M",
        "city": "Bangalore",
        "department": "Endocrinology",
        "room": "Room 12 Bed 2",
        "attending_dr": "Sharma^Priya",
        "enc_id": "ENC-005",
        "conditions": [
            {"icd10_code": "E11.65", "description": "T2DM with hyperglycaemia"},
        ],
        "observations": [
            {"loinc_code": "4548-4", "display_name": "HbA1c", "value": 8.9,
             "unit": "%", "flag": "H", "ref": "<7.0"},
            {"loinc_code": "2345-7", "display_name": "Glucose", "value": 182,
             "unit": "mg/dL", "flag": "H", "ref": "70-99"},
        ],
        "medications": [
            {"drug_name": "Metformin", "dose": "1000mg", "frequency": "BD"},
            {"drug_name": "Lisinopril", "dose": "10mg", "frequency": "OD"},
        ],
    }


def seg_names(msg):
    return [s.split("|")[0] for s in msg.split("\r")]


# ── ORU_R01 ──────────────────────────────────────────────────────────────────

def test_oru_starts_with_msh(patient):
    msg = hl7.build_hl7(patient, "ORU_R01")
    assert msg.split("\r")[0].startswith("MSH")


def test_oru_pid_contains_patient_id(patient):
    msg = hl7.build_hl7(patient, "ORU_R01")
    pid = [s for s in msg.split("\r") if s.startswith("PID")][0]
    assert "PT-001" in pid


def test_oru_one_obx_per_observation(patient):
    msg = hl7.build_hl7(patient, "ORU_R01")
    obx = [s for s in msg.split("\r") if s.startswith("OBX")]
    assert len(obx) == len(patient["observations"])


def test_oru_obx_values_present(patient):
    msg = hl7.build_hl7(patient, "ORU_R01")
    for obs in patient["observations"]:
        assert str(obs["value"]) in msg


def test_oru_segments_separated_by_cr_in_order(patient):
    msg = hl7.build_hl7(patient, "ORU_R01")
    assert "\r" in msg
    assert seg_names(msg) == ["MSH", "PID", "OBR", "OBX", "OBX"]


# ── ADT_A01 ──────────────────────────────────────────────────────────────────

def test_adt_a01_segment_order(patient):
    msg = hl7.build_hl7(patient, "ADT_A01")
    assert seg_names(msg) == ["MSH", "EVN", "PID", "PV1", "DG1"]


def test_adt_a01_pid_has_patient_id_and_name(patient):
    msg = hl7.build_hl7(patient, "ADT_A01")
    pid = [s for s in msg.split("\r") if s.startswith("PID")][0]
    assert "PT-001" in pid
    # HL7 name is Family^Given: "Rajan Menon" -> "Menon^Rajan"
    assert "Menon^Rajan" in pid


def test_adt_a01_msh_type(patient):
    msg = hl7.build_hl7(patient, "ADT_A01")
    assert "ADT^A01^ADT_A01" in msg.split("\r")[0]


def test_adt_a03_uses_outpatient_class(patient):
    msg = hl7.build_hl7(patient, "ADT_A03")
    assert seg_names(msg) == ["MSH", "EVN", "PID", "PV1"]
    pv1 = [s for s in msg.split("\r") if s.startswith("PV1")][0]
    assert pv1.split("|")[2] == "O"


# ── ADT_A04 (registration) ───────────────────────────────────────────────────

def test_adt_a04_segment_order(patient):
    msg = hl7.build_hl7(patient, "ADT_A04")
    assert seg_names(msg) == ["MSH", "EVN", "PID", "PV1"]


def test_adt_a04_msh_type(patient):
    msg = hl7.build_hl7(patient, "ADT_A04")
    assert "ADT^A04^ADT_A04" in msg.split("\r")[0]


def test_adt_a04_pid_carries_full_demographics(patient):
    patient["phone"] = "9845012345"
    msg = hl7.build_hl7(patient, "ADT_A04")
    pid = [s for s in msg.split("\r") if s.startswith("PID")][0]
    assert "PT-001" in pid
    assert "Menon^Rajan" in pid
    assert "19700412" in pid
    assert "Bangalore" in pid
    assert "9845012345" in pid


def test_adt_a04_uses_outpatient_class(patient):
    msg = hl7.build_hl7(patient, "ADT_A04")
    pv1 = [s for s in msg.split("\r") if s.startswith("PV1")][0]
    assert pv1.split("|")[2] == "O"


def test_adt_a04_tolerant_of_minimal_patient():
    minimal = {"patient_id": "PT-009", "name": "Asha Kumar",
               "dob": "19951230", "gender": "F"}
    msg = hl7.build_hl7(minimal, "ADT_A04")
    assert seg_names(msg) == ["MSH", "EVN", "PID", "PV1"]
    assert "PT-009" in msg


# ── ORM_O01 ──────────────────────────────────────────────────────────────────

def test_orm_one_rxo_per_medication(patient):
    msg = hl7.build_hl7(patient, "ORM_O01")
    rxo = [s for s in msg.split("\r") if s.startswith("RXO")]
    assert len(rxo) == len(patient["medications"])


def test_orm_segment_order(patient):
    msg = hl7.build_hl7(patient, "ORM_O01")
    assert seg_names(msg) == ["MSH", "PID", "ORC", "RXO", "RXO"]


# ── parse_destination ────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg_type,table", [
    ("ORU_R01", "observations"),
    ("ADT_A01", "encounters"),
    ("ADT_A03", "encounters"),
    ("ADT_A04", "patients"),
    ("ORM_O01", "medications"),
])
def test_parse_destination(msg_type, table):
    assert hl7.parse_destination(msg_type) == table


# ── Unknown msg_type ─────────────────────────────────────────────────────────

def test_build_hl7_unknown_type_raises(patient):
    with pytest.raises(ValueError):
        hl7.build_hl7(patient, "FOO_BAR")


def test_parse_destination_unknown_raises():
    with pytest.raises(ValueError):
        hl7.parse_destination("FOO_BAR")


# ── Determinism ──────────────────────────────────────────────────────────────

def test_deterministic_timestamp_in_msh(patient):
    msg = hl7.build_hl7(patient, "ORU_R01", now=FIXED_NOW)
    msh = msg.split("\r")[0]
    assert FIXED_TS in msh


def test_deterministic_msg_id(patient):
    msg = hl7.build_hl7(patient, "ORU_R01", now=FIXED_NOW, msg_id="MSG999")
    assert "MSG999" in msg.split("\r")[0]


# ── DOB normalization ────────────────────────────────────────────────────────

def test_dob_accepts_date_object(patient):
    patient["dob"] = date(1970, 4, 12)
    msg = hl7.build_hl7(patient, "ORU_R01")
    assert "19700412" in msg


# ── full_name alias ──────────────────────────────────────────────────────────

def test_full_name_alias(patient):
    del patient["name"]
    patient["full_name"] = "Rajan Menon"
    msg = hl7.build_hl7(patient, "ADT_A01")
    assert "Menon^Rajan" in msg


# ── Tolerance: missing optional fields ───────────────────────────────────────

def test_tolerant_of_missing_optional_fields():
    minimal = {
        "patient_id": "PT-002",
        "name": "Jane Doe",
        "dob": "19800101",
        "gender": "F",
        # no city, department, room, attending_dr, enc_id, conditions
    }
    # Should not raise.
    msg = hl7.build_hl7(minimal, "ADT_A01")
    assert seg_names(msg) == ["MSH", "EVN", "PID", "PV1", "DG1"]
    assert "PT-002" in msg


def test_tolerant_oru_no_observations():
    minimal = {"patient_id": "PT-003", "name": "Sam Roe", "dob": "19900505", "gender": "M"}
    msg = hl7.build_hl7(minimal, "ORU_R01")
    assert seg_names(msg) == ["MSH", "PID", "OBR"]
