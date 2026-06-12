"""Pipeline blueprint — the hybrid HL7 pipeline + analytics JSON API.

This is the "improvise" centrepiece: a single `POST /api/hl7/send` builds a
real HL7 v2.5 message (Task 6's pure `domain/hl7.py`) and then walks it through
a six-stage pipeline that mirrors the lab's NiFi → Postgres → Elasticsearch →
Kibana → MinIO architecture. Some stages are **real**, some are **simulated**:

    1. build          (real)       — construct the HL7 message
    2. nifi_route      (simulated)  — `parse_destination` picks the target table
    3. postgres        (real)       — INSERT a source-tagged row we can clean up
    4. elasticsearch   (real / off) — index the doc, or "skipped" when disabled
    5. kibana          (simulated)  — charts are served from Postgres aggregates
    6. minio           (real-ish)   — archive the raw HL7 to ARCHIVE_DIR

Every row the pipeline writes is tagged so it never pollutes the seed data:
the tag is the `ENC-HL7-` prefix on `enc_id`. ADT messages create that tagged
encounter directly; ORU/ORM messages create it as the FK parent for their
observation/medication child row. `GET /api/pipeline/reset` deletes everything
matching the tag (children first, then encounters) plus the archive files.

Security: every request-derived value (patient_id, msg_type) is validated and
passed as a bound `%s` parameter — never string-formatted into SQL. The one
LIKE pattern in reset is a constant, also passed as a parameter.
"""

import os
from datetime import datetime

from flask import Blueprint, jsonify, request

import db
import es
from config import Config
from blueprints.common import (
    FEED, TAG, Skip, archive_raw, load_patient, run_stage,
)
from domain.catalog import TESTS, is_critical
from domain.hl7 import build_hl7, parse_destination

bp = Blueprint("pipeline", __name__, url_prefix="/api")

VALID_TYPES = ("ADT_A01", "ADT_A03", "ORU_R01", "ORM_O01")


# ───────────────────────── persistence ─────────────────────────

