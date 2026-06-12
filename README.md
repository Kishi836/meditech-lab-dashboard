# Meditech Lab 2.5 — Dashboard

A polished, modular **Flask dashboard** for Bangalore City Hospital's
"Meditech Lab" (Module 2 of *Medical Informatics · UE26MT324*). Five modules
over the lab's real PostgreSQL, plus a **hybrid** (half-simulated) HL7 data
pipeline:

| Module        | What it does                                                            |
|---------------|-------------------------------------------------------------------------|
| **Patients**  | Searchable registry → tabbed record (demographics, encounters, lab trend charts, meds) read live from Postgres. |
| **Intake**    | Register a new patient (emits a real **ADT^A04**) or record a lab result (emits a real **ORU^R01**) — each message animates through the six-stage pipeline before the row lands in Postgres. |
| **Extractor** | Paste a clinical note → highlighted entities (vitals, labs, codes) + a structured table. |
| **Coder**     | ICD-10 / SNOMED lookup, search, hierarchy tree, and cross-map.          |
| **Pipeline**  | Build an HL7 v2.5 message from a patient → watch it flow through six stages (NiFi → Postgres → Elasticsearch → Kibana → MinIO), then live feed + analytics. |

The browser talks **only** to this app's JSON endpoints; Postgres access is
hidden behind `db.py`, and Elasticsearch behind `es.py`. Pure domain logic
lives in `domain/` (no Flask, no DB) and is unit-tested.

**Pipeline realness:** `build` (HL7) and `postgres` (a tagged row insert) are
**real**; `elasticsearch` is real when enabled, otherwise reported `skipped`;
`nifi_route`, `kibana`, and `minio` are **simulated** in-app (MinIO writes the
raw HL7 to a local archive dir). Every row the **demo pipeline** writes is
tagged with an `ENC-HL7-` `enc_id` prefix so it never pollutes the seed data,
and `Reset` cleans it all up. Rows created through **Intake** are *real* data —
they use a separate `ENC-LAB-` prefix (and `REG-`/`LAB-` archive filenames), so
`Reset` leaves them alone; non-seed patients can be removed with the guarded
DELETE endpoint instead.

---

## Prerequisites

- **Python 3.10+** and **Docker** (for the Postgres container).
- The one hard dependency is PostgreSQL. Start it from the **repo root**
  (`meditech-lab/`, one level up from this folder):

  ```powershell
  docker compose up -d postgres
  ```

  This brings up `healthcare_db` on `localhost:5432` (creds
  `admin` / `adminpassword`), seeded from `init.sql`.

## Setup & run

From this `dashboard/` folder:

```powershell
pip install -r requirements.txt
python app.py            # dev server on http://localhost:5000
# or: flask --app app run
```

Open **http://localhost:5000**. The status strip (bottom-left) polls
`GET /api/health` — the **Postgres** dot is green when the DB is reachable,
**Elasticsearch** is grey ("disabled") until you turn ES on.

## Tests

```powershell
python -m pytest -q          # or -v for the full list
```

The suite covers the pure `domain/` logic (coding, extraction, HL7) and does
**not** require Postgres.

## Configuration

Settings are read from the environment with local-dev defaults baked in
(see `config.py`):

| Variable      | Default                                                          |
|---------------|------------------------------------------------------------------|
| `DB_DSN`      | `postgresql://admin:adminpassword@localhost:5432/healthcare_db`  |
| `ES_URL`      | `http://localhost:9200`                                          |
| `ES_ENABLED`  | `False`                                                          |
| `ARCHIVE_DIR` | `data/archive`                                                  |

### Enabling Elasticsearch (optional)

ES is off by default and the pipeline's `elasticsearch` stage reports
`skipped`. To turn it on, point `ES_URL` at a running Elasticsearch and set
the flag before launching:

```powershell
$env:ES_ENABLED = "true"
$env:ES_URL = "http://localhost:9200"
python app.py
```

With ES enabled and reachable, the pipeline's `elasticsearch` stage indexes
each message and the health dot goes green; if it's unreachable the stage
turns red but the rest of the pipeline still succeeds.

## Project layout

