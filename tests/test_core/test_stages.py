"""One stage list shared by orchestrator, run graph, routes, CLI and intermediates."""

from fmriflow import intermediates
from fmriflow.core import stages
from fmriflow.orchestrator import ALL_STAGES
from fmriflow.registry import ModuleRegistry
from fmriflow.server.routes import modules as module_routes
from fmriflow.server.services import run_graph


def test_subject_stage_consumers_share_the_list():
    assert ALL_STAGES == list(stages.SUBJECT_STAGES)
    assert [name for name, _ in run_graph.SUBJECT_STAGES] == list(stages.SUBJECT_STAGES)
    assert intermediates.SAVEABLE_STAGES == stages.SUBJECT_STAGES[:5]


def test_routes_use_the_shared_category_map():
    assert module_routes.STAGE_MODULE_CATEGORIES is stages.STAGE_MODULE_CATEGORIES
    assert module_routes.GROUP_STAGES == list(stages.GROUP_MODULE_STAGES)
    assert module_routes.STUDY_STAGES == list(stages.STUDY_MODULE_STAGES)


def test_every_registry_category_belongs_to_a_stage():
    reg = ModuleRegistry()
    reg.discover()
    mapped = {c for cats in stages.STAGE_MODULE_CATEGORIES.values() for c in cats}
    categories = set(reg.list_modules()) - {"qa_reporters"}
    assert categories <= mapped, sorted(categories - mapped)


def test_every_stage_has_a_label():
    for name in (*stages.SUBJECT_STAGES, *stages.GROUP_MODULE_STAGES, *stages.STUDY_MODULE_STAGES):
        assert stages.STAGE_LABELS[name]
