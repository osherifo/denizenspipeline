/**
 * CustomAddonModal — Python authoring helper for custom workflows
 * and transforms.
 *
 * Scoped subset of resolved-decision-7: ships only the *Python
 * authoring side* (a textarea-based code editor pre-populated with
 * a starter scaffold + a Save button that drops a ``.py`` file
 * into ``$FMRIFLOW_HOME/addons/{workflows,transforms}/``).
 *
 * The full visual ReactFlow canvas + side-by-side Python view is
 * explicit future work — building it without breaking changes here
 * means picking a node library, designing the canvas, handling
 * topological export, etc., all of which warrants its own focused
 * effort. This modal gets the "I want to drop in a custom Python
 * module" path live today.
 */

import { useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import { saveCustomTransform, saveCustomWorkflow } from '../../api/client'


type Kind = 'workflow' | 'transform'


const overlayStyle: CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: 'rgba(0, 0, 0, 0.7)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
}

const modalStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--accent-cyan)',
  borderRadius: 8,
  padding: 20,
  width: '90%',
  maxWidth: 920,
  maxHeight: '85vh',
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
}

const labelStyle: CSSProperties = {
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: 'var(--text-secondary)',
  marginBottom: 4,
  display: 'block',
}

const inputStyle: CSSProperties = {
  width: '100%',
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '8px 10px',
  fontSize: 13,
  fontFamily: 'inherit',
  borderRadius: 4,
}

const codeStyle: CSSProperties = {
  ...inputStyle,
  fontFamily:
    "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
  fontSize: 12,
  minHeight: 380,
  resize: 'vertical',
  whiteSpace: 'pre',
}

const buttonStyle: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '8px 16px',
  fontSize: 13,
  cursor: 'pointer',
  borderRadius: 4,
}

const primaryButton: CSSProperties = {
  ...buttonStyle,
  background: 'var(--accent-green)',
  color: 'var(--bg-primary)',
  borderColor: 'var(--accent-green)',
  fontWeight: 700,
}


function workflowScaffold(name: string): string {
  return `"""Custom preproc workflow: ${name}.

Lives under \`$FMRIFLOW_HOME/addons/workflows/${name}.py\`. The
WorkflowRegistry auto-discovers it on rescan.

The minimal contract: implement validate / build / to_manifest.
"""

from __future__ import annotations

from typing import Any

from fmriflow.preproc.manifest import PreprocManifest, now_iso
from fmriflow.preproc.workflow_registry import register_preproc_workflow


@register_preproc_workflow("${name}")
class ${pascal(name)}Workflow:
    name = "${name}"
    version = "0.1.0"
    description = "Custom workflow."

    PARAM_SCHEMA: dict = {
        # "param_name": {"type": "float", "default": 5.0,
        #                "description": "What this does."},
    }
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def validate(self, config: Any) -> list[str]:
        """Return a list of human-readable validation errors;
        empty list means OK."""
        return []

    def build(self, config: Any) -> Any:
        """Return an unscheduled nipype Workflow, or None for a
        no-op (the runner skips workflow execution in that case)."""
        return None

    def to_manifest(self, config: Any, wf_outputs: dict[str, Any]) -> PreprocManifest:
        """Translate workflow outputs into the PreprocManifest
        contract. Required — downstream consumers (analysis,
        autoflatten, QC) read the manifest, not the workflow."""
        return PreprocManifest(
            subject=getattr(config, "subject", "unknown"),
            dataset=getattr(config, "dataset", None) or "unknown",
            sessions=list(getattr(config, "sessions", []) or []),
            runs=[],
            backend="nipype",
            backend_version=self.version,
            parameters={"workflow": self.name},
            space="native",
            output_dir=str(getattr(config, "output_dir", "")),
            additional_steps=[],
            created=now_iso(),
        )
`
}