```
dashboard/
├── app.py            Flask app factory + dashboard shell + /api/health
├── config.py         Environment-driven Config object
├── db.py             psycopg2 connection helper (query/execute/ping)
├── es.py             Optional, feature-flagged Elasticsearch client
├── blueprints/       Thin HTTP wiring — one per module
│   ├── common.py       shared pipeline plumbing (staged runner, feed, archive)
│   ├── patients.py     /api/patients[/<id>[/trends]]
│   ├── intake.py       /api/intake/*, /api/catalog/tests, DELETE /api/patients/<id>
│   ├── extractor.py    POST /api/extract
│   ├── coder.py        /api/icd10, /api/snomed/*, /api/crossmap/*
│   └── pipeline.py     POST /api/hl7/{send,preview}, /api/pipeline/*, /api/analytics/*
├── domain/           Pure domain logic — no Flask, no DB
│   ├── catalog.py      orderable-test catalog (ref ranges + critical thresholds)
│   ├── coding.py       ICD-10 + SNOMED
│   ├── extract.py      clinical-note entity extraction
│   ├── hl7.py          HL7 v2.5 message builder
│   └── intake.py       patient/result validation + id minting
├── templates/        Jinja templates (shell + one per module)
├── static/           CSS / JS (GitHub-dark theme, Chart.js)
└── tests/            pytest suite (domain logic)
```

## API quick reference

| Endpoint                                   | Purpose                                  |
|--------------------------------------------|------------------------------------------|
| `GET  /api/health`                         | Postgres + ES status                     |
| `GET  /api/patients[?q=]`                  | patient list / search                    |
| `GET  /api/patients/<id>[/trends]`         | full record / per-test trend series      |
| `POST /api/extract`                        | clinical-note entity extraction          |
| `GET  /api/icd10`, `/api/snomed/*`, `/api/crossmap/*` | coding lookups                |
| `POST /api/hl7/preview`                    | build an HL7 message (no persistence)     |
| `POST /api/hl7/send`                       | build + run the six-stage pipeline        |
| `GET  /api/catalog/tests`                  | orderable tests (unit, ref range)        |
| `POST /api/intake/preview`                 | live ADT^A04 / ORU^R01 preview while typing |
| `POST /api/intake/patient`                 | register a patient via the pipeline (ADT^A04) |
| `POST /api/intake/result`                  | record a lab result via the pipeline (ORU^R01) |
| `DELETE /api/patients/<id>`                | delete a non-seed patient (403 for PT-001…PT-008) |
| `GET  /api/pipeline/feed`                  | recent sends (this session)              |
| `GET  /api/pipeline/reset`                 | delete demo pipeline rows + archive (intake data stays) |
| `GET  /api/analytics/{conditions_by_dept,message_counts,critical_values}` | dashboard aggregates |

## Manual acceptance checklist

1. **Postgres down** (`docker compose stop postgres`) → reopen the app: the
   Patients banner reads "Couldn't reach the database…", the Postgres status
   dot is red, **no stack trace**. Bring it back with
   `docker compose start postgres`.
2. **Patients** → list loads; select **Rajan Menon (PT-001)** → the **Labs**
   tab renders the HbA1c trend chart (worsening 7.2 → 8.9 %).
3. **Extractor** → paste a note → entities highlight and the table fills.
4. **Coder** → search a term → open a concept → its cross-map returns the
   correct ICD-10.
5. **Pipeline** → pick **PT-001**, **ORU^R01** → the HL7 preview updates →
   **Send**: all six stages animate (build/postgres green, elasticsearch grey
   "skipped", kibana/minio green), the **feed** gains a row, the **charts**
   update → switch to **Patients**, PT-001 now shows a new tagged encounter →
   back in **Pipeline**, **Reset** removes the row + archive file.
6. **Intake** → **Register Patient** with a name + DOB → the ADT^A04 preview
   builds while typing → **Register**: the packet animates through all six
   stages, a toast names the new id (e.g. **PT-009**), and the patient appears
   in the Patients list.
7. **Intake** → **Record Result** for that patient: **HbA1c 9.5 %** → the
   ORU^R01 animates through, the toast flags it **critical**, the value shows
   in the Pipeline tab's critical-values panel, and the patient's **Labs** tab
   gains the trend point.
8. **Pipeline** → **Reset** → the intake-created patient and result are
   untouched (only `ENC-HL7-` demo rows go). **Patients** → open the new
   patient → **Delete** removes them (the button never appears on seed
   patients PT-001…PT-008).
