"""Patients blueprint — patient browser JSON API backed by Postgres.

Thin HTTP layer that owns the SQL + JSON shaping for the patient browser.
The browser never talks to Postgres directly; it hits these endpoints, which
read via the parameterized `db.query()` helper and hand back JSON-friendly
dicts. The blueprint is mounted at `/api`, so the final paths are exactly
`/api/patients`, `/api/patients/<id>`, and `/api/patients/<id>/trends`.

Security note: EVERY value that comes from the request (the `q` search term,
the patient id) is passed as a bound `%s` parameter — never string-formatted
into the SQL text. The only place a value is shaped in Python is the ILIKE
wildcard (`f"%{q}%"`), which is still passed as a *parameter*, not SQL.

Serialization note: psycopg2 returns NUMERIC as Decimal and DATE as
datetime.date. jsonify renders date fine, but cannot serialize Decimal, so
observation `value`s are cast to float() and trend dates to isoformat().
"""

from flask import Blueprint, jsonify, request

import db

bp = Blueprint("patients", __name__, url_prefix="/api")


# Per-test reference ranges, keyed by LOINC code, used to flag each
# observation high/low/normal. Adult, sensible-but-not-clinically-
# authoritative values. `low`/`high` are inclusive bounds; None means
# that side is unbounded.
#   (low, high) -> value < low => "low", value > high => "high", else "normal"
REFERENCE_RANGES = {
    "4548-4":  (None, 5.7),   # HbA1c %
    "2345-7":  (70, 99),      # Blood Glucose mg/dL (fasting)
    "8480-6":  (90, 120),     # Systolic BP mmHg
    "33914-3": (90, None),    # eGFR mL/min  (>=90 normal, <90 low)
    "2160-0":  (0.6, 1.3),    # Creatinine mg/dL
    "8806-2":  (55, 70),      # Echo Ejection Fraction %
    "2708-6":  (95, None),    # SpO2 %  (>=95 normal, <95 low)
    "8310-5":  (36.1, 37.2),  # Body Temp C
    "10839-9": (None, 0.04),  # Troponin I ng/mL
}


def _flag(loinc_code, value):
    """Classify a numeric value against its reference range.

    Returns "high", "low", or "normal". Tests with no known range (or a
    null value) are reported as "normal" so the UI always has a flag.
    """
    rng = REFERENCE_RANGES.get(loinc_code)
    if rng is None or value is None:
        return "normal"
    low, high = rng
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "normal"


def _not_found(patient_id):
    return jsonify({"error": f"unknown patient id {patient_id}"}), 404


def _patient_exists(patient_id):
    rows = db.query(
        "SELECT 1 FROM patients WHERE patient_id = %s", (patient_id,)
    )
    return len(rows) > 0


# ───────────── 1. patient list / search ─────────────

@bp.route("/patients")
def list_patients():
    """List patients, optionally filtered by `q`.

    With no `q`, returns every patient. With `q`, matches on full_name,
    mrn, or any of the patient's conditions (description / icd10_code).
    `summary` is a one-line hint: the count of active+chronic conditions
    and the most-recent condition description when available.
    """
    q = request.args.get("q", "").strip()

    base_select = """
        SELECT
            p.patient_id,
            p.full_name,
            p.mrn,
            p.gender,
            date_part('year', age(p.dob))::int AS age,
            (SELECT count(*) FROM conditions c
              WHERE c.patient_id = p.patient_id
                AND c.status IN ('active', 'chronic')) AS active_count,
            (SELECT c.description FROM conditions c
              WHERE c.patient_id = p.patient_id
              ORDER BY c.onset_date DESC NULLS LAST
              LIMIT 1) AS top_condition
        FROM patients p
    """

    if q:
        like = f"%{q}%"
        sql = base_select + """
            WHERE p.full_name ILIKE %s
               OR p.mrn ILIKE %s
               OR EXISTS (
                    SELECT 1 FROM conditions c
                     WHERE c.patient_id = p.patient_id
                       AND (c.description ILIKE %s OR c.icd10_code ILIKE %s)
               )
            ORDER BY p.patient_id
        """
        rows = db.query(sql, (like, like, like, like))
    else:
        rows = db.query(base_select + " ORDER BY p.patient_id")

    patients = []
    for r in rows:
        patients.append({
            "patient_id": r["patient_id"],
            "full_name": r["full_name"],
            "mrn": r["mrn"],
            "gender": r["gender"],
            "age": r["age"],
            "summary": _summary(r["active_count"], r["top_condition"]),
        })
    return jsonify(patients)


