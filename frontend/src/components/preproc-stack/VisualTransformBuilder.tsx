/**
 * VisualTransformBuilder — compose a chain of registered transforms
 * into a single custom transform class.
 *
 * Modal with three panes:
 *
 *   ┌────────────────┬────────────────────┬─────────────────┐
 *   │  Chain editor  │   ReactFlow chain  │   Selected node │
 *   │  (left)        │   (centre, large)  │   (right)       │
 *   │                │                    │                 │
 *   │  + add picker  │  Source → T1 → T2  │  ParamForm for  │
 *   │  T1 ↑ ↓ ✕      │  → ... → Sink      │  the focused    │
 *   │  T2 ↑ ↓ ✕      │  (auto-layout)     │  transform      │
 *   └────────────────┴────────────────────┴─────────────────┘
 *
 *   ┌──────────────────────────────────────────────────────┐
 *   │  Name [______]  Description [______]                 │
 *   │  Generated Python (read-only preview)                │
 *   │                              [ Cancel ] [ Save ]     │
 *   └──────────────────────────────────────────────────────┘
 *
 * The visual chain is read-only-ish: ReactFlow shows the data
 * flow, but reordering / adding / removing happens via the left
 * sidebar (cleaner accessibility + no need to invent custom
 * drop-zones). The "Generate Python" button stitches each chain
 * entry together into a `@register_transform` class that walks
 * the inner transforms in sequence; the same Save path as
 * CustomAddonModal then writes it to addons/transforms/.
 *
 * Scoped to *transforms*, not bootstrap workflows — workflows
 * are nipype graphs which need a different abstraction. For
 * those, the Python-only path stays.
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Position,
} from '@xyflow/react'
import type { Edge, Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import { saveCustomTransform } from '../../api/client'
import { ParamForm } from '../composer/ParamForm'
import type { TransformInfo } from '../../api/types'


interface ChainEntry {
  /** Stable id for the React + ReactFlow keys. */
  id: string
  /** Registered transform name. */
  name: string
  /** Current params (rendered by the right-pane ParamForm). */
  params: Record<string, unknown>
}


function schemaDefaults(
  schema: Record<string, { default?: unknown }> | undefined,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, f] of Object.entries(schema ?? {})) {
    if (f && 'default' in f) out[k] = f.default
  }
  return out
}


function pascal(name: string): string {
  return name
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join('')
}


function generatePython(
  className: string,
  description: string,
  chain: ChainEntry[],
): string {
  const slug = className || 'my_chain'
  const cls = pascal(slug) + 'Transform'
  const stages = chain.map((c, i) => {
    const tag = `s${i + 1}_${c.name}`
    const paramsJson = JSON.stringify(c.params, null, 8)
      .split('\n')
      .map((line, idx) => (idx === 0 ? line : '        ' + line))
      .join('\n')
    const prior = i === 0 ? 'inputs["in_file"]' : `r${i}["out_file"]`
    return (
      `        # Stage ${i + 1}: ${c.name}\n` +
      `        t${i + 1} = _t(${JSON.stringify(c.name)})\n` +
      `        r${i + 1} = t${i + 1}.run(\n` +
      `            {"in_file": ${prior}},\n` +
      `            out_dir / ${JSON.stringify(tag)},\n` +
      `            ${paramsJson},\n` +
      `        )`
    )
  })
  const lastIdx = chain.length || 1
  const lastRef = chain.length === 0 ? 'inputs["in_file"]' : `r${lastIdx}["out_file"]`

  return `"""${description || `Custom transform chain: ${slug}.`}

Visual-builder generated. Composes ${chain.length} transform${
    chain.length === 1 ? '' : 's'
  }: ${chain.map((c) => c.name).join(' → ') || '(empty)'}.

Edit by hand if needed; the visual builder doesn't round-trip
custom edits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fmriflow.preproc.transform_registry import (
    _REGISTRY,
    register_transform,
)


def _t(name: str):
    """Look up a registered transform class + instantiate it.

    Uses the module-level _REGISTRY directly because we're being
    invoked from inside the parent runner's process — the registry
    is already populated when our run() is called.
    """
    cls = _REGISTRY.get(name)
    if cls is None:
        raise KeyError(
            f"Sub-transform {name!r} not registered. Did the chain "
            f"reference a transform that's been removed?"
        )
    return cls()


@register_transform(${JSON.stringify(slug)})
class ${cls}:
    name = ${JSON.stringify(slug)}
    version = "0.1.0"
    description = ${JSON.stringify(description || `Chain of ${chain.length} transforms.`)}

    INPUTS = ["in_file"]
    OUTPUTS = ["out_file"]
    PARAM_SCHEMA: dict = {}
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
        out_dir.mkdir(parents=True, exist_ok=True)
${stages.join('\n\n')}
        return {"out_file": ${lastRef}}
`
}


