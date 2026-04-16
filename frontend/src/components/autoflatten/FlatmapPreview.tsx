/** Side-by-side preview of flatmap visualization PNGs. */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { autoflattenImageUrl } from '../../api/client'

interface Props {
  /** Map of hemisphere → absolute path to PNG on disk. */
  images: Record<string, string>
  /** Optional map of hemisphere → patch file path, shown as subtitle. */
  patches?: Record<string, string>
}

const container: CSSProperties = {
  marginTop: 12,
  padding: '12px 14px',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
}

const title: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginBottom: 10,
}

const grid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 12,
}

const hemiCard: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'stretch',
  gap: 6,
}

const hemiLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-primary)',
  textAlign: 'center',
}

const hemiSubtitle: CSSProperties = {
  fontSize: 9,
  color: 'var(--text-secondary)',
  wordBreak: 'break-all',
  textAlign: 'center',
  fontFamily: 'monospace',
}

const imgStyle: CSSProperties = {
  width: '100%',
  height: 'auto',
  maxHeight: 260,
  objectFit: 'contain',
  backgroundColor: '#000',
  border: '1px solid var(--border)',
  borderRadius: 4,
  cursor: 'zoom-in',
}

const modalOverlay: CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.85)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  cursor: 'zoom-out',
}

const modalImg: CSSProperties = {
  maxWidth: '92vw',
  maxHeight: '92vh',
  objectFit: 'contain',
}

const emptyState: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  fontStyle: 'italic',
}

export function FlatmapPreview({ images, patches }: Props) {
  const [zoomed, setZoomed] = useState<string | null>(null)

  const hemis = ['lh', 'rh'].filter((h) => images[h])

  if (hemis.length === 0) {
    return (
      <div style={container}>
        <div style={title}>Flatmap Preview</div>
        <div style={emptyState}>
          No preview images found. Autoflatten generates PNG previews alongside the
          flat patches — they should appear here after a fresh run.
        </div>
      </div>
    )
  }

  return (
    <div style={container}>
      <div style={title}>Flatmap Preview</div>
      <div style={grid}>
        {hemis.map((h) => (
          <div key={h} style={hemiCard}>
            <div style={hemiLabel}>{h.toUpperCase()}</div>
            <img
              style={imgStyle}
              src={autoflattenImageUrl(images[h])}
              alt={`${h} flatmap`}
              onClick={() => setZoomed(images[h])}
            />
            {patches?.[h] && (
              <div style={hemiSubtitle}>{patches[h].split('/').pop()}</div>
            )}
          </div>
        ))}
      </div>

      {zoomed && (
        <div style={modalOverlay} onClick={() => setZoomed(null)}>
          <img style={modalImg} src={autoflattenImageUrl(zoomed)} alt="flatmap full size" />
        </div>
      )}
    </div>
  )
}
