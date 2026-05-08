# `fmriflow/builtin/` — bundled built-ins

This directory ships **inside the package** and contains the
general content fmriflow provides out of the box.

## Layout

| Subdir | Purpose |
|---|---|
| `heuristics/` | Example heudiconv heuristics (currently empty; users supply their own) |
| `workflows/` | Default post-preproc workflow templates (currently empty) |
| `modules/` | Bundled file-based addon modules (currently empty; built-in Python modules live in `fmriflow/modules/`) |
| `text/` | Text catalogues — `english1000.{npz,txt}` and friends |
| `subjects.example.json` | Schema example for users to copy as `$FMRIFLOW_HOME/subjects.json` |

## How overrides work

The runtime resolves named addons in two tiers:

1. `$FMRIFLOW_HOME/addons/<kind>/<name>` — the user's tier
2. `fmriflow/builtin/<kind>/<name>` — this directory

User wins. Drop a same-named file into your addons tree and it
shadows the bundled built-in. See
`fmriflow/core/paths.py:find_in_tiers` for the resolver.

## Distributing built-ins to a lab

The fmriflow package itself stays minimal. Labs that want shared
defaults across machines pick whichever fits:

- **Fork the package** and ship extra files in
  `fmriflow/builtin/`. Lab members `pip install <fork>` instead
  of upstream.
- **Distribute an addons git repo.** Lab admin maintains
  `fmriflow-<lab>-addons`; members `git clone` it into
  `$FMRIFLOW_HOME/addons/`.
- **NFS-symlink the addons directory** to a read-only share.

All three sit in the user tier as far as the runtime is concerned.
