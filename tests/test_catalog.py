"""Tests for the shared test catalog in domain.catalog.

The catalog is the single source of truth for orderable tests: display name,
unit, reference range (drives the high/low/normal flag), critical thresholds
(drives the "call the doctor" alerts), and a plausibility window (drives
intake validation). It replaces the two dicts that previously lived in the
patients and pipeline blueprints, so these tests pin the behaviors those
blueprints rely on.
"""

from decimal import Decimal

import pytest

from domain import catalog


# ── shape ────────────────────────────────────────────────────────────────────

def test_catalog_covers_all_seeded_loincs():
    seeded = {"4548-4", "2345-7", "8480-6", "33914-3", "2160-0",
              "8806-2", "2708-6", "8310-5", "10839-9", "29463-7"}
    assert seeded <= set(catalog.TESTS)


def test_every_entry_has_required_keys():
    required = {"display_name", "unit", "ref_low", "ref_high",
                "critical_dir", "critical_at", "plaus_low", "plaus_high"}
    for loinc, entry in catalog.TESTS.items():
        assert required <= set(entry), f"{loinc} missing keys"


# ── flag(): same semantics the patients blueprint had ────────────────────────

@pytest.mark.parametrize("loinc,value,expected", [
    ("4548-4", 5.2, "normal"),    # HbA1c below 5.7 cap
    ("4548-4", 8.9, "high"),
    ("2345-7", 65, "low"),        # glucose below 70 floor
    ("2345-7", 85, "normal"),
    ("2345-7", 182, "high"),
    ("33914-3", 68, "low"),       # eGFR only has a floor
    ("33914-3", 95, "normal"),
    ("2708-6", 88, "low"),        # SpO2 only has a floor
])
def test_flag_ranges(loinc, value, expected):
    assert catalog.flag(loinc, value) == expected


def test_flag_unknown_test_or_null_value_is_normal():
    assert catalog.flag("0000-0", 50) == "normal"
    assert catalog.flag("4548-4", None) == "normal"


def test_flag_accepts_decimal():
    # psycopg2 returns NUMERIC as Decimal; flag must compare it cleanly.
    assert catalog.flag("4548-4", Decimal("8.9")) == "high"


# ── is_critical(): same thresholds the pipeline blueprint had ────────────────

@pytest.mark.parametrize("loinc,value,expected", [
    ("4548-4", 8.5, True),     # HbA1c > 8.0
    ("4548-4", 7.5, False),
    ("10839-9", 2.8, True),    # Troponin > 0.04
    ("2708-6", 88, True),      # SpO2 < 92
    ("2708-6", 97, False),
    ("2160-0", 2.4, True),     # Creatinine > 2.0
    ("8806-2", 42, True),      # Echo EF < 45
    ("8480-6", 148, True),     # Systolic BP > 140
    ("29463-7", 95, False),    # Body Weight has no critical rule
])
def test_is_critical(loinc, value, expected):
    assert catalog.is_critical(loinc, value) is expected


def test_is_critical_unknown_or_null_is_false():
    assert catalog.is_critical("0000-0", 999) is False
    assert catalog.is_critical("4548-4", None) is False
