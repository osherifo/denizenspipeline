/** Show the YAML config that produced a given run.
 *
 * The subject / group / study summaries each carry the resolved
 * ``config_snapshot`` (the dict the orchestrator actually fed to the
 * pipeline, with inheritance / env-var / defaults all expanded). We
 * dump it back to YAML for display so the user can see exactly which
 * version of the config produced this run — handy when comparing
 * timestamped reruns of the same config or chasing why "the same"
 * YAML behaved differently.
 *
 * The editor is read-only. A small toolbar offers Copy and Download.
 */

import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import Editor from '@monaco-editor/react'

import { dumpYaml } from './yamlDiff'
import { useThemeStore } from '../../stores/theme-store'


const backdrop: CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999,
}

const card: CSSProperties = {
  width: '80vw', maxWidth: 1100, height: '85vh',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  display: 'flex',
  flexDirection: 'column',
  padding: 12,
}

const header: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8,
}

const titleStyle: CSSProperties = {
  fontSize: 14, fontWeight: 700, color: 'var(--text-primary)',
}

const subtitleStyle: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)',
}

const btn: CSSProperties = {
  padding: '4px 12px',
  fontSize: 12,
  border: '1px solid var(--border)',
  borderRadius: 4,
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

const editorBox: CSSProperties = {
  flex: 1,
  border: '1px solid var(--border)',
  borderRadius: 6,
  overflow: 'hidden',
}


interface Props {
  /** Already-resolved config dict from the run summary. */
  snapshot: Record<string, unknown> | null | undefined
  /** Dialog title — e.g. ``"sub01/20260605T122659Z — config snapshot"``. */
  title: string
  /** Suggested filename for the Download button. */
  downloadName?: string
  onClose: () => void
}


export function ConfigSnapshotModal({
  snapshot, title, downloadName, onClose,
}: Props) {
  // Monaco ships its own themes; follow the app theme.
  const monacoTheme = useThemeStore((s) => s.mode) === 'light' ? 'light' : 'vs-dark'
  const [justCopied, setJustCopied] = useState(false)

  // Strip internal bookkeeping keys (anything starting with '_') and
  // dump to YAML once per render — the snapshot is normally small
  // (subject scope) but a study snapshot can have nested groups, so
  // memoising keeps the modal snappy on repeated re-renders.
  const yaml = useMemo(() => {
    if (!snapshot) return '# (no config snapshot recorded for this run)'
    const clean: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(snapshot)) {
      if (k.startsWith('_')) continue
      clean[k] = v
    }
    const text = dumpYaml(clean)
    return text || '# (snapshot is empty)'
  }, [snapshot])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(yaml)
      setJustCopied(true)
      window.setTimeout(() => setJustCopied(false), 1200)
    } catch {
      /* clipboard blocked — silent fail */
    }
  }

  const handleDownload = () => {
    const blob = new Blob([yaml], { type: 'application/x-yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = downloadName || 'config_snapshot.yaml'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    // Defer revoke so the browser has time to start the download —
    // revoking synchronously after click() intermittently cancels the
    // download in some browsers (Safari especially).
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <div style={titleStyle}>{title}</div>
          <div style={subtitleStyle}>resolved config (defaults + env vars expanded)</div>
          <div style={{ flex: 1 }} />
          <button
            style={{
              ...btn,
              ...(justCopied
                ? { background: 'rgba(0, 230, 118, 0.15)', color: 'var(--accent-green)' }
                : {}),
            }}
            onClick={handleCopy}
            title="Copy YAML to clipboard"
          >
            {justCopied ? '✓ Copied' : 'Copy'}
          </button>
          <button style={btn} onClick={handleDownload} title="Download as a .yaml file">
            Download
          </button>
          <button style={btn} onClick={onClose}>Close</button>
        </div>

        <div style={editorBox}>
          <Editor
            height="100%"
            language="yaml"
            theme={monacoTheme}
            value={yaml}
            options={{
              readOnly: true,
              domReadOnly: true,
              minimap: { enabled: false },
              fontSize: 12,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              wordWrap: 'on',
              padding: { top: 8 },
            }}
          />
        </div>
      </div>
    </div>
  )
}
