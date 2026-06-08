# Meditech Lab 2.0 — Dashboard

A modular Flask dashboard for the Meditech lab. The browser talks only to
this app's JSON endpoints; Postgres is the one hard dependency, with
Elasticsearch feature-flagged off by default and other services (NiFi,
Kibana, MinIO) simulated later.

## Setup

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python app.py
# or
flask --app app run
```

Then open http://localhost:5000 — the dashboard shell renders with four
nav panels (Patients, Extractor, Coder, Pipeline) and a service-status
strip that polls `GET /api/health`.

## Configuration

Settings are read from the environment with local-dev defaults baked in
(see `config.py`):

| Variable      | Default                                                          |
|---------------|------------------------------------------------------------------|
| `DB_DSN`      | `postgresql://admin:adminpassword@localhost:5432/healthcare_db`  |
| `ES_URL`      | `http://localhost:9200`                                         |
| `ES_ENABLED`  | `False`                                                          |
| `ARCHIVE_DIR` | `data/archive`                                                   |

## Project layout

```
dashboard/
├── app.py            Flask app factory + dashboard shell + /api/health
├── config.py         Environment-driven Config object
├── db.py             psycopg2 connection helper (query/execute/ping)
├── es.py             Optional, feature-flagged Elasticsearch client
├── blueprints/       Thin HTTP wiring, one per module (currently stubs)
├── domain/           Pure domain logic — no Flask, no DB
├── templates/        Jinja templates (dashboard shell)
├── static/           CSS / JS for the shell
└── tests/            pytest suite
```

## Health check

`GET /api/health` returns:

```json
{"postgres": true, "es": "disabled"}
```

`es` is `"disabled"` when `ES_ENABLED` is `False` (the default), or a
boolean once Elasticsearch is enabled and reachable.
