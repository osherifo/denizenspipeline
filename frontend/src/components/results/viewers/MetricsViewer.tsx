/** Metrics viewer — renders metrics.json as score cards + feature breakdown. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { artifactUrl } from '../../../api/client'
import type { ResultViewerProps } from '../registry'
import { viewerCard, viewerHeader, actionLink } from './common'

interface MetricsJson {
  mean_score?: number
  median_score?: number
  max_score?: number
  min_score?: number
  n_voxels?: number
  n_significant?: number
  feature_names?: string[]
  feature_dims?: number[]
  delays?: number[]
  [key: string]: unknown
}

const body: CSSProperties = {
  padding: '12px 14px',
  fontSize: 12,
  color: 'var(--text-primary)',
}

const scoreGrid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
  gap: 10,
  marginBottom: 14,
}

const scoreCard: CSSProperties = {
  padding: '10px 12px',
  backgroundColor: 'var(--bg-card)',
  borderRadius: 5,
  border: '1px solid var(--border)',
}

const scoreLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4,
}

const scoreValue: CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
  fontFamily: 'monospace',
}

const metaLine: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginBottom: 4,
}

const chip: CSSProperties = {
  display: 'inline-block',
  padding: '2px 8px',
  fontSize: 10,
  fontFamily: 'monospace',
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 3,
  marginRight: 4,
  marginBottom: 4,
  color: 'var(--text-primary)',
}

function fmt(n: number | undefined, digits = 4): string {
  if (n === undefined || n === null || Number.isNaN(n)) return '—'
  return Number(n).toFixed(digits)
}

function fmtInt(n: number | undefined): string {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString()
}

export function MetricsViewer({ artifact, runId }: ResultViewerProps) {
  const url = artifactUrl(runId, artifact.name)
  const [data, setData] = useState<MetricsJson | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then((j: MetricsJson) => {
        if (!cancelled) setData(j)
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
        <span>Metrics — {artifact.name}</span>
        <div style={{ display: 'flex', gap: 12 }}>
          <a style={actionLink} href={url} target="_blank" rel="noopener noreferrer">Raw JSON</a>
          <a style={actionLink} href={url} download>Download</a>
        </div>
      </div>
      <div style={body}>
        {error && <div style={{ color: 'var(--accent-red)' }}>Failed to load: {error}</div>}
        {!data && !error && <div style={{ color: 'var(--text-secondary)' }}>Loading...</div>}

        {data && (
          <>
            <div style={scoreGrid}>
              <div style={scoreCard}>
                <div style={scoreLabel}>Mean</div>
                <div style={scoreValue}>{fmt(data.mean_score)}</div>
              </div>
              <div style={scoreCard}>
                <div style={scoreLabel}>Median</div>
                <div style={scoreValue}>{fmt(data.median_score)}</div>
              </div>
              <div style={scoreCard}>
                <div style={scoreLabel}>Max</div>
                <div style={scoreValue}>{fmt(data.max_score)}</div>
              </div>
              <div style={scoreCard}>
                <div style={scoreLabel}>Min</div>
                <div style={scoreValue}>{fmt(data.min_score)}</div>
              </div>
              <div style={scoreCard}>
                <div style={scoreLabel}>Voxels</div>
                <div style={scoreValue}>{fmtInt(data.n_voxels)}</div>
              </div>
              <div style={scoreCard}>
                <div style={scoreLabel}>Significant</div>
                <div style={scoreValue}>{fmtInt(data.n_significant)}</div>
              </div>
            </div>

            {data.feature_names && data.feature_names.length > 0 && (
              <>
                <div style={metaLine}>
                  <strong style={{ color: 'var(--text-primary)' }}>Features:</strong>{' '}
                  {data.feature_names.map((name, i) => (
                    <span key={name} style={chip}>
                      {name}
                      {data.feature_dims?.[i] !== undefined && (
                        <span style={{ color: 'var(--text-secondary)', marginLeft: 4 }}>
                          ({data.feature_dims[i]}d)
                        </span>
                      )}
                    </span>
                  ))}
                </div>
              </>
            )}

            {data.delays && (
              <div style={metaLine}>
                <strong style={{ color: 'var(--text-primary)' }}>Delays:</strong>{' '}
                {data.delays.join(', ')}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
