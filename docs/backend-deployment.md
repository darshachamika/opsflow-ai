# Backend container runbook

Apply these files on chore/backend-readiness. Keep compose.yaml and the existing
.env unchanged. compose.backend.yaml extends the current project and reuses
opsflow-ai_postgres_data. No new migrations are introduced by this patch.

## Start locally

Stop any host Uvicorn process with Ctrl+C so port 8000 is free. Docker Desktop must
be running. From the project ROOT (if in backend, run cd .. once):

```powershell
docker compose -f compose.yaml -f compose.backend.yaml config --quiet
docker compose -f compose.yaml -f compose.backend.yaml build api
docker compose -f compose.yaml -f compose.backend.yaml up -d --wait api
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
docker compose -f compose.yaml -f compose.backend.yaml exec api python -m alembic current
docker compose -f compose.yaml -f compose.backend.yaml exec api python -m alembic check
```

Expected: healthy API, ready database, head e84c71d329af and no new upgrade
operations. The migrate container should exit successfully. Migration failure
prevents API startup. Inspect failures with:

```powershell
docker compose -f compose.yaml -f compose.backend.yaml logs --tail 80 migrate api
```

The build uses the committed uv.lock with --locked; dependency resolution failure
must be investigated, not bypassed by deleting the lock. Python dependencies are
installed during image build, not container startup. No .env is copied into the
image. API runs as UID 10001 with a read-only root filesystem and writable /tmp.
Container DB connection uses db:5432; Windows continues to use 127.0.0.1:5433 (or
its existing configured host port). API and database ports bind only to localhost.

## Planning worker (optional)

```powershell
docker compose -f compose.yaml -f compose.backend.yaml --profile workers up -d planning-worker
```

This consumes pending planning jobs and may call Gemini when enabled. Approval
execution is not started automatically. To use the existing interactive worker
against the same DB, run it from the host backend environment with a manager token.

## Settings or code updates

Rebuild after code changes. Recreate API/planning worker after .env changes; a
simple restart does not reload Compose environment values. Stop app processes
before applying new schema migrations:

```powershell
docker compose -f compose.yaml -f compose.backend.yaml stop api planning-worker
docker compose -f compose.yaml -f compose.backend.yaml build api
docker compose -f compose.yaml -f compose.backend.yaml run --rm migrate
docker compose -f compose.yaml -f compose.backend.yaml up -d --wait --force-recreate api
```

Only if using planning-worker, recreate it with the workers profile afterward.
Keep the existing token provisioning script on the host; it updates the host .env.
Use a real HTTPS frontend origin in CORS_ALLOWED_ORIGINS when hosting remotely.

## Existing test database

From backend:

```powershell
uv run python -m pytest tests -q
```

For a NEW test database only, first create it from the project root (commands below
assume the example opsflow DB role; adapt if changed):

```powershell
docker compose exec db createdb -U opsflow opsflow_test
```

If it already exists, do not delete it. Apply migrations in backend using a
process-local setting, restoring the prior environment afterward:

```powershell
$previousTestDbSetting = $env:POSTGRES_DB
try {
    $env:POSTGRES_DB = "opsflow_test"
    uv run python -m alembic upgrade head
} finally {
    if ($null -eq $previousTestDbSetting) {
        Remove-Item Env:POSTGRES_DB -ErrorAction SilentlyContinue
    } else {
        $env:POSTGRES_DB = $previousTestDbSetting
    }
}
```

Run tests only after successful migration. Do not use alembic stamp as a substitute
for creating schema.

## Final checks

- All tests pass in the project's locked Python environment.
- Container readiness succeeds and Alembic reports expected head/no drift.
- Swagger business request without a token returns 401; health remains public.
- Valid /api/v1/auth/me returns the expected actor/role.
- Read the history and execution for the existing successful demo proposal; no
  need to submit another order or reset stock to prove the history view.
- If demonstrating new execution, use an isolated fresh demo scenario. Approval
  and execution must happen inside validity windows with fresh evidence.
- Verify live background execution separately if claiming it in a presentation.

## Hosting boundary

This patch does not provision a cloud host, TLS, external ERP credentials or an
identity provider. Deploy API and continuous workers as separate processes with a
shared PostgreSQL database; use one migration job per release. Add backups and
restore testing, observability, secret rotation and deployment-specific resource
limits before handling real operational data. Avoid --reload for deployed API.
Do not run docker compose down -v: it removes the database volume.

## Review evidence

Source migrations have one head: e84c71d329af. Docker is unavailable in the review
environment, so image build and Compose runtime checks must run on your machine.
No claim of successful container deployment is made until those checks pass.
