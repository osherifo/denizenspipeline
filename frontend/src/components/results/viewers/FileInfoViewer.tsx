/** Fallback viewer — name, size, type, download link. */
import type { CSSProperties } from 'react'
import { artifactUrl } from '../../../api/client'
import type { ResultViewerProps } from '../registry'
import { viewerCard, viewerHeader, actionLink, viewerBody, formatSize, subtleText } from './common'

const row: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 12,
  color: 'var(--text-primary)',
  padding: '4px 0',
}

export function FileInfoViewer({ artifact, runId }: ResultViewerProps) {
  const url = artifactUrl(runId, artifact.name)
  return (
    <div style={viewerCard}>
      <div style={viewerHeader}>
        <span>{artifact.name}</span>
        <div style={{ display: 'flex', gap: 12 }}>
          <a style={actionLink} href={url} target="_blank" rel="noopener noreferrer">View</a>
          <a style={actionLink} href={url} download>Download</a>
        </div>
      </div>
      <div style={viewerBody}>
        <div style={row}>
          <span style={subtleText}>type</span>
          <span>{artifact.type}</span>
        </div>
        <div style={row}>
          <span style={subtleText}>size</span>
          <span>{formatSize(artifact.size)}</span>
        </div>
        <div style={{ ...row, overflow: 'hidden' }}>
          <span style={subtleText}>path</span>
          <span style={{ ...subtleText, textAlign: 'right', wordBreak: 'break-all' }}>{artifact.path}</span>
        </div>
      </div>
    </div>
  )
}
