"""Built-in QA reporters per pipeline stage.

QA reporters mirror the existing Reporter / Analyzer pattern but consume
a single stage's dataclass and write diagnostic plots to disk. See
:func:`fmriflow.context.PipelineContext.run_stage_qa` for invocation and
``devdocs/proposals/data-processing/stage-qa-viz.md`` for the design.

This package is imported lazily — pulling matplotlib is non-trivial, so
nothing at import time should touch it. Each plugin module imports its
own matplotlib lazily inside ``report()``.
"""
