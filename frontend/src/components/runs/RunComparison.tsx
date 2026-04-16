/** Side-by-side comparison of two runs.
 *
 * Sections:
 *  - Header: experiment / subject / status / timestamp per side
 *  - Quick stats: mean_score, total_elapsed_s, status with delta
 *  - Metrics: fetch each run's metrics.json and show A / B / Δ for each score
 *  - Config diff: YAML diff of config_snapshot
 *  - Artifacts: side-by-side common image artifacts (e.g. flatmaps, histograms)
 */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import type { ArtifactInfo, RunSummary } from '../../api/types'
import { artifactUrl } from '../../api/client'
import { diffStats, diffYaml, dumpYaml, type DiffLine } from './yamlDiff'

interface Props {
  pair: [RunSummary, RunSummary]
  onClose: () => void
}

// ── Styles ──────────────────────────────────────────────────────────────

const overlay: CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.6)',
  zIndex: 900,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 24,
}

const panel: CSSProperties = {
  width: '100%',
  maxWidth: 1400,
  maxHeight: '92vh',
  display: 'flex',
  flexDirection: 'column',
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  overflow: 'hidden',
}

const header: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '14px 20px',
  borderBottom: '1px solid var(--border)',
  backgroundColor: 'var(--bg-secondary)',
}

const titleStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  letterSpacing: 1,
}

const closeBtn: CSSProperties = {
  background: 'none',
  border: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontSize: 12,
  padding: '6px 14px',
  borderRadius: 5,
  fontFamily: 'inherit',
}

const body: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '16px 20px',
}

const sectionLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 18,
  marginBottom: 8,
}

const grid2: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 12,
}

const sideHeader: CSSProperties = {
  padding: '10px 14px',
  backgroundColor: 'var(--bg-input)',
  borderRadius: 6,
  border: '1px solid var(--border)',
  fontSize: 12,
  color: 'var(--text-primary)',
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
}

const sideLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

const fadeText: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
}

const statRow: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '180px 1fr 1fr 120px',
  gap: 12,
  padding: '8px 12px',
  borderBottom: '1px solid var(--border)',
  alignItems: 'center',
  fontSize: 12,
}

const statLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const statValue: CSSProperties = {
  fontFamily: 'monospace',
  color: 'var(--text-primary)',
}

const deltaCell = (sign: number): CSSProperties => ({
  fontFamily: 'monospace',
  fontWeight: 700,
  color: sign > 0 ? 'var(--accent-green)' : sign < 0 ? 'var(--accent-red)' : 'var(--text-secondary)',
  textAlign: 'right',
})

const diffPre: CSSProperties = {
  margin: 0,
  fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  fontSize: 11,
  lineHeight: 1.5,
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  border: '1px solid var(--border)',
  overflow: 'auto',
  maxHeight: 420,
}

const diffRow: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 0,
}

function diffCell(kind: DiffLine['kind'], side: 'left' | 'right'): CSSProperties {
  let bg = 'transparent'
  if (kind === 'changed') bg = 'rgba(255, 214, 0, 0.10)'
  else if (kind === 'removed' && side === 'left') bg = 'rgba(255, 23, 68, 0.12)'
  else if (kind === 'added' && side === 'right') bg = 'rgba(0, 230, 118, 0.12)'
  return {
    padding: '1px 10px',
    backgroundColor: bg,
    color: 'var(--text-primary)',
    borderRight: side === 'left' ? '1px solid var(--border)' : 'none',
    whiteSpace: 'pre',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  }
}

