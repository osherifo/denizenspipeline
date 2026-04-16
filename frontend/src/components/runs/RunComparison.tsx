/** N-way side-by-side comparison of pipeline runs.
 *
 * Sections (one column per selected run, up to COMPARE_MAX):
 *  - Header strip: experiment / subject / status / timestamp per run
 *  - Quick stats: mean_score, total_elapsed_s, status, with best/worst
 *    cell highlighted per row
 *  - Metrics: per-key from each run's metrics.json, best/worst highlighted
 *  - Config diff: union of flattened config_snapshot keys, one column
 *    per run, cells that differ from the row's mode are highlighted
 *  - Image artifacts: rows of N image panes, drag to reorder, dropdown
 *    per cell to override the auto-aligned filename, scroll horizontally
 *    when N is wide
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
import { autoAlignN, type PairRow } from './similarity'

interface Props {
  runs: RunSummary[]
  onClose: () => void
}

// ── Constants ───────────────────────────────────────────────────────────

/** Minimum readable width per run column in tables / image strips. */
const RUN_COL_MIN = 180

interface MetricsJson {
  mean_score?: number
  median_score?: number
  max_score?: number
  min_score?: number
  n_voxels?: number
  n_significant?: number
  [key: string]: unknown
}

type Direction = 'higher_better' | 'lower_better' | 'neutral'

const METRIC_FIELDS: {
  key: keyof MetricsJson
  label: string
  digits?: number
  integer?: boolean
  direction?: Direction
}[] = [
  { key: 'mean_score', label: 'Mean score', digits: 4, direction: 'higher_better' },
  { key: 'median_score', label: 'Median score', digits: 4, direction: 'higher_better' },
  { key: 'max_score', label: 'Max score', digits: 4, direction: 'higher_better' },
  { key: 'min_score', label: 'Min score', digits: 4, direction: 'higher_better' },
  { key: 'n_voxels', label: 'Voxels', integer: true, direction: 'neutral' },
  { key: 'n_significant', label: 'Significant', integer: true, direction: 'higher_better' },
]

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
  maxWidth: 1600,
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

const sectionLabelRow: CSSProperties = {
  ...sectionLabel,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
}

const subtleHint: CSSProperties = {
  marginLeft: 12,
  fontSize: 10,
  color: 'var(--text-secondary)',
  textTransform: 'none',
  letterSpacing: 0,
  fontWeight: 400,
}

/** Column template for a wide table: fixed label column + N run columns. */
function tableCols(n: number, labelW = 160): string {
  return `${labelW}px repeat(${n}, minmax(${RUN_COL_MIN}px, 1fr))`
}

/** Outer scroll container so wide tables get a horizontal scrollbar
 *  instead of overflowing the modal. */
const tableScroll: CSSProperties = {
  overflowX: 'auto',
  border: '1px solid var(--border)',
  borderRadius: 6,
  backgroundColor: 'var(--bg-secondary)',
}

const headerCardsScroll: CSSProperties = {
  overflowX: 'auto',
  paddingBottom: 4,
}

const headerCardsGrid = (n: number): CSSProperties => ({
  display: 'grid',
  gridTemplateColumns: `repeat(${n}, minmax(220px, 1fr))`,
  gap: 10,
  minWidth: n * 220,
})

const sideCard: CSSProperties = {
  padding: '10px 14px',
  backgroundColor: 'var(--bg-input)',
  borderRadius: 6,
  border: '1px solid var(--border)',
  fontSize: 12,
  color: 'var(--text-primary)',
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
  minWidth: 0,
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

const tableRow = (n: number, labelW = 160): CSSProperties => ({
  display: 'grid',
  gridTemplateColumns: tableCols(n, labelW),
  borderBottom: '1px solid var(--border)',
  alignItems: 'center',
  fontSize: 12,
  minWidth: labelW + n * RUN_COL_MIN,
})

const labelCell: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  padding: '8px 12px',
  borderRight: '1px solid var(--border)',
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}

const baseValueCell: CSSProperties = {
  fontFamily: 'monospace',
  color: 'var(--text-primary)',
  padding: '8px 12px',
  borderRight: '1px solid var(--border)',
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}

