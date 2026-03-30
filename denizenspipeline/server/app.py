"""FastAPI application factory for the Denizens Pipeline frontend."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from denizenspipeline.registry import PluginRegistry
from denizenspipeline.server.services.run_store import RunStore
from denizenspipeline.server.services.run_manager import RunManager
from denizenspipeline.server.services.plugin_loader import discover_user_plugins
from denizenspipeline.server.services.config_store import ConfigStore
from denizenspipeline.server.services.preproc_manager import PreprocManager
from denizenspipeline.server.services.convert_manager import ConvertManager

logger = logging.getLogger(__name__)


def create_app(
    results_dir: str = './results',
    plugins_dir: str | None = None,
    configs_dir: str = './experiments',
    derivatives_dir: str = './derivatives',
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Denizens Pipeline",
        version="0.1.0",
        description="Frontend API for the Denizens encoding model pipeline.",
    )

    # CORS — allow dev server on different port
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared state
    registry = PluginRegistry()
    registry.discover()

    # Load user plugins from ~/.denizens/plugins/ (or custom dir)
    pdir = Path(plugins_dir) if plugins_dir else None
    n_user = discover_user_plugins(pdir)
    if n_user:
        logger.info("Loaded %d user plugin(s)", n_user)

    run_store = RunStore(Path(results_dir))
    run_manager = RunManager()
    config_store = ConfigStore(Path(configs_dir))
    preproc_manager = PreprocManager(Path(derivatives_dir))
    convert_manager = ConvertManager()

    app.state.registry = registry
    app.state.run_store = run_store
    app.state.run_manager = run_manager
    app.state.config_store = config_store
    app.state.preproc_manager = preproc_manager
    app.state.convert_manager = convert_manager

    # API routes
    from denizenspipeline.server.routes.plugins import router as plugin_router
    from denizenspipeline.server.routes.config import router as config_router
    from denizenspipeline.server.routes.runs import router as run_router
    from denizenspipeline.server.routes.artifacts import router as artifact_router
    from denizenspipeline.server.routes.editor import router as editor_router
    from denizenspipeline.server.routes.configs import router as configs_router
    from denizenspipeline.server.routes.preproc import router as preproc_router
    from denizenspipeline.server.routes.convert import router as convert_router
    from denizenspipeline.server.routes.errors import router as errors_router
    from denizenspipeline.server.ws import router as ws_router

    # Editor routes must come before plugin_router so that
    # /plugins/user/{name} is matched before /plugins/{category}/{name}
    app.include_router(editor_router, prefix="/api")
    app.include_router(plugin_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(run_router, prefix="/api")
    app.include_router(artifact_router, prefix="/api")
    app.include_router(configs_router, prefix="/api")
    app.include_router(preproc_router, prefix="/api")
    app.include_router(convert_router, prefix="/api")
    app.include_router(errors_router, prefix="/api")
    app.include_router(ws_router)

    # Serve built frontend (if available)
    static_dir = Path(__file__).parent / 'static'
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True))

    return app
