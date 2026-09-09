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
