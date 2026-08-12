# Hackathon API

FastAPI API scaffold using the same tech stack and architecture as
`it-st-automation-portal`, but backed by **PostgreSQL** instead of SQLite.

## Tech stack

- **FastAPI** + **Uvicorn**
- **SQLAlchemy 2.x** ORM with **PostgreSQL** (`psycopg2`)
- **Pydantic v2** / `pydantic-settings` for config & validation
- Controller → Service → Repository layering
- Per-request DB transactions, centralized error handling, request logging
- i18n (English / Japanese)
- **uv** for dependency & environment management

## Project structure

```
hackathon-API/
├── main.py                     # FastAPI entrypoint (app = FastAPI(...))
├── pyproject.toml              # Dependencies (managed by uv)
├── .env                        # Local environment variables
└── app/
    ├── core/                   # config, database, logger, i18n
    ├── locales/                # en.json, ja.json
    └── api/
        ├── middleware/         # error handler, logging, transaction, locale
        ├── models/             # SQLAlchemy models
        ├── schemas/            # Pydantic request/response models
        ├── repositories/       # DB access layer
        ├── services/           # business logic
        └── controllers/        # API routers (endpoints)
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed
- A running PostgreSQL instance

Update the database settings in `.env` (or set `DATABASE_URL` directly):

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=hackathon
```

Create the database once (if it doesn't exist):

```bash
createdb hackathon
# or: psql -U postgres -c "CREATE DATABASE hackathon;"
```

## Run

```bash
uv sync                                        # install dependencies
uv run uvicorn main:app --reload --port 8000   # start the server
```

Then open:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/api/v1/health

## Adding a new controller

1. Create the model in `app/api/models/<name>.py` and import it in
   `app/api/models/__init__.py`.
2. Add Pydantic schemas in `app/api/schemas/<name>_schema.py`.
3. Add a repository in `app/api/repositories/<name>_repository.py`.
4. Add a service in `app/api/services/<name>_service.py`.
5. Add a controller (router) in `app/api/controllers/<name>_controller.py`.
6. Register the router in `app/api/controllers/__init__.py` and include it in
   `main.py`.

The `items` endpoints (`app/api/**/item*`) are a complete working example you
can copy from.
