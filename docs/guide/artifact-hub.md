# Artifact Hub

The **Artifact Hub** lets you browse and share fMRIflow artifacts — error-KB
entries, plugin modules, analysis configs, pipeline/workflow configs,
preproc-stack presets, heudiconv heuristics, and precomputed feature arrays —
across three tiers:

- **local** — what's already on this machine (your `$FMRIFLOW_HOME` user tier +
  the shipped builtins).
- **within-lab** — a git repository your lab **self-hosts** (Gitea / GitLab /
  bare git).
- **cross-lab / community** — a **curated** public git repository, where
  curation happens through pull-request review.

Open it from the **Hub** tab (under *Reference*).

## How it works

Each source is a **git repository** with a `hub.json` manifest at its root
listing every artifact and its `sha256` integrity hash. fMRIflow clones the
repo into a local cache (`$FMRIFLOW_HOME/stores/hub/`), reads the manifest, and
shows the artifacts merged with a **tier badge** and an **installed** flag.

**Installing copies an artifact into your local tier** — the pipeline then
resolves it exactly like a file you authored. The hub is an install/browse
layer, *not* a runtime dependency: nothing in the pipeline hot path changes, and
removing a source never breaks an already-installed artifact. Large binary
feature arrays are carried with **git-LFS**.

Prerequisites: `git` (and `git-lfs` for sources that ship binary feature
arrays) must be installed. The Hub page shows a banner if they're missing.

## Adding a source

On the Hub page, **+ Add source**:

- **Name** — a label (e.g. "My Lab").
- **Git URL** — `https://…` for a hosted repo, or a `file://` path / local path
  for a repo on a mounted share.
- **Tier** — *Within-lab* or *Community*.
- **Branch** — defaults to `main`. A brand-new **empty** repo has no branches
  yet — leave it `main`; syncing an empty repo simply shows an empty catalog,
  and your **first publish creates the branch**. For an existing repo, use the
  branch that holds the artifacts (the picker lists what's available).
- **Access token** *(optional)* — needed only for a **private** repo or to
  **publish**. Use a **Personal Access Token**: a classic PAT with the `repo`
  scope, or a fine-grained PAT scoped to the repo with **Contents: Read** (add
  **Read and write** to publish). **Do not** paste a GitHub-CLI token
  (`gho_…` from `gh auth token`) — those are short-lived session tokens that get
  rotated and will fail to authenticate.

Sources you add are **saved** (in `~/.config/fmriflow/settings.json`) — you
enter them once. Then **Sync** to clone/pull and populate the catalog, filter by
artifact kind, and **Install** what you want.

### Where the token is stored

- If your OS has a **keyring** (GNOME Keyring/libsecret, macOS Keychain, Windows
  Credential Manager — the same store `gh` uses), the token is saved there
  **securely**; the source row shows a `🔒 keyring` chip. Install the optional
  dependency with `pip install -e '.[hub]'` to enable it.
- Otherwise it falls back to `~/.config/fmriflow/settings.json` in **plaintext**
  (shown as `⚠️ plaintext`). On a shared or headless host, prefer setting
  `FMRIFLOW_HUB_TOKEN_<SOURCE_ID>` in the environment instead (shown as `🔑 env`)
  so no secret is written to disk.

The token is never sent anywhere but the git remote, and is redacted from any
error output.

## Publishing (contributing)

**Publish local** on an artifact stages your local version into the source's
clone, updates the manifest, commits, and pushes to a branch. For the community
tier you then open a **pull request** (the button surfaces a compare/PR link) so
a maintainer can review — that review *is* the curation.

## Source-repo layout

A store repo follows a fixed contract — see the
[Hub store schema](../reference/hub-store-schema.md) for the full spec. In short:

```
hub.json                 # the manifest (catalog + integrity hashes)
kinds/
  error/0026_....yaml
  analysis_config/....yaml
  module/....py
  heuristic/....py (+ .yaml sidecar)
  feature_array/....npz   # git-LFS tracked
```

`hub.json`:

```json
{ "schema": 1, "artifacts": [
  { "kind": "error", "name": "0026_fmriprep_no_t1w",
    "files": ["kinds/error/0026_fmriprep_no_t1w.yaml"],
    "sha256": "…", "description": "…", "tags": ["fmriprep"] }
]}
```

Contributing an artifact is: drop the file(s) under `kinds/<kind>/`, add a
manifest entry (fMRIflow's **Publish local** does this for you), commit, push.

## Privacy note

Syncing a source clones its git repo to your machine. Publishing pushes your
local artifact to that repo. Use tiers and tokens you trust; don't publish
artifacts that embed subject-identifiable data.
