/** Preprocessing — one page, four tabs: Build · Runs · Library · Outputs. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocPipelineStore } from '../stores/preproc-pipeline-store'
import { usePreprocRunsStore } from '../stores/preproc-runs-store'
import { usePreprocStore } from '../stores/preproc-store'
import type { PreprocNodeInfo } from '../api/types'
import { PipelineGraph } from '../components/preproc-graph/PipelineGraph'
import { NodeParamPanel } from '../components/preproc-graph/NodeParamPanel'
import { RunPanel } from '../components/preproc-graph/RunPanel'
import { RunsList } from '../components/preproc-graph/RunsList'
import { RunDetail } from '../components/preproc-graph/RunDetail'
import { NodeLibrary } from '../components/preproc-graph/NodeLibrary'
import { NewNodeModal } from '../components/preproc-graph/NewNodeModal'
import { ImportPipelineModal } from '../components/preproc-graph/ImportPipelineModal'
import { ManifestBrowser } from '../components/preproc/ManifestBrowser'
import { CollectForm } from '../components/preproc/CollectForm'
import { KIND_COLORS, KIND_LABELS } from '../components/preproc-graph/PipelineNodeCard'

export type PreprocTab = 'build' | 'runs' | 'library' | 'outputs'

const TABS: { key: PreprocTab; label: string }[] = [
  { key: 'build', label: 'Build' },
  { key: 'runs', label: 'Runs' },
  { key: 'library', label: 'Library' },
  { key: 'outputs', label: 'Outputs' },
]

const page: CSSProperties = { padding: 20, height: 'calc(100vh - 48px)', boxSizing: 'border-box', overflow: 'auto' }
const tabBar: CSSProperties = { display: 'flex', gap: 4, marginBottom: 14, alignItems: 'center' }
const tab = (active: boolean): CSSProperties => ({
  padding: '8px 20px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer', letterSpacing: 0.5, textTransform: 'uppercase',
  border: active ? '1px solid var(--accent-cyan)' : '1px solid var(--border)', borderRadius: 6,
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent', color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
})
const input: CSSProperties = { padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit' }
const btn: CSSProperties = { ...input, cursor: 'pointer' }
const small: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)' }

/* Sidebar cards (templates / saved pipelines) live in a narrow column; the
   node chain is one line that scrolls sideways when it does not fit, and a
   long name wraps instead of spilling out of the box. */
const sideCard: CSSProperties = {
  padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, marginBottom: 4,
  fontSize: 12, background: 'var(--bg-card)', minWidth: 0, overflow: 'hidden',
}
const sideCardName: CSSProperties = { fontWeight: 600, overflowWrap: 'anywhere' }
const sideCardChain: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflowX: 'auto', paddingBottom: 2,
}

function tabFromHash(): PreprocTab {
  const m = /preproc\/(build|runs|library|outputs)/.exec(window.location.hash)
  return (m?.[1] as PreprocTab) ?? 'build'
}

export function PreprocView() {
  const [tabKey, setTabKey] = useState<PreprocTab>(tabFromHash)
  const go = (t: PreprocTab) => { setTabKey(t); window.location.hash = `#preproc/${t}` }
  return (
    <div style={page}>
      <div style={tabBar}>
        {TABS.map((t) => <button key={t.key} style={tab(tabKey === t.key)} onClick={() => go(t.key)}>{t.label}</button>)}
      </div>
      {tabKey === 'build' && <BuildTab onLaunched={() => go('runs')} />}
      {tabKey === 'runs' && <RunsTab />}
      {tabKey === 'library' && <LibraryTab onUse={() => go('build')} />}
      {tabKey === 'outputs' && <OutputsTab />}
    </div>
  )
}

// ── Build ─────────────────────────────────────────────────────────