function valueCell(highlight: 'best' | 'worst' | null): CSSProperties {
  if (highlight === 'best') {
    return {
      ...baseValueCell,
      backgroundColor: 'rgba(0, 230, 118, 0.10)',
      color: 'var(--accent-green)',
      fontWeight: 700,
    }
  }
  if (highlight === 'worst') {
    return {
      ...baseValueCell,
      backgroundColor: 'rgba(255, 23, 68, 0.07)',
      color: 'var(--accent-red)',
    }
  }
  return baseValueCell
}

/** Config-diff cell: dim if matches the row mode, faintly highlighted if
 *  different. */
function configCell(matchesMode: boolean): CSSProperties {
  return {
    ...baseValueCell,
    backgroundColor: matchesMode ? 'transparent' : 'rgba(255, 214, 0, 0.10)',
    color: matchesMode ? 'var(--text-secondary)' : 'var(--text-primary)',
  }
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

const imageStripScroll: CSSProperties = {
  overflowX: 'auto',
}

const imageStripGrid = (n: number): CSSProperties => ({
  display: 'grid',
  gridTemplateColumns: `repeat(${n}, minmax(${RUN_COL_MIN + 40}px, 1fr))`,
  gap: 8,
  minWidth: n * (RUN_COL_MIN + 40),
})

const imageCell: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
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

const removeRowBtn: CSSProperties = {
  background: 'none',
  border: 'none',
  fontSize: 12,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  padding: '0 4px',
  fontFamily: 'inherit',
  opacity: 0.6,
  flexShrink: 0,
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
  maxHeight: 280,
  objectFit: 'contain',
}

const emptyImg: CSSProperties = {
  ...imgFrame,
  minHeight: 200,
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

const resetBtn: CSSProperties = {
  background: 'none',
  border: '1px solid var(--border)',
  padding: '4px 10px',
  borderRadius: 4,
  fontSize: 10,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'inherit',
  textTransform: 'uppercase',
  letterSpacing: 1,
}

// ── Helpers ─────────────────────────────────────────────────────────────

function fmt(n: number | undefined, digits = 4): string {
  if (n === undefined || n === null || Number.isNaN(n)) return '—'
  return Number(n).toFixed(digits)
}

function fmtInt(n: number | undefined): string {
  if (n === undefined || n === null) return '—'
  return n.toLocaleString()
}

function fmtDuration(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null) return '—'
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

function imageNames(artifacts: Record<string, ArtifactInfo> | undefined): string[] {
  if (!artifacts) return []
  return Object.values(artifacts)
    .filter((a) => a.type === 'image')
    .map((a) => a.name)
    .sort()
}

/** Find the best (max or min) numeric value among `values`, ignoring nulls.
 *  Returns the index, or -1 if there's no clear winner (all equal or all null). */
function bestIndex(values: (number | null | undefined)[], direction: Direction): number {
  if (direction === 'neutral') return -1
  let bestIdx = -1
  let bestVal: number | null = null
  let allEqual = true
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (v == null || Number.isNaN(v)) continue
    if (bestVal === null) {
      bestVal = v
      bestIdx = i
      continue
    }
    if (v !== bestVal) allEqual = false
    if (direction === 'higher_better' && v > bestVal) {
      bestVal = v
      bestIdx = i
    } else if (direction === 'lower_better' && v < bestVal) {
      bestVal = v
      bestIdx = i
    }
  }
  return allEqual ? -1 : bestIdx
}

function worstIndex(values: (number | null | undefined)[], direction: Direction): number {
  if (direction === 'neutral') return -1
  // Worst = best in the opposite direction.
  return bestIndex(values, direction === 'higher_better' ? 'lower_better' : 'higher_better')
}

/** Highlight category for value at index given best/worst indices. */
function cellMark(i: number, best: number, worst: number): 'best' | 'worst' | null {
  if (i === best && best !== -1) return 'best'
  if (i === worst && worst !== -1 && worst !== best) return 'worst'
  return null
}

/** Flatten an arbitrary config object to a Record<dotted_key, string>. */
function flattenConfig(obj: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  if (obj === null || obj === undefined) {
    if (prefix) out[prefix] = String(obj)
    return out
  }
  if (typeof obj !== 'object') {
    out[prefix] = String(obj)
    return out
  }
  if (Array.isArray(obj)) {
    out[prefix] = JSON.stringify(obj)
    return out
  }
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flattenConfig(v, key))
    } else {
      out[key] = v == null
        ? String(v)
        : Array.isArray(v) ? JSON.stringify(v) : String(v)
    }
  }
  return out
}

