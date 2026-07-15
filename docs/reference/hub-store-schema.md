# Hub store schema

An **artifact-hub store** is a git repository laid out to a fixed contract so
fMRIflow knows exactly what to **pull** and where to **push**. This page is the
formal spec; the [Artifact Hub guide](../guide/artifact-hub.md) is the how-to.

The machine-readable JSON Schema ships in the package at
`fmriflow/hub/hub.schema.json`.

## Repository layout

```
<store repo>/
├── hub.json                 ← the manifest: the index fMRIflow reads
├── .gitattributes           ← LFS rule for kinds/feature_array/**
├── README.md                ← (auto-generated) describes the store
└── kinds/
    ├── error/0026_....yaml
    ├── module/....py
    ├── analysis_config/....yaml
    ├── workflow_config/....yaml
    ├── stack_preset/....yaml
    ├── heuristic/....py (+ ....yaml sidecar)
    ├── transform/....py
    ├── workflow/....py
    └── feature_array/....npz         ← git-LFS tracked
```

Artifact files live under **`kinds/<kind>/<name>.<ext>`**. `README.md` and
`.gitattributes` are written automatically on the first publish (see
[Self-documenting stores](#self-documenting-stores)).

## How pull and push use it

- **Pull** — `sync` clones the repo and reads **`hub.json`**. The catalog and
  install operate entirely from the manifest's `files` lists; fMRIflow does
  **not** scan the tree to discover artifacts. A repo with no `hub.json` (e.g. a
  brand-new empty repo) simply has an empty catalog.
- **Push** — `publish` copies your file into `kinds/<kind>/<name>`, regenerates
  that artifact's entry in `hub.json` (recomputing `sha256` + `size`), commits,
  and pushes. The first publish to an empty repo initialises it on the base
  branch.

So **`hub.json` is the single source of truth** for what a store contains.

## `hub.json`

```json
{
  "schema": 1,
  "artifacts": [
    {
      "kind": "error",
      "name": "0026_fmriprep_no_t1w",
      "files": ["kinds/error/0026_fmriprep_no_t1w.yaml"],
      "sha256": "<hex>",
      "size": 1234,
      "version": "1",
      "description": "fMRIPrep aborts when a subject has no T1w",
      "author": "you@lab",
      "tags": ["fmriprep"],
      "lfs": false,
      "metadata": {}
    }
  ]
}
```

### Top level

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema` | integer | ✅ | Manifest version. Current: **1**. |
| `artifacts` | array | ✅ | One entry per artifact. |

### Artifact entry

| Field | Type | Required | Notes |
|---|---|---|---|
| `kind` | string (enum) | ✅ | One of the [artifact kinds](#artifact-kinds). Sets the local install destination. |
| `name` | string | ✅ | The identifier fMRIflow shows for that kind (config filename, module name, error `id`, heuristic name, …). Unique within a kind. |
| `files` | string[] | ✅ | Repo-relative paths under `kinds/<kind>/` (plus sidecars). Non-empty. |
| `sha256` | string | ✅ | Combined content hash. **Verified on install — a mismatch is rejected (fail-closed).** |
| `size` | integer | — | Total bytes (informational). |
| `version` | string | — | Defaults to `"1"`. |
| `description` | string | — | Shown in the catalog. |
| `author` | string | — | |
| `tags` | string[] | — | |
| `lfs` | boolean | — | `true` when git-LFS-tracked (feature arrays). |
| `metadata` | object | — | Kind-specific extras. **`module` entries MUST set `metadata.category`** (the plugin category it installs into). |

## Artifact kinds

| `kind` | File(s) | Installs to (local user tier) |
|---|---|---|
| `error` | `<id>.yaml` | `$FMRIFLOW_ERRORS/` |
| `module` | `<name>.py` (+ `metadata.category`) | `$FMRIFLOW_HOME/addons/modules/` (hot-registered) |
| `analysis_config` | `<filename>.yaml` | `$FMRIFLOW_HOME/configs/analysis/` |
| `workflow_config` | `<filename>.yaml` | `$FMRIFLOW_HOME/configs/workflows/` |
| `stack_preset` | `<name>.yaml` | `$FMRIFLOW_HOME/addons/pipelines/` |
| `heuristic` | `<name>.py` + `<name>.yaml` | `$FMRIFLOW_HOME/addons/heuristics/` |
| `transform` | `<name>.py` | `$FMRIFLOW_HOME/addons/transforms/` (rescanned) |
| `workflow` | `<name>.py` | `$FMRIFLOW_HOME/addons/workflows/` (rescanned) |
| `feature_array` | `<name>.npz` / `.hdf5` (LFS) | `$FMRIFLOW_DATA/hub_features/<name>/` |

## Validation

fMRIflow validates a synced store against this schema. `sync` returns any
problems as `warnings`, and `GET /api/hub/sources/{id}/validate` returns the full
list. Checks: supported `schema`, known `kind`, unique `kind/name`, a non-empty
`files` list whose entries are **repo-relative and exist on disk** (absolute
paths and `..` traversal are rejected — a hub install never reads or writes
outside the clone), a present `sha256`, and `metadata.category` on `module`
entries. A non-empty repo missing `hub.json` is flagged too (only a
commit-less/empty repo is exempt).

## Self-documenting stores

On the first publish to an empty repo, fMRIflow writes:

- **`.gitattributes`** — `kinds/feature_array/** filter=lfs diff=lfs merge=lfs -text`
  so binary feature arrays are LFS-tracked automatically.
- **`README.md`** — a copy of this contract, so anyone browsing the repo (or a
  maintainer reviewing a PR) sees the schema without leaving the store.

## Compatibility

`schema` is an integer. A store with a `schema` this build doesn't support is
flagged by validation and its artifacts are not offered for install. Bump the
version only for breaking layout/field changes.