function transformScaffold(name: string): string {
  return `"""Custom transform: ${name}.

Lives under \`$FMRIFLOW_HOME/addons/transforms/${name}.py\`. The
TransformRegistry auto-discovers it on rescan.

Minimal contract: declare INPUTS / OUTPUTS / PARAM_SCHEMA and
implement run(inputs, out_dir, params) -> dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.transform_registry import register_transform


@register_transform("${name}")
class ${pascal(name)}Transform:
    name = "${name}"
    version = "0.1.0"
    description = "Custom transform."

    INPUTS = ["in_file"]
    OUTPUTS = ["out_file"]

    PARAM_SCHEMA: dict = {
        # "param_name": {"type": "float", "default": 5.0,
        #                "description": "What this does."},
    }
    REQUIRED_PYTHON: list[str] = []
    REQUIRED_TOOLS: list[str] = []
    REQUIRED_ENV: list[str] = []
    CONTAINER: str | None = None

    def run(
        self,
        inputs: dict[str, Any],
        out_dir: Path,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        in_file = Path(inputs["in_file"])
        out_dir.mkdir(parents=True, exist_ok=True)
        # TODO: produce out_dir / <something>.nii.gz and return its path.
        return {"out_file": in_file}
`
}


function pascal(name: string): string {
  return name
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join('')
}


// JS-side template helper that mirrors the Python f-string syntax
// used in the scaffolds above. We render the scaffold by template
// substitution; the `${pascal(name)}` in the strings is a literal
// that gets substituted client-side before sending to the backend.
function renderScaffold(kind: Kind, name: string): string {
  const safe = name.trim() || 'my_addon'
  return (kind === 'workflow' ? workflowScaffold(safe) : transformScaffold(safe))
    // The scaffolds use template-literal expansions which JS already
    // resolves; nothing more to do.
}


export function CustomAddonModal({
  kind,
  isOpen,
  onClose,
}: {
  kind: Kind
  isOpen: boolean
  onClose: () => void
}) {
  const loadCatalogue = usePreprocStackStore((s) => s.loadCatalogue)

  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [codeDirty, setCodeDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Re-render the scaffold when the name changes *until* the user
  // starts editing the code body — then we leave it alone.
  function onNameChange(value: string) {
    setName(value)
    if (!codeDirty) {
      setCode(renderScaffold(kind, value))
    }
  }

  function onCodeChange(value: string) {
    setCode(value)
    setCodeDirty(true)
  }

  async function onSave() {
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Name is required.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (kind === 'workflow') {
        await saveCustomWorkflow(trimmed, code)
      } else {
        await saveCustomTransform(trimmed, code)
      }
      // Reload registries so the new entry appears in the dropdowns.
      await loadCatalogue()
      onClose()
      // Reset for next open.
      setName('')
      setCode('')
      setCodeDirty(false)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  // First open: seed the scaffold so the textarea isn't empty.
  if (isOpen && !code && !codeDirty) {
    setCode(renderScaffold(kind, name || 'my_addon'))
  }

  if (!isOpen) return null

  const kindLabel = kind === 'workflow' ? 'bootstrap workflow' : 'transform'
  const dest = kind === 'workflow' ? 'addons/workflows/' : 'addons/transforms/'

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16 }}>
              Author custom {kindLabel}
            </h3>
            <div
              style={{
                fontSize: 11,
                color: 'var(--text-secondary)',
                marginTop: 4,
              }}
            >
              Saves to <code>$FMRIFLOW_HOME/{dest}{name || 'my_addon'}.py</code>;
              registry auto-rescans.
            </div>
          </div>
          <button style={buttonStyle} onClick={onClose}>
            Cancel
          </button>
        </div>

        <div>
          <label style={labelStyle}>Name (letters/digits/underscore)</label>
          <input
            style={inputStyle}
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="my_lab_workflow"
            spellCheck={false}
          />
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <label style={labelStyle}>Python source</label>
          <textarea
            style={codeStyle}
            value={code}
            onChange={(e) => onCodeChange(e.target.value)}
            spellCheck={false}
          />
        </div>

        {error && (
          <div
            style={{
              color: 'var(--accent-red)',
              fontSize: 12,
              padding: 8,
              background: 'var(--bg-input)',
              border: '1px solid var(--accent-red)',
              borderRadius: 4,
            }}
          >
            {error}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button
            style={primaryButton}
            disabled={saving || !name.trim()}
            onClick={() => void onSave()}
          >
            {saving ? 'Saving...' : `Save ${kindLabel}`}
          </button>
        </div>
      </div>
    </div>
  )
}
