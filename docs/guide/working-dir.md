# Working directory: `$FMRIFLOW_HOME`

fmriflow keeps everything **the user owns** in one external
directory: `$FMRIFLOW_HOME`. The package itself ships only its
code and a small folder of bundled built-ins (`fmriflow/builtin/`).

The split mirrors the **package + addons** model — we provide the
main stuff, you (or your lab) drop addons that extend or override
it.

## Location

- **Default:** `~/projects/fmriflow/`
- **Override:** set `$FMRIFLOW_HOME` to any absolute path before
  starting fmriflow.

`fmriflow init` materialises the layout. It's idempotent — safe
to run on every machine, every checkout.

```bash
fmriflow init
fmriflow paths        # confirm what was resolved
```

## Layout

```
$FMRIFLOW_HOME/
├── addons/                 # your overrides + extensions
│   ├── heuristics/         # heudiconv heuristics
│   ├── workflows/          # post-preproc workflow templates
│   └── modules/            # custom Python plugins
├── configs/                # YAML configs
│   ├── convert/
│   ├── preproc/
│   ├── autoflatten/
│   └── workflows/
├── runs/                   # run registry (state.json + stdout.log per run)
├── stores/                 # named state stores
│   ├── structural_qc/
│   └── post_preproc_workflows/
├── secrets/
│   └── freesurfer-license.txt
├── subjects.json           # your subject metadata
└── data/
    ├── dicoms/<study>/<subject>/...
    ├── bids/<study>/...
    ├── derivatives/<study>/<pipeline>/...
    ├── work/<run_id>/      # fmriprep work_dirs
    └── results/<study>/<run_name>/
```

Everything is two levels deep at most. Names are nouns. There is
no third tier.

## Splitting `data/` onto a different disk

For workstations where MRI data lives on a RAID separate from your
configs, set:

```bash
export FMRIFLOW_DATA=/mnt/raid/fmriflow-data
```

`$FMRIFLOW_DATA` overrides the location of `data/` only. Configs,
addons, runs, and stores still live under `$FMRIFLOW_HOME`. The
default (`$FMRIFLOW_DATA` unset) is `$FMRIFLOW_HOME/data/`.

## Two-tier resolution

For content where you might want to shadow a built-in (heuristics,
workflow templates, modules), fmriflow resolves names in two
tiers:

| Tier | Location | Owner |
|---|---|---|
| **builtin** | `fmriflow/builtin/<kind>/<name>` | upstream maintainers |
| **user** | `$FMRIFLOW_HOME/addons/<kind>/<name>` | the user |

**user wins**. A heuristic named `siemens_default` looks first
under `$FMRIFLOW_HOME/addons/heuristics/siemens_default.py`, then
falls back to `fmriflow/builtin/heuristics/siemens_default.py`.

Override by filename — drop a same-named file into your addons
tree and it shadows the bundled built-in.

## Lab-wide defaults

The runtime has no separate "shared" tier. Labs that want to ship
defaults across machines pick whichever fits:

- **Fork the package.** Maintain `fmriflow-<lab>` with extra files
  in `fmriflow/builtin/`; lab members install the fork instead of
  upstream.
- **Distribute an addons git repo.** Lab admin maintains
  `fmriflow-<lab>-addons`; members `git clone` it into
  `$FMRIFLOW_HOME/addons/`. Versioned, lightweight.
- **NFS-symlink the addons directory** to a read-only share.

All three sit in the user tier.

## Migrating from older versions

If you have data under the legacy locations:

- `~/.fmriflow/runs/`, `~/.fmriflow/modules/`,
  `~/.fmriflow/heuristics/`, `~/.fmriflow/structural_qc/`,
  `~/.fmriflow/post_preproc_workflows/`
- `./experiments/<stage>/`
- `./results/`, `./derivatives/`

run:

```bash
fmriflow migrate --dry-run    # preview
fmriflow migrate              # actually copy
```

It copies (not moves) into the new layout, so the legacy
locations stay intact until you delete them yourself.

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `FMRIFLOW_HOME` | `~/projects/fmriflow` | The user's working directory (auto-created) |
| `FMRIFLOW_DATA` | `$FMRIFLOW_HOME/data` | Big-data subtree (errors out if set to a missing path) |
| `FMRIFLOW_HEURISTICS_DIR` | resolved | Legacy override; honoured if set |
| `FMRIFLOW_MODULES_DIR` | resolved | Legacy override; honoured if set |
| `FS_LICENSE` | `$FMRIFLOW_HOME/secrets/freesurfer-license.txt` | FreeSurfer license file |

`fmriflow paths` prints all resolved paths; the server logs them
on startup too.