// ── Styles ─────────────────────────────────────────────────────────


const overlayStyle: CSSProperties = {
  position: 'fixed',
  top: 0, left: 0, right: 0, bottom: 0,
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
  padding: 16,
  width: '95%',
  maxWidth: 1200,
  height: '90vh',
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
}

const bodyStyle: CSSProperties = {
  flex: 1,
  display: 'grid',
  gridTemplateColumns: '240px 1fr 280px',
  gap: 12,
  minHeight: 0,
}

const sidebarStyle: CSSProperties = {
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: 10,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
}

const canvasWrapperStyle: CSSProperties = {
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  overflow: 'hidden',
  position: 'relative',
}

const labelStyle: CSSProperties = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: 'var(--text-secondary)',
}

const inputStyle: CSSProperties = {
  width: '100%',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '6px 8px',
  fontSize: 12,
  fontFamily: 'inherit',
  borderRadius: 4,
}

const smallButton: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '2px 6px',
  fontSize: 10,
  cursor: 'pointer',
  borderRadius: 3,
}

const primaryButton: CSSProperties = {
  background: 'var(--accent-green)',
  color: 'var(--bg-primary)',
  border: 'none',
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer',
  borderRadius: 4,
}

const chainRowStyle = (focused: boolean): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 8px',
  border: `1px solid ${focused ? 'var(--accent-cyan)' : 'var(--border)'}`,
  borderRadius: 4,
  background: focused ? 'rgba(0, 229, 255, 0.06)' : 'transparent',
  cursor: 'pointer',
  fontSize: 12,
})


// ── Component ──────────────────────────────────────────────────────


