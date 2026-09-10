/** API client for the unified preprocessing surface: node library, pipelines, runs. */
import type {
  CheckpointRecord,
  CheckpointSummary,
  BuiltinCheckInfo,
  CheckDef,
  CheckEvaluation,
  ManifestDetail,
  MetricDetail,
  MetricInfo,
  MetricRunResult,
  NodeInnerStatus,
  NormsRow,
  RunNodeRecord,
  PipelineDoc,
  PipelineEvent,
  PipelineRunDetail,
  PipelineRunRequestBody,
  PipelineRunSummary,
  PipelineSummary,
  PipelineTemplateSummary,
  PreprocNodeDetail,
  PreprocNodeInfo,
} from './types'

const BASE = '/api'

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const text = await res.text()
    let detail = text
    try {
      const parsed = JSON.parse(text)
      if (parsed && typeof parsed.detail === 'string') detail = parsed.detail
    } catch { /* plain text */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

const post = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

const enc = encodeURIComponent

// ── node library ──────────────────────────────────────────────────

export async function fetchNodeLibrary(kind?: string): Promise<{ nodes: PreprocNodeInfo[]; shadowed: { name: string; shadowed_source: string }[] }> {
  return json(`${BASE}/preproc/nodes${kind ? `?kind=${enc(kind)}` : ''}`)
}

export async function fetchNodeDetail(name: string): Promise<PreprocNodeDetail> {
  return json(`${BASE}/preproc/nodes/${enc(name)}`)
}

export async function nodePreflight(name: string): Promise<{ ok: boolean; errors: string[]; warnings: string[] }> {
  return json(`${BASE}/preproc/nodes/${enc(name)}/preflight`)
}

export async function fetchNodeScaffold(kind: string): Promise<{ kind: string; code: string }> {
  return json(`${BASE}/preproc/nodes/scaffold/${enc(kind)}`)
}

export async function saveNodeCode(name: string, code: string): Promise<{ saved: boolean; path: string }> {
  return json(`${BASE}/preproc/nodes`, post({ name, code }))
}

export async function importPipelineFile(path: string, name?: string): Promise<{
  imported: boolean; node: string; shape: string; path: string; inputs: string[]; outputs: string[]; warnings: string[]
}> {
  return json(`${BASE}/preproc/nodes/import`, post({ path, name: name || null }))
}

export async function rescanNodes(): Promise<{ n_nodes: number; shadowed: number }> {
  return json(`${BASE}/preproc/nodes/rescan`, { method: 'POST' })
}

// ── pipelines ─────────────────────────────────────────────────────

export async function fetchPipelines(): Promise<{ pipelines: PipelineSummary[]; legacy: { name: string; path: string; hint: string }[]; root: string }> {
  return json(`${BASE}/preproc/pipelines`)
}

export async function fetchPipelineTemplates(): Promise<{ templates: PipelineTemplateSummary[] }> {
  return json(`${BASE}/preproc/pipelines/templates`)
}

export async function fetchPipelineTemplate(name: string): Promise<{ pipeline: PipelineDoc }> {
  return json(`${BASE}/preproc/pipelines/templates/${enc(name)}`)
}

/** "Save as template": writes to the user tier; the run panel is dropped server-side. */
export async function savePipelineTemplate(name: string, pipeline: PipelineDoc): Promise<{ saved: boolean; name: string; tier: 'user'; path: string; warnings: string[]; errors: string[] }> {
  return json(`${BASE}/preproc/pipelines/templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, pipeline }),
  })
}

export async function deletePipelineTemplate(name: string): Promise<{ deleted: boolean }> {
  return json(`${BASE}/preproc/pipelines/templates/${enc(name)}`, { method: 'DELETE' })
}

export async function fetchPipeline(name: string): Promise<{ name: string; pipeline: PipelineDoc; path: string }> {
  return json(`${BASE}/preproc/pipelines/${enc(name)}`)
}

export async function savePipeline(name: string, pipeline: PipelineDoc): Promise<{ saved: boolean; name: string; path: string; errors: string[] }> {
  return json(`${BASE}/preproc/pipelines/${enc(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline }),
  })
}

export async function deletePipeline(name: string): Promise<{ deleted: boolean }> {
  return json(`${BASE}/preproc/pipelines/${enc(name)}`, { method: 'DELETE' })
}

export async function validatePipeline(pipeline: PipelineDoc): Promise<{ ok: boolean; errors: string[]; is_linear: boolean }> {
  return json(`${BASE}/preproc/pipelines/validate`, post({ pipeline }))
}

export async function runPipeline(body: PipelineRunRequestBody): Promise<{ run_id: string; status: string }> {
  return json(`${BASE}/preproc/pipelines/run`, post(body))
}

// ── runs ──────────────────────────────────────────────────────────

export async function fetchPipelineRuns(): Promise<{ runs: PipelineRunSummary[] }> {
  return json(`${BASE}/preproc/runs`)
}

