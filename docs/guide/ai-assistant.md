# AI Assistant (experimental)

fMRIflow ships an optional, in-app **advisory AI assistant** powered by Claude.
It reads your configs, modules, run results, and error knowledge base to answer
questions and suggest changes — but it is **advisory only**: it never edits files,
writes configs, or runs anything. You copy what's useful.

The feature is **off by default** and fully decoupled: nothing about it loads
unless you turn it on.

## Enabling it

1. **Install the optional dependency:**

    ```bash
    pip install -e '.[agent]'
    ```

2. **Provide a Claude API key.** The key is read from the `ANTHROPIC_API_KEY`
   environment variable first; if that isn't set, from a key you enter in the
   Settings page. (When stored via Settings it lives in
   `~/.config/fmriflow/settings.json` in plaintext — fine on a single-user
   machine; prefer the env var on shared hosts.)

3. **Turn it on** in **Settings → AI assistant (experimental)**: tick *Enable the
   assistant*, optionally set the model (default `claude-opus-4-8`), and save.
   The change applies live — no restart.

A floating **✦ Ask AI** button then appears at the bottom-right of every page.

## The four modes

The assistant picks a mode automatically from the page you're on (you can also
switch it from the panel header):

| Mode | Active on | What it helps with |
|---|---|---|
| **Pipeline builder** | Analysis Composer | Designing a valid analysis config — which module fits which stage, what each parameter means, and the YAML to paste. Sees your current composer YAML and validation errors. |
| **Coding assistant** | Module Editor | Authoring a new plugin module — conventions, `PARAM_SCHEMA`, and an existing module read as a template. Sees your current editor buffer. |
| **Error-KB helper** | Errors page | Finding the known error that matches your problem and explaining its cause and fix; connecting a failed run's triage capture to KB entries. |
| **General helper** | Everywhere else | Questions about the pipeline, modules, configs, and results. |

Behind the scenes the assistant calls **read-only tools** to fetch real context
(your configs, module metadata and source, run summaries and metrics, and the
error knowledge base). It cannot call any tool that writes.

## Privacy note

When enabled, your questions plus the context the assistant reads (config YAML,
module code, run metrics, error entries) are sent to the Anthropic API to
generate a reply. Don't enable it if that isn't acceptable for your data. Turning
the toggle off (or uninstalling the `agent` extra) removes the feature entirely.
