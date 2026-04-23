/** Workflows — end-to-end orchestration across convert / preproc / autoflatten / analysis. */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type {
  WorkflowConfigSummary,
  WorkflowConfigDetail,
  WorkflowRunSummary,
} from '../api/types'
import {
  fetchWorkflowConfigs,
  fetchWorkflowConfigDetail,
  runWorkflowConfig,
  fetchWorkflowRuns,
  cancelWorkflowRun,
  fetchInFlightRun,
} from '../api/client'
import type { AnalysisInnerStage } from '../api/types'
import { WorkflowGraph } from '../components/workflow/WorkflowGraph'
import { StageLogModal } from '../components/workflow/StageLogModal'
import { LiveStageLog } from '../components/workflow/LiveStageLog'

// ── Styles ──────────────────────────────────────────────────────────────

const pageTitle: CSSProperties = {
  fontSize: 20, fontWeight: 800, color: 'var(--text-primary)',
  marginBottom: 4, letterSpacing: 1,
}
const pageDesc: CSSProperties = {
  fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16,
}

const topPanel: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '14px 18px',
  marginBottom: 12,
}

const sectionLabel: CSSProperties = {
  fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)',
  textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10,
}

const containerStyle: CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 48px - 280px)',
  minHeight: 320,
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
}

const sidebar: CSSProperties = {
  width: 280,
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex', flexDirection: 'column', overflow: 'hidden',
}
const sidebarHeader: CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  padding: '12px 16px', borderBottom: '1px solid var(--border)',
}
const sidebarTitle: CSSProperties = {
  fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)',
  textTransform: 'uppercase', letterSpacing: 1,
}
const refreshBtn: CSSProperties = {
  padding: '4px 10px', fontSize: 10, fontWeight: 600, fontFamily: 'inherit',
  border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer',
  backgroundColor: 'transparent', color: 'var(--text-secondary)',
}

const listStyle: CSSProperties = { flex: 1, overflowY: 'auto' }
const itemStyle = (active: boolean): CSSProperties => ({
  padding: '10px 16px', cursor: 'pointer',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
  borderBottom: '1px solid var(--border)',
})
const itemName: CSSProperties = {
  fontSize: 12, fontWeight: 600, color: 'var(--text-primary)',
  marginBottom: 2, fontFamily: 'monospace',
}
const itemMeta: CSSProperties = {
  fontSize: 10, color: 'var(--text-secondary)',
}

const mainPanel: CSSProperties = {
  flex: 1, overflowY: 'auto', padding: '20px 24px',
  display: 'flex', flexDirection: 'column', gap: 16,
}
const emptyState: CSSProperties = {
  flex: 1, display: 'flex', flexDirection: 'column',
  alignItems: 'center', justifyContent: 'center',
  color: 'var(--text-secondary)', fontSize: 13, gap: 8, height: '100%',
}

const runBtn = (disabled: boolean): CSSProperties => ({
  padding: '8px 20px', fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
  border: `1px solid ${disabled ? 'var(--border)' : 'var(--accent-cyan)'}`,
  borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
  backgroundColor: disabled ? 'transparent' : 'rgba(0, 229, 255, 0.1)',
  color: disabled ? 'var(--text-secondary)' : 'var(--accent-cyan)',
  textTransform: 'uppercase', letterSpacing: 1,
})

const summaryGrid: CSSProperties = {
  display: 'grid', gridTemplateColumns: '120px 1fr',
  gap: '6px 16px', fontSize: 12, padding: '12px 0',
}
const summaryLabel: CSSProperties = {
  color: 'var(--text-secondary)', fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: 0.5, fontSize: 10,
}
const summaryValue: CSSProperties = {
  color: 'var(--text-primary)', fontFamily: 'monospace',
  wordBreak: 'break-all',
}

const yamlPre: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)', borderRadius: 6,
  padding: '12px 14px', fontSize: 11, lineHeight: 1.6,
  fontFamily: 'monospace', color: 'var(--text-primary)',
  overflow: 'auto', maxHeight: 360, whiteSpace: 'pre',
  border: '1px solid var(--border)',
}

