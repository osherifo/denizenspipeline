"""Status vocabulary of the run-graph builder.

A stage that hasn't started is a *known* state and must not be reported as
``unknown`` — that word is reserved for a record that exists but carries no
usable status. Conflating the two made every stage of a never-run config, and
every stage after a failure, read as "unknown" in the graph viewer.
"""

from fmriflow.registry import ModuleRegistry
from fmriflow.server.services.run_graph import (
    _stage_status,
    _subject_overall_status,
    build_subject_graph,
)


def _cfg():
    return {
        'experiment': 'exp',
        'subject': 'sub01',
        'stimulus': {'loader': 'some_stimulus_loader'},
        'response': {'loader': 'some_response_loader'},
        'features': [{'name': 'f1', 'source': 'compute', 'extractor': 'some_extractor'}],
        'model': {'type': 'some_model'},
    }


def _stage_map(graph):
    return {n.label: n.status for n in graph.nodes if n.kind == 'stage'}


def test_never_run_config_is_pending_not_unknown():
    graph = build_subject_graph(_cfg(), [], ModuleRegistry())
    statuses = _stage_map(graph)

    assert statuses, "expected stage nodes"
    assert set(statuses.values()) == {'pending'}
    assert 'unknown' not in statuses.values()


def test_stages_after_a_failure_are_pending():
    records = [
        {'name': 'stimuli', 'status': 'ok', 'elapsed_s': 1.0},
        {'name': 'responses', 'status': 'ok', 'elapsed_s': 2.0},
        {'name': 'features', 'status': 'failed', 'detail': 'boom'},
    ]
    statuses = _stage_map(build_subject_graph(_cfg(), records, ModuleRegistry()))

    assert statuses['Stimuli'] == 'ok'
    assert statuses['Features'] == 'failed'
    # Everything downstream never started.
    for later in ('Prepare', 'Model', 'Analyze', 'Report'):
        assert statuses[later] == 'pending', later


def test_unknown_is_kept_for_a_record_with_no_status():
    """The one case that is genuinely indeterminate."""
    assert _stage_status([{'name': 'model'}], 'model')[0] == 'unknown'


def test_plugin_nodes_inherit_the_pending_stage_status():
    graph = build_subject_graph(_cfg(), [], ModuleRegistry())
    plugins = [n for n in graph.nodes if n.kind != 'stage']

    assert plugins, "expected plugin nodes under the stages"
    assert all(n.status == 'pending' for n in plugins)


def test_subject_with_nothing_recorded_is_pending():
    assert _subject_overall_status({'subject': 'sub01'}) == 'pending'


def test_subject_with_an_unrecognised_verdict_stays_unknown():
    assert _subject_overall_status({'subject': 'sub01', 'status': 'weird'}) == 'unknown'
