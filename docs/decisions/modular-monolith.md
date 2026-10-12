# ADR 001: Modular Monolith with a Separate Worker

- Status: Accepted
- Date: 2026-10-12

## Context

OpsFlow AI needs an HTTP API, business rules, database access,
external connectors and long-running investigation workflows.

The MVP is developed by a small team and must be easy to run,
test and debug. Investigations must continue independently of
the lifetime of an HTTP request.

## Decision

Build a modular monolith with a separate background worker process.

- FastAPI handles HTTP requests and authentication.
- Shared Python services implement business rules.
- A worker processes durable jobs stored in PostgreSQL.
- LangGraph coordinates the agent workflow.
- Connector interfaces isolate external ERP, WMS and carrier APIs.
- The API and worker share the same backend codebase.
- Next.js provides the operator interface.

Create an incident and its initial job in one database transaction.

Keep module boundaries explicit:
API routes → business services → persistence and connector interfaces.

## Alternatives Considered

### Microservices

Separate services could be deployed and scaled independently.

Rejected for the MVP because distributed communication,
deployment and consistency would add unnecessary complexity.

### Run Workflows Inside HTTP Requests

This would reduce the number of running processes.

Rejected because request timeouts and API restarts must not
interrupt durable investigation and approval workflows.

## Consequences

### Benefits

- Simple local development and deployment.
- Shared, testable business rules.
- Local transactions for related database changes.
- API and worker processes can scale separately.

### Trade-offs

- Modules share a database and require disciplined boundaries.
- API and worker releases must remain compatible.
- The worker requires job claiming, leases and recovery logic.
- PostgreSQL job processing requires monitoring and tuning.

## Revisit When

Reconsider service separation when measured scaling needs,
deployment requirements or team ownership justify it.