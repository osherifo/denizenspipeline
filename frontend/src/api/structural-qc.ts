/** Structural-QC API client. */

import type { StructuralQCReview, StructuralQCStatus } from './types'

const BASE = '/api'

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

export function reportUrl(subject: string): string {
  return `${BASE}/preproc/subjects/${subject}/structural-qc/report`
}

export function fsFileUrl(subject: string, rel: string): string {
  return `${BASE}/preproc/subjects/${subject}/structural-qc/fs-file?rel=${encodeURIComponent(rel)}`
}
