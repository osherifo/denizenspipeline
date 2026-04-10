/** Tab 2: Heuristic browser — list, view, edit, and create heuristic files. */
import { useEffect, useState, useCallback, useRef } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { useConvertStore } from '../../stores/convert-store'
import { CodeEditor } from '../editor/CodeEditor'
import type { HeuristicInfo } from '../../api/types'

/* ── Styles ──────────────────────────────────────────────────────────── */

const containerStyle: CSSProperties = {
  display: 'flex',
  gap: 0,
  height: 'calc(100vh - 150px)',
  minHeight: 500,
}

const sidebarStyle: CSSProperties = {
  width: 260,
  minWidth: 260,
  backgroundColor: 'var(--bg-card)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  borderRadius: '8px 0 0 8px',
}

const sidebarHeader: CSSProperties = {
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
}

const titleStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: 'var(--text-primary)',
}

const btnSmall: CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 4,
  cursor: 'pointer',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

const btnPrimary: CSSProperties = {
  ...btnSmall,
  backgroundColor: 'var(--accent-cyan)',
  color: 'var(--bg-primary)',
  border: '1px solid var(--accent-cyan)',
}

const listStyle: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '8px 0',
}

const itemStyle: CSSProperties = {
  padding: '8px 16px',
  cursor: 'pointer',
  fontSize: 12,
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
}

const editorPanelStyle: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  backgroundColor: 'var(--bg-card)',
  borderRadius: '0 8px 8px 0',
}

const editorHeaderStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '8px 16px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  fontSize: 13,
}

const inputStyle: CSSProperties = {
  padding: '4px 8px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
}

const statusBarStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '8px 16px',
  backgroundColor: 'var(--bg-secondary)',
  borderTop: '1px solid var(--border)',
  fontSize: 12,
}

const emptyStyle: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--text-secondary)',
  fontSize: 14,
  gap: 8,
}

const tagStyle: CSSProperties = {
  display: 'inline-block',
  padding: '1px 5px',
  borderRadius: 3,
  fontSize: 9,
  fontWeight: 600,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
}

const overlayStyle: CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
}

const dialogStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '24px',
  width: 360,
  maxWidth: '90vw',
}

/* ── Component ───────────────────────────────────────────────────────── */

