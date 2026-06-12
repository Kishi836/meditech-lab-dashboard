"""Pure intake validation — the Register-Patient / Record-Result contracts.

`validate_patient` and `validate_result` take the raw JSON payload from the
browser and return ``(clean, errors)``:

* ``clean`` — the normalized dict the blueprint can persist as-is (names
  stripped, gender uppercased, dates parsed to ``datetime.date``, result
  values parsed to ``float`` and enriched with the catalog's display
  name/unit). Only meaningful when ``errors`` is empty.
* ``errors`` — field name → human-readable message; empty dict when valid.

`next_patient_id` / `next_mrn` mint the next sequential id from a passed-in
list of existing ids, so the blueprint owns the SQL and this module stays
PURE: no Flask, no database access, no IO.
"""

import re
from datetime import date

from domain import catalog

BLOOD_TYPES = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}

# 7-15 digits, optionally with a leading + and -/space separators.
_PHONE_RE = re.compile(r"^\+?[\d\- ]{7,17}$")


def _parse_iso_date(raw):
    """Parse a strict YYYY-MM-DD string to a date, or None when invalid."""
    try:
        return date.fromisoformat(str(raw).strip())
    except (ValueError, TypeError):
        return None


# ── patient registration ─────────────────────────────────────────────────────

def validate_patient(payload):
    """Validate + normalize a Register-Patient payload."""
    payload = payload or {}
    errors = {}

    full_name = str(payload.get("full_name") or "").strip()
    if len(full_name) < 2:
        errors["full_name"] = "Full name is required (at least 2 characters)."

    dob = _parse_iso_date(payload.get("dob"))
    if dob is None:
        errors["dob"] = "Date of birth must be a valid YYYY-MM-DD date."
    elif dob >= date.today():
        errors["dob"] = "Date of birth must be in the past."

    gender = str(payload.get("gender") or "").strip().upper()
    if gender not in ("M", "F"):
        errors["gender"] = "Gender must be M or F."

    blood_type = str(payload.get("blood_type") or "").strip().upper()
    if blood_type and blood_type not in BLOOD_TYPES:
        errors["blood_type"] = "Blood type must be one of A/B/AB/O with +/-."

    phone = str(payload.get("phone") or "").strip()
    if phone and not _PHONE_RE.match(phone):
        errors["phone"] = "Phone must be 7-15 digits."

    city = str(payload.get("city") or "").strip()

    clean = {
        "full_name": full_name,
        "dob": dob,
        "gender": gender,
        "blood_type": blood_type,
        "phone": phone,
        "city": city,
    }
    return clean, errors


# ── result entry ─────────────────────────────────────────────────────────────

def validate_result(payload):
    """Validate + normalize a Record-Result payload against the catalog."""
    payload = payload or {}
    errors = {}

    loinc = str(payload.get("loinc_code") or "").strip()
    entry = catalog.TESTS.get(loinc)
    if entry is None:
        errors["loinc_code"] = "Pick a test from the catalog."

    value = None
    raw_value = payload.get("value")
    if raw_value is None or str(raw_value).strip() == "":
        errors["value"] = "A numeric value is required."
    else:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            errors["value"] = "Value must be a number."
    if value is not None and entry is not None:
        if not (entry["plaus_low"] <= value <= entry["plaus_high"]):
            errors["value"] = (
                f"{entry['display_name']} must be between "
                f"{entry['plaus_low']} and {entry['plaus_high']} {entry['unit']}."
            )

    raw_date = payload.get("obs_date")
    if raw_date is None or str(raw_date).strip() == "":
        obs_date = date.today()
    else:
        obs_date = _parse_iso_date(raw_date)
        if obs_date is None:
            errors["obs_date"] = "Date must be a valid YYYY-MM-DD date."
        elif obs_date > date.today():
            errors["obs_date"] = "Date must not be in the future."

    clean = {
        "loinc_code": loinc,
        "display_name": entry["display_name"] if entry else "",
        "unit": entry["unit"] if entry else "",
        "value": value,
        "obs_date": obs_date,
    }
    return clean, errors


# ── id minting ───────────────────────────────────────────────────────────────

def _next_in_sequence(existing, prefix, width, start):
    """Largest numeric suffix among `prefix`-ids, +1, zero-padded to `width`."""
    highest = start - 1
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for raw in existing:
        m = pattern.match(str(raw))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"{prefix}{highest + 1:0{width}d}"


def next_patient_id(existing):
    """Next sequential patient id: PT-001, PT-002, … (gaps don't reuse)."""
    return _next_in_sequence(existing, "PT-", 3, 1)


def next_mrn(existing):
    """Next sequential MRN: MRN-10001, MRN-10002, …"""
    return _next_in_sequence(existing, "MRN-", 5, 10001)