function BuildTab({ onLaunched }: { onLaunched: (runId: string) => void }) {
  const s = usePreprocPipelineStore()
  const runsSelect = usePreprocRunsStore((r) => r.select)
  const [saveAs, setSaveAs] = useState('')
  useEffect(() => { void s.loadLibrary(); void s.loadTemplates(); void s.loadPipelines() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const selected = s.pipeline.nodes.find((n) => n.id === s.selectedNodeId) ?? null
  const info = selected ? s.library.find((n) => n.name === selected.type) : undefined
  const byName = new Map(s.library.map((n) => [n.name, n]))

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 340px', gap: 12, alignItems: 'start' }}>
      {/* left: templates + saved pipelines */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div>
          <div style={{ ...small, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Templates</div>
          {s.templates.map((t) => (
            <div key={t.name} title={t.description} onClick={() => void s.loadTemplate(t.name)}
              style={{ ...sideCard, cursor: 'pointer' }}>
              <div style={sideCardName}>{t.name}</div>
              <div style={sideCardChain}>{t.node_types.join(' → ')}</div>
            </div>
          ))}
        </div>
        <div>
          <div style={{ ...small, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Saved pipelines</div>
          {s.pipelines.length === 0 && <div style={small}>none yet</div>}
          {s.pipelines.map((p) => (
            <div key={p.name} onClick={() => void s.loadPipeline(p.name)}
              style={{ ...sideCard, cursor: 'pointer', border: `1px solid ${s.pipelineName === p.name ? 'var(--accent-cyan)' : 'var(--border)'}`, display: 'flex', gap: 6 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={sideCardName}>{p.name}</div>
                <div style={sideCardChain}>{p.error ? <span style={{ color: '#ef4444' }}>{p.error}</span> : p.node_types.join(' → ')}</div>
              </div>
              <button title="delete" onClick={(e) => { e.stopPropagation(); if (confirm(`Delete pipeline ${p.name}?`)) void s.remove(p.name) }} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}>✕</button>
            </div>
          ))}
          <button style={{ ...btn, marginTop: 6, width: '100%' }} onClick={() => s.newPipeline()}>+ New empty pipeline</button>
        </div>
      </div>

      {/* middle: editor */}
      <div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
          <input style={{ ...input, width: 200, fontWeight: 700 }} value={s.pipeline.name} onChange={(e) => s.setPipelineMeta({ name: e.target.value })} />
          <input style={{ ...input, flex: 1 }} placeholder="description" value={s.pipeline.description ?? ''} onChange={(e) => s.setPipelineMeta({ description: e.target.value })} />
          <button style={btn} onClick={() => void s.validate()}>Validate</button>
          <input style={{ ...input, width: 150 }} placeholder={s.pipelineName ?? 'save as…'} value={saveAs} onChange={(e) => setSaveAs(e.target.value)} />
          <button style={{ ...btn, borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }} onClick={() => void s.save(saveAs || s.pipelineName || s.pipeline.name)}>Save{s.dirty ? ' *' : ''}</button>
        </div>
        {s.validation && (
          <div style={{ fontSize: 12, marginBottom: 8, color: s.validation.ok ? '#10b981' : '#ef4444' }}>
            {s.validation.ok ? '✓ pipeline is valid' : s.validation.errors.map((e, i) => <div key={i}>✗ {e}</div>)}
          </div>
        )}
        {(
          <div style={{ display: 'grid', gridTemplateColumns: '190px 1fr', gap: 8 }}>
            <NodePalette library={s.library} onAdd={(t) => s.addNode(t)} />
            <div>
              <div style={{ ...small, marginBottom: 6 }}>click a node in the palette to add it · drag ports to connect · Backspace deletes the selection</div>
              <PipelineGraph
                pipeline={s.pipeline}
                library={s.library}
                editable
                selectedNodeId={s.selectedNodeId}
                onSelect={s.selectNode}
                onMove={s.moveNode}
                onConnectPorts={s.addEdge}
                onRemoveNodes={(ids) => ids.forEach(s.removeNode)}
                onRemoveEdges={(ids) => ids.forEach(s.removeEdge)}
                height={460}
                fitViewKey={s.pipelineName ?? s.pipeline.name}
              />
            </div>
          </div>
        )}
        <div style={{ marginTop: 10, fontSize: 11 }}>
          <span style={small}>pipeline inputs: </span>
          {Object.entries(s.pipeline.inputs ?? {}).map(([k, v]) => <code key={k} style={{ marginRight: 8 }} title={v.description}>{k}</code>)}
          <button style={{ ...btn, padding: '2px 8px' }} onClick={() => { const n = prompt('input name (e.g. bids_dir)'); if (n) s.setPipelineMeta({ inputs: { ...s.pipeline.inputs, [n]: { kind: /dir$/.test(n) ? 'dir' : 'str' } } }) }}>+ input</button>
        </div>
      </div>

      {/* right: params + run */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {selected ? <NodeParamPanel node={selected} info={info ?? byName.get(selected.type)} /> : <div style={{ ...small, padding: 8 }}>Select a node to edit its parameters.</div>}
        <RunPanel onLaunched={(id) => { void runsSelect(id); onLaunched(id) }} />
      </div>
    </div>
  )
}

// ── Node palette (Build · Graph view) ─────────────────────────────

function NodePalette({ library, onAdd }: { library: PreprocNodeInfo[]; onAdd: (type: string) => void }) {
  const [filter, setFilter] = useState('')
  const shown = library.filter((n) => !filter || `${n.name} ${n.description}`.toLowerCase().includes(filter.toLowerCase()))
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', padding: 8, height: 480, overflowY: 'auto', boxSizing: 'border-box' }}>
      <input style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 8 }} placeholder="find a node…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      {(['source', 'container_app', 'composite', 'interface'] as const).map((k) => {
        const items = shown.filter((n) => n.kind === k)
        if (items.length === 0) return null
        return (
          <div key={k} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: 0.6, textTransform: 'uppercase', color: KIND_COLORS[k], marginBottom: 4 }}>{KIND_LABELS[k]}</div>
            {items.map((n) => (
              <div
                key={n.name}
                title={`${n.description}\n${Object.keys(n.inputs).join(', ') || '—'} → ${Object.keys(n.outputs).join(', ') || '—'}\nclick to add`}
                onClick={() => onAdd(n.name)}
                style={{ padding: '4px 6px', borderLeft: `3px solid ${KIND_COLORS[k]}`, borderRadius: 4, marginBottom: 3, cursor: 'pointer', fontSize: 12, background: 'var(--bg-primary)' }}
              >
                <div style={{ fontWeight: 600 }}>{n.name}{n.source === 'user' ? <span style={{ ...small, marginLeft: 4 }}>user</span> : null}</div>
                <div style={{ ...small, fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.description}</div>
              </div>
            ))}
          </div>
        )
      })}
      {shown.length === 0 && <div style={small}>no node matches</div>}
    </div>
  )
}

// ── Runs ──────────────────────────────────────────────────────────

function RunsTab() {
  const loadRuns = usePreprocRunsStore((r) => r.loadRuns)
  const selectedRunId = usePreprocRunsStore((r) => r.selectedRunId)
  const select = usePreprocRunsStore((r) => r.select)
  const disconnect = usePreprocRunsStore((r) => r.disconnect)
  useEffect(() => {
    void loadRuns()
    const id = setInterval(() => void loadRuns(), 5000)
    return () => { clearInterval(id); disconnect() }
  }, [loadRuns, disconnect])
  // Re-open the socket for the selected run when the tab mounts.
  useEffect(() => { if (selectedRunId) void select(selectedRunId) }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 12, alignItems: 'start' }}>
      <div style={{ border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-card)', maxHeight: 'calc(100vh - 140px)', overflow: 'auto' }}>
        <RunsList />
      </div>
      <div><RunDetail /></div>
    </div>
  )
}

