# Denizens Pipeline Frontend

Web-based UI for browsing plugins, composing pipeline configs, and managing runs.

## Quick Start

### 1. Install backend dependencies

```bash
pip install fastapi uvicorn[standard] websockets
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
```

### 3. Run (development mode)

Open two terminals:

**Terminal 1 — API server:**
```bash
denizens serve --port 8421
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
npm run build        # outputs to ../denizenspipeline/server/static/
cd ..
denizens serve       # serves API + frontend on http://127.0.0.1:8421
```

## CLI Commands

```bash
denizens serve                        # Start server (default port 8421)
denizens serve --port 9000            # Custom port
denizens serve --host 0.0.0.0         # Expose on network
denizens serve --results-dir ./results  # Where to find run summaries
denizens serve --no-open              # Don't auto-open browser

denizens compose experiment.yaml      # Open a config in the composer
```

## Views

- **Plugins** — Browse all 54 registered plugins organized by stage. Search, view parameters and docs.
- **Composer** — Build a pipeline config visually. Select plugins, configure parameters, add features/steps/analyzers. Live YAML preview. Validate and export.
- **Runs** — Browse past runs from `run_summary.json` files. View stage timelines, results, and artifacts. Launch new runs.

## Architecture

```
Browser (React SPA)  ←→  FastAPI Server  ←→  PluginRegistry / Pipeline
       :5173                 :8421              (same Python process)
```

The server introspects the live `PluginRegistry` — no separate metadata to maintain. Config validation uses the same `validate_config()` the CLI uses.
