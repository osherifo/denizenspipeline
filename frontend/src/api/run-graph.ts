/** Run-graph endpoints — power the "View graph" modal in the dashboard.
 *
 * One module handles both subject and group runs. Each fetcher takes a
 * `target` describing which run to query; URL building lives in
 * `urlFor()` so callers only deal with the typed return value.
 */

const BASE = '/api'

export type GraphTarget =
  | { kind: 'subject'; runId: string }
  | { kind: 'group'; groupName: string; runId: string }
  | { kind: 'group-subject'; groupName: string; runId: string; subject: string }

export interface RunGraphNode {
  id: string
  label: string
  kind: string                   // 'stage' | 'stimulus_loader' | … | 'subject'
  stage: string
  status: string
  elapsed_s: number | null
  detail: string
  source_path: string | null
  plugin_name: string | null
  params: Record<string, unknown>
  children: string[]
  outputs: string[]              // paths recorded by the orchestrator
}

export interface RunGraphEdge {
  source: string
  target: string
}

export interface RunGraphResponse {
  run_id: string
  output_dir: string
  experiment?: string
  subject?: string
  group_name?: string
  nodes: RunGraphNode[]
  edges: RunGraphEdge[]
}

export interface NodeSourceResponse {
  path: string
  language: string
  text: string
  size: number
}

export interface NodeOutputFile {
  name: string
  rel: string
  size: number
  suffix: string
}

export interface NodeOutputsResponse {
  node_id: string
  output_dir: string
  files: NodeOutputFile[]
}


function urlFor(target: GraphTarget, suffix: string): string {
  switch (target.kind) {
    case 'subject':
      return `${BASE}/runs/${encodeURIComponent(target.runId)}${suffix}`
    case 'group':
      return `${BASE}/group-runs/${encodeURIComponent(target.groupName)}/${encodeURIComponent(target.runId)}${suffix}`
    case 'group-subject':
      return `${BASE}/group-runs/${encodeURIComponent(target.groupName)}/${encodeURIComponent(target.runId)}/subject/${encodeURIComponent(target.subject)}${suffix}`
  }
}


function nodeSegment(nodeId: string): string {
  // FastAPI :path accepts colons; encode for safety but don't touch '/'
  // since we never include slashes in node IDs.
  return encodeURIComponent(nodeId)
}


export async function fetchRunGraph(
  target: GraphTarget,
): Promise<RunGraphResponse> {
  const res = await fetch(urlFor(target, '/graph'))
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}


export async function fetchNodeSource(
  target: GraphTarget, nodeId: string,
): Promise<NodeSourceResponse> {
  const res = await fetch(urlFor(target, `/node/${nodeSegment(nodeId)}/source`))
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}


export async function fetchNodeOutputs(
  target: GraphTarget, nodeId: string,
): Promise<NodeOutputsResponse> {
  const res = await fetch(urlFor(target, `/node/${nodeSegment(nodeId)}/outputs`))
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}


export function nodeFileUrl(
  target: GraphTarget, nodeId: string, rel: string,
): string {
  return urlFor(target, `/node/${nodeSegment(nodeId)}/file/${encodeURI(rel)}`)
}
