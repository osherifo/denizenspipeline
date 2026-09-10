"""Parked built-in nodes.

Nodes that shipped with the preprocessing redesign but that no pipeline uses.
They are kept out of the node library to keep it small; the code is intact
and each still passes its tests. The registry skips this package (leading
underscore); to load them, point a registry at :data:`PARKED_DIR`::

    NodeRegistry(user_dirs=[PARKED_DIR]).discover()

or copy a file into ``$FMRIFLOW_HOME/addons/nodes/`` to use it in a pipeline.

Parked here: ``bids_app`` (any BIDS App as a container app), ``custom_shell``
(a shell command with a file pattern), ``identity`` (pass-through, used by the
tests), ``mask_apply``, ``reference_fsl_ants`` (a hand-written FSL/ANTs nipype
workflow as a composite node) and ``select`` (pick one item of a list, the way
to iterate a composite's output).
"""

from pathlib import Path

PARKED_DIR = Path(__file__).parent
