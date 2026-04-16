/** Image viewer — thumbnail with click-to-zoom fullscreen overlay. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { artifactUrl } from '../../../api/client'
import type { ResultViewerProps } from '../registry'
import { viewerCard, viewerHeader, actionLink, formatSize } from './common'

const imgContainer: CSSProperties = {
  backgroundColor: '#000',
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  padding: 8,
  cursor: 'zoom-in',
}

const imgStyle: CSSProperties = {
  maxWidth: '100%',
  maxHeight: 420,
  objectFit: 'contain',
  display: 'block',
}

const modalOverlay: CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.9)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  cursor: 'zoom-out',
}

const modalImg: CSSProperties = {
  maxWidth: '95vw',
  maxHeight: '95vh',
  objectFit: 'contain',
}

interface Props extends ResultViewerProps {
  /** Optional title override (e.g., "Flatmap", "Histogram"). */
  title?: string
}

export function ImageViewer({ artifact, runId, title }: Props) {
  const [zoomed, setZoomed] = useState(false)
  const url = artifactUrl(runId, artifact.name)

  return (
    <>
      <div style={viewerCard}>
        <div style={viewerHeader}>
          <span>{title ? `${title} — ${artifact.name}` : artifact.name}</span>
          <div style={{ display: 'flex', gap: 12 }}>
            <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
              {formatSize(artifact.size)}
            </span>
            <a style={actionLink} href={url} target="_blank" rel="noopener noreferrer">Open</a>
            <a style={actionLink} href={url} download>Download</a>
          </div>
        </div>
        <div style={imgContainer} onClick={() => setZoomed(true)}>
          <img src={url} alt={artifact.name} style={imgStyle} />
        </div>
      </div>

      {zoomed && (
        <div style={modalOverlay} onClick={() => setZoomed(false)}>
          <img src={url} alt={artifact.name} style={modalImg} />
        </div>
      )}
    </>
  )
}
