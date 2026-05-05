/** Per-node fmriprep output endpoints. */

import type { NodeOutputsList, NodePickleResponse } from './types'

const BASE = '/api'

function nodePath(p: string): string {
  // FastAPI's :path converter accepts the dotted node path verbatim;
  // we still encode segments to be safe (no slashes in node leaves).
  return encodeURI(p)
}

export async function fetchNodeOutputs(
  runId: string,
  node: string,
): Promise<NodeOutputsList> {
  const res = await fetch(
    `${BASE}/preproc/runs/${encodeURIComponent(runId)}/node/${nodePath(node)}/files`,
  )
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function fetchNodePickle(
  runId: string,
  node: string,
  rel: string,
): Promise<NodePickleResponse> {
  const res = await fetch(
    `${BASE}/preproc/runs/${encodeURIComponent(runId)}/node/${nodePath(node)}/pickle?rel=${encodeURIComponent(rel)}`,
  )
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export function nodeFileUrl(
  runId: string,
  node: string,
  rel: string,
): string {
  return `${BASE}/preproc/runs/${encodeURIComponent(runId)}/node/${nodePath(node)}/file?rel=${encodeURIComponent(rel)}`
}
