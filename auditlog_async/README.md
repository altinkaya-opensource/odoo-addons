# Auditlog Async

Asynchronous audit logging for Odoo. Extends the OCA `auditlog` module to process logs
in the background using `queue_job`, reducing performance overhead on CRUD operations by
up to 10x.

## Installation

1. Install dependencies: `auditlog`, `queue_job`
2. Install this module
3. Ensure queue job workers are running

## How it works

- CRUD operations create lightweight `auditlog.pending` records synchronously
- A cron job (every 5 minutes) triggers background processing via `queue_job`
- Actual audit logs are created asynchronously without blocking main operations
