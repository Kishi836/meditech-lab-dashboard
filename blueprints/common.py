"""Shared plumbing for the blueprints that run HL7 messages through the
hybrid pipeline (pipeline.py's demo sender and intake.py's registration /
result-entry workflows).

Extracted from pipeline.py so intake can reuse the staged runner, the
patient loader, the archive writer, and the session feed without circular
imports. Everything here keeps pipeline.py's original semantics.
"""

import os
import time
from collections import deque

import db
from config import Config

# All rows the demo pipeline writes carry this enc_id prefix so reset can
# find them. Intake rows deliberately use a different prefix (ENC-LAB-) so
# reset leaves real entered data alone.
TAG = "ENC-HL7-"

# Recent sends, newest first — powers /api/pipeline/feed and message_counts.
# In-memory by design (a lab convenience); pipeline reset clears it.
FEED = deque(maxlen=25)


class Skip(Exception):
    """Raised inside a stage to mark it 'skipped' rather than 'error'."""


def load_patient(patient_id):
    """Assemble the build_hl7 patient dict from Postgres, or None if unknown."""
    demo = db.query(
        """
        SELECT patient_id, full_name, dob, gender, blood_type, phone, city
        FROM patients WHERE patient_id = %s
        """,
        (patient_id,),
    )
    if not demo:
        return None
    p = dict(demo[0])

    enc = db.query(
        """
        SELECT enc_id, department, attending_dr, enc_type
        FROM encounters WHERE patient_id = %s
        ORDER BY enc_date DESC LIMIT 1
        """,
        (patient_id,),
    )
    if enc:
        p.update(enc[0])

    p["conditions"] = db.query(
        """
        SELECT icd10_code, description FROM conditions
        WHERE patient_id = %s ORDER BY onset_date DESC NULLS LAST
        """,
        (patient_id,),
    )

    obs_rows = db.query(
        """
        SELECT o.loinc_code, o.display_name, o.value, o.unit
        FROM observations o JOIN encounters e ON e.enc_id = o.enc_id
        WHERE e.patient_id = %s ORDER BY o.obs_date DESC LIMIT 5
        """,
        (patient_id,),
    )
    p["observations"] = [
        {**o, "value": float(o["value"]) if o["value"] is not None else None}
        for o in obs_rows
    ]

    p["medications"] = db.query(
        """
        SELECT drug_name, dose, frequency FROM medications
        WHERE patient_id = %s ORDER BY start_date DESC NULLS LAST
        """,
        (patient_id,),
    )

    # build_hl7 reads "name"; the DB column is full_name.
    p["name"] = p.get("full_name", "")
    return p


def run_stage(stages, name, fn):
    """Time `fn`, append a {stage,status,ms,detail} record, swallow failures."""
    t0 = time.perf_counter()
    try:
        detail = fn()
        status = "ok"
    except Skip as exc:
        status, detail = "skipped", str(exc)
    except Exception as exc:  # noqa: BLE001 — a failed stage must not 500 the request
        status, detail = "error", str(exc)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    stages.append({"stage": name, "status": status, "ms": ms, "detail": detail})


def archive_raw(msg_id, raw):
    """Write the raw HL7 to ARCHIVE_DIR/<msg_id>.hl7 (the MinIO sim)."""
    os.makedirs(Config.ARCHIVE_DIR, exist_ok=True)
    path = os.path.join(Config.ARCHIVE_DIR, f"{msg_id}.hl7")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(raw)
    return path
