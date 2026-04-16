/** Slide-in detail panel for editing a selected node's configuration. */
import type { CSSProperties } from 'react'
import { useGraphStore, type StageType, type StageNodeData } from '../../stores/graph-store'
import { useState, useEffect } from 'react'

// ── Styles ──────────────────────────────────────────────────────────────

const overlay: CSSProperties = {
  position: 'fixed',
  top: 0,
  right: 0,
  width: 380,
  height: '100vh',
  backgroundColor: '#111128',
  borderLeft: '1px solid var(--border)',
  zIndex: 200,
  display: 'flex',
  flexDirection: 'column',
  boxShadow: '-4px 0 20px rgba(0,0,0,0.4)',
}

const header: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '16px 20px',
  borderBottom: '1px solid var(--border)',
}

const titleStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
}

const closeBtn: CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  fontSize: 18,
  cursor: 'pointer',
  padding: '4px 8px',
}

const body: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '16px 20px',
}

const fieldRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 12,
  gap: 10,
}

const label: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  width: 100,
  textAlign: 'right',
  flexShrink: 0,
}

const input: CSSProperties = {
  padding: '7px 10px',
  fontSize: 12,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  color: 'var(--text-primary)',
  flex: 1,
}

const select: CSSProperties = { ...input, appearance: 'auto' as const }

const sectionTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 16,
  marginBottom: 10,
}

const checkRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 8,
}

// ── Per-stage config forms ──────────────────────────────────────────────

function SourceConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Path</span>
        <input style={input} value={(config.path as string) || ''} onChange={(e) => onChange({ ...config, path: e.target.value })}
          placeholder="/data/dicoms/sub01/" />
      </div>
    </>
  )
}

function ConvertConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Heuristic</span>
        <input style={input} value={(config.heuristic as string) || ''} onChange={(e) => onChange({ ...config, heuristic: e.target.value })}
          placeholder="reading_paradigm" />
      </div>
      <div style={fieldRow}>
        <span style={label}>BIDS Dir</span>
        <input style={input} value={(config.bids_dir as string) || ''} onChange={(e) => onChange({ ...config, bids_dir: e.target.value })}
          placeholder="/data/bids" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Session</span>
        <input style={input} value={(config.session as string) || ''} onChange={(e) => onChange({ ...config, session: e.target.value })}
          placeholder="ses01" />
      </div>
    </>
  )
}

function PreprocConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Mode</span>
        <select style={select} value={(config.mode as string) || 'full'} onChange={(e) => onChange({ ...config, mode: e.target.value })}>
          <option value="full">Full</option>
          <option value="anat_only">Anat Only</option>
          <option value="func_only">Func Only</option>
          <option value="func_precomputed_anat">Pre-computed Anat</option>
        </select>
      </div>
      <div style={fieldRow}>
        <span style={label}>Output Dir</span>
        <input style={input} value={(config.output_dir as string) || ''} onChange={(e) => onChange({ ...config, output_dir: e.target.value })}
          placeholder="/data/derivatives/fmriprep" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Spaces</span>
        <input style={input} value={(config.output_spaces as string) || 'T1w'} onChange={(e) => onChange({ ...config, output_spaces: e.target.value })}
          placeholder="T1w, MNI152NLin2009cAsym:res-2" />
      </div>
      <div style={sectionTitle}>Resources</div>
      <div style={fieldRow}>
        <span style={label}>Threads</span>
        <input style={{ ...input, maxWidth: 80 }} type="number" value={(config.nthreads as string) || ''} onChange={(e) => onChange({ ...config, nthreads: e.target.value })}
          placeholder="8" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Memory (MB)</span>
        <input style={{ ...input, maxWidth: 100 }} type="number" value={(config.mem_mb as string) || ''} onChange={(e) => onChange({ ...config, mem_mb: e.target.value })}
          placeholder="32000" />
      </div>
    </>
  )
}

function AutoflattenConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Backend</span>
        <select style={select} value={(config.backend as string) || 'pyflatten'} onChange={(e) => onChange({ ...config, backend: e.target.value })}>
          <option value="pyflatten">pyflatten (JAX)</option>
          <option value="freesurfer">freesurfer</option>
        </select>
      </div>
      <div style={checkRow}>
        <span style={label} />
        <input type="checkbox" checked={config.import_to_pycortex !== false}
          onChange={(e) => onChange({ ...config, import_to_pycortex: e.target.checked })} />
        <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>Import to pycortex</span>
      </div>
      <div style={fieldRow}>
        <span style={label}>Surface name</span>
        <input style={input} value={(config.pycortex_surface as string) || ''} onChange={(e) => onChange({ ...config, pycortex_surface: e.target.value })}
          placeholder="sub01fs (auto)" />
      </div>
    </>
  )
}

function ResponseLoaderConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Loader</span>
        <select style={select} value={(config.loader as string) || 'preproc'} onChange={(e) => onChange({ ...config, loader: e.target.value })}>
          <option value="preproc">preproc (manifest)</option>
          <option value="local">local (files)</option>
          <option value="bids">BIDS</option>
          <option value="cloud">cloud (S3)</option>
        </select>
      </div>
      <div style={fieldRow}>
        <span style={label}>Manifest</span>
        <input style={input} value={(config.manifest as string) || ''} onChange={(e) => onChange({ ...config, manifest: e.target.value })}
          placeholder="auto (from preproc)" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Mask type</span>
        <input style={input} value={(config.mask_type as string) || 'thick'} onChange={(e) => onChange({ ...config, mask_type: e.target.value })}
          placeholder="thick" />
      </div>
    </>
  )
}

function FeaturesConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  const features = (config.features as { name: string; source: string }[]) || []
  const [newName, setNewName] = useState('')

  const addFeature = () => {
    if (!newName.trim()) return
    onChange({ ...config, features: [...features, { name: newName.trim(), source: 'compute' }] })
    setNewName('')
  }

  const removeFeature = (i: number) => {
    onChange({ ...config, features: features.filter((_, idx) => idx !== i) })
  }

  return (
    <>
      {features.map((f, i) => (
        <div key={i} style={{ ...fieldRow, backgroundColor: 'var(--bg-input)', borderRadius: 5, padding: '6px 10px' }}>
          <span style={{ fontSize: 12, color: 'var(--text-primary)', flex: 1 }}>{f.name}</span>
          <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{f.source}</span>
          <span onClick={() => removeFeature(i)} style={{ cursor: 'pointer', color: 'var(--accent-red)', fontWeight: 700 }}>x</span>
        </div>
      ))}
      <div style={fieldRow}>
        <input style={input} value={newName} onChange={(e) => setNewName(e.target.value)}
          placeholder="Feature name" onKeyDown={(e) => { if (e.key === 'Enter') addFeature() }} />
        <button onClick={addFeature} style={{
          padding: '6px 12px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
          borderRadius: 5, border: '1px solid var(--border)', backgroundColor: 'var(--bg-input)',
          color: 'var(--text-secondary)', cursor: 'pointer',
        }}>Add</button>
      </div>
    </>
  )
}

function PrepareConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Type</span>
        <select style={select} value={(config.type as string) || 'pipeline'} onChange={(e) => onChange({ ...config, type: e.target.value })}>
          <option value="pipeline">pipeline (stackable steps)</option>
          <option value="default">default (trim+zscore+concat)</option>
        </select>
      </div>
      <div style={fieldRow}>
        <span style={label}>Steps</span>
        <input style={input} value={(config.steps_str as string) || 'split, trim, zscore, concatenate'}
          onChange={(e) => onChange({ ...config, steps_str: e.target.value })}
          placeholder="split, trim, zscore, concatenate" />
      </div>
    </>
  )
}

function ModelConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Type</span>
        <select style={select} value={(config.type as string) || 'bootstrap_ridge'} onChange={(e) => onChange({ ...config, type: e.target.value })}>
          <option value="bootstrap_ridge">bootstrap_ridge</option>
          <option value="himalaya_ridge">himalaya_ridge</option>
          <option value="banded_ridge">banded_ridge</option>
          <option value="multiple_kernel_ridge">multiple_kernel_ridge</option>
        </select>
      </div>
      <div style={fieldRow}>
        <span style={label}>Delays</span>
        <input style={input} value={(config.delays as string) || '0,1,2,3,4,5,6,7,8,9'}
          onChange={(e) => onChange({ ...config, delays: e.target.value })}
          placeholder="0,1,2,3,4,5,6,7,8,9" />
      </div>
    </>
  )
}

function ReportConfig({ config, onChange }: { config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  return (
    <>
      <div style={fieldRow}>
        <span style={label}>Formats</span>
        <input style={input} value={(config.formats as string) || 'metrics, flatmap'}
          onChange={(e) => onChange({ ...config, formats: e.target.value })}
          placeholder="metrics, flatmap, histogram" />
      </div>
      <div style={fieldRow}>
        <span style={label}>Output Dir</span>
        <input style={input} value={(config.output_dir as string) || ''}
          onChange={(e) => onChange({ ...config, output_dir: e.target.value })}
          placeholder="./results/sub01" />
      </div>
    </>
  )
}

// ── Config form router ──────────────────────────────────────────────────

const CONFIG_FORMS: Record<StageType, React.FC<{ config: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }>> = {
  source: SourceConfig,
  convert: ConvertConfig,
  preproc: PreprocConfig,
  autoflatten: AutoflattenConfig,
  response_loader: ResponseLoaderConfig,
  features: FeaturesConfig,
  prepare: PrepareConfig,
  model: ModelConfig,
  report: ReportConfig,
}

// ── Main component ──────────────────────────────────────────────────────

export function NodeDetailPanel() {
  const { nodes, selectedNodeId, detailOpen, closeDetail, updateNodeConfig, updateNodeSummary } = useGraphStore()

  const node = nodes.find((n) => n.id === selectedNodeId)

  if (!detailOpen || !node) return null

  const data = node.data as StageNodeData
  const ConfigForm = CONFIG_FORMS[data.stageType]

  const handleConfigChange = (newConfig: Record<string, unknown>) => {
    updateNodeConfig(node.id, newConfig)
    // Update summary from config
    const summary = buildSummary(data.stageType, newConfig)
    updateNodeSummary(node.id, summary)
  }

  return (
    <div style={overlay}>
      <div style={header}>
        <span style={titleStyle}>{data.label}</span>
        <button style={closeBtn} onClick={closeDetail}>x</button>
      </div>
      <div style={body}>
        {ConfigForm && <ConfigForm config={data.config} onChange={handleConfigChange} />}
      </div>
    </div>
  )
}

function buildSummary(stageType: StageType, config: Record<string, unknown>): string[] {
  switch (stageType) {
    case 'source':
      return config.path ? [`path: ${config.path}`] : []
    case 'convert':
      return [
        config.heuristic ? `heuristic: ${config.heuristic}` : '',
        config.bids_dir ? `bids: ${config.bids_dir}` : '',
      ].filter(Boolean)
    case 'preproc':
      return [
        `mode: ${config.mode || 'full'}`,
        config.output_spaces ? `spaces: ${config.output_spaces}` : '',
      ].filter(Boolean)
    case 'autoflatten':
      return [`backend: ${config.backend || 'pyflatten'}`]
    case 'response_loader':
      return [`loader: ${config.loader || 'preproc'}`]
    case 'features': {
      const feats = (config.features as { name: string }[]) || []
      return feats.length > 0
        ? [feats.map((f) => f.name).join(', ')]
        : ['(add features)']
    }
    case 'prepare':
      return [config.steps_str as string || 'trim, zscore, concat']
    case 'model':
      return [`type: ${config.type || 'bootstrap_ridge'}`]
    case 'report':
      return [config.formats as string || 'metrics, flatmap']
    default:
      return []
  }
}
