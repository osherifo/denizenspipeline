/** Analysis builder: compose a subject analysis as a graph of typed nodes, save it,
 *  run it, and watch its nodes as they run. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { nodeIdFor, useAnalysisGraphStore, type GraphScope } from '../stores/analysis-graph-store'
import { GraphCanvas, type GraphConnection } from '../components/graph/GraphCanvas'
import { NodePalette, type PaletteItem } from '../components/graph/NodePalette'
import { checkConnection, latticeFrom } from '../components/graph/connection'
import { layoutPositions } from '../components/graph/layout'
import {
  CATEGORY_COLORS, CATEGORY_GROUPS, CATEGORY_ORDER, categoryOf, describeAnalysisNode,
} from '../components/analysis-graph/describe'
import { AnalysisNodePanel } from '../components/analysis-graph/AnalysisNodePanel'
import { GraphSettingsPanel } from '../components/analysis-graph/GraphSettingsPanel'
import { AnalysisRunPanel } from '../components/analysis-graph/AnalysisRunPanel'
import { GraphYamlTab } from '../components/analysis-graph/GraphYamlTab'
import { useDialog } from '../components/common/Dialog'

const input: CSSProperties = { padding: '5px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit' }
const btn: CSSProperties = { ...input, cursor: 'pointer' }
const small: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)' }
const heading: CSSProperties = { ...small, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }
const sideCard: CSSProperties = {
  padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, marginBottom: 4,
  fontSize: 12, background: 'var(--bg-card)', minWidth: 0, overflow: 'hidden', cursor: 'pointer', display: 'flex', gap: 6,
}
const sideCardName: CSSProperties = { fontWeight: 600, overflowWrap: 'anywhere' }
const sideCardChain: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflowX: 'auto', paddingBottom: 2 }
const badge: CSSProperties = {
  marginLeft: 6, padding: '0 5px', borderRadius: 3, fontSize: 9, fontWeight: 600, verticalAlign: 'middle',
  border: '1px solid var(--accent-cyan)', color: 'var(--accent-cyan)', textTransform: 'uppercase', letterSpacing: 0.5,
}
const tabBtn = (active: boolean): CSSProperties => ({
  ...btn, borderColor: active ? 'var(--accent-cyan)' : 'var(--border)', color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
})
const deleteBtn: CSSProperties = { background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }

const PALETTE_GROUPS = CATEGORY_ORDER.map((c) => CATEGORY_GROUPS[c])

/** Node types that belong in a graph of ``scope``. */
export function allowedInScope(scope: GraphScope, type: string): boolean {
  const category = categoryOf(type)
  if (scope === 'group') {
    return category === 'group_analyzer' || category === 'group_reporter'
      || type === 'control:map_subjects' || type === 'control:subject_pass'
  }
  if (scope === 'study') {
    return category === 'study_analyzer' || category === 'study_reporter'
      || type === 'control:group' || type === 'control:study_groups'
  }
  return !/^(group_|study_|control$)/.test(category)
}

const SCOPES: GraphScope[] = ['subject', 'group', 'study']

