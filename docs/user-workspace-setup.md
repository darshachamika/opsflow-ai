# User workspace upgrade

This patch extends the existing backend and Next.js frontend. Keep your current
feat/frontend-dashboard branch and copy the patch's backend/, frontend/ and docs/
files into the matching project directories. Do not replace .env or remove data.

## 1. Local settings

In the project ROOT .env, keep database credentials and add/update:

```dotenv
CORS_ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
SESSION_COOKIE_SECURE=false
SESSION_HOURS=8
```

In frontend/.env.local set:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Use http://localhost:3000 in the browser. Do not mix localhost UI with 127.0.0.1
API. SameSite=Lax cookies work between different ports on the same site. For a
remote deployment use HTTPS, SESSION_COOKIE_SECURE=true and same-site frontend/API
origins (or a properly configured same-origin gateway). Cross-site hosting is not
configured by this local setup.

## 2. Rebuild backend and apply migration

Stop the frontend dev terminal with Ctrl+C. From the PROJECT ROOT:

```powershell
docker compose -f compose.yaml -f compose.backend.yaml stop api planning-worker
docker compose -f compose.yaml -f compose.backend.yaml build api
docker compose -f compose.yaml -f compose.backend.yaml run --rm migrate
docker compose -f compose.yaml -f compose.backend.yaml up -d --wait --force-recreate api
docker compose -f compose.yaml -f compose.backend.yaml exec api python -m alembic current
docker compose -f compose.yaml -f compose.backend.yaml exec api python -m alembic check
```

Run one command at a time and stop on any error. Expected head: f190a2bc710d.
Expected check: No new upgrade operations detected. The migration creates web_users
and web_sessions only. Existing stock, incidents, approvals and mock orders remain.
Restart the optional planning worker afterward only if you use it.

## 3. One-time administrator setup

From PROJECT ROOT, create a manager account:

```powershell
docker compose -f compose.yaml -f compose.backend.yaml exec api python -m app.provision_web_user --subject chamii.manager --role PROCUREMENT_MANAGER
```

Type a password of 15–256 characters and confirm it. Input is hidden. Choose your
own password; do not paste it into chat. No API restart is needed.

Optionally provision a separate operator:

```powershell
docker compose -f compose.yaml -f compose.backend.yaml exec api python -m app.provision_web_user --subject chamii.operator --role OPERATOR
```

Only an administrator with local container/database access runs these commands.
Normal users only use the login page. Re-running provisioning resets the password
and revokes that user's browser sessions. To disable a user:

```powershell
docker compose -f compose.yaml -f compose.backend.yaml exec api python -m app.provision_web_user --subject chamii.operator --role OPERATOR --disable
```

Legacy bearer credentials for CLI workers remain separately configured; disabling
a browser login does not revoke a legacy bearer token. Rotate/revoke those using
the existing credential configuration when retiring an identity.

## 4. Start UI

From PROJECT ROOT:

```powershell
cd frontend
npm ci
npm run test
npm run build
npm run dev
```

Open http://localhost:3000, log in with chamii.manager and the password you chose.
No token or UUID entry is required. Keep the dev server running.

## 5. Normal user workflow

1. Select an incident by name or click New incident.
2. Choose product and plant from searchable selectors; enter title/description.
3. Choose a warehouse and review lead time/cost inputs, then Analyze incident.
4. If evidence is incomplete, read the issues. Real operational data needs an
   upstream refresh; do not bypass evidence checks or alter dates to force approval.
5. For a usable recovery option, click Create transfer/purchase proposal.
6. Open Approvals. A procurement manager inspects saved plan/evidence, writes a
   decision reason and approves or rejects before validity expires.
7. For an approved proposal, explicitly confirm Execute mock recovery.
8. Check the execution result and Record history. A second execution request on
   the same proposal must return the existing result rather than another order.

The earlier successful demo has existing reservations and demand claims. A new
incident for the same demand pool may correctly fail revalidation; it does not
create new supply. Do not delete reservations to make the UI look successful.
For a fictional demonstration only, the existing reset_demo_timeline command may
refresh demo dates, but it does not remove those claims or replenish quantities.

## 6. Regression checks

In a separate terminal, from backend, apply migrations to the existing disposable
opsflow_test database before running integration tests:

```powershell
$priorDbSetting = $env:POSTGRES_DB
try {
    $env:POSTGRES_DB = "opsflow_test"
    uv run python -m alembic upgrade head
} finally {
    if ($null -eq $priorDbSetting) {
        Remove-Item Env:POSTGRES_DB -ErrorAction SilentlyContinue
    } else {
        $env:POSTGRES_DB = $priorDbSetting
    }
}
uv run python -m pytest tests -q
```

Stop if migration fails. Do not run tests against valuable data. The new unit tests
use disposable SQLite tables to validate login/session/role/CSRF behavior and list
queries; PostgreSQL migration and full integration execution need your environment.

Manual checks: wrong password rejected; correct login persists on reload; logout
revokes session; OPERATOR cannot approve/execute; no-origin or foreign-origin cookie
writes rejected; expired proposal disabled; refresh incident records after action;
new incident uses selected catalog records; failed evidence shows no fabricated
options; repeated execution has no duplicate mock order.

## Security and scope

Password hashes use salted scrypt N=32768,r=8,p=3. Session tokens are random and only
SHA-256 hashes are stored. Cookies are HttpOnly + SameSite=Lax; browser mutation
requests require an exact configured Origin. Five failed account logins lock the
account for 15 minutes; each new login replaces the prior browser session. Role
and enabled state are read from the DB per authenticated request. There is no public
registration or client-selected role.

This is an internal single-organization prototype. Before public exposure add edge
rate limits (including unknown-user attempts), HTTPS, SSO/MFA where appropriate,
secret management, audit/monitoring and a reviewed password recovery process.

## Commit (project root, after local checks)

```powershell
git add frontend docs/user-workspace-setup.md backend/app/main.py backend/app/core/approval_auth.py backend/app/core/passwords.py backend/app/core/session_config.py backend/app/api/web_auth.py backend/app/api/workspace.py backend/app/services/web_sessions.py backend/app/models/web_identity.py backend/app/models/__init__.py backend/app/provision_web_user.py backend/migrations/versions/f190a2bc710d_add_browser_sessions.py backend/tests/unit/test_web_login.py backend/tests/unit/test_workspace_lists.py backend/tests/unit/test_backend_readiness.py
git commit -m "feat: connect browser login and end-to-end recovery workspace"
git push -u origin feat/frontend-dashboard
```

Never stage .env, .env.local, ZIP review archives, node_modules or .next.