export async function fetchPipelineRun(runId: string, nipype = true): Promise<PipelineRunDetail> {
  return json(`${BASE}/preproc/runs/${enc(runId)}?nipype=${nipype ? 'true' : 'false'}`)
}

export async function fetchPipelineRunEvents(runId: string, offset = 0): Promise<{ events: PipelineEvent[]; offset: number }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/events?offset=${offset}`)
}

export async function fetchPipelineRunLog(runId: string, tail = 200): Promise<{ lines: string[]; total?: number }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/log?tail=${tail}`)
}

export async function fetchRunCrash(runId: string, name: string): Promise<{ name: string; text: string }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/crashes/${enc(name)}`)
}

// ── checkpoints from the UI ──

export async function fetchCheckMetrics(): Promise<{ metrics: MetricInfo[]; addons_dir?: string; hidden?: number }> {
  return json(`${BASE}/preproc/checks/metrics`)
}

export async function fetchMetricScaffold(): Promise<{ code: string }> {
  return json(`${BASE}/preproc/checks/metrics/scaffold`)
}

export async function fetchMetric(name: string): Promise<MetricDetail> {
  return json(`${BASE}/preproc/checks/metrics/${enc(name)}`)
}

/** Create or update a user metric: writes $FMRIFLOW_HOME/addons/checks/<name>.py and reloads. */
export async function saveMetric(name: string, code: string): Promise<{ saved: boolean; name: string; path: string; metrics: MetricInfo[] }> {
  return json(`${BASE}/preproc/checks/metrics/${enc(name)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }),
  })
}

export async function deleteMetric(name: string): Promise<{ deleted: boolean; metrics: MetricInfo[] }> {
  return json(`${BASE}/preproc/checks/metrics/${enc(name)}`, { method: 'DELETE' })
}

/** Apply a metric to one file without recording anything (the editor's try-it). */
export async function runMetric(name: string, path: string): Promise<MetricRunResult> {
  return json(`${BASE}/preproc/checks/metrics/${enc(name)}/run`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }),
  })
}

export async function fetchNorms(): Promise<{ rows: NormsRow[]; user: Record<string, unknown>; path: string }> {
  return json(`${BASE}/preproc/checks/norms`)
}

export async function saveNorms(norms: Record<string, unknown>): Promise<{ saved: boolean; rows: NormsRow[] }> {
  return json(`${BASE}/preproc/checks/norms`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ norms }) })
}

export async function fetchNodeChecks(nodeType: string): Promise<{ checks: BuiltinCheckInfo[] }> {
  return json(`${BASE}/preproc/nodes/${encodeURIComponent(nodeType)}/checks`)
}

export async function evaluateCheck(check: CheckDef, runId: string, nodeId: string, sequence?: string): Promise<CheckEvaluation> {
  return json(`${BASE}/preproc/checks/evaluate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ check, run_id: runId, node_id: nodeId, sequence: sequence ?? null }),
  })
}

// ── one node of one run (the node popup) ──

export async function fetchRunNode(runId: string, nodeId: string): Promise<RunNodeRecord> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/nodes/${enc(nodeId)}`)
}

export async function fetchRunNodeLog(runId: string, nodeId: string, tail = 500): Promise<{ lines: string[]; total: number }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/nodes/${enc(nodeId)}/log?tail=${tail}`)
}

export async function fetchRunNodeInner(runId: string, nodeId: string, cap = 500): Promise<NodeInnerStatus> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/nodes/${enc(nodeId)}/inner?cap=${cap}`)
}

export async function fetchRunNodeManifest(runId: string, nodeId: string): Promise<ManifestDetail> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/nodes/${enc(nodeId)}/manifest`)
}

/** Ends with `/report/` so the report's relative asset URLs resolve under it. */
export function runNodeReportUrl(runId: string, nodeId: string): string {
  return `${BASE}/preproc/runs/${enc(runId)}/nodes/${enc(nodeId)}/report/`
}

export async function fetchRunCheckpoints(runId: string): Promise<{ checkpoints: CheckpointRecord[]; summary: CheckpointSummary }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/checkpoints`)
}

export function checkpointThumbnailUrl(runId: string, index: number): string {
  return `${BASE}/preproc/runs/${enc(runId)}/checkpoints/${index}/thumbnail`
}

export async function cancelPipelineRun(runId: string): Promise<{ cancelled: boolean; reason?: string }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/cancel`, { method: 'POST' })
}

export async function resumePipelineRun(runId: string): Promise<{ run_id: string; resumed_from: string }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/resume`, { method: 'POST' })
}

export async function restartPipelineRun(runId: string): Promise<{ run_id: string; restarted_from: string }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}/restart`, { method: 'POST' })
}

export async function deletePipelineRun(runId: string): Promise<{ deleted: boolean }> {
  return json(`${BASE}/preproc/runs/${enc(runId)}`, { method: 'DELETE' })
}

export function openPipelineRunSocket(runId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${proto}//${window.location.host}/ws/preproc/${enc(runId)}`)
}
