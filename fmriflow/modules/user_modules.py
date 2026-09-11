"""Discovery of user add-on analysis modules.

Add-on modules are plain ``*.py`` files in the user modules directory whose
decorators (``@reporter``, ``@study_analyzer``, ...) register classes in the
global module registries when the file is executed. Every process that runs
analysis modules (the web server *and* the CLI child processes it spawns)
must call :func:`discover_user_modules`, otherwise configs naming add-on
modules fail to resolve.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_modules_dir() -> Path:
    """Return the user modules directory, creating it if needed.

    Resolution order:
    1. ``$FMRIFLOW_MODULES_DIR`` (legacy env var, still honoured).
    2. ``$FMRIFLOW_HOME/addons/modules/`` (new home).
    3. Legacy ``~/.fmriflow/modules/`` if it exists with content
       and the new dir is still empty (migration grace).
    """
    custom = os.environ.get('FMRIFLOW_MODULES_DIR')
    if custom:
        d = Path(custom)
        d.mkdir(parents=True, exist_ok=True)
        return d
    from fmriflow.core import paths
    new = paths.addons_dir("modules")
    legacy = paths.legacy_modules_root()
    if legacy.is_dir() and any(legacy.iterdir()) and not any(new.iterdir()):
        return legacy
    return new


def discover_user_modules(modules_dir: Path | None = None) -> int:
    """Load all user modules from the modules directory.

    Returns the number of modules successfully loaded.
    """
    if modules_dir is None:
        modules_dir = get_modules_dir()

    if not modules_dir.is_dir():
        return 0

    loaded = 0
    for py_file in sorted(modules_dir.glob('*.py')):
        try:
            code = py_file.read_text()
            exec(compile(code, str(py_file), 'exec'))
            logger.info("Loaded user module: %s", py_file.stem)
            loaded += 1
        except Exception as e:
            logger.warning("Failed to load user module %s: %s", py_file.stem, e)

    return loaded