// ── Library ───────────────────────────────────────────────────────

function LibraryTab({ onUse }: { onUse: (type: string) => void }) {
  const loadLibrary = usePreprocPipelineStore((s) => s.loadLibrary)
  const addNode = usePreprocPipelineStore((s) => s.addNode)
  const library = usePreprocPipelineStore((s) => s.library)
  const [newNode, setNewNode] = useState(false)
  const [importing, setImporting] = useState(false)
  useEffect(() => { void loadLibrary() }, [loadLibrary])
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center', fontSize: 12 }}>
        <span style={small}>{library.length} nodes</span>
        <span style={{ flex: 1 }} />
        <button style={btn} onClick={() => setNewNode(true)}>+ New node</button>
        <button style={btn} onClick={() => setImporting(true)}>Import nipype pipeline…</button>
        <button style={btn} onClick={() => void loadLibrary()}>Rescan</button>
      </div>
      <NodeLibrary onUseInPipeline={(t) => { addNode(t); onUse(t) }} />
      {newNode && <NewNodeModal onClose={() => setNewNode(false)} />}
      {importing && <ImportPipelineModal onClose={() => setImporting(false)} />}
    </div>
  )
}

// ── Outputs ───────────────────────────────────────────────────────

function OutputsTab() {
  const [sub, setSub] = useState<'manifests' | 'collect'>('manifests')
  const loadManifests = usePreprocStore((s) => s.loadManifests)
  useEffect(() => { void loadManifests() }, [loadManifests])
  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
        <button style={tab(sub === 'manifests')} onClick={() => setSub('manifests')}>Manifests</button>
        <button style={tab(sub === 'collect')} onClick={() => setSub('collect')}>Collect existing derivatives</button>
      </div>
      {sub === 'manifests' ? <ManifestBrowser /> : <CollectForm />}
    </div>
  )
}
