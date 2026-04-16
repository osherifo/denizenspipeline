/** Generic JSON viewer — pretty-print fallback for .json artifacts. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { artifactUrl } from '../../../api/client'
import type { ResultViewerProps } from '../registry'
import { viewerCard, viewerHeader, actionLink } from './common'

const pre: CSSProperties = {
  margin: 0,
  padding: '12px 14px',
  fontSize: 11,
  lineHeight: 1.5,
  fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  color: 'var(--text-primary)',
  maxHeight: 400,
  overflow: 'auto',
  whiteSpace: 'pre',
  backgroundColor: 'var(--bg-input)',
}

export function JsonViewer({ artifact, runId }: ResultViewerProps) {
  const url = artifactUrl(runId, artifact.name)
  const [text, setText] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.text()
      })
      .then((t) => {
        if (cancelled) return
        try {
          setText(JSON.stringify(JSON.parse(t), null, 2))
        } catch {
          setText(t) // show as-is if parse fails
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
    return () => {
      cancelled = true
    }
  }, [url])

  return (
    <div style={viewerCard}>
      <div style={viewerHeader}>
        <span>{artifact.name}</span>
        <div style={{ display: 'flex', gap: 12 }}>
          <a style={actionLink} href={url} target="_blank" rel="noopener noreferrer">Open</a>
          <a style={actionLink} href={url} download>Download</a>
        </div>
      </div>
      {error
        ? <div style={{ ...pre, color: 'var(--accent-red)' }}>Failed to load: {error}</div>
        : <pre style={pre}>{text}</pre>}
    </div>
  )
}
