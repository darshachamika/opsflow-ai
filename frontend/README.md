# OpsFlow AI — authenticated workspace

Next.js App Router + Tailwind CSS. This replaces the demonstration-only home page
with a real browser workflow backed by FastAPI.

Users sign in with a provisioned username/password. Session cookies are HttpOnly;
no token entry, localStorage authentication, API-key form or Swagger navigation is
required for the normal workflow.

Supported flow: sign in -> select/create incident -> set planning inputs -> Analyze
-> review transfer/purchase alternatives -> create proposal -> manager decision ->
confirm mock execution -> read execution and history. Lists are selected by names,
not manually pasted IDs. Run/record/proposal lists have load-more controls. Catalog
selectors show up to 50 matches and allow narrower searches.

## Run

Follow docs/user-workspace-setup.md in the project root to apply the backend
migration and provision an account first. Then, from frontend:

```powershell
npm ci
npm run dev
```

Set frontend/.env.local:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Open http://localhost:3000 (not 127.0.0.1). Both sides must use the same hostname
for SameSite cookies. Backend CORS must explicitly allow http://localhost:3000
and allow credentials (included in backend patch). Restart Next after env changes.

```powershell
npm run test
npm run typecheck
npm run build
```

Node 24 supports the TypeScript request tests. No new frontend dependency is needed.
Existing demo components may remain on disk but app/page.tsx now loads OperationsApp.

## Behavior

- No demo fallback; all displayed operational data comes from authenticated APIs.
- Managers alone may approve/reject or execute. Backend enforces the role.
- Financial/supply writes are explicit. Execution has a confirmation dialog.
- Revalidation failures, expired proposals and missing evidence remain visible;
  the UI does not change timestamps or bypass business controls.
- Idempotency retry keys are kept in sessionStorage after uncertain network failures.
  Credentials and request payloads are not stored there.
- A successful login replaces the previous browser session for that account.
- Stored runs display their assessment time. Analyze again for fresh evidence.
- Synchronous runs that remain RUNNING after a server crash are not automatically
  recovered. Stop watching releases the UI only; it does not cancel the run.
- Mock execution reserves data and records a mock order; it is not physical delivery.
- This is a single-organization prototype. Production SSO/MFA, self-service password
  recovery, tenant isolation and ERP evidence ingestion are outside this change.

Build, TypeScript and request tests were executed in the review environment.
Browser QA against your Docker API remains a local acceptance check.
