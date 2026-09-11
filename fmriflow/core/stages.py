"""Canonical stage names.

Single source of truth for code that lists or orders stages: the subject
orchestrator, the run-graph builder, the module/stage API routes, the CLI
and the intermediates writer. Group and study orchestrators keep their own
plumbing stage lists (``group_collect``, ``groups_fanout``, ...); only the
stages that hold user-pluggable modules are listed here.
"""

from __future__ import annotations

SUBJECT_STAGES: tuple[str, ...] = (
    'stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report',
)

STAGE_LABELS: dict[str, str] = {
    'stimuli': 'Stimuli',
    'responses': 'Responses',
    'features': 'Features',
    'prepare': 'Prepare',
    'model': 'Model',
    'analyze': 'Analyze',
    'report': 'Report',
    'group_analyze': 'Group analyze',
    'group_report': 'Group report',
    'study_analyze': 'Study analyze',
    'study_report': 'Study report',
}

# Stages whose output the intermediates writer can dump (the ones that
# produce a single typed value).
SAVEABLE_STAGES: tuple[str, ...] = SUBJECT_STAGES[:5]

GROUP_MODULE_STAGES: tuple[str, ...] = ('group_analyze', 'group_report')
STUDY_MODULE_STAGES: tuple[str, ...] = ('study_analyze', 'study_report')

# stage -> module registry categories that plug into it
STAGE_MODULE_CATEGORIES: dict[str, list[str]] = {
    'stimuli': ['stimulus_loaders'],
    'responses': ['response_loaders', 'response_readers'],
    'features': ['feature_extractors', 'feature_sources'],
    'prepare': ['preparers', 'preparation_steps'],
    'model': ['models'],
    'analyze': ['analyzers'],
    'report': ['reporters'],
    'group_analyze': ['group_analyzers'],
    'group_report': ['group_reporters'],
    'study_analyze': ['study_analyzers'],
    'study_report': ['study_reporters'],
}
