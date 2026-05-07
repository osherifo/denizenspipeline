"""Built-in post-fmriprep nipype-style nodes.

Each node defines:
  - ``name`` (registered via ``@nipype_node("name")``)
  - ``INPUTS``: list of input handle names (e.g. ``["in_file"]``)
  - ``OUTPUTS``: list of output handle names
  - ``PARAM_SCHEMA``: dict for the UI/CLI form
  - ``run(inputs, out_dir, params) -> dict[str, Path]``: produce outputs from inputs

v1 is implemented in pure Python (nibabel + scipy) so it works without
nipype installed. A future v2 may swap to nipype ``Workflow`` execution
when the user opts into the optional ``[nipype]`` extra.
"""
