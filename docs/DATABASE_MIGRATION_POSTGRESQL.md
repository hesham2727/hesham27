# Database Migrations and the SQLite → PostgreSQL Path

## Migrations (Alembic)

* Migrations live in `backend/migrations/versions/`. The initial schema is `0001_initial_schema.py`.
* The application runs `alembic upgrade head` automatically at start-up (desktop and server), so installed copies upgrade themselves.
* `render_as_batch=True` is enabled so future `ALTER TABLE` operations work on SQLite.

Creating a new migration after changing `app/models.py`:
```bash
cd backend
TAHQIQ_DATABASE_URL=sqlite:///./dev.db ../.venv/bin/alembic upgrade head
TAHQIQ_DATABASE_URL=sqlite:///./dev.db ../.venv/bin/alembic revision --autogenerate -m "describe change"
# review the generated file, then commit it
```

## When to move to PostgreSQL

SQLite (WAL mode) is the right choice for one host and 1–5 users. Consider PostgreSQL when any of these become true:
* More than one application server, or the database must live on a separate host.
* Sustained concurrent writes from many users (SQLite serializes writers).
* Centralized backup/replication requirements.

PostgreSQL is free and open-source; self-hosting it on the same VPS adds no licence cost.

## Migration steps

1. Install the driver: `pip install "psycopg[binary]"` (LGPL, free).
2. Create an empty database and user in PostgreSQL.
3. Create the schema: `TAHQIQ_DATABASE_URL=postgresql+psycopg://user:pass@host/tahqiq alembic upgrade head`
4. Copy the data (application stopped):
   ```python
   # one-off script, run from backend/
   from sqlalchemy import create_engine, MetaData
   src = create_engine("sqlite:///path/to/tahqiq.db")
   dst = create_engine("postgresql+psycopg://user:pass@host/tahqiq")
   meta = MetaData(); meta.reflect(src)
   with src.connect() as s, dst.begin() as d:
       for t in meta.sorted_tables:
           if t.name == "alembic_version":
               continue
           rows = [dict(r._mapping) for r in s.execute(t.select())]
           if rows:
               d.execute(t.insert(), rows)
   ```
5. Reset sequences (`SELECT setval(pg_get_serial_sequence('users','id'), max(id)) FROM users;` for each table with an integer id).
6. Set `TAHQIQ_DATABASE_URL` permanently and start the application.

Design choices that keep this path simple: only portable column types (String, Text, Integer, Float, Boolean, JSON, timezone-aware DateTime), no SQLite-specific SQL, all timestamps stored in UTC.