function modeOf(values: (string | undefined)[]): string | undefined {
  const counts = new Map<string, number>()
  for (const v of values) {
    if (v === undefined) continue
    counts.set(v, (counts.get(v) ?? 0) + 1)
  }
  let best: string | undefined
  let bestCount = 0
  for (const [v, c] of counts) {
    if (c > bestCount) {
      bestCount = c
      best = v
    }
  }
  return best
}

// ── Per-comparison row layout (localStorage) ────────────────────────────

const ROWS_PREFIX = 'compareImageRows:'

function rowsKey(runIds: string[]): string {
  // Stable key: sort the IDs so the same selection in any order shares storage.
  const sorted = [...runIds].sort().join(':')
  return ROWS_PREFIX + sorted
}

function loadRows(runIds: string[]): PairRow[] | null {
  try {
    const raw = localStorage.getItem(rowsKey(runIds))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed.filter((r) =>
      r && typeof r.id === 'string'
      && r.perRun && typeof r.perRun === 'object',
    )
  } catch {
    return null
  }
}

function saveRows(runIds: string[], rows: PairRow[]): void {
  try {
    localStorage.setItem(rowsKey(runIds), JSON.stringify(rows))
  } catch {
    // ignore quota errors
  }
}

/** Drop saved rows that reference filenames no longer present, and clear
 *  per-run entries for runs not in the current selection. */
function reconcileRows(
  saved: PairRow[],
  runIds: string[],
  namesByRun: Record<string, string[]>,
): PairRow[] {
  const setsByRun: Record<string, Set<string>> = {}
  for (const rid of runIds) setsByRun[rid] = new Set(namesByRun[rid] || [])

  return saved
    .map((r) => {
      const perRun: Record<string, string | null> = {}
      let any = false
      for (const rid of runIds) {
        const v = r.perRun?.[rid] ?? null
        if (v && setsByRun[rid].has(v)) {
          perRun[rid] = v
          any = true
        } else {
          perRun[rid] = null
        }
      }
      return { id: r.id, perRun, _hasAny: any }
    })
    .filter((r) => r._hasAny)
    .map(({ id, perRun }) => ({ id, perRun }))
}

// ── Component ───────────────────────────────────────────────────────────

