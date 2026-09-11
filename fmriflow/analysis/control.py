"""Control nodes: fan-out over subjects and groups.

They are not modules. A group or study run executes them itself (see
:mod:`fmriflow.analysis.scope_runners`); the catalog lists them so graphs can
name them, validate their ports and show them in a builder.

- ``control:map_subjects`` runs the subject analysis once per subject (a stage
  config template plus per-subject overrides) and yields the group.
- ``control:subject_pass`` re-runs each subject's analyze and report stages
  with values that group analyzers bind into subjects.
- ``control:group`` runs one group config inside a study under a label.
- ``control:study_groups`` collects a study's groups for study modules.
"""

from __future__ import annotations

from typing import Any, ClassVar

from fmriflow.analysis.adapters import NotRunnableYet


class _ControlNode:
    NODE_TYPE: ClassVar[str] = ""
    STAGE: ClassVar[str] = ""
    SCOPE: ClassVar[str] = ""
    PARAM_SCHEMA: ClassVar[dict] = {}
    INPUTS: ClassVar[dict] = {}
    OUTPUTS: ClassVar[dict] = {}

    def run(self, inputs: dict, params: dict, env: Any) -> dict:
        raise NotRunnableYet(f"{self.NODE_TYPE} runs as part of a {self.SCOPE} run, not inside a subject graph")


class MapSubjects(_ControlNode):
    """Run the subject analysis once per subject and collect the runs into a group."""

    NODE_TYPE = "control:map_subjects"
    STAGE = "subject_fanout"
    SCOPE = "group"
    PARAM_SCHEMA = {
        "subjects": {"type": "list[string]", "required": True, "description": "Subject ids"},
        "body": {"type": "string",
                 "description": "Subject graph run for each subject: a graph file, a saved graph or a template name"},
        "inputs": {"type": "dict",
                   "description": "Values for the body's inputs for every subject; {subject} becomes the subject id"},
        "subject_inputs": {"type": "dict", "description": "Per-subject input values: {subject: {input: value}}"},
        "subject_template": {"type": "dict", "description": "Stage config shared by every subject (instead of a body)"},
        "subject_overrides": {"type": "dict", "description": "Per-subject stage config, deep-merged over the template"},
        "max_workers": {"type": "int", "default": 4, "description": "Subjects that run at the same time"},
    }
    OUTPUTS = {"group": {"type": "GroupRun"}}

    @staticmethod
    def validate_params(params: dict) -> list[str]:
        errors = []
        subjects = params.get("subjects")
        if not isinstance(subjects, list) or not subjects:
            errors.append("'subjects' must be a non-empty list of subject ids")
        if bool(params.get("body")) == bool(params.get("subject_template")):
            errors.append("give either 'body' (a subject graph) or 'subject_template' (a stage config)")
        return errors


class SubjectPass(_ControlNode):
    """Re-run each subject's analyze and report stages with values bound by group analyzers."""

    NODE_TYPE = "control:subject_pass"
    STAGE = "subject_second_pass"
    SCOPE = "group"
    PARAM_SCHEMA = {
        "mode": {"type": "string", "default": "legacy", "enum": ["legacy", "minimal"],
                 "description": "legacy re-runs every analyzer and reporter; minimal only modules marked binding_consumer"},
    }
    INPUTS = {
        "group": {"type": "GroupRun", "required": True},
        "bindings": {"type": "Context", "multiple": True, "required": True,
                     "description": "Values from group analyzers, bound as external.<name>"},
    }
    OUTPUTS = {"group": {"type": "GroupRun"}}


class RunGroup(_ControlNode):
    """Run one group config inside a study, under a study-scope label."""

    NODE_TYPE = "control:group"
    STAGE = "groups_fanout"
    SCOPE = "study"
    PARAM_SCHEMA = {
        "name": {"type": "string", "required": True, "description": "Study-scope label"},
        "config": {"type": "path", "required": True, "description": "Group config YAML"},
    }
    OUTPUTS = {"group": {"type": "GroupRun"}}


class StudyGroups(_ControlNode):
    """Collect the study's groups, in connection order, for study analyzers and reporters."""

    NODE_TYPE = "control:study_groups"
    STAGE = "groups_fanout"
    SCOPE = "study"
    INPUTS = {"groups": {"type": "GroupRun", "multiple": True, "required": True}}
    OUTPUTS = {"study": {"type": "StudyRun"}}


CONTROL_NODES: tuple[type, ...] = (MapSubjects, SubjectPass, RunGroup, StudyGroups)
CONTROL_SCOPES: dict[str, str] = {cls.NODE_TYPE: cls.SCOPE for cls in CONTROL_NODES}
