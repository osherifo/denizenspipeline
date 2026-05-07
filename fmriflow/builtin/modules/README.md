# Built-in file-based addon modules

This directory is intentionally empty in the public package. The
real built-in Python modules (decorator-registered feature
extractors, reporters, models, etc.) live under
`fmriflow/modules/` and ship with the package via Python entry
points.

This directory exists for symmetry with
`$FMRIFLOW_HOME/addons/modules/`, where users drop their own
single-file plugins.
