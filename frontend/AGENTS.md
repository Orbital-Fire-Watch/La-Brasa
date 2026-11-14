# Frontend: guidelines for AI assistants and contributors

These are **default best practices, not fixed rules**. If you have more context (the existing code,
the task, the team's decisions) and a different approach fits better, choose it. Explain the
deviation in your answer or commit message, and stay consistent with the code that already exists.

## How to work

1. **Look before you write.** Check the existing setup first (framework, build tool, styling, data
   fetching) and follow the patterns already in use.
2. **Keep it simple.** Build what the task needs. Do not add libraries, global state or abstractions
   the app does not need yet.
3. **Small, verifiable steps.** Make one logical change at a time. Check that the app builds and the tests pass.
4. **Report.** Say what you changed, what you deliberately left out, and any open questions.

## Structure

The folders in `frontend/` are a starting point that separates concerns:

| Concern | Typical home |
|---|---|
| Page-level views | `routes/` |
| Reusable UI building blocks | `components/` |
| Reusable stateful logic (custom hooks) | `hooks/` |
| Communication with the backend | `services/` |
| Pure helper functions without UI | `lib/` |
| Global styles and design tokens | `styles/` |
| Assets imported by code / files served as-is | `assets/` / `public/` |

- Dependencies point in one direction: views → components/hooks → services/lib. Helpers in `lib/`
  stay free of UI code, and components do not talk to the network directly.
- If the project grows and another structure fits better (e.g. grouping by feature), restructure
  deliberately and consistently. Do not mix two layouts.

## Talking to the backend

- The backend API is versioned in the path (`/api/v1/...`). Define the versioned base path once in
  the central HTTP client, not in every call, so switching to a new version is a one-line change.
- Use one central place for HTTP calls: base URL, headers, timeouts, and turning failures into one
  consistent error type.
- Keep API functions small and typed, and define each endpoint path once.
- Derive API types from the backend contract (e.g. generated from OpenAPI) rather than writing them
  by hand twice where possible.
- Cancel outdated requests (e.g. `AbortController`) and debounce high-frequency input such as map
  moves or sliders.
- Build query strings with `URLSearchParams`, never by string concatenation.
- Handle every state in the UI: loading, error, empty, success. Never swallow errors silently.

## TypeScript

- Turn on strict mode. Avoid `any` (use `unknown` and narrow it). Avoid non-null assertions and
  unchecked casts except at well-understood boundaries.
- Model closed value sets as string unions and UI states as discriminated unions, not as several
  booleans that can contradict each other.
- Derive types instead of duplicating them. Use `import type` for type-only imports.

## Components (React, if used)

- Function components with typed props. Keep components small and focused, and split data loading
  from presentation when a component does too much.
- Use effects only to sync with external systems (DOM APIs, map/chart libraries), always with cleanup.
  Compute derived values during render instead of storing them in state.
- Keep state minimal and as local as possible. Use stable keys from data ids, not array indices.
- Consider keeping shareable view state (filters, selections) in the URL.

## Naming

- Follow the ecosystem conventions: `PascalCase` for components and types, `camelCase` for functions
  and variables, `useXxx` for hooks, `UPPER_SNAKE` for constants.
- Whatever file naming the project uses, keep it consistent.

## Styling and accessibility

- Use one styling approach consistently, with design tokens (colors, spacing, fonts) defined once
  instead of hard-coded values.
- Use semantic HTML and make everything keyboard-operable. Clickable elements are real buttons or links.
- Give icon-only buttons an accessible label and use sufficient contrast. Never use color alone to
  convey meaning, so maps and charts need legends or labels.
- Prefer colorblind-safe color scales for data visualization.

## Security and configuration

- Environment variables bundled into the client are public. Never put secrets in them.
- Read configuration once in a typed module, not throughout components.
- Do not render untrusted HTML (`dangerouslySetInnerHTML`/`innerHTML`). External links with
  `target="_blank"` use `rel="noopener noreferrer"`.

## Performance

- Lazy-load heavy libraries and views where it helps. Import only what you use.
- Never fetch unbounded data. Paginate, aggregate or virtualize large lists.
- Measure before optimizing.

## Quality

- Use a type check, linter and formatter if configured, and keep them passing.
- Write unit tests for pure helpers and focused tests for key user flows. Test behavior, not
  implementation details.
- Do not leave dead or commented-out code. Comments explain *why*.
