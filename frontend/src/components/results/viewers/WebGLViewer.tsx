/** WebGL viewer — iframe embed for pycortex interactive viewer. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { artifactUrl } from '../../../api/client'
import type { ResultViewerProps } from '../registry'
import { viewerCard, viewerHeader, actionLink } from './common'

const iframeStyle: CSSProperties = {
  display: 'block',
  width: '100%',
  height: 560,
  border: 0,
  backgroundColor: '#000',
}

const placeholder: CSSProperties = {
  padding: '32px 16px',
  textAlign: 'center',
  color: 'var(--text-secondary)',
  fontSize: 12,
  backgroundColor: '#000',
}

const btn: CSSProperties = {
  padding: '6px 14px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 5,
  cursor: 'pointer',
  border: 'none',
  backgroundColor: 'var(--accent-cyan)',
  color: '#000',
}

export function WebGLViewer({ artifact, runId }: ResultViewerProps) {
  const [loaded, setLoaded] = useState(false)

  // The artifact is typically a directory like "webgl_viewer" — the real
  // entry point is index.html inside it.
  const entryName =
    artifact.name.endsWith('.html') ? artifact.name : `${artifact.name}/index.html`
  const url = artifactUrl(runId, entryName)

  return (
    <div style={viewerCard}>
      <div style={viewerHeader}>
        <span>WebGL viewer — {artifact.name}</span>
        <div style={{ display: 'flex', gap: 12 }}>
          <a style={actionLink} href={url} target="_blank" rel="noopener noreferrer">Open in new tab</a>
        </div>
      </div>
      {loaded ? (
        <iframe
          style={iframeStyle}
          src={url}
          title={artifact.name}
          sandbox="allow-scripts allow-same-origin allow-popups"
        />
      ) : (
        <div style={placeholder}>
          <div style={{ marginBottom: 12 }}>
            WebGL viewers can be heavy (up to 30 MB). Click to load inline, or open in a new tab.
          </div>
          <button style={btn} onClick={() => setLoaded(true)}>Load viewer</button>
        </div>
      )}
    </div>
  )
}
