# ADR 002: Human Approval for External Business Changes

- Status: Accepted
- Date: 2026-10-12

## Context

Recovery actions can commit money, move stock or change shipments.
An incorrect or repeated action could cause operational harm.

LLM output is not an authorization decision.
Input validation alone does not establish business permission.

## Decision

In the MVP, every recovery action that changes an external business
system requires approval from an authenticated procurement manager.

Read-only investigation runs automatically.

Actions requiring approval include:
- Creating a purchase order.
- Requesting a warehouse transfer.
- Requesting shipment expediting.
- Cancelling or changing an existing commitment if later supported.

Operators may investigate and review proposals.
The administrator role alone does not grant approval permission.

## Approval Binding

Approval applies to one immutable proposal version containing:
- Action type.
- Product and quantity.
- Supplier or source location.
- Destination.
- Cost and currency.
- Expected arrival.
- Supporting evidence references.
- Expiration time.

A change to the approved business payload requires a new proposal
and a new approval.

The MVP allows one selected recovery action per incident at a time.
Approval processing locks the incident record and checks for an
existing approved or executing action.

## Execution Controls

Before execution, the backend verifies:
- An authorized approval exists for the exact proposal.
- The proposal has not expired or been superseded.
- Current stock, price and eligibility remain valid.
- The action has not already been executed.

If conditions invalidate the proposal, execution stops and the
incident returns for review.

Persist the approval decision and its resume job in one transaction.

Use a stable idempotency key for each logical external action.
If the external outcome is uncertain, reconcile before resubmitting.

## Alternatives Considered

### Automatic Approval Below a Spending Threshold

This could reduce manager workload.

Deferred until policy enforcement and operational reliability
have been evaluated. Low-cost actions can still disrupt operations.

### Let the LLM Decide Whether Approval Is Required

Rejected because authorization must be enforced by deterministic
backend policies.

## Consequences

### Benefits

- Explicit human accountability.
- Clear linkage between proposal, approval and execution.
- Easier demonstration and testing of authorization boundaries.

### Trade-offs

- Recovery may wait for a manager.
- The UI must support approval, rejection and expiration.
- Revalidation can require a new approval.
- Approval does not guarantee that external execution succeeds.

## Audit Requirements

Record the proposal reference, manager identity, decision time,
decision reason and execution outcome.

Store concise decision summaries and evidence.
Do not store credentials or hidden model reasoning.

## Revisit When

Consider narrowly scoped automatic actions only after policies,
failure recovery and evaluation results support the change.