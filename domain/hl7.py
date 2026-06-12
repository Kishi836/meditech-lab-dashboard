"""Pure HL7 v2.5 message builder.

Ported from the `buildHL7` JavaScript function in `../hl7_sender.py`
(lines ~499-546). Reproduces the same segment structure in Python, driven
by a Postgres-derived patient record (see the contract below).

This module is intentionally PURE: module-level data plus pure functions.
No Flask, no database access, no network/file I/O. Only the standard library
(`datetime`) is used.

Determinism
-----------
HL7 messages carry a 14-char timestamp (MSH-7, EVN-2, OBR-7, ORC-9) and a
message control id (MSH-10). To keep `build_hl7` testable, both are
injectable:

* ``now``    — a ``datetime`` (default ``datetime.now()``) → ``YYYYMMDDHHMMSS``.
* ``msg_id`` — an explicit control id; when omitted it is derived
  deterministically from the timestamp as ``"MSG" + ts[-6:]``.

Patient dict contract (be tolerant — every optional field uses ``.get()``)
--------------------------------------------------------------------------
::

    {
      "patient_id": "PT-001",
      "name": "Rajan Menon",          # accepts "name" or "full_name"
      "dob": "19700412",              # "YYYYMMDD" str or datetime.date
      "gender": "M",
      "city": "Bangalore",            # optional
      "department": "Endocrinology",  # optional (PV1)
      "room": "Room 12 Bed 2",        # optional (PV1)
      "attending_dr": "Sharma^Priya", # optional (PV1 / ORC)
      "enc_id": "ENC-005",            # optional (PV1 / ORC)
      "conditions": [                 # ADT DG1 (first condition only)
          {"icd10_code": "E11.65", "description": "T2DM ..."}],
      "observations": [               # ORU OBX (one per obs)
          {"loinc_code": "4548-4", "display_name": "HbA1c", "value": 8.9,
           "unit": "%", "flag": "H", "ref": "<7.0"}],
      "medications": [                # ORM RXO (one per med)
          {"drug_name": "Metformin", "dose": "1000mg", "frequency": "BD"}],
    }
"""

from datetime import date, datetime

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

# Segment separator — HL7 uses the carriage return, NOT a newline.
SEP = "\r"

# MSH encoding characters: component(^) repetition(~) escape(\) subcomponent(&).
ENCODING_CHARS = r"^~\&"

# Sending application per message type (MSH-3); BCH facility constants mirror
# the reference JS.
_SENDING_APP = {
    "ADT_A01": "HIS",
    "ADT_A03": "HIS",
    "ADT_A04": "HIS",
    "ORU_R01": "LIS",
    "ORM_O01": "CPOE",
}

# msg_type → Postgres destination table.
_DESTINATIONS = {
    "ADT_A01": "encounters",
    "ADT_A03": "encounters",
    "ADT_A04": "patients",
    "ORU_R01": "observations",
    "ORM_O01": "medications",
}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _ts14(now: datetime) -> str:
    """Format a datetime as the 14-char HL7 timestamp ``YYYYMMDDHHMMSS``."""
    return now.strftime("%Y%m%d%H%M%S")


def _norm_dob(dob) -> str:
    """Normalize a DOB to the 8-digit HL7 form ``YYYYMMDD``.

    Accepts a ``datetime.date``/``datetime`` or a string (already
    ``YYYYMMDD`` or otherwise — digits are extracted). Missing → "".
    """
    if dob is None:
        return ""
    if isinstance(dob, (date, datetime)):
        return dob.strftime("%Y%m%d")
    # String: keep only digits so "1970-04-12" also normalizes cleanly.
    digits = "".join(ch for ch in str(dob) if ch.isdigit())
    return digits[:8]


def _name_hl7(patient: dict) -> str:
    """Render an HL7 ``Family^Given`` name from "name" or "full_name".

    Mirrors the reference ``name.split(' ').reverse().join('^')`` — the
    words are reversed and joined with ``^`` (so "Rajan Menon" → "Menon^Rajan").
    """
    raw = patient.get("name") or patient.get("full_name") or ""
    parts = raw.split()
    return "^".join(reversed(parts))


def _pid(patient: dict) -> str:
    """Patient-identifier component ``<patient_id>^^^BCH^MR``."""
    return f"{patient.get('patient_id', '')}^^^BCH^MR"


