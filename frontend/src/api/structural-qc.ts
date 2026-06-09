/** Structural-QC API client. */

import type { StructuralQCReview, StructuralQCStatus } from './types'

const BASE = '/api'

export async function fetchAllReviews(dataset?: string): Promise<StructuralQCReview[]> {
  const qs = dataset ? `?dataset=${encodeURIComponent(dataset)}` : ''
  const res = await fetch(`${BASE}/structural-qc/reviews${qs}`)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function fetchReview(subject: string): Promise<StructuralQCReview> {
  const res = await fetch(`${BASE}/preproc/subjects/${subject}/structural-qc`)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function saveReview(
  subject: string,
  body: {
    status: StructuralQCStatus
    reviewer?: string
    notes?: string
    freeview_command_used?: string | null
  },
): Promise<{ saved: boolean; review: StructuralQCReview }> {
  const res = await fetch(`${BASE}/preproc/subjects/${subject}/structural-qc`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function fetchFreeviewCommand(
  subject: string,
): Promise<{ command: string; fs_subject_dir: string }> {
  const res = await fetch(
    `${BASE}/preproc/subjects/${subject}/structural-qc/freeview-command`,
  )
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function uploadDrawing(
  subject: string,
  niftiBytes: Uint8Array,
  ras: [number, number, number],
): Promise<{ saved: boolean; path: string; command: string }> {
  const form = new FormData()
  form.append('file', new Blob([new Uint8Array(niftiBytes)], { type: 'application/octet-stream' }), 'drawing.nii')
  const qs = `?ras_x=${ras[0].toFixed(1)}&ras_y=${ras[1].toFixed(1)}&ras_z=${ras[2].toFixed(1)}`
  const res = await fetch(
    `${BASE}/preproc/subjects/${subject}/structural-qc/drawing${qs}`,
    { method: 'POST', body: form },
  )
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export function reportUrl(subject: string): string {
  return `${BASE}/preproc/subjects/${subject}/structural-qc/report`
}

export function fsFileUrl(subject: string, rel: string): string {
  return `${BASE}/preproc/subjects/${subject}/structural-qc/fs-file?rel=${encodeURIComponent(rel)}`
}
