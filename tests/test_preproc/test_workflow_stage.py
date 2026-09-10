"""The workflow-stage entry point launches pipelines and rejects the old config shape."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from tests.test_preproc.conftest import install_parked_nodes  # noqa: E402

nib = pytest.importorskip("nibabel")
nipype = pytest.importorskip("nipype")

from fmriflow.preproc.node_registry import NodeRegistry  # noqa: E402
from fmriflow.server.services.pipeline_store import PipelineStore  # noqa: E402
from fmriflow.server.services.preproc_run_manager import PreprocRunManager  # noqa: E402
from fmriflow.server.services.run_registry import RunRegistry  # noqa: E402
from fmriflow.server.services.workflow_config_store import VALID_STAGES  # noqa: E402
from fmriflow.preproc.nodes._parked import PARKED_DIR  # noqa: E402


def test_post_preproc_is_not_a_workflow_stage():
    assert "post_preproc" not in VALID_STAGES
    assert "preproc" in VALID_STAGES


def test_stage_config_with_inline_pipeline_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path / "home"))
    install_parked_nodes(tmp_path / "home")
    mgr = PreprocRunManager(run_registry=RunRegistry(root=tmp_path / "runs"),
                            pipeline_store=PipelineStore(tmp_path / "cfg"),
                            node_registry=NodeRegistry(user_dirs=[PARKED_DIR]).discover())
    src = tmp_path / "in.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 2), dtype="float32"), np.eye(4)), src)
    cfg = tmp_path / "stage.yaml"
    cfg.write_text(f"""preproc:
  subject: '01'
  output_dir: {tmp_path / 'out'}
  pipeline:
    name: inline
    nodes:
      - id: ident
        type: identity
        data: {{literal_inputs: {{in_file: {src}}}}}
    manifest: {{backend_node: ident}}
""")
    run_id = mgr.start_run_from_config_file(str(cfg))
    for _ in range(120):
        s = mgr.get_run(run_id)
        if s["status"] != "running":
            break
        time.sleep(0.5)
    assert s["status"] == "done", s
    assert Path(s["manifest_path"]).is_file()
    assert s["config_path"] == str(cfg.resolve())
