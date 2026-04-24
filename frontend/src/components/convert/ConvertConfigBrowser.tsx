/** Tab: browse saved convert YAML configs and run them. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { SavedConvertConfig, SavedConvertConfigDetail } from '../../api/types'
import {
  fetchSavedConvertConfigs,
  fetchSavedConvertConfig,
  runSavedConvertConfig,
  deleteSavedConvertConfig,
} from '../../api/client'
import { ConvertInFlightRuns } from './ConvertInFlightRuns'

const containerStyle: CSSProperties = {
  display: 'flex',
  // Leave room for the tab bar + in-flight panel above.
  height: 'calc(100vh - 48px - 220px)',
  minHeight: 320,
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
}

const sidebarStyle: CSSProperties = {
  width: 300,
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

const typeBadge = (kind: string, isLegacy: boolean): CSSProperties => ({
  display: 'inline-block',
  padding: '1px 6px',
  fontSize: 9,
  fontWeight: 700,
  borderRadius: 3,
  marginRight: 6,
  letterSpacing: 0.5,
  color: kind === 'batch' ? 'var(--accent-cyan)' : 'var(--accent-green)',
  border: `1px solid ${kind === 'batch' ? 'var(--accent-cyan)' : 'var(--accent-green)'}`,
  opacity: isLegacy ? 0.6 : 1,
})

const legacyTag: CSSProperties = {
  marginLeft: 6,
  fontSize: 9,
  fontWeight: 600,
  color: 'var(--accent-yellow, #e2a832)',
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

const btn = (variant: 'primary' | 'muted' | 'danger', disabled = false): CSSProperties => ({
  padding: '8px 20px',
  fontSize: 12,
  fontWeight: 700,
  fontFamily: 'inherit',
  border: `1px solid ${
    variant === 'primary' ? 'var(--accent-cyan)' :
    variant === 'danger' ? 'var(--accent-red)' :
    'var(--border)'
  }`,
  borderRadius: 6,
  cursor: disabled ? 'not-allowed' : 'pointer',
  backgroundColor:
    variant === 'primary' ? 'rgba(0, 229, 255, 0.1)' :
    'transparent',
  color:
    variant === 'primary' ? 'var(--accent-cyan)' :
    variant === 'danger' ? 'var(--accent-red)' :
    'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  opacity: disabled ? 0.5 : 1,
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

const resultBox = (ok: boolean): CSSProperties => ({
  fontSize: 11,
  padding: '8px 12px',
  borderRadius: 6,
  backgroundColor: ok ? 'rgba(0, 230, 118, 0.08)' : 'rgba(255, 23, 68, 0.08)',
  border: `1px solid ${ok ? 'rgba(0, 230, 118, 0.25)' : 'rgba(255, 23, 68, 0.25)'}`,
  color: ok ? 'var(--accent-green)' : 'var(--accent-red)',
  fontFamily: 'monospace',
})

export function ConvertConfigBrowser() {
  const [configs, setConfigs] = useState<SavedConvertConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<SavedConvertConfigDetail | null>(null)
  const [selectedLoading, setSelectedLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [lastResult, setLastResult] = useState<
    { ok: boolean; message: string } | null
  >(null)

  async function reload() {
    setLoading(true)
    try {
      const list = await fetchSavedConvertConfigs()
      setConfigs(list)
    } finally {
      setLoading(false)
    }
  }

  async function select(filename: string) {
    setSelected(null)
    setSelectedLoading(true)
    setLastResult(null)
    try {
      const detail = await fetchSavedConvertConfig(filename)
      setSelected(detail)
    } catch (e) {
      setLastResult({ ok: false, message: String(e) })
    } finally {
      setSelectedLoading(false)
    }
  }

  async function runNow() {
    if (!selected) return
    setRunning(true)
    setLastResult(null)
    try {
      const r = await runSavedConvertConfig(selected.filename)
      const id = r.kind === 'batch' ? r.batch_id : r.run_id
      setLastResult({
        ok: true,
        message: `${r.kind} started — id=${id}. Watch progress in the Convert or Batch tab.`,
      })
    } catch (e) {
      setLastResult({ ok: false, message: String(e) })
    } finally {
      setRunning(false)
    }
  }

  async function remove(filename: string) {
    if (!confirm(`Delete ${filename}?`)) return
    try {
      await deleteSavedConvertConfig(filename)
      if (selected?.filename === filename) setSelected(null)
      reload()
    } catch (e) {
      alert(String(e))
    }
  }

  useEffect(() => { reload() }, [])

  const currentMeta = configs.find((c) => c.filename === selected?.filename)

  return (
    <>
      <ConvertInFlightRuns />
      <div style={containerStyle}>
      <div style={sidebarStyle}>
        <div style={sidebarHeader}>
          <span style={sidebarTitle}>Configs ({configs.length})</span>
          <button style={btn('muted')} onClick={reload}>{loading ? '...' : 'Refresh'}</button>
        </div>
        <div style={listStyle}>
          {configs.length === 0 && !loading && (
            <div style={{ padding: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
              No saved configs yet. Save one from the Convert or Batch tab's Save button.
            </div>
          )}
          {configs.map((c) => {
            const isLegacy = Boolean((c as SavedConvertConfig & { legacy?: boolean }).legacy)
            return (
              <div
                key={c.filename}
                style={itemStyle(c.filename === selected?.filename)}
                onClick={() => select(c.filename)}
              >
                <div style={itemName}>
                  <span style={typeBadge(c.type, isLegacy)}>{c.type}</span>
                  {c.name || c.filename}
                  {isLegacy && <span style={legacyTag}>LEGACY</span>}
                </div>
                <div style={itemMeta}>
                  {c.filename}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div style={mainPanel}>
        {!selected && !selectedLoading && (
          <div style={emptyState}>
            <div>Select a config on the left.</div>
            <div style={{ fontSize: 11 }}>Saved configs are YAML files under <code>./experiments/convert/</code>.</div>
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
                  {(selected as SavedConvertConfigDetail & { path?: string }).path || ''}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button style={btn('primary', running)} disabled={running} onClick={runNow}>
                  {running ? 'Starting…' : 'Run'}
                </button>
                <button style={btn('danger')} onClick={() => remove(selected.filename)}>Delete</button>
              </div>
            </div>

            {lastResult && <div style={resultBox(lastResult.ok)}>{lastResult.message}</div>}

            {currentMeta && (
              <div style={summaryGrid}>
                <div style={summaryLabel}>Type</div>
                <div style={summaryValue}>{currentMeta.type}</div>
                <div style={summaryLabel}>Heuristic</div>
                <div style={summaryValue}>{currentMeta.heuristic || '-'}</div>
                <div style={summaryLabel}>BIDS dir</div>
                <div style={summaryValue}>{currentMeta.bids_dir || '-'}</div>
                {currentMeta.type === 'single' && (
                  <>
                    <div style={summaryLabel}>Subject</div>
                    <div style={summaryValue}>{(currentMeta as SavedConvertConfig & { subject?: string }).subject || '-'}</div>
                  </>
                )}
                {currentMeta.type === 'batch' && (
                  <>
                    <div style={summaryLabel}>Jobs</div>
                    <div style={summaryValue}>{(currentMeta as SavedConvertConfig & { n_jobs?: number }).n_jobs ?? '-'}</div>
                  </>
                )}
                {currentMeta.description && (
                  <>
                    <div style={summaryLabel}>Description</div>
                    <div style={summaryValue}>{currentMeta.description}</div>
                  </>
                )}
              </div>
            )}

            <div style={sectionLabel}>YAML</div>
            <pre style={yamlPre}>{selected.yaml_string}</pre>
          </>
        )}
      </div>
    </div>
    </>
  )
}