def _msh(msg_code: str, trigger: str, structure: str, app: str,
         ts: str, mid: str) -> str:
    """Build an MSH segment."""
    return (
        f"MSH|{ENCODING_CHARS}|{app}|BCH|NiFi|BCH|{ts}||"
        f"{msg_code}^{trigger}^{structure}|{mid}|P|2.5"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Message builder
# ═══════════════════════════════════════════════════════════════════════════

def build_hl7(patient: dict, msg_type: str, *,
              now: datetime | None = None,
              msg_id: str | None = None) -> str:
    """Build an HL7 v2.5 message for `msg_type`.

    `msg_type` must be one of ``{"ADT_A01", "ADT_A03", "ADT_A04",
    "ORU_R01", "ORM_O01"}``; anything else raises ``ValueError``. Segments
    are joined by the carriage return ``\\r``.
    """
    if msg_type not in _SENDING_APP:
        raise ValueError(f"Unknown HL7 msg_type: {msg_type!r}")

    now = now or datetime.now()
    ts = _ts14(now)
    mid = msg_id if msg_id is not None else "MSG" + ts[-6:]

    name = _name_hl7(patient)
    dob = _norm_dob(patient.get("dob"))
    gender = patient.get("gender", "")
    pid_id = _pid(patient)
    app = _SENDING_APP[msg_type]

    if msg_type == "ADT_A04":
        # Registration: full demographics in the PID (address PID-11, phone
        # PID-13), outpatient class — there is no admission yet.
        city = patient.get("city", "")
        phone = patient.get("phone", "")
        return SEP.join([
            _msh("ADT", "A04", msg_type, app, ts, mid),
            f"EVN||{ts}",
            f"PID|1||{pid_id}||{name}||{dob}|{gender}|||{city}||{phone}",
            "PV1|1|O|Registration",
        ])

    if msg_type in ("ADT_A01", "ADT_A03"):
        trigger = "A01" if msg_type == "ADT_A01" else "A03"
        patient_class = "I" if msg_type == "ADT_A01" else "O"
        dept = patient.get("department", "")
        room = patient.get("room", "")
        dr = patient.get("attending_dr", "")
        enc = patient.get("enc_id", "")

        segments = [
            _msh("ADT", trigger, msg_type, app, ts, mid),
            f"EVN||{ts}",
        ]
        if msg_type == "ADT_A01":
            city = patient.get("city", "")
            segments.append(
                f"PID|1||{pid_id}||{name}||{dob}|{gender}|||{city}"
            )
        else:
            segments.append(f"PID|1||{pid_id}||{name}||{dob}|{gender}")
        segments.append(
            f"PV1|1|{patient_class}|{dept}^{room}|||||||{dr}||||||||{enc}"
        )
        if msg_type == "ADT_A01":
            conditions = patient.get("conditions") or []
            first = conditions[0] if conditions else {}
            icd = first.get("icd10_code", "")
            desc = first.get("description", "")
            segments.append(f"DG1|1||{icd}^{desc}^I10")
        return SEP.join(segments)

    if msg_type == "ORU_R01":
        segments = [
            _msh("ORU", "R01", msg_type, app, ts, mid),
            f"PID|1||{pid_id}||{name}||{dob}|{gender}",
            f"OBR|1|||LAB^Laboratory Panel^L|||{ts}",
        ]
        for i, obs in enumerate(patient.get("observations") or [], start=1):
            loinc = obs.get("loinc_code", "")
            display = obs.get("display_name", "")
            value = obs.get("value", "")
            unit = obs.get("unit", "")
            ref = obs.get("ref", "")
            flag = obs.get("flag", "")
            segments.append(
                f"OBX|{i}|NM|{loinc}^{display}^LN||{value}|{unit}|{ref}||{flag}|||F"
            )
        return SEP.join(segments)

    # ORM_O01
    enc = patient.get("enc_id", "")
    dr = patient.get("attending_dr", "")
    segments = [
        _msh("ORM", "O01", msg_type, app, ts, mid),
        f"PID|1||{pid_id}||{name}||{dob}|{gender}",
        f"ORC|NW|{enc}-001|||||||{ts}|||{dr}",
    ]
    for med in patient.get("medications") or []:
        drug = med.get("drug_name", "")
        dose = med.get("dose", "")
        freq = med.get("frequency", "")
        segments.append(f"RXO|{drug}^{drug}^RxNorm|{dose}||{freq}")
    return SEP.join(segments)


# ═══════════════════════════════════════════════════════════════════════════
# Routing
# ═══════════════════════════════════════════════════════════════════════════

def parse_destination(msg_type: str) -> str:
    """Return the Postgres table an `msg_type` routes to.

    ADT_A01/ADT_A03 → "encounters", ADT_A04 → "patients",
    ORU_R01 → "observations", ORM_O01 → "medications". Unknown types
    raise ``ValueError`` (consistent with ``build_hl7``).
    """
    try:
        return _DESTINATIONS[msg_type]
    except KeyError:
        raise ValueError(f"Unknown HL7 msg_type: {msg_type!r}")
