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
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import type { ArtifactInfo, RunSummary } from '../../api/types'
import { artifactUrl } from '../../api/client'
import { diffStats, diffYaml, dumpYaml, type DiffLine } from './yamlDiff'
import { autoAlign, type PairRow } from './similarity'

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

const sortableRow = (dragging: boolean): CSSProperties => ({
  display: 'flex',
  gap: 6,
  alignItems: 'stretch',
  opacity: dragging ? 0.5 : 1,
})

const dragHandle = (dragging: boolean): CSSProperties => ({
  width: 18,
  flexShrink: 0,
  cursor: dragging ? 'grabbing' : 'grab',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: 14,
  color: dragging ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  userSelect: 'none',
})

const rowContent: CSSProperties = {
  flex: 1,
  minWidth: 0,
}

const cellHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 4,
}

const nameSelect: CSSProperties = {
  flex: 1,
  minWidth: 0,
  padding: '4px 8px',
  fontSize: 11,
  fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  appearance: 'auto' as const,
}

const removeBtn: CSSProperties = {
  background: 'none',
  border: 'none',
  fontSize: 12,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  padding: '0 4px',
  fontFamily: 'inherit',
  opacity: 0.6,
}

const emptyImg: CSSProperties = {
  ...imgFrame,
  minHeight: 220,
  color: 'var(--text-secondary)',
  fontSize: 11,
  fontStyle: 'italic',
}

