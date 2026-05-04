# Playwright E2E Tests

## Modes

- **Mocked (default)** — `npm run test:e2e`
  Vite dev server starts; routes are intercepted via the `apiPage` fixture
  in `fixtures/api.ts`. No backend required.

- **Live (nightly)** — `LIVE=1 npm run test:e2e:live`
  Tests run against a real `fmriflow serve` on http://127.0.0.1:8421.
  Only `@live`-tagged tests execute. Boot the server yourself or in CI.

## Adding a flow

1. Create `flows/<view>.spec.ts`.
2. `import { test, expect } from '../fixtures/api'`.
3. Use `apiPage` instead of `page` to inherit the canned API surface.
4. Override specific routes per-test with `page.route(...)`.
