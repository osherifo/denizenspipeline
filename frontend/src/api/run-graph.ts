import { QA_STAGE_NAMES } from '../utils/stages'
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
  // Subject drilldown inside a finished study — reaches into one of the
  // study's groups, then into one of that group's subjects.
  | { kind: 'study-group-subject'; studyName: string; runId: string; groupLabel: string; subject: string }
  // Preview the graph of a config that hasn't been run yet. Source code
  // is still viewable; outputs are not (no run dir exists).
  | { kind: 'config'; filename: string }
  // Subject drilldown into a *group* config preview — backend derives
  // the per-subject config from the group YAML and returns the subject
  // graph skeleton (every stage unknown).
  | { kind: 'config-subject'; filename: string; subject: string }
  // Live graph of a run still in progress. Backend synthesizes stage
  // records from handle.events; the modal polls this endpoint until
  // the run finishes (or the user closes it).
  | { kind: 'in-flight'; runId: string }
  // Subject drilldown inside an in-flight group/study run.
  | { kind: 'in-flight-subject'; runId: string; subject: string }
  // Group drilldown inside an in-flight *study* run — one of the study's
  // groups, viewed in the same live run.
  | { kind: 'in-flight-group'; runId: string; groupLabel: string }
  // Subject drilldown inside an in-flight study's group.
  | { kind: 'in-flight-group-subject'; runId: string; groupLabel: string; subject: string }

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


export interface QaFile {
  name: string
  rel: string
  size: number
  suffix: string
}


export interface QaPluginGroup {
  name: string
  files: QaFile[]
}


export interface QaArtifactsResponse {
  stage: string
  qa_dir: string
  available: boolean
  plugins: QaPluginGroup[]
  registered_plugins: string[]
}


// Pipeline stages where QA reporters exist. Used both to gate the QA
// tab in the node panel and to reject obvious "no plugins here" stages
// (analyze / report) without a round-trip.
export const QA_STAGES = new Set<string>(QA_STAGE_NAMES)


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
    case 'study-group-subject':
      return `${BASE}/study-runs/${encodeURIComponent(target.studyName)}/${encodeURIComponent(target.runId)}/group/${encodeURIComponent(target.groupLabel)}/subject/${encodeURIComponent(target.subject)}${suffix}`
    case 'config':
      return `${BASE}/configs/${encodeURIComponent(target.filename)}${suffix}`
    case 'config-subject':
      return `${BASE}/configs/${encodeURIComponent(target.filename)}/subject/${encodeURIComponent(target.subject)}${suffix}`
    case 'in-flight':
      return `${BASE}/runs/in-flight/${encodeURIComponent(target.runId)}${suffix}`
    case 'in-flight-subject':
      return `${BASE}/runs/in-flight/${encodeURIComponent(target.runId)}/subject/${encodeURIComponent(target.subject)}${suffix}`
    case 'in-flight-group':
      return `${BASE}/runs/in-flight/${encodeURIComponent(target.runId)}/group/${encodeURIComponent(target.groupLabel)}${suffix}`
    case 'in-flight-group-subject':
      return `${BASE}/runs/in-flight/${encodeURIComponent(target.runId)}/group/${encodeURIComponent(target.groupLabel)}/subject/${encodeURIComponent(target.subject)}${suffix}`
  }
}


export function isLiveTarget(target: GraphTarget): boolean {
  return (
    target.kind === 'in-flight'
    || target.kind === 'in-flight-subject'
    || target.kind === 'in-flight-group'
    || target.kind === 'in-flight-group-subject'
  )
}


/** True when the target is a config preview — outputs/file endpoints
 *  don't exist for these (no run dir yet). */
export function isConfigPreview(target: GraphTarget): boolean {
  return target.kind === 'config' || target.kind === 'config-subject'
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


/** Targets the QA endpoints accept. Finished subject / group→subject /
 *  study→group→subject runs plus their live in-flight counterparts —
 *  the in-flight endpoints scan the partial run dir so QA tabs
 *  populate as soon as each stage's plugins finish. ``config``
 *  previews still have no on-disk run, so they're excluded. */
export function targetSupportsQa(target: GraphTarget): boolean {
  return (
    target.kind === 'subject'
    || target.kind === 'group-subject'
    || target.kind === 'study-group-subject'
    || target.kind === 'in-flight'
    || target.kind === 'in-flight-subject'
    || target.kind === 'in-flight-group-subject'
  )
}


export async function fetchQaArtifacts(
  target: GraphTarget, stage: string,
): Promise<QaArtifactsResponse> {
  const res = await fetch(urlFor(target, `/qa/${encodeURIComponent(stage)}`))
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}


export async function regenerateQa(
  target: GraphTarget, stage: string,
): Promise<QaArtifactsResponse> {
  const res = await fetch(
    urlFor(target, `/qa/regenerate/${encodeURIComponent(stage)}`),
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
}


export function qaFileUrl(
  target: GraphTarget, stage: string, rel: string,
): string {
  return urlFor(target, `/qa/${encodeURIComponent(stage)}/file/${encodeURI(rel)}`)
}