export function HeuristicBrowser() {
  const store = useConvertStore()
  const {
    heuristics, heuristicsLoading, loadHeuristics,
    editorCode, editorName, editorDirty, editorLoading, editorSaving,
    editorError, editorSaveSuccess,
    openHeuristic, newHeuristic, setEditorCode, setEditorName,
    saveHeuristic: doSave, deleteHeuristic: doDelete, closeEditor,
  } = store

  const [showNewDialog, setShowNewDialog] = useState(false)

  useEffect(() => { loadHeuristics() }, [])

  const hasEditor = editorCode.length > 0 || editorLoading

  return (
    <div style={containerStyle}>
      {/* ── Sidebar: heuristic list ── */}
      <div style={sidebarStyle}>
        <div style={sidebarHeader}>
          <div style={titleStyle}>Heuristics</div>
          <div style={{ display: 'flex', gap: 4 }}>
            <button style={btnPrimary} onClick={() => setShowNewDialog(true)}>+ New</button>
            <button style={btnSmall} onClick={loadHeuristics} disabled={heuristicsLoading}>
              {heuristicsLoading ? '...' : 'Refresh'}
            </button>
          </div>
        </div>

        <div style={listStyle}>
          {heuristics.length === 0 && !heuristicsLoading && (
            <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text-secondary)' }}>
              No heuristics found.
            </div>
          )}
          {heuristics.map((h) => (
            <div
              key={h.name}
              style={{
                ...itemStyle,
                backgroundColor: editorName === h.name ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
              }}
              onClick={() => openHeuristic(h.name)}
            >
              <div>
                <div style={{ fontWeight: 600, color: editorName === h.name ? 'var(--accent-cyan)' : 'var(--text-primary)' }}>
                  {h.name}
                </div>
                {h.description && (
                  <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {h.description}
                  </div>
                )}
              </div>
              {h.version && <span style={tagStyle}>v{h.version}</span>}
            </div>
          ))}
        </div>
      </div>

      {/* ── Editor panel ── */}
      <div style={editorPanelStyle}>
        {hasEditor ? (
          <>
            {/* Header with name input */}
            <div style={editorHeaderStyle}>
              <label style={{ color: 'var(--text-secondary)' }}>Name:</label>
              <input
                type="text"
                value={editorName}
                onChange={(e) => setEditorName(e.target.value)}
                style={{ ...inputStyle, width: 200 }}
                placeholder="heuristic_name"
              />
              {editorDirty && (
                <span style={{ fontSize: 10, color: 'var(--accent-cyan)', fontWeight: 600 }}>
                  UNSAVED
                </span>
              )}
              <button
                onClick={closeEditor}
                style={{
                  marginLeft: 'auto',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: 16,
                  padding: '2px 6px',
                  lineHeight: 1,
                  borderRadius: 4,
                }}
                onMouseOver={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-input)' }}
                onMouseOut={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.backgroundColor = 'transparent' }}
                title="Close editor"
              >
                &#x2715;
              </button>
            </div>

            {/* Monaco editor */}
            {editorLoading ? (
              <div style={emptyStyle}>Loading...</div>
            ) : (
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <CodeEditor code={editorCode} onChange={setEditorCode} />
              </div>
            )}

            {/* Status bar */}
            <div style={statusBarStyle}>
              {editorError && (
                <span style={{ color: '#ef4444', fontSize: 11 }}>{editorError}</span>
              )}
              {editorSaveSuccess && !editorDirty && (
                <span style={{ color: '#22c55e', fontSize: 11 }}>Saved</span>
              )}
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                {heuristics.some((h) => h.name === editorName) && (
                  <button
                    style={{ ...btnSmall, color: '#ef4444', borderColor: '#ef4444' }}
                    onClick={() => {
                      if (confirm(`Delete heuristic "${editorName}"?`)) {
                        doDelete(editorName)
                      }
                    }}
                  >
                    Delete
                  </button>
                )}
                <button
                  style={btnPrimary}
                  onClick={doSave}
                  disabled={editorSaving || !editorName.trim()}
                >
                  {editorSaving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
          </>
        ) : (
          <div style={emptyStyle}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>{'</>'}</div>
            <div>Select a heuristic or create a new one</div>
            <div style={{ fontSize: 12 }}>
              Click a heuristic in the sidebar or press "+ New"
            </div>
          </div>
        )}
      </div>

      {/* ── New heuristic dialog ── */}
      {showNewDialog && (
        <NewHeuristicDialog
          onSubmit={(name) => {
            setShowNewDialog(false)
            newHeuristic(name)
          }}
          onClose={() => setShowNewDialog(false)}
        />
      )}
    </div>
  )
}


/* ── New Heuristic Dialog ────────────────────────────────────────────── */

function NewHeuristicDialog({
  onSubmit,
  onClose,
}: {
  onSubmit: (name: string) => void
  onClose: () => void
}) {
  const [name, setName] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    onSubmit(name.trim())
  }

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={dialogStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 16 }}>
          New Heuristic from Template
        </div>
        <form onSubmit={handleSubmit}>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
            Heuristic Name
          </label>
          <input
            style={{ ...inputStyle, width: '100%', boxSizing: 'border-box', marginBottom: 16 }}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my_study"
            autoFocus
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button type="button" style={btnSmall} onClick={onClose}>Cancel</button>
            <button type="submit" style={btnPrimary} disabled={!name.trim()}>Create</button>
          </div>
        </form>
      </div>
    </div>
  )
}