const addRowBtn: CSSProperties = {
  alignSelf: 'flex-start',
  padding: '6px 14px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 5,
  cursor: 'pointer',
  border: '1px dashed var(--border)',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
  marginTop: 4,
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

/** Image artifacts (filenames) on a side, sorted alphabetically. */
function imageNames(artifacts: Record<string, ArtifactInfo> | undefined): string[] {
  if (!artifacts) return []
  return Object.values(artifacts)
    .filter((a) => a.type === 'image')
    .map((a) => a.name)
    .sort()
}

// ── Per-pair row layout (localStorage) ──────────────────────────────────

const ROWS_PREFIX = 'compareImageRows:'

function rowsKey(aId: string, bId: string): string {
  // Stable key: sort the two IDs so order(A, B) == order(B, A).
  const sorted = [aId, bId].sort().join(':')
  return ROWS_PREFIX + sorted
}

function loadRows(aId: string, bId: string): PairRow[] | null {
  try {
    const raw = localStorage.getItem(rowsKey(aId, bId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed.filter((r) =>
      r && typeof r.id === 'string'
      && (r.leftName === null || typeof r.leftName === 'string')
      && (r.rightName === null || typeof r.rightName === 'string'),
    )
  } catch {
    return null
  }
}

function saveRows(aId: string, bId: string, rows: PairRow[]): void {
  try {
    localStorage.setItem(rowsKey(aId, bId), JSON.stringify(rows))
  } catch {
    // ignore quota errors
  }
}

/** Drop saved rows that reference filenames that no longer exist. */
function reconcileRows(saved: PairRow[], leftAvail: string[], rightAvail: string[]): PairRow[] {
  const ls = new Set(leftAvail)
  const rs = new Set(rightAvail)
  return saved
    .map((r) => ({
      ...r,
      leftName: r.leftName && ls.has(r.leftName) ? r.leftName : null,
      rightName: r.rightName && rs.has(r.rightName) ? r.rightName : null,
    }))
    .filter((r) => r.leftName !== null || r.rightName !== null)
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

  // Available image artifact names per side.
  const leftNames = useMemo(() => imageNames(a.artifacts), [a.artifacts])
  const rightNames = useMemo(() => imageNames(b.artifacts), [b.artifacts])

  // Pair-row layout: load saved arrangement if present, otherwise auto-align.
  const [rows, setRowsState] = useState<PairRow[]>(() => {
    const saved = loadRows(a.run_id, b.run_id)
    if (saved && saved.length > 0) {
      return reconcileRows(saved, leftNames, rightNames)
    }
    return autoAlign(leftNames, rightNames)
  })

  // Re-reconcile when run pair changes (open a different pair).
  useEffect(() => {
    const saved = loadRows(a.run_id, b.run_id)
    if (saved && saved.length > 0) {
      setRowsState(reconcileRows(saved, leftNames, rightNames))
    } else {
      setRowsState(autoAlign(leftNames, rightNames))
    }
    // Intentionally only on run id change; manual edits are preserved.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.run_id, b.run_id])

  const setRows = (next: PairRow[]) => {
    setRowsState(next)
    saveRows(a.run_id, b.run_id, next)
  }

  const updateRow = (id: string, patch: Partial<PairRow>) => {
    setRows(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }

  const removeRow = (id: string) => {
    setRows(rows.filter((r) => r.id !== id))
  }

  const addRow = () => {
    const id = `pair-${Date.now()}`
    setRows([...rows, { id, leftName: null, rightName: null }])
  }

  const resetAlignment = () => setRows(autoAlign(leftNames, rightNames))

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIdx = rows.findIndex((r) => r.id === active.id)
    const newIdx = rows.findIndex((r) => r.id === over.id)
    if (oldIdx < 0 || newIdx < 0) return
    setRows(arrayMove(rows, oldIdx, newIdx))
  }

  const hasAnyImages = leftNames.length > 0 || rightNames.length > 0

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
          <div style={{ ...sectionLabel, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>
              Image artifacts ({rows.length})
              <span style={{ marginLeft: 12, fontSize: 10, color: 'var(--text-secondary)', textTransform: 'none', letterSpacing: 0 }}>
                auto-aligned by filename similarity — change either side or drag to reorder
              </span>
            </span>
            <button
              type="button"
              style={{
                background: 'none', border: '1px solid var(--border)',
                padding: '4px 10px', borderRadius: 4, fontSize: 10,
                color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'inherit',
                textTransform: 'uppercase', letterSpacing: 1,
              }}
              onClick={resetAlignment}
              title="Discard manual edits and re-run auto-alignment"
            >
              Reset
            </button>
          </div>
          {!hasAnyImages ? (
            <div style={noticeBox}>Neither run has image artifacts.</div>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext items={rows.map((r) => r.id)} strategy={verticalListSortingStrategy}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {rows.map((row) => (
                    <SortableImageRow
                      key={row.id}
                      row={row}
                      leftNames={leftNames}
                      rightNames={rightNames}
                      leftSrc={row.leftName ? artifactUrl(a.run_id, row.leftName) : null}
                      rightSrc={row.rightName ? artifactUrl(b.run_id, row.rightName) : null}
                      onChangeLeft={(name) => updateRow(row.id, { leftName: name })}
                      onChangeRight={(name) => updateRow(row.id, { rightName: name })}
                      onRemove={() => removeRow(row.id)}
                    />
                  ))}
                  <button type="button" style={addRowBtn} onClick={addRow}>
                    + Add row
                  </button>
                </div>
              </SortableContext>
            </DndContext>
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

interface SortableImageRowProps {
  row: PairRow
  leftNames: string[]
  rightNames: string[]
  leftSrc: string | null
  rightSrc: string | null
  onChangeLeft: (name: string | null) => void
  onChangeRight: (name: string | null) => void
  onRemove: () => void
}

function NameSelect({
  value, options, onChange,
}: {
  value: string | null
  options: string[]
  onChange: (next: string | null) => void
}) {
  return (
    <select
      style={nameSelect}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
    >
      <option value="">— none —</option>
      {options.map((name) => (
        <option key={name} value={name}>{name}</option>
      ))}
    </select>
  )
}

function SortableImageRow({
  row, leftNames, rightNames, leftSrc, rightSrc,
  onChangeLeft, onChangeRight, onRemove,
}: SortableImageRowProps) {
  const {
    attributes, listeners, setNodeRef, setActivatorNodeRef,
    transform, transition, isDragging,
  } = useSortable({ id: row.id })

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    ...sortableRow(isDragging),
  }

  return (
    <div ref={setNodeRef} style={style}>
      <div
        ref={setActivatorNodeRef}
        style={dragHandle(isDragging)}
        title="Drag to reorder"
        {...attributes}
        {...listeners}
      >
        {'\u22EE\u22EE'}
      </div>
      <div style={rowContent}>
        <div style={grid2}>
          <div>
            <div style={cellHeader}>
              <NameSelect value={row.leftName} options={leftNames} onChange={onChangeLeft} />
            </div>
            {leftSrc ? (
              <div style={imgFrame}>
                <img src={leftSrc} alt={`${row.leftName} (A)`} style={imgStyle} />
              </div>
            ) : (
              <div style={emptyImg}>no image selected for A</div>
            )}
          </div>
          <div>
            <div style={cellHeader}>
              <NameSelect value={row.rightName} options={rightNames} onChange={onChangeRight} />
              <button
                type="button"
                style={removeBtn}
                title="Remove this row"
                onClick={onRemove}
              >
                {'\u2715'}
              </button>
            </div>
            {rightSrc ? (
              <div style={imgFrame}>
                <img src={rightSrc} alt={`${row.rightName} (B)`} style={imgStyle} />
              </div>
            ) : (
              <div style={emptyImg}>no image selected for B</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
