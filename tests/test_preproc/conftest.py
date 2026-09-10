"""Shared preproc test fixtures."""

from __future__ import annotations

import pytest


_FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def fixture_pipeline(name: str):
    """A test-only pipeline YAML under tests/test_preproc/fixtures/."""
    from fmriflow.preproc.graph import Pipeline
    return Pipeline.from_yaml((_FIXTURES / f"{name}.yaml").read_text())


@pytest.fixture
def sample_pipeline():
    return fixture_pipeline


def install_parked_nodes(home) -> None:
    """Copy the parked built-in nodes into ``<home>/addons/nodes/`` so a detached
    run (a child process with its own registry) can use ``identity`` & co."""
    import shutil
    from fmriflow.preproc.nodes._parked import PARKED_DIR
    dst = __import__("pathlib").Path(home) / "addons" / "nodes"
    dst.mkdir(parents=True, exist_ok=True)
    for f in PARKED_DIR.glob("*.py"):
        if not f.name.startswith("_"):
            shutil.copy(f, dst / f.name)

