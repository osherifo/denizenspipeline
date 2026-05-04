"""FastAPI application factory for the fMRIflow frontend."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from fmriflow.registry import ModuleRegistry
from fmriflow.server.services.run_store import RunStore
from fmriflow.server.services.run_manager import RunManager
from fmriflow.server.services.module_loader import discover_user_modules
from fmriflow.server.services.config_store import ConfigStore
from fmriflow.server.services.preproc_config_store import PreprocConfigStore
from fmriflow.server.services.preproc_manager import PreprocManager
from fmriflow.server.services.convert_manager import ConvertManager
from fmriflow.server.services.convert_config_store import ConvertConfigStore
from fmriflow.server.services.autoflatten_manager import AutoflattenManager
from fmriflow.server.services.autoflatten_config_store import AutoflattenConfigStore
from fmriflow.server.services.workflow_manager import WorkflowManager
from fmriflow.server.services.workflow_config_store import WorkflowConfigStore
from fmriflow.server.services.structural_qc_store import StructuralQCStore

logger = logging.getLogger(__name__)


def create_app(
    results_dir: str = './results',
    modules_dir: str | None = None,
    configs_dir: str = './experiments',
    preproc_configs_dir: str = './experiments/preproc',
    convert_configs_dir: str = './experiments/convert',
    autoflatten_configs_dir: str = './experiments/autoflatten',
    workflow_configs_dir: str = './experiments/workflows',
    derivatives_dir: str = './derivatives',
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="fMRIflow",
        version="0.1.0",
        description="Frontend API for the fMRIflow encoding model pipeline.",
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
    registry = ModuleRegistry()
    registry.discover()

    # Load user modules from ~/.fmriflow/modules/ (or custom dir)
    mdir = Path(modules_dir) if modules_dir else None
    n_user = discover_user_modules(mdir)
    if n_user:
        logger.info("Loaded %d user module(s)", n_user)

    run_store = RunStore(Path(results_dir))
    run_manager = RunManager()
    config_store = ConfigStore(Path(configs_dir))
    preproc_config_store = PreprocConfigStore(Path(preproc_configs_dir))
    preproc_manager = PreprocManager(Path(derivatives_dir))
    convert_manager = ConvertManager()
    convert_config_store = ConvertConfigStore(Path(convert_configs_dir))
    autoflatten_manager = AutoflattenManager()
    autoflatten_config_store = AutoflattenConfigStore(Path(autoflatten_configs_dir))
    workflow_config_store = WorkflowConfigStore(Path(workflow_configs_dir))
    workflow_manager = WorkflowManager()
    structural_qc_store = StructuralQCStore(
        Path.home() / ".fmriflow" / "structural_qc"
    )
    workflow_manager.bind_stage_managers(
        convert=convert_manager,
        preproc=preproc_manager,
        autoflatten=autoflatten_manager,
        analysis=run_manager,
    )

    app.state.registry = registry
    app.state.run_store = run_store
    app.state.run_manager = run_manager
    app.state.config_store = config_store
    app.state.preproc_config_store = preproc_config_store
    app.state.preproc_manager = preproc_manager
    app.state.convert_manager = convert_manager
    app.state.convert_config_store = convert_config_store
    app.state.autoflatten_manager = autoflatten_manager
    app.state.autoflatten_config_store = autoflatten_config_store
    app.state.workflow_config_store = workflow_config_store
    app.state.workflow_manager = workflow_manager
    app.state.structural_qc_store = structural_qc_store

    # API routes
    from fmriflow.server.routes.modules import router as module_router
    from fmriflow.server.routes.config import router as config_router
    from fmriflow.server.routes.runs import router as run_router
    from fmriflow.server.routes.artifacts import router as artifact_router
    from fmriflow.server.routes.editor import router as editor_router
    from fmriflow.server.routes.configs import router as configs_router
    from fmriflow.server.routes.preproc import router as preproc_router
    from fmriflow.server.routes.convert import router as convert_router
    from fmriflow.server.routes.errors import router as errors_router
    from fmriflow.server.routes.autoflatten import router as autoflatten_router
    from fmriflow.server.routes.workflows import router as workflows_router
    from fmriflow.server.routes.triage import router as triage_router
    from fmriflow.server.routes.structural_qc import router as structural_qc_router
    from fmriflow.server.ws import router as ws_router

    # Editor routes must come before module_router so that
    # /modules/user/{name} is matched before /modules/{category}/{name}
    app.include_router(editor_router, prefix="/api")
    app.include_router(module_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(run_router, prefix="/api")
    app.include_router(artifact_router, prefix="/api")
    app.include_router(configs_router, prefix="/api")
    app.include_router(preproc_router, prefix="/api")
    app.include_router(convert_router, prefix="/api")
    app.include_router(errors_router, prefix="/api")
    app.include_router(autoflatten_router, prefix="/api")
    app.include_router(workflows_router, prefix="/api")
    app.include_router(triage_router, prefix="/api")
    app.include_router(structural_qc_router, prefix="/api")
    app.include_router(ws_router)

    # Serve built frontend (if available)
    static_dir = Path(__file__).parent / 'static'
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True))

    return app
