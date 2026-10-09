---
paths:
  - "tests/**"
---

# Tests

## Do
- Put fast tests with no database or network in `tests/unit/`. Put HTTP/DB tests that go through the app and Postgres in `tests/functional/`.
- Name files `test_<area>.py` and functions `test_<behaviour>_<condition>`.
- Mock external services: email (`flask_mail` outbox or patch), HTTP calls, clocks.
- Reuse fixtures from `tests/conftest.py`. Each test sets up its own data and doesn't depend on test order.
- Cover the failure path (401/403/404/422) as well as the happy path, and cross-organization access for scoped routes.
- Use dummy credentials in test data only.

## Don't
- Don't skip, `xfail`, delete or weaken a test (looser asserts, broader `except`) to make it pass. Fix the code, or ask.
- Don't call real mail servers or other external services.
- Don't rely on data left behind by another test.
- Don't point tests at the development or production database.
