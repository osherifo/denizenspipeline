/** Post-preproc API client. */

import type {
  NipypeNodeMeta,
  PostPreprocGraph,
  PostPreprocRunHandle,
  PostPreprocManifest,
} from './types'

const BASE = '/api'

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}

export async function fetchNipypeNodes(): Promise<NipypeNodeMeta[]> {
  return json(`${BASE}/post-preproc/nodes`)
}

export async function validateGraph(
  graph: PostPreprocGraph,
): Promise<{ valid: boolean; errors: string[] }> {
  return json(`${BASE}/post-preproc/graphs/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ graph }),
  })
}

export async function startRun(body: {
  subject: string
  source_manifest_path: string
  graph: PostPreprocGraph
  output_dir: string
  name?: string | null
}): Promise<PostPreprocRunHandle> {
  return json(`${BASE}/post-preproc/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function getRun(runId: string): Promise<
  PostPreprocRunHandle & { error: string | null; manifest: PostPreprocManifest | null }
> {
  return json(`${BASE}/post-preproc/runs/${runId}`)
}
