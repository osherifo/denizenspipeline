"""Built-in nipype bootstrap workflows.

Each module in this package registers one workflow via
``@register_preproc_workflow``. The WorkflowRegistry imports every
module here on ``discover()``; the decorators fire and the
workflows become available to the stack runner.

To add a new built-in workflow: drop a ``.py`` file here with a
class decorated by ``@register_preproc_workflow("<name>")``.
"""
