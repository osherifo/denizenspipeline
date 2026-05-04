import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { CodeEditor } from '../components/editor/CodeEditor'
import { fetchModuleCode, reloadModule, saveModuleCode } from '../api/client'

interface ModuleSourceEditorProps {
  category: string
  name: string
  onBack: () => void
}

const rootStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  // Inside App's contentStyle (padded, overflow-auto) — fill what's there
  // rather than fight viewport height.
  minHeight: 'calc(100vh - 96px)',
  margin: '-24px -32px',
  backgroundColor: 'var(--bg-primary)',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 16,
  padding: '12px 16px',
  borderBottom: '1px solid var(--border)',
  backgroundColor: 'var(--bg-secondary)',
  position: 'sticky',
  top: 0,
  zIndex: 5,
}

const backButtonStyle: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '6px 12px',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: 12,
  fontFamily: 'inherit',
}

const titleStyle: CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  color: 'var(--text-primary)',
}

const categoryBadgeStyle: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 4,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
  letterSpacing: 0.5,
  textTransform: 'uppercase',
}

const pathStyle: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  fontFamily: 'monospace',
  marginLeft: 'auto',
  maxWidth: '50%',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  direction: 'rtl',
  textAlign: 'left',
}

const editorWrapStyle: CSSProperties = {
  height: '70vh',
  minHeight: 480,
}

const footerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 12,
  padding: '10px 16px',
  borderTop: '1px solid var(--border)',
  backgroundColor: 'var(--bg-secondary)',
}

const saveButtonStyle = (disabled: boolean): CSSProperties => ({
  background: disabled ? 'var(--bg-card)' : 'var(--accent-cyan)',
  border: 'none',
  color: disabled ? 'var(--text-secondary)' : '#000',
  padding: '8px 18px',
  borderRadius: 4,
  cursor: disabled ? 'not-allowed' : 'pointer',
  fontSize: 12,
  fontWeight: 700,
  fontFamily: 'inherit',
  letterSpacing: 0.5,
  textTransform: 'uppercase',
})

const statusStyle = (kind: 'idle' | 'ok' | 'err' | 'partial' | 'dirty'): CSSProperties => ({
  fontSize: 11,
  color:
    kind === 'ok' ? 'var(--accent-green)'
    : kind === 'err' ? 'var(--accent-red)'
    : kind === 'partial' ? 'var(--accent-yellow)'
    : kind === 'dirty' ? 'var(--accent-yellow)'
    : 'var(--text-secondary)',
})

const messageStyle: CSSProperties = {
  flex: 1,
  fontSize: 13,
  color: 'var(--text-secondary)',
  textAlign: 'center',
  padding: 40,
}

const errorStyle: CSSProperties = {
  ...messageStyle,
  color: 'var(--accent-red)',
}

const warnBannerStyle: CSSProperties = {
  fontSize: 11,
  color: 'var(--accent-yellow)',
  padding: '8px 16px',
  borderBottom: '1px solid var(--border)',
  backgroundColor: 'rgba(255, 214, 0, 0.06)',
}

const tracebackStyle: CSSProperties = {
  marginTop: 6,
  padding: 8,
  fontFamily: 'monospace',
  fontSize: 10,
  color: 'var(--accent-red)',
  backgroundColor: 'rgba(255, 23, 68, 0.06)',
  border: '1px solid rgba(255, 23, 68, 0.3)',
  borderRadius: 4,
  whiteSpace: 'pre-wrap',
  maxHeight: 160,
  overflow: 'auto',
}

export function ModuleSourceEditor({ category, name, onBack }: ModuleSourceEditorProps) {
  const [originalCode, setOriginalCode] = useState<string | null>(null)
  const [code, setCode] = useState<string>('')
  const [path, setPath] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<
    { kind: 'ok' | 'err' | 'partial'; text: string; traceback?: string } | null
  >(null)

  // Scroll back to top when entering the editor (the module list may have
  // been scrolled down when "Edit source" was clicked).
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    fetchModuleCode(category, name)
      .then((c) => {
        if (cancelled) return
        setOriginalCode(c.code)
        setCode(c.code)
        setPath(c.path)
      })
      .catch((e) => {
        if (cancelled) return
        setLoadError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [category, name])

  const dirty = originalCode != null && code !== originalCode

  function handleBack() {
    if (dirty && !window.confirm('You have unsaved changes. Discard them?')) return
    onBack()
  }

  async function handleSave() {
    if (!dirty || saving) return
    setSaving(true)
    setSaveMessage(null)
    let saved = false
    try {
      const sr = await saveModuleCode(category, name, code)
      saved = true
      setOriginalCode(code)
      const rr = await reloadModule(category, name)
      setSaveMessage({
        kind: 'ok',
        text: `Saved ${sr.bytes} bytes & reloaded ${rr.module} — new runs use the updated code`,
      })
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e)
      let text = raw
      let tb: string | undefined
      try {
        const parsed = JSON.parse(raw.replace(/^[^{]*/, '')) as {
          detail?: string | { message?: string; traceback?: string }
        }
        if (typeof parsed.detail === 'string') {
          text = parsed.detail
        } else if (parsed.detail && typeof parsed.detail === 'object') {
          if (parsed.detail.message) text = parsed.detail.message
          if (parsed.detail.traceback) tb = parsed.detail.traceback
        }
      } catch { /* not JSON */ }
      setSaveMessage({
        kind: saved ? 'partial' : 'err',
        text: saved
          ? `Saved on disk but reload failed: ${text}. Old code still running.`
          : `Save failed: ${text}`,
        traceback: tb,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={rootStyle}>
      <div style={headerStyle}>
        <button type="button" style={backButtonStyle} onClick={handleBack}>
          ← Back
        </button>
        <span style={categoryBadgeStyle}>{category}</span>
        <span style={titleStyle}>{name}</span>
        <span style={pathStyle} title={path}>{path}</span>
      </div>
      <div style={warnBannerStyle}>
        Save & Reload writes the file and re-imports it in the running
        server, so subsequent runs use the new code. In-flight runs keep
        the old code until they finish.
      </div>
      {loading && <div style={messageStyle}>Loading source…</div>}
      {loadError && <div style={errorStyle}>Error: {loadError}</div>}
      {!loading && !loadError && (
        <>
          <div style={editorWrapStyle}>
            <CodeEditor code={code} onChange={setCode} />
          </div>
          <div style={footerStyle}>
            <button
              type="button"
              style={saveButtonStyle(!dirty || saving)}
              onClick={handleSave}
              disabled={!dirty || saving}
            >
              {saving ? 'Saving & Reloading…' : 'Save & Reload'}
            </button>
            <div style={{ flex: 1, minWidth: 0 }}>
              {saveMessage ? (
                <>
                  <div style={statusStyle(saveMessage.kind)}>{saveMessage.text}</div>
                  {saveMessage.traceback && (
                    <div style={tracebackStyle}>{saveMessage.traceback}</div>
                  )}
                </>
              ) : dirty ? (
                <span style={statusStyle('dirty')}>Unsaved changes</span>
              ) : (
                <span style={statusStyle('idle')}>Saved</span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