export function AnalysisBuilder() {
  const s = useAnalysisGraphStore()
  const dlg = useDialog()
  const [tab, setTab] = useState<'graph' | 'yaml'>('graph')
  const [saveAs, setSaveAs] = useState('')
  // Bumped by Tidy so the canvas remounts and fits the new layout.
  const [layoutVersion, setLayoutVersion] = useState(0)
  useEffect(() => { void s.loadCatalog(); void s.loadTemplates(); void s.loadGraphs() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const catalog = useMemo(() => new Map(s.catalog.map((n) => [n.type, n])), [s.catalog])
  const lattice = useMemo(() => latticeFrom(s.portTypes), [s.portTypes])
  const describeNode = useMemo(() => describeAnalysisNode(catalog, s.runStatus), [catalog, s.runStatus])
  const { nodes, edges } = s.graph

  const isValidConnection = useCallback((c: GraphConnection) => {
    const portOf = (nodeId: string, side: 'in' | 'out', port: string) => {
      const node = nodes.find((n) => n.id === nodeId)
      const info = node ? catalog.get(node.type) : undefined
      return side === 'in' ? info?.inputs[port] : info?.outputs[port]
    }
    return checkConnection(edges, c, portOf, lattice) === null
  }, [nodes, edges, catalog, lattice])

  const scope = s.graph.scope
  const palette = useMemo<PaletteItem[]>(() => s.catalog
    .filter((n) => !n.hidden && allowedInScope(scope, n.type))
    .map((n) => {
      const category = categoryOf(n.type)
      return {
        type: n.type,
        label: nodeIdFor(n.type),
        group: CATEGORY_GROUPS[category] ?? category,
        color: CATEGORY_COLORS[category] ?? '#9ca3af',
        description: n.description,
        detail: `${Object.keys(n.inputs).join(', ') || '—'} → ${Object.keys(n.outputs).join(', ') || '—'}`,
      }
    }), [s.catalog, scope])

  async function saveAsTemplate() {
    const suggested = (s.graphName || s.graph.name || 'my_template').replace(/[^a-zA-Z0-9_-]/g, '_')
    const name = await dlg.prompt('Save the current graph as a template named:', { defaultValue: suggested, placeholder: 'template_name' })
    if (!name) return
    if (s.templates.some((t) => t.name === name && t.tier === 'user') && !(await dlg.confirm(`Overwrite your template "${name}"?`))) return
    const warnings = await s.saveTemplate(name)
    if (warnings && warnings.length) {
      await dlg.alert(`Template "${name}" saved. These node values hold a concrete path and will not carry over to another dataset. Use a graph input instead:\n\n${warnings.join('\n')}`)
    }
  }

  async function openStageConfig() {
    const filename = await dlg.prompt('Compile a saved subject stage config into a graph. Its file name:', { placeholder: 'experiment.yaml' })
    if (filename) await s.openStageConfig({ filename })
  }

  function tidy() {
    const positions = layoutPositions(s.graph, (n) => {
      const info = catalog.get(n.type)
      return { inputs: Object.keys(info?.inputs ?? {}).length, outputs: Object.keys(info?.outputs ?? {}).length }
    })
    s.setGraph({ ...s.graph, nodes: s.graph.nodes.map((n) => ({ ...n, position: positions[n.id] ?? n.position })) })
    setLayoutVersion((v) => v + 1)
  }

  const selected = s.graph.nodes.find((n) => n.id === s.selectedNodeId) ?? null

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '230px minmax(0, 1fr) 340px', gap: 12, alignItems: 'start' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div>
          <div style={heading}>Templates</div>
          {s.templates.map((t) => (
            <div key={t.name} style={sideCard} title={t.description} onClick={() => void s.loadTemplate(t.name)}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={sideCardName}>{t.name}{t.scope && t.scope !== 'subject' && <span style={badge}>{t.scope}</span>}{t.tier === 'user' && <span style={badge}>user</span>}</div>
                <div style={sideCardChain}>{t.error ? <span style={{ color: 'var(--accent-red)' }}>{t.error}</span> : `${t.n_nodes} nodes`}</div>
              </div>
              {t.tier === 'user' && (
                <button style={deleteBtn} aria-label={`delete template ${t.name}`}
                  onClick={async (e) => { e.stopPropagation(); if (await dlg.confirm(`Delete template "${t.name}"?`)) await s.removeTemplate(t.name) }}>✕</button>
              )}
            </div>
          ))}
        </div>
        <div>
          <div style={heading}>Saved graphs</div>
          {s.graphs.length === 0 && <div style={small}>none yet</div>}
          {s.graphs.map((g) => (
            <div key={g.name} style={{ ...sideCard, borderColor: s.graphName === g.name ? 'var(--accent-cyan)' : 'var(--border)' }}
              title={g.description} onClick={() => void s.loadGraph(g.name)}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={sideCardName}>{g.name}</div>
                <div style={sideCardChain}>{g.error ? <span style={{ color: 'var(--accent-red)' }}>{g.error}</span> : `${g.scope} · ${g.n_nodes} nodes`}</div>
              </div>
              <button style={deleteBtn} aria-label={`delete graph ${g.name}`}
                onClick={async (e) => { e.stopPropagation(); if (await dlg.confirm(`Delete graph "${g.name}"?`)) await s.remove(g.name) }}>✕</button>
            </div>
          ))}
          {SCOPES.map((sc) => (
            <button key={sc} style={{ ...btn, marginTop: 6, width: '100%' }} onClick={() => s.newGraph(sc)}>+ New {sc} graph</button>
          ))}
          <button style={{ ...btn, marginTop: 6, width: '100%' }} onClick={() => void openStageConfig()}>Open a stage config…</button>
        </div>
        <div>
          <div style={heading}>Add a node</div>
          <NodePalette items={palette} groupOrder={PALETTE_GROUPS} onAdd={(t) => s.addNode(t)} height={460} />
        </div>
      </div>

      <div style={{ minWidth: 0 }}>
        {s.stack.length > 0 && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8, fontSize: 12 }}>
            <button style={btn} onClick={() => s.closeBody()}>← Back</button>
            {s.stack.map((frame, i) => <span key={i} style={small}>{frame.label} ›</span>)}
            <b>{s.graphName ?? s.graph.name}</b>
            <span style={small}>(subject graph; save it to keep changes)</span>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
          <span style={{ ...badge, marginLeft: 0 }} title="graph scope">{scope}</span>
          <input style={{ ...input, width: 200, fontWeight: 700 }} value={s.graph.name} onChange={(e) => s.setMeta({ name: e.target.value })} aria-label="graph name" />
          <input style={{ ...input, flex: 1 }} placeholder="description" value={s.graph.description ?? ''} onChange={(e) => s.setMeta({ description: e.target.value })} />
          <button style={btn} onClick={() => void s.validate()}>Validate</button>
          <input style={{ ...input, width: 150 }} placeholder={s.graphName ?? 'save as…'} value={saveAs} onChange={(e) => setSaveAs(e.target.value)} />
          <button style={{ ...btn, borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }}
            onClick={() => void s.save(saveAs || s.graphName || s.graph.name)}>Save{s.dirty ? ' *' : ''}</button>
          <button style={btn} title="Keep this graph as a reusable starting point (input values are not kept)" onClick={() => void saveAsTemplate()}>Save as template</button>
        </div>
        {s.validation && (
          <div style={{ fontSize: 12, marginBottom: 8, color: s.validation.ok ? 'var(--accent-green)' : 'var(--accent-red)' }}>
            {s.validation.ok ? '✓ graph is valid' : s.validation.errors.map((e, i) => <div key={i}>✗ {e}</div>)}
          </div>
        )}
        <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
          <button style={tabBtn(tab === 'graph')} onClick={() => setTab('graph')}>Graph</button>
          <button style={tabBtn(tab === 'yaml')} onClick={() => setTab('yaml')}>YAML</button>
          <span style={{ flex: 1 }} />
          {tab === 'graph' && <button style={btn} title="Lay the nodes out left to right and fit them in view" onClick={tidy}>Tidy</button>}
        </div>
        {tab === 'graph' ? (
          <div>
            <div>
              <div style={{ ...small, marginBottom: 6 }}>click a node type on the left to add it · drag between ports of matching types to connect · Backspace deletes the selection</div>
              <GraphCanvas
                doc={s.graph}
                describeNode={describeNode}
                editable
                selectedNodeId={s.selectedNodeId}
                onSelect={s.selectNode}
                onMove={s.moveNode}
                onConnectPorts={s.addEdge}
                onRemoveNodes={(ids) => ids.forEach(s.removeNode)}
                onRemoveEdges={(ids) => ids.forEach(s.removeEdge)}
                isValidConnection={isValidConnection}
                height={620}
                fitViewKey={`${s.graphName ?? s.graph.name}:${layoutVersion}`}
              />
            </div>
          </div>
        ) : (
          <GraphYamlTab />
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {selected ? <AnalysisNodePanel node={selected} info={catalog.get(selected.type)} /> : <GraphSettingsPanel />}
        <AnalysisRunPanel />
      </div>
    </div>
  )
}