export function RunComparison({ runs, onClose }: Props) {
  const n = runs.length
  const runIds = useMemo(() => runs.map((r) => r.run_id), [runs])

  // Image artifact names per run.
  const namesByRun = useMemo(() => {
    const m: Record<string, string[]> = {}
    for (const r of runs) m[r.run_id] = imageNames(r.artifacts)
    return m
  }, [runs])

  // Auto-aligned (or saved) image-row layout.
  const [rows, setRowsState] = useState<PairRow[]>(() => {
    const saved = loadRows(runIds)
    if (saved && saved.length > 0) return reconcileRows(saved, runIds, namesByRun)
    return autoAlignN(runIds, namesByRun)
  })

  useEffect(() => {
    const saved = loadRows(runIds)
    if (saved && saved.length > 0) {
      setRowsState(reconcileRows(saved, runIds, namesByRun))
    } else {
      setRowsState(autoAlignN(runIds, namesByRun))
    }
    // Re-run when the set of selected runs changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runIds.join('|')])

  const setRows = (next: PairRow[]) => {
    setRowsState(next)
    saveRows(runIds, next)
  }

  const updateRow = (id: string, runId: string, name: string | null) => {
    setRows(rows.map((r) => (
      r.id === id ? { ...r, perRun: { ...r.perRun, [runId]: name } } : r
    )))
  }

  const removeRow = (id: string) => setRows(rows.filter((r) => r.id !== id))

  const addRow = () => {
    const id = `pair-${Date.now()}`
    const perRun: Record<string, string | null> = {}
    for (const rid of runIds) perRun[rid] = null
    setRows([...rows, { id, perRun }])
  }

  const resetAlignment = () => setRows(autoAlignN(runIds, namesByRun))

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

  const hasAnyImages = Object.values(namesByRun).some((arr) => arr.length > 0)

  // Lazy-load each run's metrics.json (in parallel).
  const [metricsByRun, setMetricsByRun] = useState<Record<string, MetricsJson | null>>({})
  const [metricsErr, setMetricsErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setMetricsErr(null)
    setMetricsByRun({})
    Promise.all(
      runs.map(async (run) => {
        const has = run.artifacts && Object.keys(run.artifacts).some((nm) =>
          nm === 'metrics.json' || nm.endsWith('/metrics.json'),
        )
        if (!has) return [run.run_id, null] as const
        try {
          const r = await fetch(artifactUrl(run.run_id, 'metrics.json'))
          if (!r.ok) throw new Error(String(r.status))
          return [run.run_id, (await r.json()) as MetricsJson] as const
        } catch (e) {
          if (!cancelled) setMetricsErr(String(e))
          return [run.run_id, null] as const
        }
      }),
    ).then((entries) => {
      if (cancelled) return
      const next: Record<string, MetricsJson | null> = {}
      for (const [rid, m] of entries) next[rid] = m
      setMetricsByRun(next)
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runIds.join('|')])

  // Flattened configs for the diff matrix.
  const flatConfigs = useMemo(
    () => runs.map((r) => flattenConfig(r.config_snapshot ?? {})),
    [runs],
  )
  const allConfigKeys = useMemo(() => {
    const s = new Set<string>()
    for (const c of flatConfigs) for (const k of Object.keys(c)) s.add(k)
    return [...s].sort()
  }, [flatConfigs])

  // Only show rows where at least 2 runs differ.
  const differingKeys = useMemo(
    () => allConfigKeys.filter((k) => {
      const vs = flatConfigs.map((c) => c[k])
      const set = new Set(vs)
      return set.size > 1
    }),
    [allConfigKeys, flatConfigs],
  )

  const haveAnyMetrics = Object.values(metricsByRun).some((m) => m != null)

  return (
    <div style={overlay} onClick={onClose}>
      <div style={panel} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <div style={titleStyle}>Compare {n} runs</div>
          <button style={closeBtn} onClick={onClose}>Close</button>
        </div>

        <div style={body}>
          {/* Run header cards */}
          <div style={headerCardsScroll}>
            <div style={headerCardsGrid(n)}>
              {runs.map((run, i) => (
                <RunHeaderCard key={run.run_id} index={i} run={run} />
              ))}
            </div>
          </div>

          {/* Quick stats */}
          <div style={sectionLabel}>Quick stats</div>
          <div style={tableScroll}>
            <NumericRow
              n={n}
              label="Mean score (top-level)"
              values={runs.map((r) => r.mean_score ?? null)}
              direction="higher_better"
              format={(v) => fmt(v ?? undefined, 4)}
            />
            <NumericRow
              n={n}
              label="Total elapsed"
              values={runs.map((r) => r.total_elapsed_s ?? null)}
              direction="lower_better"
              format={(v) => fmtDuration(v ?? undefined)}
            />
            <StringRow n={n} label="Status" values={runs.map((r) => r.status || '—')} />
          </div>

          {/* Metrics from metrics.json */}
          <div style={sectionLabel}>Metrics (metrics.json)</div>
          {metricsErr && (
            <div style={{ ...noticeBox, color: 'var(--accent-red)' }}>
              Could not load some metrics.json: {metricsErr}
            </div>
          )}
          {!haveAnyMetrics && !metricsErr && (
            <div style={noticeBox}>No metrics.json artifact in any selected run.</div>
          )}
          {haveAnyMetrics && (
            <div style={tableScroll}>
              {METRIC_FIELDS.map(({ key, label, digits, integer, direction }) => {
                const values = runs.map((r) => {
                  const v = metricsByRun[r.run_id]?.[key]
                  return typeof v === 'number' ? v : null
                })
                return (
                  <NumericRow
                    key={String(key)}
                    n={n}
                    label={label}
                    values={values}
                    direction={direction ?? 'higher_better'}
                    format={integer ? (v) => fmtInt(v ?? undefined) : (v) => fmt(v ?? undefined, digits ?? 4)}
                  />
                )
              })}
            </div>
          )}

          {/* Config diff matrix */}
          <div style={sectionLabelRow}>
            <span>
              Config diff
              <span style={subtleHint}>
                {differingKeys.length > 0
                  ? `${differingKeys.length} differing key(s) — cells highlighted where they differ from the row's mode`
                  : 'all keys identical across selected runs'}
              </span>
            </span>
          </div>
          {differingKeys.length === 0 ? (
            <div style={noticeBox}>Config snapshots are identical.</div>
          ) : (
            <div style={tableScroll}>
              {differingKeys.map((key) => {
                const values = flatConfigs.map((c) => c[key])
                const mode = modeOf(values)
                return (
                  <div key={key} style={tableRow(n, 220)}>
                    <span style={labelCell} title={key}>{key}</span>
                    {values.map((v, i) => (
                      <span
                        key={`${key}-${i}`}
                        style={configCell(v === mode)}
                        title={v ?? '(absent)'}
                      >
                        {v ?? '—'}
                      </span>
                    ))}
                  </div>
                )
              })}
            </div>
          )}

          {/* Image artifacts as N-pane horizontal strips */}
          <div style={sectionLabelRow}>
            <span>
              Image artifacts ({rows.length})
              <span style={subtleHint}>
                auto-aligned by filename similarity — change any cell or drag to reorder
              </span>
            </span>
            <button
              type="button"
              style={resetBtn}
              onClick={resetAlignment}
              title="Discard manual edits and re-run auto-alignment"
            >
              Reset
            </button>
          </div>
          {!hasAnyImages ? (
            <div style={noticeBox}>No image artifacts in any selected run.</div>
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
                      runs={runs}
                      namesByRun={namesByRun}
                      onChange={(rid, name) => updateRow(row.id, rid, name)}
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

function RunHeaderCard({ index, run }: { index: number; run: RunSummary }) {
  // Letter labels A, B, C, ... up to F (we cap at COMPARE_MAX = 6).
  const letter = String.fromCharCode('A'.charCodeAt(0) + index)
  return (
    <div style={sideCard}>
      <span style={sideLabel}>Run {letter}</span>
      <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {run.experiment || '—'} · {run.subject || '—'}
      </span>
      <span style={fadeText}>{fmtTimestamp(run.started_at)}</span>
      <span style={{ ...fadeText, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {run.run_id}
      </span>
    </div>
  )
}

function NumericRow({
  n, label, values, direction, format,
}: {
  n: number
  label: string
  values: (number | null)[]
  direction: Direction
  format: (v: number | null) => string
}) {
  const best = bestIndex(values, direction)
  const worst = worstIndex(values, direction)
  return (
    <div style={tableRow(n)}>
      <span style={labelCell}>{label}</span>
      {values.map((v, i) => (
        <span key={i} style={valueCell(cellMark(i, best, worst))}>
          {format(v)}
        </span>
      ))}
    </div>
  )
}

function StringRow({ n, label, values }: { n: number; label: string; values: string[] }) {
  return (
    <div style={tableRow(n)}>
      <span style={labelCell}>{label}</span>
      {values.map((v, i) => (
        <span key={i} style={baseValueCell}>{v}</span>
      ))}
    </div>
  )
}

interface SortableImageRowProps {
  row: PairRow
  runs: RunSummary[]
  namesByRun: Record<string, string[]>
  onChange: (runId: string, name: string | null) => void
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
  row, runs, namesByRun, onChange, onRemove,
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
        <div style={imageStripScroll}>
          <div style={imageStripGrid(runs.length)}>
            {runs.map((run, idx) => {
              const name = row.perRun[run.run_id] ?? null
              const isLast = idx === runs.length - 1
              return (
                <div key={run.run_id} style={imageCell}>
                  <div style={cellHeader}>
                    <NameSelect
                      value={name}
                      options={namesByRun[run.run_id] || []}
                      onChange={(next) => onChange(run.run_id, next)}
                    />
                    {isLast && (
                      <button
                        type="button"
                        style={removeRowBtn}
                        title="Remove this row"
                        onClick={onRemove}
                      >
                        {'\u2715'}
                      </button>
                    )}
                  </div>
                  {name ? (
                    <div style={imgFrame}>
                      <img
                        src={artifactUrl(run.run_id, name)}
                        alt={`${name} (run ${idx + 1})`}
                        style={imgStyle}
                      />
                    </div>
                  ) : (
                    <div style={emptyImg}>no image selected</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
