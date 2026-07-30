"""Route-level guards for the flat-render endpoints.

`subject` arrives straight from a query string and is interpolated into a
filesystem path, so the traversal tests here are the load-bearing ones: a
containment check on the *resolved* directory cannot catch an escape,
because the escaped directory is what it would be measured against.
"""

import numpy as np
import pytest

from fmriflow.server.routes.autoflatten import _subject_surf_dir

fastapi = pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402


ESCAPES = [
    "../other",
    "../../../../etc",
    "sub-01/../../elsewhere",
    "/absolute",
    "..",
    ".",
    "",
    "sub\\win",
]


@pytest.mark.parametrize("subject", ESCAPES)
def test_rejects_subjects_that_are_not_one_component(tmp_path, subject):
    with pytest.raises(HTTPException) as excinfo:
        _subject_surf_dir(str(tmp_path), subject)

    assert excinfo.value.status_code == 400


def test_accepts_a_plain_subject_label(tmp_path):
    surf = tmp_path / "sub-01" / "surf"
    surf.mkdir(parents=True)

    resolved = _subject_surf_dir(str(tmp_path), "sub-01")

    assert resolved == surf.resolve()


def test_resolved_path_stays_inside_the_subjects_dir(tmp_path):
    """Whatever a caller passes, the result never leaves the root."""
    (tmp_path / "sub-01" / "surf").mkdir(parents=True)
    root = tmp_path.resolve()

    for subject in ("sub-01", "sub_02", "sub-01.bak"):
        assert _subject_surf_dir(str(tmp_path), subject).is_relative_to(root)


def test_validation_does_not_require_the_directory_to_exist(tmp_path):
    """Existence is each endpoint's call — render 404s, discovery returns empty."""
    resolved = _subject_surf_dir(str(tmp_path), "not-created-yet")

    assert not resolved.exists()
    assert resolved.is_relative_to(tmp_path.resolve())
