# Availability and reliability review (Issue 14)

## Target and assessment

- Required availability: **99.5% per calendar month**.
- This allows about **3 hours 36 minutes** of downtime in a 30-day month.
- **Observed monthly availability: not yet measurable.** No production uptime history or configured external monitor is available in this project, so target compliance cannot be claimed. This evidence gap is the current deviation from the target.

## Monitoring plan

Use an external HTTPS monitor against `/health/`: check once per minute, require HTTP 200 within 10 seconds, validate TLS, and alert after two consecutive failures. The endpoint checks database connectivity and returns HTTP 503 if the database is unavailable. Record each check and incident start/recovery time. Calculate monthly availability as successful scheduled checks divided by all scheduled checks, multiplied by 100. Review incidents and the monthly result against 99.5%.

## Reliability checks and recovery behavior

- A failed reservation with insufficient stock rolls back without partially changing inventory, request status, or audit entries.
- Concurrent reservations for the same unit allow one request to reserve it; the competing request is rejected.
- Repeated reserve/issue actions are rejected safely, and issuing inventory is all-or-nothing.
- Temporary database lock errors are retried up to three times; persistent contention returns a retryable workflow error.
- These are application-level automated checks. A production outage, server restart, database restore, and backup recovery have not been exercised because no deployed environment or backup procedure is configured here.

## Evidence

The health check tests are in `accounts/tests.py`. Rollback, repeat-action, issuance, and competing-reservation tests are in `bloodbank_requests/tests.py`. Run the reliability checks with:

```powershell
.\.venv\Scripts\python.exe manage.py test bloodbank_requests.tests.BloodRequestTests.test_reservation_updates_inventory_and_audit_atomically bloodbank_requests.tests.BloodRequestTests.test_reservation_rolls_back_when_matching_stock_is_insufficient bloodbank_requests.tests.BloodRequestTests.test_request_cannot_be_reserved_twice bloodbank_requests.tests.BloodRequestTests.test_issue_is_atomic_traceable_and_cannot_repeat bloodbank_requests.tests.ConcurrentReservationTests.test_competing_requests_cannot_reserve_the_same_unit
```

Latest verification: all 16 account tests (including healthy and database-failure health checks) and all five listed reliability tests passed; `manage.py check` reported no issues.
