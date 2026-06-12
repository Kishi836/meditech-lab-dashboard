"""Intake blueprint — front-desk workflows that enter REAL data via HL7.

Where the pipeline blueprint demos the integration stack with tagged,
resettable rows, intake is how new data actually gets into the hospital:

* Register Patient  → an ADT^A04 document → `INSERT INTO patients`.
* Record Result     → an ORU^R01 document → a `ENC-LAB-` encounter + the
  observation row.

Both run the same six visible stages as /api/hl7/send (build → nifi_route →
postgres → elasticsearch → kibana → minio) via the shared staged runner, so
the UI can animate the document travelling the wire. Intake rows are real
data: they use the ENC-LAB- prefix / normal patient ids and deliberately
SURVIVE `GET /api/pipeline/reset` (which only deletes ENC-HL7-% demo rows).

Security: every request-derived value is validated in domain/intake.py and
passed as a bound %s parameter — never string-formatted into SQL. Seed
patients PT-001…PT-008 cannot be deleted.
"""

import os
from datetime import datetime

from flask import Blueprint, jsonify, request

import db
import es
from blueprints.common import FEED, Skip, archive_raw, load_patient, run_stage
from domain import catalog
from domain import intake as iv
from domain.hl7 import build_hl7, parse_destination

bp = Blueprint("intake", __name__, url_prefix="/api")

# Rows created by Record Result carry this enc_id prefix: identifiable, but
# distinct from the demo pipeline's ENC-HL7- tag so reset leaves them alone.
LAB_TAG = "ENC-LAB-"

SEED_PATIENTS = tuple(f"PT-{n:03d}" for n in range(1, 9))

_FLAG_HL7 = {"high": "H", "low": "L", "normal": ""}


def _msg_id(now):
    return now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"


def _ref_str(entry):
    """Human reference-range string for OBX-7, e.g. "70-99", "<5.7", ">=90"."""
    low, high = entry["ref_low"], entry["ref_high"]
    if low is not None and high is not None:
        return f"{low}-{high}"
    if high is not None:
        return f"<{high}"
    if low is not None:
        return f">={low}"
    return ""


# ───────────────────────── catalog ─────────────────────────

@bp.route("/catalog/tests")
def catalog_tests():
    """The orderable-test catalog, for the Record Result form's dropdown."""
    return jsonify([
        {"loinc_code": loinc, **entry}
        for loinc, entry in catalog.TESTS.items()
    ])


# ───────────────────────── live preview ─────────────────────────

@bp.route("/intake/preview", methods=["POST"])
def intake_preview():
    """Build (never persist) the HL7 document a form would emit.

    Deliberately lenient — the form may be half-typed; whatever fields are
    present flow into the message so the preview updates keystroke by
    keystroke. `kind` is "patient" (ADT^A04) or "result" (ORU^R01).
    """
    body = request.get_json(silent=True) or {}
    kind = body.get("kind")

    if kind == "patient":
        patient = {
            "patient_id": body.get("patient_id") or "PT-NEW",
            "name": body.get("full_name") or "",
            "dob": body.get("dob") or "",
            "gender": (body.get("gender") or "").upper(),
            "city": body.get("city") or "",
            "phone": body.get("phone") or "",
        }
        return jsonify({"hl7": build_hl7(patient, "ADT_A04")})

    if kind == "result":
        patient = load_patient((body.get("patient_id") or "").strip()) or {
            "patient_id": body.get("patient_id") or "PT-?", "name": "",
        }
        entry = catalog.TESTS.get(body.get("loinc_code") or "")
        value = body.get("value")
        patient["observations"] = [{
            "loinc_code": body.get("loinc_code") or "",
            "display_name": entry["display_name"] if entry else "",
            "value": value if value not in (None, "") else "",
            "unit": entry["unit"] if entry else "",
            "ref": _ref_str(entry) if entry else "",
            "flag": _FLAG_HL7.get(
                catalog.flag(body.get("loinc_code"), _safe_float(value)), ""
            ),
        }]
        return jsonify({"hl7": build_hl7(patient, "ORU_R01")})

    return jsonify({"error": "kind must be 'patient' or 'result'"}), 400