export function VisualTransformBuilder({
  isOpen,
  onClose,
}: {
  isOpen: boolean
  onClose: () => void
}) {
  const transforms = usePreprocStackStore((s) => s.transforms)
  const loadCatalogue = usePreprocStackStore((s) => s.loadCatalogue)

  const [chain, setChain] = useState<ChainEntry[]>([])
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [pickerName, setPickerName] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [_nextId, setNextId] = useState(0)

  // Reset state every time the modal opens so it doesn't carry
  // over from a previous session.
  useEffect(() => {
    if (!isOpen) return
    setChain([])
    setFocusedId(null)
    setPickerName('')
    setName('')
    setDescription('')
    setError(null)
    setSaving(false)
    setNextId(0)
  }, [isOpen])

  const focused = chain.find((c) => c.id === focusedId) ?? null
  const focusedInfo: TransformInfo | undefined = focused
    ? transforms.find((t) => t.name === focused.name)
    : undefined

  function addChainEntry() {
    if (!pickerName) return
    const info = transforms.find((t) => t.name === pickerName)
    setChain((prev) => {
      // Use a fresh nextId computed off the current state so adds
      // in quick succession don't collide.
      const newId = `chain-${prev.length}-${Date.now()}`
      return [
        ...prev,
        {
          id: newId,
          name: pickerName,
          params: schemaDefaults(info?.params_schema),
        },
      ]
    })
    setPickerName('')
  }

  function removeChainEntry(id: string) {
    setChain((prev) => prev.filter((c) => c.id !== id))
    if (focusedId === id) setFocusedId(null)
  }

  function moveChainEntry(id: string, delta: number) {
    setChain((prev) => {
      const idx = prev.findIndex((c) => c.id === id)
      if (idx < 0) return prev
      const newIdx = idx + delta
      if (newIdx < 0 || newIdx >= prev.length) return prev
      const next = [...prev]
      ;[next[idx], next[newIdx]] = [next[newIdx], next[idx]]
      return next
    })
  }

  function setFocusedParam(key: string, value: unknown) {
    if (!focused) return
    setChain((prev) =>
      prev.map((c) =>
        c.id === focused.id ? { ...c, params: { ...c.params, [key]: value } } : c,
      ),
    )
  }

  // ── ReactFlow nodes + edges (read-only visualisation) ──

  const { nodes, edges } = useMemo(() => {
    const xs = 220
    const y = 70
    const nodes: Node[] = []
    const edges: Edge[] = []

    // Source node (in_file).
    nodes.push({
      id: 'source',
      type: 'input',
      position: { x: 30, y },
      data: { label: 'Source\nin_file' },
      sourcePosition: Position.Right,
      style: {
        background: 'var(--bg-card)',
        border: '1px solid var(--accent-cyan)',
        color: 'var(--text-primary)',
        fontSize: 11,
        width: 100,
      },
    })

    // Transform nodes.
    chain.forEach((c, i) => {
      const id = c.id
      nodes.push({
        id,
        position: { x: 30 + xs * (i + 1), y },
        data: { label: `${i + 1}. ${c.name}` },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          background: focusedId === id ? 'rgba(0,229,255,0.12)' : 'var(--bg-card)',
          border: `1px solid ${
            focusedId === id ? 'var(--accent-cyan)' : 'var(--border)'
          }`,
          color: 'var(--text-primary)',
          fontSize: 11,
          width: 160,
        },
      })
      const fromId = i === 0 ? 'source' : chain[i - 1].id
      edges.push({
        id: `e-${fromId}-${id}`,
        source: fromId,
        target: id,
        animated: true,
        style: { stroke: 'var(--accent-cyan)' },
      })
    })

    // Sink node (out_file).
    const sinkX = 30 + xs * (chain.length + 1)
    nodes.push({
      id: 'sink',
      type: 'output',
      position: { x: sinkX, y },
      data: { label: 'Output\nout_file' },
      targetPosition: Position.Left,
      style: {
        background: 'var(--bg-card)',
        border: '1px solid var(--accent-green)',
        color: 'var(--text-primary)',
        fontSize: 11,
        width: 100,
      },
    })
    const lastSrc = chain.length === 0 ? 'source' : chain[chain.length - 1].id
    edges.push({
      id: `e-${lastSrc}-sink`,
      source: lastSrc,
      target: 'sink',
      animated: chain.length > 0,
      style: { stroke: 'var(--accent-green)' },
    })

    return { nodes, edges }
  }, [chain, focusedId])

  const generated = useMemo(
    () => generatePython(name.trim() || 'my_chain', description, chain),
    [name, description, chain],
  )

  async function onSave() {
    const slug = name.trim()
    if (!slug) {
      setError('Name is required.')
      return
    }
    if (chain.length === 0) {
      setError('Chain is empty — add at least one transform.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await saveCustomTransform(slug, generated)
      await loadCatalogue()
      onClose()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (!isOpen) return null

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16 }}>Compose custom transform (visual)</h3>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
              Chain registered transforms together; saves as a single
              <code> @register_transform </code> class under
              <code> $FMRIFLOW_HOME/addons/transforms/{name.trim() || 'my_chain'}.py</code>.
            </div>
          </div>
          <button style={smallButton} onClick={onClose}>Cancel</button>
        </div>

        <div style={bodyStyle}>
          {/* LEFT — chain editor */}
          <div style={sidebarStyle}>
            <div>
              <label style={labelStyle}>Add transform</label>
              <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
                <select
                  style={{ ...inputStyle, flex: 1 }}
                  value={pickerName}
                  onChange={(e) => setPickerName(e.target.value)}
                >
                  <option value="">(pick...)</option>
                  {transforms.map((t) => (
                    <option key={t.name} value={t.name}>
                      {t.name}
                    </option>
                  ))}
                </select>
                <button
                  style={{
                    ...smallButton,
                    color: pickerName ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                    borderColor: pickerName ? 'var(--accent-cyan)' : 'var(--border)',
                  }}
                  disabled={!pickerName}
                  onClick={addChainEntry}
                >
                  + Add
                </button>
              </div>
            </div>

            <div style={{ marginTop: 4 }}>
              <label style={labelStyle}>Chain ({chain.length})</label>
            </div>

            {chain.length === 0 && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                Empty. Add a transform above.
              </div>
            )}

            {chain.map((c, i) => (
              <div
                key={c.id}
                style={chainRowStyle(focusedId === c.id)}
                onClick={() => setFocusedId(c.id)}
              >
                <span style={{ flex: 1 }}>
                  {i + 1}. {c.name}
                </span>
                <button
                  style={smallButton}
                  onClick={(e) => { e.stopPropagation(); moveChainEntry(c.id, -1) }}
                  disabled={i === 0}
                  title="Move up"
                >↑</button>
                <button
                  style={smallButton}
                  onClick={(e) => { e.stopPropagation(); moveChainEntry(c.id, +1) }}
                  disabled={i === chain.length - 1}
                  title="Move down"
                >↓</button>
                <button
                  style={{ ...smallButton, color: 'var(--accent-red)' }}
                  onClick={(e) => { e.stopPropagation(); removeChainEntry(c.id) }}
                  title="Remove"
                >✕</button>
              </div>
            ))}
          </div>

          {/* CENTRE — ReactFlow canvas */}
          <div style={canvasWrapperStyle}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              onNodeClick={(_, n) => {
                if (n.id !== 'source' && n.id !== 'sink') setFocusedId(n.id)
              }}
            >
              <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            </ReactFlow>
          </div>

          {/* RIGHT — selected-node params */}
          <div style={sidebarStyle}>
            <div>
              <label style={labelStyle}>Selected node</label>
              <div style={{ fontSize: 13, marginTop: 4 }}>
                {focused ? (
                  <>
                    <div style={{ fontWeight: 600 }}>{focused.name}</div>
                    {focusedInfo?.description && (
                      <div
                        style={{
                          fontSize: 11,
                          color: 'var(--text-secondary)',
                          fontStyle: 'italic',
                          marginTop: 4,
                        }}
                      >
                        {focusedInfo.description}
                      </div>
                    )}
                  </>
                ) : (
                  <span style={{ color: 'var(--text-secondary)' }}>
                    Click a chain node to edit its params.
                  </span>
                )}
              </div>
            </div>
            {focused && (
              <div>
                <label style={labelStyle}>Params</label>
                {Object.keys(focusedInfo?.params_schema ?? {}).length > 0 ? (
                  <ParamForm
                    schema={focusedInfo!.params_schema}
                    values={focused.params}
                    onChange={(k, v) => setFocusedParam(k, v)}
                  />
                ) : (
                  <div
                    style={{
                      fontSize: 11,
                      color: 'var(--text-secondary)',
                      fontStyle: 'italic',
                    }}
                  >
                    No schema declared for this transform.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* BOTTOM — name/description + generated preview + save */}

        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr auto', gap: 8 }}>
          <input
            style={inputStyle}
            placeholder="my_chain (a-z, 0-9, _)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            style={inputStyle}
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button
            style={{
              ...primaryButton,
              opacity: saving || !name.trim() || chain.length === 0 ? 0.5 : 1,
              cursor: saving || !name.trim() || chain.length === 0 ? 'not-allowed' : 'pointer',
            }}
            disabled={saving || !name.trim() || chain.length === 0}
            onClick={() => void onSave()}
          >
            {saving ? 'Saving...' : 'Generate + Save'}
          </button>
        </div>

        {error && (
          <div
            style={{
              color: 'var(--accent-red)',
              fontSize: 12,
              padding: 6,
              background: 'var(--bg-input)',
              border: '1px solid var(--accent-red)',
              borderRadius: 4,
            }}
          >
            {error}
          </div>
        )}

        <details style={{ fontSize: 12 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)' }}>
            Generated Python preview
          </summary>
          <pre
            style={{
              background: 'var(--bg-input)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              padding: 10,
              maxHeight: 200,
              overflow: 'auto',
              fontSize: 11,
              fontFamily:
                "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
            }}
          >
            {generated}
          </pre>
        </details>
      </div>
    </div>
  )
}
