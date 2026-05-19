/**
 * PreprocStackView — single-page UI for composing + running a
 * preprocessing stack (Phase 6 of the preprocessing-stack rollout).
 *
 * Layout (top → bottom):
 *
 *   ┌── Bootstrap card ──────────────────────────────────┐
 *   │  Backend selector · workflow picker · params · preflight badge │
 *   └────────────────────────────────────────────────────┘
 *
 *   ┌── Transform card (Stage 1) ────────────────────────┐
 *   │  name · status · params · up/down/remove           │
 *   └────────────────────────────────────────────────────┘
 *   ...
 *
 *   [+ Add transform ▼] [ Add ]
 *
 *   ┌── Run binding ─────────────────────────────────────┐
 *   │  Subject · output_dir · BIDS dir · derivatives_dir │
 *   │  [Run pipeline]  [Cancel]                          │
 *   └────────────────────────────────────────────────────┘
 *
 *   ┌── Live events ─────────────────────────────────────┐
 *   │  ▶ run started · subject=sub01 · 2 stages          │
 *   │  · stage 0 (bootstrap): identity starting          │
 *   │  ✓ stage 0 (bootstrap): identity done 0.01s        │
 *   │  · stage 1 (transform): identity starting          │
 *   │  ✓ stage 1 (transform): identity done 0.00s        │
 *   │  ✓ completed · 2 stages · 0.02s                    │
 *   │  — terminal · status=done                          │
 *   └────────────────────────────────────────────────────┘
 *
 * Visual builder for custom workflows + drag-to-reorder + save-as-
 * preset are explicit Phase 6b / later concerns and not included
 * here.
 */

import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../stores/preproc-stack-store'
import { BootstrapCard } from '../components/preproc-stack/BootstrapCard'
import { TransformCard } from '../components/preproc-stack/TransformCard'
import { AddTransformPicker } from '../components/preproc-stack/AddTransformPicker'
import { RunControls } from '../components/preproc-stack/RunControls'
import { EventLog } from '../components/preproc-stack/EventLog'


const containerStyle: CSSProperties = {
  maxWidth: 880,
  margin: '0 auto',
}

const headerStyle: CSSProperties = {
  marginBottom: 8,
  fontSize: 18,
  fontWeight: 700,
}

const subheaderStyle: CSSProperties = {
  marginBottom: 20,
  color: 'var(--text-secondary)',
  fontSize: 13,
}

const errorStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--accent-red)',
  borderRadius: 8,
  padding: 12,
  marginBottom: 12,
  color: 'var(--accent-red)',
  fontSize: 13,
}


export function PreprocStackView() {
  const loadCatalogue = usePreprocStackStore((s) => s.loadCatalogue)
  const catalogueLoaded = usePreprocStackStore((s) => s.catalogueLoaded)
  const catalogueError = usePreprocStackStore((s) => s.catalogueError)
  const transformsStack = usePreprocStackStore((s) => s.transformsStack)

  useEffect(() => {
    void loadCatalogue()
  }, [loadCatalogue])

  if (!catalogueLoaded) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>Preprocessing (stack)</div>
        <div style={subheaderStyle}>Loading registry...</div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Preprocessing (stack)</div>
      <div style={subheaderStyle}>
        Compose an ordered pipeline: pick a bootstrap backend, append
        transforms, run. Outputs are cached by fingerprint; identical
        stages skip on rerun.
      </div>

      {catalogueError && (
        <div style={errorStyle}>
          Could not load registry: {catalogueError}
        </div>
      )}

      <BootstrapCard />

      {transformsStack.map((t, i) => (
        <TransformCard
          key={i}
          index={i}
          name={t.name}
          params={t.params ?? {}}
        />
      ))}

      <AddTransformPicker />

      <RunControls />

      <EventLog />
    </div>
  )
}
