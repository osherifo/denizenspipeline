"""Importing a nipype pipeline .py as a composite node."""

from __future__ import annotations

import textwrap

import pytest

nipype = pytest.importorskip("nipype")

from fmriflow.preproc.importer import import_pipeline_file, inspect_pipeline_file  # noqa: E402
from fmriflow.preproc.node_registry import NodeRegistry  # noqa: E402

BUILD_FN = '''
    from nipype import Node, Workflow
    from nipype.interfaces.utility import IdentityInterface

    def build(config):
        wf = Workflow(name="mine")
        i = Node(IdentityInterface(fields=["t1w"]), name="inputnode")
        o = Node(IdentityInterface(fields=["cleaned"]), name="outputnode")
        wf.connect(i, "t1w", o, "cleaned")
        return wf
'''


def test_build_function_file_becomes_a_composite_node(tmp_path):
    src = tmp_path / "my_clean.py"
    src.write_text(textwrap.dedent(BUILD_FN))
    spec = inspect_pipeline_file(src)
    assert spec.shape == "build_function" and spec.inputs == ["t1w"] and spec.outputs == ["cleaned"]

    dest = tmp_path / "nodes"
    node_file, spec = import_pipeline_file(src, dest_dir=dest)
    assert node_file == dest / "my_clean.py"
    assert (dest / "_my_clean_source.py").exists()

    reg = NodeRegistry(include_parked=True, user_dirs=[dest]).discover()
    assert reg.kind("my_clean") == "composite" and reg.source("my_clean") == "user"
    ins, outs = reg.ports("my_clean")
    assert set(ins) == {"t1w"} and set(outs) == {"cleaned"}

    from fmriflow.preproc.nipype_adapters import build_composite
    wf = build_composite(reg.cls("my_clean"), object())
    assert wf.name == "mine"


def test_registered_class_file_is_copied_verbatim(tmp_path):
    src = tmp_path / "already.py"
    src.write_text(textwrap.dedent('''
        from fmriflow.preproc.node_registry import preproc_node

        @preproc_node("already_node", kind="composite")
        class Already:
            INPUTS = ["a"]; OUTPUTS = ["b"]
            def build(self, config): return None
    '''))
    spec = inspect_pipeline_file(src)
    assert spec.shape == "registered" and spec.node_name == "already_node"
    node_file, _ = import_pipeline_file(src, dest_dir=tmp_path / "nodes")
    assert node_file.read_text() == src.read_text()


def test_workflow_object_file(tmp_path):
    src = tmp_path / "wf_obj.py"
    src.write_text(textwrap.dedent('''
        from nipype import Node, Workflow
        from nipype.interfaces.utility import IdentityInterface
        WF = Workflow(name="obj")
        WF.add_nodes([Node(IdentityInterface(fields=["x"]), name="inputnode")])
    '''))
    spec = inspect_pipeline_file(src, node_name="objnode")
    assert spec.shape == "workflow_object" and spec.symbol == "WF" and spec.inputs == ["x"]


def test_unrecognised_file_is_rejected(tmp_path):
    src = tmp_path / "nothing.py"
    src.write_text("x = 1\n")
    with pytest.raises(ValueError, match="no registered node class"):
        inspect_pipeline_file(src)