const imgFrame: CSSProperties = {
  backgroundColor: '#000',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: 6,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const imgStyle: CSSProperties = {
  maxWidth: '100%',
  maxHeight: 320,
  objectFit: 'contain',
}

const noticeBox: CSSProperties = {
  padding: '8px 12px',
  fontSize: 11,
  color: 'var(--text-secondary)',
  fontStyle: 'italic',
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  border: '1px solid var(--border)',
}

// ── Helpers ─────────────────────────────────────────────────────────────

interface MetricsJson {
  mean_score?: number
  median_score?: number
  max_score?: number
  min_score?: number
  n_voxels?: number
  n_significant?: number
  [key: string]: unknown
}

const METRIC_FIELDS: { key: keyof MetricsJson; label: string; digits?: number; integer?: boolean }[] = [
  { key: 'mean_score', label: 'Mean score', digits: 4 },
  { key: 'median_score', label: 'Median score', digits: 4 },
  { key: 'max_score', label: 'Max score', digits: 4 },
  { key: 'min_score', label: 'Min score', digits: 4 },
  { key: 'n_voxels', label: 'Voxels', integer: true },
  { key: 'n_significant', label: 'Significant', integer: true },
]

function fmt(n: number | undefined, digits = 4): string {
  if (n === undefined || n === null || Number.isNaN(n)) return '—'
  return Number(n).toFixed(digits)
}

function fmtInt(n: number | undefined): string {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString()
}

function fmtDelta(a: number | undefined, b: number | undefined, digits = 4, integer = false): {
  text: string
  sign: number
} {
  if (a === undefined || b === undefined || a === null || b === null) {
    return { text: '—', sign: 0 }
  }
  const d = b - a
  const sign = d > 0 ? 1 : d < 0 ? -1 : 0
  const prefix = d > 0 ? '+' : ''
  return {
    text: integer ? `${prefix}${d.toLocaleString()}` : `${prefix}${d.toFixed(digits)}`,
    sign,
  }
}

function fmtDuration(seconds: number): string {
  if (!seconds && seconds !== 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function fmtTimestamp(iso: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

/** Pick artifacts that exist in BOTH runs and look comparable as images. */
function commonImageArtifacts(
  a: Record<string, ArtifactInfo> | undefined,
  b: Record<string, ArtifactInfo> | undefined,
): { name: string; left: ArtifactInfo; right: ArtifactInfo }[] {
  if (!a || !b) return []
  const out: { name: string; left: ArtifactInfo; right: ArtifactInfo }[] = []
  for (const [name, leftArt] of Object.entries(a)) {
    if (leftArt.type !== 'image') continue
    const rightArt = b[name]
    if (!rightArt || rightArt.type !== 'image') continue
    out.push({ name, left: leftArt, right: rightArt })
  }
  return out
}

// ── Component ───────────────────────────────────────────────────────────

export function RunComparison({ pair, onClose }: Props) {
  const [a, b] = pair

  // Config diff (from config_snapshot).
  const diffLines = useMemo(() => {
    const left = dumpYaml(a.config_snapshot ?? {})
    const right = dumpYaml(b.config_snapshot ?? {})
    return diffYaml(left, right)
  }, [a.config_snapshot, b.config_snapshot])
  const stats = diffStats(diffLines)

  const sharedImages = useMemo(
    () => commonImageArtifacts(a.artifacts, b.artifacts),
    [a.artifacts, b.artifacts],
  )

  // Lazy-load each run's metrics.json (if present).
  const [metricsA, setMetricsA] = useState<MetricsJson | null>(null)
  const [metricsB, setMetricsB] = useState<MetricsJson | null>(null)
  const [metricsErr, setMetricsErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load(run: RunSummary, set: (m: MetricsJson | null) => void) {
      const has = run.artifacts && Object.keys(run.artifacts).some((n) => n === 'metrics.json' || n.endsWith('/metrics.json'))
      if (!has) {
        set(null)
        return
      }
      try {
        const r = await fetch(artifactUrl(run.run_id, 'metrics.json'))
        if (!r.ok) throw new Error(String(r.status))
        const j = (await r.json()) as MetricsJson
        if (!cancelled) set(j)
      } catch (e) {
        if (!cancelled) setMetricsErr(String(e))
      }
    }
    setMetricsErr(null)
    load(a, setMetricsA)
    load(b, setMetricsB)
    return () => {
      cancelled = true
    }
  }, [a.run_id, b.run_id])

  return (
    <div style={overlay} onClick={onClose}>
      <div style={panel} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <div style={titleStyle}>Compare runs</div>
          <button style={closeBtn} onClick={onClose}>Close</button>
        </div>

        <div style={body}>
          {/* Side headers */}
          <div style={grid2}>
            <RunHeader label="A" run={a} />
            <RunHeader label="B" run={b} />
          </div>

          {/* Quick stats from RunSummary */}
          <div style={sectionLabel}>Quick stats</div>
          <div>
            <StatRow label="Mean score (top-level)"
              a={a.mean_score ?? undefined} b={b.mean_score ?? undefined} digits={4} />
            <StatRow label="Total elapsed (s)"
              a={a.total_elapsed_s} b={b.total_elapsed_s} digits={2}
              fmtFn={fmtDuration} />
            <div style={{ ...statRow, color: 'var(--text-primary)' }}>
              <span style={statLabel}>Status</span>
              <span style={statValue}>{a.status || '—'}</span>
              <span style={statValue}>{b.status || '—'}</span>
              <span style={fadeText}>{a.status === b.status ? 'same' : 'differs'}</span>
            </div>
          </div>

          {/* Metrics from metrics.json */}
          <div style={sectionLabel}>Metrics (metrics.json)</div>
          {metricsErr && (
            <div style={{ ...noticeBox, color: 'var(--accent-red)' }}>
              Could not load metrics.json: {metricsErr}
            </div>
          )}
          {!metricsA && !metricsB && !metricsErr && (
            <div style={noticeBox}>Neither run has a metrics.json artifact.</div>
          )}
          {(metricsA || metricsB) && (
            <div>
              {METRIC_FIELDS.map(({ key, label, digits, integer }) => {
                const av = metricsA?.[key] as number | undefined
                const bv = metricsB?.[key] as number | undefined
                const delta = fmtDelta(av, bv, digits, integer)
                const fmtFn = integer ? fmtInt : (n: number | undefined) => fmt(n, digits)
                return (
                  <div key={String(key)} style={statRow}>
                    <span style={statLabel}>{label}</span>
                    <span style={statValue}>{fmtFn(av)}</span>
                    <span style={statValue}>{fmtFn(bv)}</span>
                    <span style={deltaCell(delta.sign)}>{delta.text}</span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Config diff */}
          <div style={sectionLabel}>
            Config diff
            <span style={{ marginLeft: 12, fontSize: 10, color: 'var(--text-secondary)', textTransform: 'none', letterSpacing: 0 }}>
              {stats.changed} changed · +{stats.added} · −{stats.removed}
            </span>
          </div>
          {stats.changed === 0 && stats.added === 0 && stats.removed === 0 ? (
            <div style={noticeBox}>Config snapshots are identical.</div>
          ) : (
            <pre style={diffPre}>
              {diffLines.map((line, i) => (
                <div key={i} style={diffRow}>
                  <span style={diffCell(line.kind, 'left')}>{line.left || '\u00A0'}</span>
                  <span style={diffCell(line.kind, 'right')}>{line.right || '\u00A0'}</span>
                </div>
              ))}
            </pre>
          )}

          {/* Side-by-side images */}
          <div style={sectionLabel}>Image artifacts ({sharedImages.length})</div>
          {sharedImages.length === 0 ? (
            <div style={noticeBox}>
              No image artifacts shared between the two runs. (Each run keeps its own
              artifacts; comparison only shows files with matching names in both.)
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {sharedImages.map(({ name, left, right }) => (
                <div key={name}>
                  <div style={{ ...fadeText, fontFamily: 'monospace', marginBottom: 6 }}>
                    {name}
                  </div>
                  <div style={grid2}>
                    <div style={imgFrame}>
                      <img src={artifactUrl(a.run_id, left.name)} alt={`${name} (A)`} style={imgStyle} />
                    </div>
                    <div style={imgFrame}>
                      <img src={artifactUrl(b.run_id, right.name)} alt={`${name} (B)`} style={imgStyle} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ──────────────────────────────────────────────────────

function RunHeader({ label, run }: { label: string; run: RunSummary }) {
  return (
    <div style={sideHeader}>
      <span style={sideLabel}>Run {label}</span>
      <span style={{ fontWeight: 600 }}>{run.experiment || '—'} · {run.subject || '—'}</span>
      <span style={fadeText}>{fmtTimestamp(run.started_at)}</span>
      <span style={{ ...fadeText, fontFamily: 'monospace' }}>{run.run_id}</span>
    </div>
  )
}

function StatRow({
  label, a, b, digits = 4, fmtFn,
}: {
  label: string
  a: number | undefined
  b: number | undefined
  digits?: number
  fmtFn?: (n: number) => string
}) {
  const delta = fmtDelta(a, b, digits)
  const formatter = fmtFn ?? ((n: number) => fmt(n, digits))
  return (
    <div style={statRow}>
      <span style={statLabel}>{label}</span>
      <span style={statValue}>{a == null ? '—' : formatter(a)}</span>
      <span style={statValue}>{b == null ? '—' : formatter(b)}</span>
      <span style={deltaCell(delta.sign)}>{delta.text}</span>
    </div>
  )
}
