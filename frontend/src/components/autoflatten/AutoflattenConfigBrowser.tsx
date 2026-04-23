/** Tab: browse autoflatten YAML configs and run them. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { AutoflattenConfigSummary, AutoflattenConfigDetail } from '../../api/types'
import {
  fetchAutoflattenConfigs,
  fetchAutoflattenConfigDetail,
  runAutoflattenConfig,
} from '../../api/client'
import { useAutoflattenStore } from '../../stores/autoflatten-store'
import { AutoflattenProgress } from './AutoflattenProgress'
import { AutoflattenInFlightRuns } from './AutoflattenInFlightRuns'

const containerStyle: CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 48px - 280px)',
  minHeight: 320,
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
}

const sidebarStyle: CSSProperties = {
  width: 280,
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const sidebarHeader: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
}

const sidebarTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const refreshBtn: CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
}

const listStyle: CSSProperties = { flex: 1, overflowY: 'auto' }

const itemStyle = (active: boolean): CSSProperties => ({
  padding: '10px 16px',
  cursor: 'pointer',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
  borderBottom: '1px solid var(--border)',
})

const itemName: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: 2,
  fontFamily: 'monospace',
}

const itemMeta: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
}

const mainPanel: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '20px 24px',
  display: 'flex',
  flexDirection: 'column',
  gap: 16,
}

const emptyState: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--text-secondary)',
  fontSize: 13,
  gap: 8,
  height: '100%',
}

const runBtn = (disabled: boolean): CSSProperties => ({
  padding: '8px 20px',
  fontSize: 12,
  fontWeight: 700,
  fontFamily: 'inherit',
  border: `1px solid ${disabled ? 'var(--border)' : 'var(--accent-cyan)'}`,
  borderRadius: 6,
  cursor: disabled ? 'not-allowed' : 'pointer',
  backgroundColor: disabled ? 'transparent' : 'rgba(0, 229, 255, 0.1)',
  color: disabled ? 'var(--text-secondary)' : 'var(--accent-cyan)',
  textTransform: 'uppercase',
  letterSpacing: 1,
})

const summaryGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '120px 1fr',
  gap: '6px 16px',
  fontSize: 12,
  padding: '12px 0',
}

const summaryLabel: CSSProperties = {
  color: 'var(--text-secondary)',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  fontSize: 10,
}

const summaryValue: CSSProperties = {
  color: 'var(--text-primary)',
  fontFamily: 'monospace',
  wordBreak: 'break-all',
}

const yamlPre: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '12px 14px',
  fontSize: 11,
  lineHeight: 1.6,
  fontFamily: 'monospace',
  color: 'var(--text-primary)',
  overflow: 'auto',
  maxHeight: 420,
  whiteSpace: 'pre',
  border: '1px solid var(--border)',
}

const sectionLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 4,
}

export function AutoflattenConfigBrowser() {
  const [configs, setConfigs] = useState<AutoflattenConfigSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<AutoflattenConfigDetail | null>(null)
  const [selectedLoading, setSelectedLoading] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)

  // Reuse the store's live event pipeline by attaching via its WebSocket
  // plumbing — we call the existing /autoflatten/configs/{f}/run endpoint
  // which produces a run_id compatible with connectAutoflattenWs.
  const {
    running, runEvents, runStartTime, runError: storeRunError,
    clearRun, attachToRun,
  } = useAutoflattenStore()

  async function reload() {
    setLoading(true)
    try {
      const list = await fetchAutoflattenConfigs()
      setConfigs(list)
    } finally {
      setLoading(false)
    }
  }

  async function select(filename: string) {
    setSelected(null)
    setSelectedLoading(true)
    try {
      const detail = await fetchAutoflattenConfigDetail(filename)
      setSelected(detail)
    } finally {
      setSelectedLoading(false)
    }
  }

  async function runNow() {
    if (!selected) return
    setRunError(null)
    try {
      const r = await runAutoflattenConfig(selected.filename)
      attachToRun(r.run_id)
    } catch (e) {
      setRunError(String(e))
    }
  }

  useEffect(() => { reload() }, [])

  return (
    <>
      <AutoflattenInFlightRuns />
      <div style={containerStyle}>
        <div style={sidebarStyle}>
          <div style={sidebarHeader}>
            <span style={sidebarTitle}>Configs ({configs.length})</span>
            <button style={refreshBtn} onClick={reload}>{loading ? '...' : 'Refresh'}</button>
          </div>
          <div style={listStyle}>
            {configs.length === 0 && !loading && (
              <div style={{ padding: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
                No YAMLs found. Add one under <code>experiments/autoflatten/</code> with a top-level <code>autoflatten:</code> section.
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
                  {c.subject} · {c.backend} · {c.hemispheres}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={mainPanel}>
          {!selected && !selectedLoading && (
            <div style={emptyState}>
              <div>Select a config on the left.</div>
              <div style={{ fontSize: 11 }}>
                Each YAML must have a top-level <code>autoflatten:</code> section.
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
                  {running ? 'Running…' : 'Run'}
                </button>
              </div>

              {runError && (
                <div style={{
                  fontSize: 11, padding: '8px 12px', borderRadius: 6,
                  backgroundColor: 'rgba(255, 23, 68, 0.08)',
                  border: '1px solid rgba(255, 23, 68, 0.25)',
                  color: 'var(--accent-red)', fontFamily: 'monospace',
                }}>{runError}</div>
              )}

              {(() => {
                const summary = configs.find((c) => c.filename === selected.filename)
                if (!summary) return null
                return (
                  <div style={summaryGrid}>
                    <div style={summaryLabel}>Subject</div>
                    <div style={summaryValue}>{summary.subject || '-'}</div>
                    <div style={summaryLabel}>Subjects dir</div>
                    <div style={summaryValue}>{summary.subjects_dir || '-'}</div>
                    <div style={summaryLabel}>Hemispheres</div>
                    <div style={summaryValue}>{summary.hemispheres}</div>
                    <div style={summaryLabel}>Backend</div>
                    <div style={summaryValue}>{summary.backend}</div>
                    {summary.output_dir && (
                      <>
                        <div style={summaryLabel}>Output dir</div>
                        <div style={summaryValue}>{summary.output_dir}</div>
                      </>
                    )}
                  </div>
                )
              })()}

              <div style={sectionLabel}>YAML</div>
              <pre style={yamlPre}>{selected.yaml_string}</pre>
            </>
          )}
        </div>
      </div>

      {(running || runEvents.length > 0 || storeRunError) && (
        <AutoflattenProgress
          events={runEvents}
          startTime={runStartTime}
          running={running}
          error={storeRunError}
          onDismiss={clearRun}
        />
      )}
    </>
  )
}