// ── Helpers ─────────────────────────────────────────────────────────────

function statusColor(status: string): string {
  switch (status) {
    case 'running': return 'var(--accent-cyan)'
    case 'done': return 'var(--accent-green)'
    case 'failed':
    case 'cancelled':
    case 'lost': return 'var(--accent-red)'
    case 'pending': return 'var(--text-secondary)'
    default: return 'var(--text-secondary)'
  }
}

function formatElapsed(startedAt: number, finishedAt: number, isRunning: boolean): string {
  if (!startedAt) return '-'
  const end = isRunning ? Date.now() / 1000 : finishedAt
  const s = Math.max(0, end - startedAt)
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
}

function formatWhen(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// ── Run history panel ──────────────────────────────────────────────────

const runRowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 90px 80px 110px auto',
  alignItems: 'center', gap: 8, padding: '6px 0',
  borderTop: '1px solid var(--border)', fontSize: 11,
}

const btn = (variant: 'danger' | 'muted'): CSSProperties => ({
  padding: '3px 8px', fontSize: 10, fontWeight: 600, fontFamily: 'inherit',
  border: `1px solid ${variant === 'danger' ? 'var(--accent-red)' : 'var(--border)'}`,
  borderRadius: 4, cursor: 'pointer', backgroundColor: 'transparent',
  color: variant === 'danger' ? 'var(--accent-red)' : 'var(--text-secondary)',
})

