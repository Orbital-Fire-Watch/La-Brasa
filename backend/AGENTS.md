# Backend: guidelines for AI assistants and contributors

These are **default best practices, not fixed rules**. If you have more context (the existing code,
the task, the team's decisions) and a different approach fits better, choose it. Explain the
deviation in your answer or commit message, and stay consistent with the code that already exists.

## How to work

1. **Look before you write.** Read the existing code, config and folder layout first. Follow the
   patterns already in use rather than introducing a second way of doing the same thing.
2. **Keep it simple.** Build what the task needs, not what it might need someday. Prefer a few clear
   files over many tiny ones. Add abstractions only when they remove real duplication or complexity.
3. **Small, verifiable steps.** Make one logical change at a time and check that it still runs and the tests pass.
4. **Report.** Say what you changed, what you deliberately left out, and any open questions.

## Structure and layering

The folders in `backend/` are a starting point that separates concerns:

| Concern | Typical home |
|---|---|
| HTTP layer: parse the request, call the logic, return a response | `routes/` |
| Business logic | `services/` |
| Database access | `repositories/` |
| Database table definitions | `models/` |
| Request/response data shapes | `schemas/` |
| Shared infrastructure: config, DB connection, logging, error types | `core/` |
| Tests | `tests/` |

- Dependencies point in one direction: HTTP layer → logic → data access. Lower layers never import higher ones.
- Keep HTTP-specific code out of business logic, so the logic can be tested without a web server.
- Keep shared infrastructure free of business logic.
- If a layer adds no value for a feature, it is fine to merge it (e.g. queries inside a service).
  Restructure when the code calls for it. When you do, keep the change consistent across the project.

## Code style (Python)

- Type hints on public functions. Avoid `Any` where a precise type is practical.
- PEP 8 naming: `snake_case` for modules, functions and variables, `PascalCase` for classes, `UPPER_SNAKE` for constants.
- Small functions with one job. Names show intent. Add units when the type does not (`radius_km`).
- Named constants instead of magic numbers and strings.
- Idiomatic Python: f-strings, `pathlib`, context managers for resources, comprehensions where they read well.
- Avoid the classic pitfalls: mutable default arguments, bare `except:`, silently swallowed
  exceptions, wildcard imports, global mutable state, `assert` for runtime validation.
- Use the `logging` module rather than `print`, and never log secrets.
- Docstrings on public functions where the behavior is not obvious. Comments explain *why*, not *what*.
- No dead or commented-out code. Use a formatter/linter (e.g. Ruff) if the project has one configured.

## Errors and validation

- Validate input at the boundary (request models, config, external data). Enforce business rules in the logic layer.
- Use meaningful exception types and translate them to responses in one central place, not in every handler.
- Return consistent, machine-readable error responses. Never expose stack traces, SQL or internal paths to clients.
- Catch only what you can handle, and re-raise with context (`raise ... from err`).

## Configuration and secrets

- Read environment-specific values from environment variables, ideally in one typed settings object
  rather than scattered `os.environ` calls.
- Document every new variable in `.env.example`. Never hard-code or commit secrets.
- Fail fast at startup if required configuration is missing.

## API design

- The API is versioned in the path: all endpoints live under `/api/v1/...` (e.g. `/api/v1/regions`).
  Breaking changes go into a new version (`/api/v2/...`) while the previous version keeps working
  until the frontend has migrated. Non-breaking additions (new optional fields, new endpoints) stay
  in the current version. Operational endpoints such as health checks can live outside the version prefix.
- Use clear, consistent resource names, correct HTTP methods and meaningful status codes.
- Declare explicit response models instead of returning raw internal objects.
- Use ISO-8601 dates and UTC timestamps.
- Large collections need limits or pagination.
- Treat the API as a contract with the frontend. Communicate breaking changes, and keep the generated
  API docs (e.g. OpenAPI) accurate.

## Data and database

- Use parameterized queries, never SQL built from string concatenation.
- Filter, aggregate and sort in the database rather than in Python memory when data is large.
- Version schema changes in files (migrations or SQL scripts) instead of creating tables ad hoc from code.
- Keep transactions short, with one unit of work per request or use case.
- Preserve source data. Store derived or processed data separately rather than overwriting the originals.

## Dependencies

- Pin versions for reproducible builds.
- Prefer the standard library or existing dependencies before adding new ones. Justify new, heavy dependencies.

## Testing

- Test business logic with unit tests: happy path, edge cases, error cases.
- Test endpoints with the framework's test client.
- Never call real external services in tests. Mock them.
- Name tests after behavior, with one behavior per test. Do not leave failing tests behind.

## Security

- No `eval`/`exec` on input, no unsafe deserialization, no `shell=True` with user input.
- Configure CORS restrictively. Do not log personal data or credentials.
