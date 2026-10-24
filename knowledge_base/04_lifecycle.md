# DEMO-POL-04 — Incident lifecycle
Synthetic demonstration policy. Version 1.0, 2026-10-23. Source: OpsPilot illustrative knowledge base. Owner: fictional demonstration service desk. Not an official Accenture policy or a UCI source document.

## Record and investigate
Create an incident record when a service interruption is reported. Capture opening time, contact channel, service, impact and urgency when known. Assign an accountable team, investigate evidence and record meaningful updates. A New incident enters active investigation after triage. Awaiting information or a vendor should identify the dependency, accountable owner and next review time; waiting is not resolution.

## Resolve and close
Record the resolution action and verification evidence. Notify the requester and ask for confirmation where appropriate. Follow DEMO-POL-08 for closure and reopening. Restoration can precede full resolution or root-cause investigation. Create a separate problem investigation when recurring causes require analysis.

## Interpretation of observations
The historical dataset has New, Active, Resolved, Closed and several Awaiting states. Those are observations in an anonymized log, not proof that this demonstration process occurred. Unknown normalized states mean missing interpretation, not a new lifecycle stage. Do not infer event occurrence times solely from completion fields: an early observation can already contain a future resolved_at or closed_at timestamp. OpsPilot therefore does not compute historical as-of state or completion analytics.