def _safe_float(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ───────────────────────── register patient ─────────────────────────

@bp.route("/intake/patient", methods=["POST"])
def register_patient():
    """Validate → mint ids → run the ADT^A04 through the staged pipeline."""
    clean, errors = iv.validate_patient(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"errors": errors}), 400

    ids = db.query("SELECT patient_id, mrn FROM patients")
    patient_id = iv.next_patient_id([r["patient_id"] for r in ids])
    mrn = iv.next_mrn([r["mrn"] for r in ids])

    patient = {**clean, "patient_id": patient_id, "name": clean["full_name"]}
    now = datetime.now()
    msg_id = _msg_id(now)
    state = {"raw": ""}
    stages = []

    def s_build():
        state["raw"] = build_hl7(patient, "ADT_A04", now=now, msg_id=msg_id)
        return f"ADT^A04: {len(state['raw'].split(chr(13)))} segments built"

    def s_nifi():
        state["table"] = parse_destination("ADT_A04")
        return f"routed to Postgres table '{state['table']}'"

    def s_postgres():
        db.execute(
            """
            INSERT INTO patients
                (patient_id, mrn, full_name, dob, gender, blood_type, phone, city)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (patient_id, mrn, clean["full_name"], clean["dob"], clean["gender"],
             clean["blood_type"] or None, clean["phone"] or None,
             clean["city"] or None),
        )
        return f"INSERT patients → {patient_id} ({mrn})"

    def s_es():
        res = es.index({
            "msg_id": msg_id, "patient_id": patient_id,
            "msg_type": "ADT_A04", "hl7": state["raw"],
        })
        if res == es.SKIPPED:
            raise Skip("ES_ENABLED is off — indexing skipped")
        if res is False:
            raise RuntimeError("ES index request failed")
        return "indexed registration document"

    def s_kibana():
        return "registry aggregates refreshed from Postgres"

    def s_minio():
        # REG- prefix: real data — the demo pipeline's reset must skip it.
        path = archive_raw(f"REG-{msg_id}", state["raw"])
        return f"archived raw HL7 → {os.path.basename(path)}"

    run_stage(stages, "build", s_build)
    run_stage(stages, "nifi_route", s_nifi)
    run_stage(stages, "postgres", s_postgres)
    run_stage(stages, "elasticsearch", s_es)
    run_stage(stages, "kibana", s_kibana)
    run_stage(stages, "minio", s_minio)

    ok = all(s["status"] != "error" for s in stages)
    FEED.appendleft({
        "msg_id": msg_id,
        "patient_id": patient_id,
        "patient": clean["full_name"],
        "msg_type": "ADT_A04",
        "table": state.get("table"),
        "ts": now.isoformat(timespec="seconds"),
        "status": "ok" if ok else "error",
    })

    return jsonify({
        "hl7": state["raw"], "msg_id": msg_id, "stages": stages,
        "patient_id": patient_id, "mrn": mrn,
    })


# ───────────────────────── record result ─────────────────────────

@bp.route("/intake/result", methods=["POST"])
def record_result():
    """Validate → run the ORU^R01 (with the entered value) through the pipeline.

    The postgres stage writes a parent ENC-LAB- encounter plus the
    observation row — real data, untouched by the demo pipeline's reset.
    """
    body = request.get_json(silent=True) or {}
    clean, errors = iv.validate_result(body)
    if errors:
        return jsonify({"errors": errors}), 400

    patient = load_patient((body.get("patient_id") or "").strip())
    if patient is None:
        return jsonify({"error": f"unknown patient id {body.get('patient_id')!r}"}), 404

    entry = catalog.TESTS[clean["loinc_code"]]
    flag_word = catalog.flag(clean["loinc_code"], clean["value"])
    patient["observations"] = [{
        "loinc_code": clean["loinc_code"],
        "display_name": clean["display_name"],
        "value": clean["value"],
        "unit": clean["unit"],
        "ref": _ref_str(entry),
        "flag": _FLAG_HL7[flag_word],
    }]

    now = datetime.now()
    msg_id = _msg_id(now)
    enc_id = LAB_TAG + msg_id
    state = {"raw": ""}
    stages = []

    def s_build():
        state["raw"] = build_hl7(patient, "ORU_R01", now=now, msg_id=msg_id)
        return f"ORU^R01: {clean['display_name']} = {clean['value']} {clean['unit']}"

    def s_nifi():
        state["table"] = parse_destination("ORU_R01")
        return f"routed to Postgres table '{state['table']}'"

    def s_postgres():
        db.execute(
            """
            INSERT INTO encounters
                (enc_id, patient_id, enc_date, enc_type, department, attending_dr)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (enc_id, patient["patient_id"], clean["obs_date"], "outpatient",
             "Laboratory", "Lab Services"),
        )
        db.execute(
            """
            INSERT INTO observations
                (enc_id, loinc_code, display_name, value, unit, obs_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (enc_id, clean["loinc_code"], clean["display_name"],
             clean["value"], clean["unit"], clean["obs_date"]),
        )
        return f"INSERT observations → {clean['display_name']} (enc {enc_id})"

    def s_es():
        res = es.index({
            "msg_id": msg_id, "patient_id": patient["patient_id"],
            "msg_type": "ORU_R01", "hl7": state["raw"],
        })
        if res == es.SKIPPED:
            raise Skip("ES_ENABLED is off — indexing skipped")
        if res is False:
            raise RuntimeError("ES index request failed")
        return "indexed result document"

    def s_kibana():
        return "trend + critical-value charts refresh from Postgres"

    def s_minio():
        # LAB- prefix: real data — the demo pipeline's reset must skip it.
        path = archive_raw(f"LAB-{msg_id}", state["raw"])
        return f"archived raw HL7 → {os.path.basename(path)}"

    run_stage(stages, "build", s_build)
    run_stage(stages, "nifi_route", s_nifi)
    run_stage(stages, "postgres", s_postgres)
    run_stage(stages, "elasticsearch", s_es)
    run_stage(stages, "kibana", s_kibana)
    run_stage(stages, "minio", s_minio)

    ok = all(s["status"] != "error" for s in stages)
    FEED.appendleft({
        "msg_id": msg_id,
        "patient_id": patient["patient_id"],
        "patient": patient.get("full_name", ""),
        "msg_type": "ORU_R01",
        "table": state.get("table"),
        "ts": now.isoformat(timespec="seconds"),
        "status": "ok" if ok else "error",
    })

    return jsonify({
        "hl7": state["raw"], "msg_id": msg_id, "stages": stages,
        "obs": {
            "loinc_code": clean["loinc_code"],
            "display_name": clean["display_name"],
            "value": clean["value"],
            "unit": clean["unit"],
            "obs_date": clean["obs_date"].isoformat(),
            "flag": flag_word,
        },
        "critical": catalog.is_critical(clean["loinc_code"], clean["value"]),
    })


# ───────────────────────── delete patient ─────────────────────────

@bp.route("/patients/<patient_id>", methods=["DELETE"])
def delete_patient(patient_id):
    """Remove a non-seed patient and every dependent row.

    Seed patients (PT-001…PT-008) are protected — the lab's worked examples
    depend on them. Children go first to satisfy the FKs.
    """
    if patient_id in SEED_PATIENTS:
        return jsonify({"error": "seed patients cannot be deleted"}), 403

    exists = db.query(
        "SELECT 1 FROM patients WHERE patient_id = %s", (patient_id,)
    )
    if not exists:
        return jsonify({"error": f"unknown patient id {patient_id}"}), 404

    db.execute(
        """
        DELETE FROM observations USING encounters
        WHERE observations.enc_id = encounters.enc_id
          AND encounters.patient_id = %s
        """,
        (patient_id,),
    )
    db.execute("DELETE FROM medications WHERE patient_id = %s", (patient_id,))
    db.execute("DELETE FROM conditions WHERE patient_id = %s", (patient_id,))
    db.execute("DELETE FROM encounters WHERE patient_id = %s", (patient_id,))
    db.execute("DELETE FROM patients WHERE patient_id = %s", (patient_id,))

    return jsonify({"status": "deleted", "patient_id": patient_id})
