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
  | { kind: 'study'; studyName: string; runId: string }
  | { kind: 'study-group'; studyName: string; runId: string; groupLabel: string }
  // Preview the graph of a config that hasn't been run yet. Source code
  // is still viewable; outputs are not (no run dir exists).
  | { kind: 'config'; filename: string }
  // Live graph of a run still in progress. Backend synthesizes stage
  // records from handle.events; the modal polls this endpoint until
  // the run finishes (or the user closes it).
  | { kind: 'in-flight'; runId: string }
  // Subject drilldown inside an in-flight group/study run.
  | { kind: 'in-flight-subject'; runId: string; subject: string }

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

export interface LogTailResponse {
  log_tail: string
  log_path: string
}


function urlFor(target: GraphTarget, suffix: string): string {
  switch (target.kind) {
    case 'subject':
      return `${BASE}/runs/${encodeURIComponent(target.runId)}${suffix}`
    case 'group':
      return `${BASE}/group-runs/${encodeURIComponent(target.groupName)}/${encodeURIComponent(target.runId)}${suffix}`
    case 'group-subject':
      return `${BASE}/group-runs/${encodeURIComponent(target.groupName)}/${encodeURIComponent(target.runId)}/subject/${encodeURIComponent(target.subject)}${suffix}`
    case 'study':
      return `${BASE}/study-runs/${encodeURIComponent(target.studyName)}/${encodeURIComponent(target.runId)}${suffix}`
    case 'study-group':
      return `${BASE}/study-runs/${encodeURIComponent(target.studyName)}/${encodeURIComponent(target.runId)}/group/${encodeURIComponent(target.groupLabel)}${suffix}`
    case 'config':
      return `${BASE}/configs/${encodeURIComponent(target.filename)}${suffix}`
    case 'in-flight':
      return `${BASE}/runs/in-flight/${encodeURIComponent(target.runId)}${suffix}`
    case 'in-flight-subject':
      return `${BASE}/runs/in-flight/${encodeURIComponent(target.runId)}/subject/${encodeURIComponent(target.subject)}${suffix}`
  }
}


export function isLiveTarget(target: GraphTarget): boolean {
  return target.kind === 'in-flight' || target.kind === 'in-flight-subject'
}


/** True when the target is a config preview — outputs/file endpoints
 *  don't exist for these (no run dir yet). */
export function isConfigPreview(target: GraphTarget): boolean {
  return target.kind === 'config'
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


/** Tail the run-scope log for a target. Only meaningful for live
 *  in-flight targets right now — the backend currently surfaces logs
 *  for ``in-flight`` (group.log / study.log / subject stdout) and
 *  ``in-flight-subject`` (per-subject pipeline.log). Returns null for
 *  finished targets so callers can hide the Log tab. */
export async function fetchLogTail(
  target: GraphTarget,
): Promise<LogTailResponse | null> {
  if (target.kind !== 'in-flight' && target.kind !== 'in-flight-subject') {
    return null
  }
  const res = await fetch(urlFor(target, '/log'))
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}


export function targetSupportsLog(target: GraphTarget): boolean {
  return target.kind === 'in-flight' || target.kind === 'in-flight-subject'
}