function RunHistoryPanel({
  runs, loading, onReload, onCancel, onSelect,
}: {
  runs: WorkflowRunSummary[]
  loading: boolean
  onReload: () => void
  onCancel: (runId: string, name: string) => void
  onSelect: (runId: string) => void
}) {
  return (
    <div style={topPanel}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={sectionLabel}>Workflow Runs ({runs.length})</span>
        <button style={refreshBtn} onClick={onReload}>{loading ? '...' : 'Refresh'}</button>
      </div>
      {runs.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
          No workflow runs yet.
        </div>
      )}
      {runs.map((r) => {
        const isRunning = r.status === 'running'
        const stagesSummary = r.stages
          .map((s) => `${s.stage}:${s.status}`)
          .join(' · ')
        return (
          <div key={r.run_id} style={runRowStyle}>
            <div
              onClick={() => onSelect(r.run_id)}
              style={{ cursor: 'pointer' }}
            >
              <div style={{ fontFamily: 'monospace', color: 'var(--text-primary)', fontWeight: 600 }}>
                {r.name}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                {r.run_id} · {stagesSummary}
              </div>
            </div>
            <div style={{ color: statusColor(r.status), fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {r.status}
            </div>
            <div style={{ color: 'var(--text-secondary)' }}>
              {formatElapsed(r.started_at, r.finished_at, isRunning)}
            </div>
            <div style={{ color: 'var(--text-secondary)' }}>
              {formatWhen(r.started_at)}
            </div>
            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
              {isRunning && (
                <button style={btn('danger')} onClick={() => onCancel(r.run_id, r.name)}>Cancel</button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main view ──────────────────────────────────────────────────────────

export function WorkflowsView() {
  const [configs, setConfigs] = useState<WorkflowConfigSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<WorkflowConfigDetail | null>(null)
  const [selectedLoading, setSelectedLoading] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const [runs, setRuns] = useState<WorkflowRunSummary[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [selectedRun, setSelectedRun] = useState<WorkflowRunSummary | null>(null)
  const [logStage, setLogStage] = useState<{ stage: string; runId: string; subject?: string } | null>(null)
  const [analysisInner, setAnalysisInner] = useState<{ runId: string; stages: AnalysisInnerStage[] } | null>(null)

  async function reloadConfigs() {
    setLoading(true)
    try {
      setConfigs(await fetchWorkflowConfigs())
    } finally {
      setLoading(false)
    }
  }

  async function reloadRuns() {
    setRunsLoading(true)
    try {
      setRuns(await fetchWorkflowRuns(true))
    } finally {
      setRunsLoading(false)
    }
  }

  async function select(filename: string) {
    setSelected(null)
    setSelectedLoading(true)
    setRunError(null)
    try {
      setSelected(await fetchWorkflowConfigDetail(filename))
    } finally {
      setSelectedLoading(false)
    }
  }

  async function runNow() {
    if (!selected) return
    setRunning(true)
    setRunError(null)
    try {
      await runWorkflowConfig(selected.filename)
      await reloadRuns()
    } catch (e) {
      setRunError(String(e))
    } finally {
      setRunning(false)
    }
  }

  async function cancel(runId: string, name: string) {
    if (!confirm(`Cancel workflow "${name}"?`)) return
    try {
      await cancelWorkflowRun(runId)
      reloadRuns()
    } catch (e) {
      alert(String(e))
    }
  }

  useEffect(() => { reloadConfigs() }, [])
  useEffect(() => { reloadRuns() }, [])

  // Auto-refresh runs while any are running
  useEffect(() => {
    const hasLive = runs.some((r) => r.status === 'running')
    if (!hasLive) return
    const id = setInterval(reloadRuns, 3000)
    return () => clearInterval(id)
  }, [runs])

  // Auto-select the most relevant run so the graph appears without a
  // click. Preference order: running → most recent (by started_at).
  useEffect(() => {
    if (selectedRun) {
      // Keep the user's current selection in sync with fresh data so
      // the graph updates live after a restart / reload.
      const refreshed = runs.find((r) => r.run_id === selectedRun.run_id)
      if (refreshed && refreshed !== selectedRun) setSelectedRun(refreshed)
      return
    }
    if (runs.length === 0) return
    const running = runs.find((r) => r.status === 'running')
    if (running) {
      setSelectedRun(running)
      return
    }
    // Otherwise pick the newest one (list is already sorted newest-first)
    setSelectedRun(runs[0])
  }, [runs])

  // Auto-refresh selectedRun detail when one is open and running
  useEffect(() => {
    if (!selectedRun) return
    if (selectedRun.status !== 'running') return
    const id = setInterval(async () => {
      try {
        const latest = runs.find((r) => r.run_id === selectedRun.run_id)
        if (latest) setSelectedRun(latest)
      } catch { /* ignore */ }
    }, 3000)
    return () => clearInterval(id)
  }, [selectedRun, runs])

  // Fetch the analysis stage's inner-stage progression while it's
  // the active (running / failed) stage. Poll every 2s to keep the
  // graph's analysis node live. Clears when no analysis run is on.
  useEffect(() => {
    const analysisStage = selectedRun?.stages.find((s) => s.stage === 'analysis')
    const rid = analysisStage?.run_id
    if (!rid || !analysisStage || analysisStage.status === 'pending') {
      setAnalysisInner(null)
      return
    }
    let cancelled = false
    async function load() {
      try {
        const detail = await fetchInFlightRun(rid!)
        if (!cancelled && detail.inner_stages) {
          setAnalysisInner({ runId: rid!, stages: detail.inner_stages })
        }
      } catch { /* ignore */ }
    }
    load()
    if (analysisStage.status !== 'running') return () => { cancelled = true }
    const id = setInterval(load, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [selectedRun?.stages.find((s) => s.stage === 'analysis')?.run_id,
      selectedRun?.stages.find((s) => s.stage === 'analysis')?.status])

  // Merge fetched inner_stages onto the analysis stage before handing
  // to WorkflowGraph so the custom node renders them inline.
  const graphStages = useMemo(() => {
    if (!selectedRun) return []
    if (!analysisInner) return selectedRun.stages
    return selectedRun.stages.map((s) =>
      s.stage === 'analysis' && s.run_id === analysisInner.runId
        ? { ...s, inner_stages: analysisInner.stages }
        : s,
    )
  }, [selectedRun, analysisInner])

  const currentMeta = configs.find((c) => c.filename === selected?.filename)

  return (
    <div>
      <div style={pageTitle}>Workflows</div>
      <div style={pageDesc}>
        End-to-end pipelines — stringing together convert, preproc, autoflatten, and analysis in order.
      </div>

      <RunHistoryPanel
        runs={runs}
        loading={runsLoading}
        onReload={reloadRuns}
        onCancel={cancel}
        onSelect={(run_id) => {
          const r = runs.find((x) => x.run_id === run_id)
          if (r) setSelectedRun(r)
        }}
      />

      {selectedRun && (
        <div style={topPanel}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                {selectedRun.name}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                {selectedRun.run_id} · {selectedRun.status}
                {' · '}
                {formatElapsed(selectedRun.started_at, selectedRun.finished_at, selectedRun.status === 'running')}
              </div>
            </div>
            <button style={btn('muted')} onClick={() => setSelectedRun(null)}>Close</button>
          </div>
          {selectedRun.error && (
            <div style={{
              fontSize: 11, color: 'var(--accent-red)',
              backgroundColor: 'rgba(255, 23, 68, 0.08)',
              border: '1px solid rgba(255, 23, 68, 0.25)',
              borderRadius: 6, padding: '8px 12px', marginBottom: 8,
              fontFamily: 'monospace',
            }}>
              {selectedRun.error}
            </div>
          )}
          <WorkflowGraph
            stages={graphStages}
            height={300}
            onStageClick={(s) => {
              if (!s.run_id) return
              setLogStage({ stage: s.stage, runId: s.run_id })
            }}
          />
          <LiveStageLog
            stages={selectedRun.stages}
            onOpenFull={(stage, runId) => setLogStage({ stage, runId })}
          />
        </div>
      )}

      {logStage && (
        <StageLogModal
          stage={logStage.stage}
          runId={logStage.runId}
          subjectHint={logStage.subject}
          onClose={() => setLogStage(null)}
        />
      )}

      <div style={containerStyle}>
        <div style={sidebar}>
          <div style={sidebarHeader}>
            <span style={sidebarTitle}>Configs ({configs.length})</span>
            <button style={refreshBtn} onClick={reloadConfigs}>
              {loading ? '...' : 'Refresh'}
            </button>
          </div>
          <div style={listStyle}>
            {configs.length === 0 && !loading && (
              <div style={{ padding: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
                No YAMLs under <code>experiments/workflows/</code>. Add one with a top-level <code>workflow:</code> section.
              </div>
            )}
            {configs.map((c) => (
              <div
                key={c.filename}
                style={itemStyle(c.filename === selected?.filename)}
                onClick={() => select(c.filename)}
              >
                <div style={itemName}>{c.filename}</div>
                <div style={itemMeta}>
                  {c.stage_names.join(' → ')} ({c.n_stages})
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={mainPanel}>
          {!selected && !selectedLoading && (
            <div style={emptyState}>
              <div>Select a workflow config to inspect + run.</div>
              <div style={{ fontSize: 11 }}>
                Each YAML must have a top-level <code>workflow:</code> section with an ordered <code>stages:</code> list.
              </div>
            </div>
          )}
          {selectedLoading && <div style={emptyState}>Loading…</div>}
          {selected && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                    {selected.filename}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {selected.path}
                  </div>
                </div>
                <button style={runBtn(running)} disabled={running} onClick={runNow}>
                  {running ? 'Starting…' : 'Run'}
                </button>
              </div>

              {runError && (
                <div style={{
                  fontSize: 11, color: 'var(--accent-red)',
                  backgroundColor: 'rgba(255, 23, 68, 0.08)',
                  border: '1px solid rgba(255, 23, 68, 0.25)',
                  borderRadius: 6, padding: '8px 12px',
                  fontFamily: 'monospace',
                }}>{runError}</div>
              )}

              {currentMeta && (
                <div style={summaryGrid}>
                  <div style={summaryLabel}>Name</div>
                  <div style={summaryValue}>{currentMeta.name}</div>
                  <div style={summaryLabel}>Stages</div>
                  <div style={summaryValue}>{currentMeta.stage_names.join(' → ')}</div>
                </div>
              )}

              <div style={sectionLabel}>YAML</div>
              <pre style={yamlPre}>{selected.yaml_string}</pre>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