def _summary(active_count, top_condition):
    """Build the one-line list-row summary string."""
    count = active_count or 0
    label = f"{count} active/chronic condition" + ("" if count == 1 else "s")
    if top_condition:
        return f"{label} · {top_condition}"
    return label


# ───────────── 2. patient detail ─────────────

@bp.route("/patients/<patient_id>")
def patient_detail(patient_id):
    """Full record for one patient, or 404 if the id is unknown."""
    demo_rows = db.query(
        """
        SELECT
            patient_id, mrn, full_name, dob, gender, blood_type, phone, city,
            date_part('year', age(dob))::int AS age
        FROM patients
        WHERE patient_id = %s
        """,
        (patient_id,),
    )
    if not demo_rows:
        return _not_found(patient_id)

    encounters = db.query(
        """
        SELECT enc_id, enc_date, enc_type, department, attending_dr, discharge_dt
        FROM encounters
        WHERE patient_id = %s
        ORDER BY enc_date DESC
        """,
        (patient_id,),
    )

    conditions = db.query(
        """
        SELECT cond_id, icd10_code, description, onset_date, status
        FROM conditions
        WHERE patient_id = %s
        ORDER BY onset_date DESC NULLS LAST
        """,
        (patient_id,),
    )

    medications = db.query(
        """
        SELECT med_id, rxnorm_code, drug_name, dose, frequency, start_date, end_date
        FROM medications
        WHERE patient_id = %s
        ORDER BY start_date DESC NULLS LAST
        """,
        (patient_id,),
    )

    obs_rows = db.query(
        """
        SELECT o.obs_id, o.loinc_code, o.display_name, o.value, o.unit, o.obs_date
        FROM observations o
        JOIN encounters e ON e.enc_id = o.enc_id
        WHERE e.patient_id = %s
        ORDER BY o.obs_date
        """,
        (patient_id,),
    )
    observations = [
        {
            "obs_id": o["obs_id"],
            "loinc_code": o["loinc_code"],
            "display_name": o["display_name"],
            "value": float(o["value"]) if o["value"] is not None else None,
            "unit": o["unit"],
            "obs_date": o["obs_date"].isoformat() if o["obs_date"] else None,
            "flag": _flag(o["loinc_code"], o["value"]),
        }
        for o in obs_rows
    ]

    return jsonify({
        "demographics": demo_rows[0],
        "encounters": encounters,
        "conditions": conditions,
        "medications": medications,
        "observations": observations,
    })


# ───────────── 3. observation trends ─────────────

@bp.route("/patients/<patient_id>/trends")
def patient_trends(patient_id):
    """Observations grouped per test, each series ordered by date.

    Shape: { "<display_name>": [ {date, value, unit, flag}, ... ], ... }.
    404 if the patient id is unknown (consistent with the detail endpoint).
    """
    if not _patient_exists(patient_id):
        return _not_found(patient_id)

    rows = db.query(
        """
        SELECT o.loinc_code, o.display_name, o.value, o.unit, o.obs_date
        FROM observations o
        JOIN encounters e ON e.enc_id = o.enc_id
        WHERE e.patient_id = %s
        ORDER BY o.display_name, o.obs_date
        """,
        (patient_id,),
    )

    trends = {}
    for r in rows:
        value = float(r["value"]) if r["value"] is not None else None
        point = {
            "date": r["obs_date"].isoformat() if r["obs_date"] else None,
            "value": value,
            "unit": r["unit"],
            "flag": _flag(r["loinc_code"], r["value"]),
        }
        trends.setdefault(r["display_name"], []).append(point)

    return jsonify(trends)
