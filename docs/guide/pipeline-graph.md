# Pipeline Graph

A visual node-based editor for describing an end-to-end workflow: DICOM conversion → fmriprep → autoflatten → analysis (features, preparation, model, reporting).

Unlike the Composer (which is a form for a single experiment config), the Pipeline Graph captures structure — which outputs feed which inputs, where data forks, where steps run in parallel — and serializes it to a workflow YAML that can round-trip back to the graph.

## When to use

- **Composer**: analysis-only. Good for quick YAML edits and submitting runs.
- **Pipeline Graph**: end-to-end workflows involving conversion, preprocessing, flattening, and analysis in the same view. Good for exploring how stages connect and for subjects where you want to run everything from DICOMs to flatmaps.

Both views coexist — pick what fits the task.

## Opening the view

Sidebar → **Preprocessing → Pipeline Graph**, or go to `#graph` in the URL.

On first open, the "Full Pipeline" template loads automatically.

## Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Pipeline Graph  [workflow name]    [Load template▾] [Re-layout] [YAML] │
├─────────────────────────────────────────────────────────────────────────┤
│ Add node: [source] [convert] [preproc] [autoflatten] [response_loader] │
│           [features] [prepare] [model] [report]                         │
├─────────────────────────────────────────────────────┬───────────────────┤
│                                                     │                   │
│              Graph canvas                           │   Workflow YAML   │
│           (React Flow)                              │   (textarea,      │
│                                                     │    bidirectional) │
│           [MiniMap]  [Controls]                     │                   │
└─────────────────────────────────────────────────────┴───────────────────┘
```

## Node types

| Node | Color | Icon | Inputs | Outputs |
|------|-------|------|--------|---------|
| Source | gray | 📁 | — | DICOM |
| DICOM → BIDS | blue | 🔄 | DICOM | BIDS |
| Preproc (fmriprep) | green | ⚙️ | BIDS | Manifest, FreeSurfer |
| Autoflatten | teal | 🧠 | FreeSurfer | Surface |
| Response Loader | purple | 📥 | Manifest | Responses |
| Features | yellow | ✨ | — | Features |
| Prepare | orange | 🔧 | Responses, Features | Prepared |
| Model | red | 📊 | Prepared, Surface | Results |
| Report | pink | 📝 | Results | — |

Each node shows:

- An icon + label in the stage's color
- A status dot (gray pending, blue running, green done, red error)
- Two or three summary lines pulled from the node's config
- Typed handles for incoming/outgoing data

Click a node to open the detail panel (right-side slide-in) and edit its config. The summary lines update as you type.

## Connecting nodes

Drag from an output handle (bottom of a node) to an input handle (top of another). Connections are validated by data type — you can't connect a `DICOM` output to a `Responses` input. Invalid attempts are rejected silently.

Allowed connections (summary):

```
DICOM     → DICOM (source → convert)
BIDS      → BIDS (convert → preproc)
Manifest  → Manifest (preproc → response_loader)
FreeSurfer → FreeSurfer (preproc → autoflatten)
Surface   → Surface (autoflatten → model)
Responses → Responses (response_loader → prepare)
Features  → Features (features → prepare)
Prepared  → Prepared (prepare → model)
Results   → Results (model → report)
```

Delete an edge or node with `Backspace` or `Delete`.

## Templates

Pre-built starting points in the dropdown:

| Template | Nodes |
|----------|-------|
| **Full Pipeline** | source → convert → preproc → autoflatten + response_loader → features → prepare → model → report |
| **Analysis Only** | response_loader → features → prepare → model → report |
| **Preprocessing Only** | source → convert → preproc → autoflatten |

Loading a template replaces the current graph.

## The YAML panel

The right side is a live workflow YAML view. The graph and YAML sync bidirectionally:

- Any graph change (drag, add node, edit config, connect edges) regenerates the YAML
- Typing in the YAML debounces 800 ms, then re-parses back into the graph
- Blurring the textarea applies immediately
- Parse errors show below the editor; the graph stays intact

Use the "Hide YAML" button to collapse the panel for more canvas space.

### Serialization format

```yaml
workflow: my_reading_study

nodes:
  source:
    type: source
    config:
      path: /data/dicoms/sub01

  convert:
    type: convert
    config:
      heuristic: reading_paradigm
      bids_dir: /data/bids

  preproc:
    type: preproc
    config:
      mode: full
      output_spaces: [T1w, MNI152NLin2009cAsym:res-2]

  autoflatten:
    type: autoflatten
    config:
      backend: pyflatten

  response:
    type: response_loader
    config:
      loader: preproc

  features:
    type: features
    config:
      features: [english1000]

  prepare:
    type: prepare
    config:
      steps_str: trim → zscore → concat

  model:
    type: model
    config:
      type: bootstrap_ridge

  report:
    type: report
    config:
      formats: metrics, flatmap

edges:
  - { from: source,       out: dicom,       to: convert,     in: dicom       }
  - { from: convert,      out: bids,        to: preproc,     in: bids        }
  - { from: preproc,      out: freesurfer,  to: autoflatten, in: freesurfer  }
  - { from: preproc,      out: manifest,    to: response,    in: manifest    }
  - { from: autoflatten,  out: surface,     to: model,       in: surface     }
  - { from: response,     out: responses,   to: prepare,     in: responses   }
  - { from: features,     out: features,    to: prepare,     in: features    }
  - { from: prepare,      out: prepared,    to: model,       in: prepared    }
  - { from: model,        out: results,     to: report,      in: results     }
```

This format is deliberately graph-shaped (nodes + edges), not a flat experiment config. It preserves topology, which the stepper/form views can't. A workflow can be exported as this YAML, pasted into another session, and fully reconstructed.

## Editing a node

Click any node to open the slide-in detail panel. The panel renders a config form specific to the stage type — mode/spaces for Preproc, backend/import-to-pycortex for Autoflatten, feature list for Features, and so on.

Changes update both the node summary and the YAML in real time.

## Tips

- **Auto-layout after bulk edits** — if nodes drift after a lot of dragging, click "Re-layout" to re-run dagre.
- **Workflow name** goes into the `workflow:` YAML key and is used for filenames when saving (planned).
- **Keyboard shortcuts** — `Backspace` / `Delete` remove selected nodes or edges, scroll wheel zooms, drag on empty canvas pans.
- **Add nodes** via the palette above the canvas, then connect them by dragging from handle to handle.

## Current limitations

- **Run All is disabled** — the graph is currently for *description* only. Executing a workflow from the graph (topological traversal, live progress per node) is planned but not wired up yet. For now, use the individual views (Preproc, Autoflatten, Composer/Runs) to actually run stages.
- **Node positions aren't persisted** across sessions unless exported to YAML.
- **Sub-flows** (collapsing the analysis sub-stages into a single "Analysis" group node) is planned but not implemented.

## Related

- [Autoflatten guide](autoflatten.md) — details on the autoflatten node
- [Preprocessing guide](preprocessing.md) — details on the fmriprep node
- [DICOM to BIDS guide](dicom-to-bids.md) — details on the convert node
- [Web UI guide](web-ui.md) — overview of all views
