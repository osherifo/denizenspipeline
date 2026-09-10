/** Subject / path bindings + execution options + the Run button. */
import type { CSSProperties } from 'react'
import { usePreprocPipelineStore } from '../../stores/preproc-pipeline-store'
import { PathField } from '../common/PathPicker'

const panel: CSSProperties = { border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 12, fontSize: 12 }
const row: CSSProperties = { display: 'grid', gridTemplateColumns: '110px 1fr', gap: 8, alignItems: 'center', marginBottom: 6 }
const input: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}
const primary: CSSProperties = {
  padding: '8px 18px', borderRadius: 6, border: 'none', background: 'var(--accent-cyan)', color: 'var(--on-accent)',
  fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
}

interface Props {
  onLaunched?: (runId: string) => void
}

export function RunPanel({ onLaunched }: Props) {
  const pipeline = usePreprocPipelineStore((s) => s.pipeline)
  const binding = usePreprocPipelineStore((s) => s.binding)
  const setBinding = usePreprocPipelineStore((s) => s.setBinding)
  const launch = usePreprocPipelineStore((s) => s.launch)
  const launching = usePreprocPipelineStore((s) => s.launching)
  const validation = usePreprocPipelineStore((s) => s.validation)
  const error = usePreprocPipelineStore((s) => s.error)
  const declared = Object.keys(pipeline.inputs ?? {})
  const wants = (name: string) => declared.length === 0 || declared.includes(name)
  const canRun = Boolean(binding.subject && binding.output_dir) && pipeline.nodes.length > 0 && !launching

  const text = (key: keyof typeof binding, placeholder: string) => (
    <input style={input} placeholder={placeholder} value={String(binding[key] ?? '')} onChange={(e) => setBinding({ [key]: e.target.value } as never)} />
  )
  // Directory bindings get the server-side browser (with "New folder" for a fresh output dir).
  const dir = (key: keyof typeof binding, placeholder: string) => (
    <PathField style={input} compact placeholder={placeholder} value={String(binding[key] ?? '')} onChange={(v) => setBinding({ [key]: v } as never)} />
  )

  return (
    <div style={panel}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 2 }}>Run</div>
      <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 8 }}>these values are saved with the pipeline (Save above) and come back when you reopen it</div>
      <div style={row}><label>subject *</label>{text('subject', 'participant label, e.g. 01')}</div>
      <div style={row}><label>output_dir *</label>{dir('output_dir', 'where derivatives + work go')}</div>
      {wants('bids_dir') && <div style={row}><label>bids_dir</label>{dir('bids_dir', 'BIDS root')}</div>}
      {wants('derivatives_dir') && <div style={row}><label>derivatives_dir</label>{dir('derivatives_dir', 'existing preprocessed data')}</div>}
      <div style={row}><label>work_dir</label>{dir('work_dir', 'default: <output_dir>/work')}</div>
      <div style={row}><label>dataset</label>{text('dataset', 'label for the manifest')}</div>
      <div style={row}>
        <label>plugin</label>
        <div style={{ display: 'flex', gap: 6 }}>
          <select style={{ ...input, width: 'auto' }} value={binding.plugin} onChange={(e) => setBinding({ plugin: e.target.value as 'Linear' | 'MultiProc' })}>
            <option value="Linear">Linear</option>
            <option value="MultiProc">MultiProc</option>
          </select>
          {binding.plugin === 'MultiProc' && (
            <input style={{ ...input, width: 80 }} type="number" min={1} placeholder="n_procs" value={binding.n_procs ?? ''} onChange={(e) => setBinding({ n_procs: e.target.value ? Number(e.target.value) : null })} />
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 14, margin: '6px 0 10px', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={binding.use_cache} onChange={(e) => setBinding({ use_cache: e.target.checked })} /> use cache
        </label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center' }} title="terminate the run on a bad checkpoint verdict">
          <input type="checkbox" checked={binding.abort_on_bad} onChange={(e) => setBinding({ abort_on_bad: e.target.checked })} /> abort on bad checkpoint
        </label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center' }} title="re-execute from these nodes (comma-separated ids), downstream follows">
          rerun from
          <input style={{ ...input, width: 160 }} placeholder="node ids" value={binding.rerun_from.join(',')} onChange={(e) => setBinding({ rerun_from: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
        </label>
      </div>
      {validation && !validation.ok && (
        <div style={{ color: 'var(--accent-red, #ef4444)', marginBottom: 8 }}>
          {validation.errors.map((e, i) => <div key={i}>• {e}</div>)}
        </div>
      )}
      {error && <div style={{ color: 'var(--accent-red, #ef4444)', marginBottom: 8 }}>{error}</div>}
      <button
        style={{ ...primary, opacity: canRun ? 1 : 0.5 }}
        disabled={!canRun}
        onClick={async () => { const id = await launch(); if (id) onLaunched?.(id) }}
      >
        {launching ? 'Launching…' : '▶ Run pipeline'}
      </button>
    </div>
  )
}
