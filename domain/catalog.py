"""Pure test catalog — the single source of truth for orderable tests.

One entry per LOINC code, carrying everything the app needs to know about a
test:

* ``display_name`` / ``unit`` — what the UI shows.
* ``ref_low`` / ``ref_high`` — the inclusive reference range that drives the
  high/low/normal flag (None = that side unbounded). These are the adult,
  sensible-but-not-clinically-authoritative values the patients blueprint
  used to keep in its own REFERENCE_RANGES dict.
* ``critical_dir`` / ``critical_at`` — "call the doctor" thresholds for the
  critical-values alerts (previously the pipeline blueprint's CRITICAL dict).
  ``critical_dir`` is "high" (value > threshold) or "low" (value < threshold);
  None means the test has no critical rule.
* ``plaus_low`` / ``plaus_high`` — the physically plausible window used to
  validate manually entered results (a HbA1c of 250 is a typo, not a value).

This module is intentionally PURE: module-level data plus pure functions.
No Flask, no database access, no IO.
"""

TESTS = {
    "4548-4": {
        "display_name": "HbA1c", "unit": "%",
        "ref_low": None, "ref_high": 5.7,
        "critical_dir": "high", "critical_at": 8.0,
        "plaus_low": 3, "plaus_high": 20,
    },
    "2345-7": {
        "display_name": "Blood Glucose", "unit": "mg/dL",
        "ref_low": 70, "ref_high": 99,
        "critical_dir": "high", "critical_at": 400,
        "plaus_low": 20, "plaus_high": 1000,
    },
    "8480-6": {
        "display_name": "Systolic BP", "unit": "mmHg",
        "ref_low": 90, "ref_high": 120,
        "critical_dir": "high", "critical_at": 140,
        "plaus_low": 40, "plaus_high": 300,
    },
    "33914-3": {
        "display_name": "eGFR", "unit": "mL/min",
        "ref_low": 90, "ref_high": None,
        "critical_dir": "low", "critical_at": 30,
        "plaus_low": 0, "plaus_high": 200,
    },
    "2160-0": {
        "display_name": "Creatinine", "unit": "mg/dL",
        "ref_low": 0.6, "ref_high": 1.3,
        "critical_dir": "high", "critical_at": 2.0,
        "plaus_low": 0.1, "plaus_high": 20,
    },
    "8806-2": {
        "display_name": "Echo EF", "unit": "%",
        "ref_low": 55, "ref_high": 70,
        "critical_dir": "low", "critical_at": 45,
        "plaus_low": 5, "plaus_high": 90,
    },
    "2708-6": {
        "display_name": "SpO2", "unit": "%",
        "ref_low": 95, "ref_high": None,
        "critical_dir": "low", "critical_at": 92,
        "plaus_low": 40, "plaus_high": 100,
    },
    "8310-5": {
        "display_name": "Body Temp", "unit": "C",
        "ref_low": 36.1, "ref_high": 37.2,
        "critical_dir": "high", "critical_at": 40.0,
        "plaus_low": 30, "plaus_high": 45,
    },
    "10839-9": {
        "display_name": "Troponin I", "unit": "ng/mL",
        "ref_low": None, "ref_high": 0.04,
        "critical_dir": "high", "critical_at": 0.04,
        "plaus_low": 0, "plaus_high": 100,
    },
    "29463-7": {
        "display_name": "Body Weight", "unit": "kg",
        "ref_low": None, "ref_high": None,
        "critical_dir": None, "critical_at": None,
        "plaus_low": 1, "plaus_high": 400,
    },
}


def flag(loinc_code, value):
    """Classify a value against its reference range: "high"/"low"/"normal".

    Tests with no known range (or a null value) report "normal" so the UI
    always has a flag. Accepts Decimal (psycopg2 NUMERIC) as well as float.
    """
    entry = TESTS.get(loinc_code)
    if entry is None or value is None:
        return "normal"
    if entry["ref_low"] is not None and value < entry["ref_low"]:
        return "low"
    if entry["ref_high"] is not None and value > entry["ref_high"]:
        return "high"
    return "normal"


def is_critical(loinc_code, value):
    """True when `value` crosses the test's call-the-doctor threshold."""
    entry = TESTS.get(loinc_code)
    if entry is None or value is None or entry["critical_dir"] is None:
        return False
    if entry["critical_dir"] == "high":
        return value > entry["critical_at"]
    return value < entry["critical_at"]
