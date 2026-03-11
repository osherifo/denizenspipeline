/** Tab 2: Left sidebar — manifest list + right panel — manifest details. */
import { useEffect, useState } from 'react'
import { usePreprocStore } from '../../stores/preproc-store'
import { ManifestDetail } from './ManifestDetail'

const containerStyle: React.CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 56px - 48px - 80px)',
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
}

const sidebarStyle: React.CSSProperties = {
  width: 240,
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const sidebarHeader: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
}

const sidebarTitle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const listStyle: React.CSSProperties = {
  flex: 1,
  overflowY: 'auto',
}

const itemStyle = (active: boolean): React.CSSProperties => ({
  padding: '10px 16px',
  cursor: 'pointer',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
  borderBottom: '1px solid var(--border)',
})

const mainPanel: React.CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '20px 24px',
}

const emptyState: React.CSSProperties = {
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

const rescanBtn: React.CSSProperties = {
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

export function ManifestBrowser() {
  const {
    manifests, manifestsLoading, selectedSubject, selectedManifest,
    loadManifests, rescan, selectManifest,
  } = usePreprocStore()

  useEffect(() => { loadManifests() }, [])

  return (
    <div style={containerStyle}>
      <div style={sidebarStyle}>
        <div style={sidebarHeader}>
          <span style={sidebarTitle}>Manifests ({manifests.length})</span>
          <button style={rescanBtn} onClick={rescan} disabled={manifestsLoading}>
            {manifestsLoading ? '...' : 'Rescan'}
          </button>
        </div>
        <div style={listStyle}>
          {manifests.map((m) => (
            <div
              key={m.subject}
              style={itemStyle(selectedSubject === m.subject)}
              onClick={() => selectManifest(m.subject)}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                sub-{m.subject}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                {m.backend} {m.backend_version} &middot; {m.n_runs} runs
              </div>
            </div>
          ))}
          {manifests.length === 0 && !manifestsLoading && (
            <div style={{ padding: 16, fontSize: 11, color: 'var(--text-secondary)' }}>
              No manifests found. Use the Collect tab to create one, or check --derivatives-dir.
            </div>
          )}
        </div>
      </div>

      <div style={mainPanel}>
        {selectedManifest ? (
          <ManifestDetail manifest={selectedManifest} />
        ) : (
          <div style={emptyState}>
            <div style={{ fontSize: 28, color: 'var(--text-secondary)' }}>{'\u2630'}</div>
            <div>Select a manifest to view details</div>
          </div>
        )}
      </div>
    </div>
  )
}