def _persist(patient, msg_type, msg_id, now):
    """INSERT the routed, source-tagged row(s). Returns a human detail string.

    Always writes a tagged encounter (the ADT deliverable, and the FK parent
    for ORU/ORM child rows), then the child row when routing to a child table.
    """
    table = parse_destination(msg_type)
    enc_id = TAG + msg_id
    today = now.date()
    pid = patient["patient_id"]
    dept = patient.get("department") or "HL7 Intake"
    dr = patient.get("attending_dr") or "Dr. HL7"
    enc_type = "inpatient" if msg_type == "ADT_A01" else "outpatient"

    db.execute(
        """
        INSERT INTO encounters (enc_id, patient_id, enc_date, enc_type, department, attending_dr)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (enc_id, pid, today, enc_type, dept, dr),
    )

    if table == "encounters":
        return f"INSERT encounters → {enc_id} ({enc_type})"

    if table == "observations":
        obs = (patient.get("observations") or [{}])[0]
        db.execute(
            """
            INSERT INTO observations (enc_id, loinc_code, display_name, value, unit, obs_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (enc_id, obs.get("loinc_code"), obs.get("display_name"),
             obs.get("value"), obs.get("unit"), today),
        )
        return f"INSERT observations → {obs.get('display_name', '?')} (enc {enc_id})"

    # medications
    med = (patient.get("medications") or [{}])[0]
    db.execute(
        """
        INSERT INTO medications (patient_id, enc_id, drug_name, dose, frequency, start_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (pid, enc_id, med.get("drug_name"), med.get("dose"),
         med.get("frequency"), today),
    )
    return f"INSERT medications → {med.get('drug_name', '?')} (enc {enc_id})"


# ───────────────────────── send endpoint ─────────────────────────

@bp.route("/hl7/send", methods=["POST"])
def hl7_send():
    """Build an HL7 message for a patient and run it through the pipeline."""
    body = request.get_json(silent=True) or {}
    patient_id = (body.get("patient_id") or "").strip()
    msg_type = (body.get("msg_type") or "").strip()

    if msg_type not in VALID_TYPES:
        return jsonify({"error": f"unknown msg_type {msg_type!r}"}), 400
    patient = load_patient(patient_id)
    if patient is None:
        return jsonify({"error": f"unknown patient id {patient_id}"}), 404

    now = datetime.now()
    msg_id = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    state = {"raw": ""}
    stages = []

    def s_build():
        state["raw"] = build_hl7(patient, msg_type, now=now, msg_id=msg_id)
        n = len(state["raw"].split("\r"))
        return f"{msg_type}: {n} segments built"

    def s_nifi():
        state["table"] = parse_destination(msg_type)
        return f"routed to Postgres table '{state['table']}'"

    def s_postgres():
        return _persist(patient, msg_type, msg_id, now)

    def s_es():
        res = es.index({
            "msg_id": msg_id, "patient_id": patient_id,
            "msg_type": msg_type, "hl7": state["raw"],
        })
        if res == es.SKIPPED:
            raise Skip("ES_ENABLED is off — indexing skipped")
        if res is False:
            raise RuntimeError("ES index request failed")
        return "indexed message document"

    def s_kibana():
        return "dashboards rendered from Postgres aggregates"

    def s_minio():
        path = archive_raw(msg_id, state["raw"])
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
        "patient": patient.get("full_name", ""),
        "msg_type": msg_type,
        "table": state.get("table"),
        "ts": now.isoformat(timespec="seconds"),
        "status": "ok" if ok else "error",
    })

    return jsonify({"hl7": state["raw"], "msg_id": msg_id, "stages": stages})


@bp.route("/hl7/preview", methods=["POST"])
def hl7_preview():
    """Build (but do not persist) an HL7 message — drives the live preview."""
    body = request.get_json(silent=True) or {}
    patient_id = (body.get("patient_id") or "").strip()
    msg_type = (body.get("msg_type") or "").strip()

    if msg_type not in VALID_TYPES:
        return jsonify({"error": f"unknown msg_type {msg_type!r}"}), 400
    patient = load_patient(patient_id)
    if patient is None:
        return jsonify({"error": f"unknown patient id {patient_id}"}), 404

    return jsonify({"hl7": build_hl7(patient, msg_type)})


# ───────────────────────── feed / reset ─────────────────────────

@bp.route("/pipeline/feed")
def pipeline_feed():
    """Recent sends, newest first."""
    return jsonify(list(FEED))


@bp.route("/pipeline/reset")
def pipeline_reset():
    """Remove every pipeline-created row + archive file; clear the feed."""
    db.execute("DELETE FROM observations WHERE enc_id LIKE %s", (TAG + "%",))
    db.execute("DELETE FROM medications WHERE enc_id LIKE %s", (TAG + "%",))
    db.execute("DELETE FROM encounters WHERE enc_id LIKE %s", (TAG + "%",))

    files = 0
    if os.path.isdir(Config.ARCHIVE_DIR):
        for fn in os.listdir(Config.ARCHIVE_DIR):
            # REG-/LAB- archives are intake's real documents — keep them.
            if fn.endswith(".hl7") and not fn.startswith(("REG-", "LAB-")):
                os.remove(os.path.join(Config.ARCHIVE_DIR, fn))
                files += 1

    FEED.clear()
    return jsonify({"status": "reset", "archive_files_removed": files})


# ───────────────────────── analytics ─────────────────────────

@bp.route("/analytics/conditions_by_dept")
def conditions_by_dept():
    """How many distinct diagnoses each department's patients carry."""
    rows = db.query(
        """
        SELECT e.department AS department, COUNT(DISTINCT c.cond_id) AS count
        FROM encounters e
        JOIN conditions c ON c.patient_id = e.patient_id
        WHERE e.department IS NOT NULL
        GROUP BY e.department
        ORDER BY count DESC, e.department
        """
    )
    return jsonify(rows)


@bp.route("/analytics/message_counts")
def message_counts():
    """Pipeline activity this session, grouped by HL7 message type."""
    counts = {}
    for entry in FEED:
        counts[entry["msg_type"]] = counts.get(entry["msg_type"], 0) + 1
    data = [{"msg_type": k, "count": v} for k, v in sorted(counts.items())]
    return jsonify(data)


@bp.route("/analytics/critical_values")
def critical_values():
    """Latest observation per patient/test that crosses a critical threshold."""
    rows = db.query(
        """
        SELECT DISTINCT ON (e.patient_id, o.loinc_code)
               e.patient_id, p.full_name, o.loinc_code,
               o.display_name, o.value, o.unit, o.obs_date
        FROM observations o
        JOIN encounters e ON o.enc_id = e.enc_id
        JOIN patients p   ON e.patient_id = p.patient_id
        ORDER BY e.patient_id, o.loinc_code, o.obs_date DESC
        """
    )

    alerts = []
    for r in rows:
        value = float(r["value"]) if r["value"] is not None else None
        if not is_critical(r["loinc_code"], value):
            continue
        entry = TESTS[r["loinc_code"]]
        alerts.append({
            "patient_id": r["patient_id"],
            "full_name": r["full_name"],
            "display_name": r["display_name"] or entry["display_name"],
            "value": value,
            "unit": r["unit"],
            "obs_date": r["obs_date"].isoformat() if r["obs_date"] else None,
            "direction": entry["critical_dir"],
            "threshold": entry["critical_at"],
        })
    alerts.sort(key=lambda a: a["full_name"])
    return jsonify(alerts)
