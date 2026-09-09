/** Structural-QC API client.
 *
 * Every function takes a `StructuralQCSource` (or a bare subject label, the
 * original form): the subject's manifest, or one run's node. Files come from
 * whichever the source says; reviews are always filed per (dataset, subject).
 */

import type { StructuralQCReview, StructuralQCSource, StructuralQCStatus } from './types'

const BASE = '/api'

export type SourceLike = string | StructuralQCSource

export function toSource(src: SourceLike): StructuralQCSource {
  return typeof src === 'string' ? { kind: 'subject', subject: src } : src
}

/** Base URL for the file-serving endpoints of a source. */
export function qcBase(src: SourceLike): string {
  const s = toSource(src)
  if (s.kind === 'run') return `${BASE}/preproc/runs/${encodeURIComponent(s.runId)}/nodes/${encodeURIComponent(s.nodeId)}`
  return `${BASE}/preproc/subjects/${s.subject}/structural-qc`
}

/** Reviews live on the subject route; a run source passes its dataset along
 *  for subjects the outputs scanner does not know. */
function reviewUrl(src: SourceLike): string {
  const s = toSource(src)
  const qs = s.kind === 'run' && s.dataset ? `?dataset=${encodeURIComponent(s.dataset)}` : ''
  return `${BASE}/preproc/subjects/${s.subject}/structural-qc${qs}`
}

export async function fetchAllReviews(dataset?: string): Promise<StructuralQCReview[]> {
  const qs = dataset ? `?dataset=${encodeURIComponent(dataset)}` : ''
  const res = await fetch(`${BASE}/structural-qc/reviews${qs}`)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function fetchReview(src: SourceLike): Promise<StructuralQCReview> {
  const res = await fetch(reviewUrl(src))
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function saveReview(
  src: SourceLike,
  body: {
    status: StructuralQCStatus
    reviewer?: string
    notes?: string
    freeview_command_used?: string | null
  },
): Promise<{ saved: boolean; review: StructuralQCReview }> {
  const res = await fetch(reviewUrl(src), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function fetchFreeviewCommand(
  src: SourceLike,
): Promise<{ command: string; fs_subject_dir: string }> {
  const res = await fetch(`${qcBase(src)}/freeview-command`)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function uploadDrawing(
  src: SourceLike,
  niftiBytes: Uint8Array,
  ras: [number, number, number],
): Promise<{ saved: boolean; path: string; command: string }> {
  const form = new FormData()
  form.append('file', new Blob([new Uint8Array(niftiBytes)], { type: 'application/octet-stream' }), 'drawing.nii')
  const qs = `?ras_x=${ras[0].toFixed(1)}&ras_y=${ras[1].toFixed(1)}&ras_z=${ras[2].toFixed(1)}`
  const res = await fetch(`${qcBase(src)}/drawing${qs}`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

/** The HTML report. A run source's URL ends in `/report/` so the report's
 *  relative figure paths resolve under it. */
export function reportUrl(src: SourceLike): string {
  return toSource(src).kind === 'run' ? `${qcBase(src)}/report/` : `${qcBase(src)}/report`
}

export function fsFileUrl(src: SourceLike, rel: string): string {
  return `${qcBase(src)}/fs-file?rel=${encodeURIComponent(rel)}`
}
