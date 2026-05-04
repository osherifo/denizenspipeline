# fMRIflow Frontend

Web-based UI for browsing plugins, composing pipeline configs, managing runs, and writing custom plugins.

## Quick Start

### 1. Install backend dependencies

These are needed in whichever conda/pip environment you use to run `fmriflow`:

```bash
pip install fastapi "uvicorn[standard]" websockets
```

If you switch environments (e.g. `conda activate dv2`), you need to install these in that environment too.

### 2. Install Node.js (if not already installed)

The frontend requires Node.js 18+. Install via nvm:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc    # or restart your shell
nvm install 22
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Run (development mode)

Open two terminals:

**Terminal 1 — API server:**
```bash
conda activate dv2   # or whichever env has fmriflow installed
fmriflow serve --port 8421
```

**Terminal 2 — Frontend dev server (with hot reload):**
```bash
cd frontend
npm run dev
```

Open http://localhost:5173 in your browser. The Vite dev server proxies `/api` and `/ws` calls to the backend on port 8421.

### Alternative: Single-command (production)

Build the frontend into static files, then serve everything from the backend:

```bash
cd frontend
npm run build        # outputs to ../fmriflow/server/static/
cd ..
fmriflow serve       # serves API + frontend on http://127.0.0.1:8421
```

## Tests

```bash
npm test                 # vitest run (unit + component + view)
npm run test:watch       # interactive
npm run test:coverage    # v8 coverage to ./coverage
npm run test:e2e         # Playwright against mocked API
npm run test:e2e:live    # Playwright against real fmriflow serve (LIVE=1)
```

Layout:

- `src/api/__tests__/` — API client tests
- `src/stores/__tests__/` — Zustand store tests (one file per store)
- `src/components/<area>/__tests__/` — component tests
- `src/views/__tests__/` — view tests
- `src/test/` — harness: `setup.ts`, `render.tsx`, `factories.ts`, `ws.ts`, `mocks/`
- `e2e/flows/` — Playwright flows; `e2e/fixtures/api.ts` is the canned-API fixture

The harness never touches real subject data — every test runs against
synthetic factories or canned MSW responses. See
`devdocs/proposals/infrastructure/frontend-testing-plan.md` and
`devdocs/proposals/infrastructure/test-data-strategy.md`.

## CLI Commands

```bash
fmriflow serve                            # Start server (default port 8421)
fmriflow serve --port 9000                # Custom port
fmriflow serve --host 0.0.0.0             # Expose on network
fmriflow serve --results-dir ./results    # Where to find run summaries
fmriflow serve --configs-dir ./experiments  # Where to find experiment YAMLs
fmriflow serve --plugins-dir ~/.fmriflow/plugins  # User plugins directory
fmriflow serve --no-open                  # Don't auto-open browser

fmriflow compose experiment.yaml          # Open a config in the composer
```

## Views

- **Plugins** — Browse all registered plugins organized by stage. Search, view parameters and docs.
- **Composer** — Build a pipeline config visually. Select plugins, configure parameters, add features/steps/analyzers. Live YAML preview. Validate and export.
- **Dashboard** — Browse experiment configs, launch runs, watch live stage-by-stage progress via WebSocket, and review past run history per config.
- **Runs** — Flat view of all past runs from `run_summary.json` files. View stage timelines, results, and artifacts.
- **Editor** — Write custom plugins in the browser with Monaco editor. Python syntax highlighting, live validation, and hot registration into the pipeline.

## Architecture

```
Browser (React SPA)  ←→  FastAPI Server  ←→  PluginRegistry / Pipeline
       :5173                 :8421              (same Python process)
```

The server introspects the live `PluginRegistry` — no separate metadata to maintain. Config validation uses the same `validate_config()` the CLI uses.

## Troubleshooting

**"Frontend dependencies not installed"** — You need `fastapi`, `uvicorn`, and `websockets` in your active Python environment:
```bash
pip install fastapi "uvicorn[standard]" websockets
```

**Vite SyntaxError / "Unexpected reserved word"** — Your Node.js is too old. Vite 6 requires Node 18+:
```bash
nvm install 22
```

**"No configs found" in Dashboard** — Make sure you pass `--configs-dir` pointing to where your YAML files live, or run `fmriflow serve` from the project root (defaults to `./experiments`).
