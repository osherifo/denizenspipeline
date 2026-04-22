/** Tab: browse preproc YAML configs and run them. */
import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'
import { PreprocProgress } from './PreprocProgress'

const containerStyle: CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 48px - 80px)',
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

const rescanBtn: CSSProperties = {
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

const detailHeader: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
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

export function PreprocConfigBrowser() {
  const {
    preprocConfigs,
    preprocConfigsLoading,
    selectedPreprocConfig,
    selectedPreprocConfigLoading,
    loadPreprocConfigs,
    selectPreprocConfig,
    runPreprocConfig,
    runId,
    runEvents,
    runStartTime,
    runError,
    running,
    clearRun,
  } = usePreprocStore()

  useEffect(() => {
    loadPreprocConfigs()
  }, [loadPreprocConfigs])

  const selectedFilename = selectedPreprocConfig?.filename

  return (
    <>
      <div style={containerStyle}>
        <div style={sidebarStyle}>
          <div style={sidebarHeader}>
            <span style={sidebarTitle}>Configs ({preprocConfigs.length})</span>
            <button style={rescanBtn} onClick={() => loadPreprocConfigs()}>
              {preprocConfigsLoading ? '...' : 'Refresh'}
            </button>
          </div>
          <div style={listStyle}>
            {preprocConfigs.length === 0 && !preprocConfigsLoading && (
              <div style={{ padding: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
                No YAMLs found. Add one under <code>experiments/preproc/</code> with a top-level <code>preproc:</code> section.
              </div>
            )}
            {preprocConfigs.map((cfg) => (
              <div
                key={cfg.filename}
                style={itemStyle(cfg.filename === selectedFilename)}
                onClick={() => selectPreprocConfig(cfg.filename)}
              >
                <div style={itemName}>{cfg.filename}</div>
                <div style={itemMeta}>
                  {cfg.subject} · {cfg.backend}{cfg.mode ? ` · ${cfg.mode}` : ''}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={mainPanel}>
          {!selectedPreprocConfig && !selectedPreprocConfigLoading && (
            <div style={emptyState}>
              <div>Select a config on the left.</div>
              <div style={{ fontSize: 11 }}>
                Each YAML must have a top-level <code>preproc:</code> section.
              </div>
            </div>
          )}
          {selectedPreprocConfigLoading && (
            <div style={emptyState}>Loading…</div>
          )}
          {selectedPreprocConfig && (
            <>
              <div style={detailHeader}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'monospace' }}>
                    {selectedPreprocConfig.filename}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {selectedPreprocConfig.path}
                  </div>
                </div>
                <button
                  style={runBtn(running)}
                  disabled={running}
                  onClick={() => runPreprocConfig(selectedPreprocConfig.filename)}
                >
                  {running ? 'Running…' : 'Run'}
                </button>
              </div>

              <div style={summaryGrid}>
                {(() => {
                  const summary = preprocConfigs.find((c) => c.filename === selectedPreprocConfig.filename)
                  if (!summary) return null
                  return (
                    <>
                      <div style={summaryLabel}>Subject</div>
                      <div style={summaryValue}>{summary.subject || '-'}</div>
                      <div style={summaryLabel}>Backend</div>
                      <div style={summaryValue}>{summary.backend || '-'}</div>
                      <div style={summaryLabel}>Mode</div>
                      <div style={summaryValue}>{summary.mode || '-'}</div>
                      <div style={summaryLabel}>BIDS dir</div>
                      <div style={summaryValue}>{summary.bids_dir || '-'}</div>
                      <div style={summaryLabel}>Output dir</div>
                      <div style={summaryValue}>{summary.output_dir || '-'}</div>
                      <div style={summaryLabel}>Container</div>
                      <div style={summaryValue}>{summary.container || '-'}</div>
                    </>
                  )
                })()}
              </div>

              <div style={sectionLabel}>YAML</div>
              <pre style={yamlPre}>{selectedPreprocConfig.yaml_string}</pre>
            </>
          )}
        </div>
      </div>

      {(runId || running || runError) && (
        <PreprocProgress
          events={runEvents}
          startTime={runStartTime}
          running={running}
          error={runError}
          onDismiss={clearRun}
        />
      )}
    </>
  )
}
