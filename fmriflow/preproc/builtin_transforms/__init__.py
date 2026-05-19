"""Built-in Stage-N transforms.

Each module in this package registers one transform via
``@register_transform``. The TransformRegistry imports every
module here on ``discover()``; the decorators fire and the
transforms become available to the stack runner.

To add a new built-in transform: drop a ``.py`` file here with a
class decorated by ``@register_transform("<name>")``. The class
must satisfy the ``Transform`` Protocol (INPUTS / OUTPUTS /
PARAM_SCHEMA / run).

A transform that's also useful inside the post-preproc DAG
builder can register twice — once with ``@register_transform``
here, once with ``@nipype_node`` in the modules tree — sharing
the same implementation class. The two registries are deliberately
independent so neither surface contaminates the other.
"""
