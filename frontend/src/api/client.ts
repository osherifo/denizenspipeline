/** Typed API client for the fMRIflow backend. */

import type {
  ModuleMetadata,
  ModuleInfo,
  StageInfo,
  PipelineConfig,
  ValidationResult,
  RunSummary,
  ParamSchema,
  CodeValidationResult,
  SaveModuleResult,
  UserModule,
  TemplateResult,
  ConfigSummary,
  ConfigDetail,
  BackendInfo,
  ManifestSummary,
  ManifestDetail,
  CollectResult,
  ErrorEntry,
  HeuristicInfo,
  SaveHeuristicParams,
  ToolStatus,
  ConvertManifestSummary,
  ConvertManifestDetail,
  DicomScanResult,
  BatchRunParams,
  BatchSummary,
  SavedConvertConfig,
  SavedConvertConfigDetail,
  PreprocConfigSummary,
  PreprocConfigDetail,
  PreprocRunSummary,
  AutoflattenConfigSummary,
  AutoflattenConfigDetail,
} from './types'

const BASE = '/api'

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// ── Modules ──

export async function fetchModules(): Promise<ModuleMetadata> {
  return json(`${BASE}/modules`)
}

export async function fetchModule(category: string, name: string): Promise<ModuleInfo> {
  return json(`${BASE}/modules/${category}/${name}`)
}

export async function fetchStages(): Promise<StageInfo[]> {
  return json(`${BASE}/stages`)
}

// ── Config ──

export async function validateConfig(config: PipelineConfig): Promise<ValidationResult> {
  return json(`${BASE}/config/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  })
}

export async function configFromYaml(yaml: string): Promise<{ config: PipelineConfig; errors: string[] }> {
  const res = await fetch(`${BASE}/config/from-yaml`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: yaml,
  })
  return res.json()
}

export async function configToYaml(config: PipelineConfig): Promise<string> {
  const res = await fetch(`${BASE}/config/to-yaml`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  })
  return res.text()
}

export async function fetchDefaults(category: string, module: string): Promise<{ params: Record<string, unknown> }> {
  return json(`${BASE}/config/defaults`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, module }),
  })
}

// ── Runs ──

export async function fetchRuns(opts?: {
  limit?: number
  experiment?: string
  subject?: string
}): Promise<RunSummary[]> {
  const params = new URLSearchParams()
  if (opts?.limit) params.set('limit', String(opts.limit))
  if (opts?.experiment) params.set('experiment', opts.experiment)
  if (opts?.subject) params.set('subject', opts.subject)
  const qs = params.toString()
  return json(`${BASE}/runs${qs ? '?' + qs : ''}`)
}

export async function fetchRun(runId: string): Promise<RunSummary> {
  return json(`${BASE}/runs/${runId}`)
}

export async function startRun(config: PipelineConfig): Promise<{ run_id: string; status: string }> {
  return json(`${BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  })
}

export function artifactUrl(runId: string, artifactName: string): string {
  return `${BASE}/runs/${runId}/artifacts/${artifactName}`
}

export async function deleteArtifact(
  runId: string, artifactName: string,
): Promise<{ deleted: boolean; path: string }> {
  return json(`${BASE}/runs/${runId}/artifacts/${artifactName}`, {
    method: 'DELETE',
  })
}

// ── Experiment Configs ──

export async function fetchConfigs(): Promise<ConfigSummary[]> {
  return json(`${BASE}/configs`)
}

export type FieldValues = Record<string, string[]>

export async function fetchFieldValues(): Promise<FieldValues> {
  return json(`${BASE}/configs/field-values`)
}

export async function fetchConfigDetail(filename: string): Promise<ConfigDetail> {
  return json(`${BASE}/configs/${encodeURIComponent(filename)}`)
}

export async function validateConfigFile(filename: string): Promise<ValidationResult> {
  return json(`${BASE}/configs/${encodeURIComponent(filename)}/validate`, { method: 'POST' })
}

export async function saveConfigFile(
  filename: string, yamlString: string,
): Promise<{ saved: boolean; path: string; errors: string[] }> {
  return json(`${BASE}/configs/${encodeURIComponent(filename)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ yaml_string: yamlString }),
  })
}

export async function copyConfigFile(
  source: string, newFilename: string,
): Promise<{ saved: boolean; path: string; filename: string; errors: string[] }> {
  return json(`${BASE}/configs/${encodeURIComponent(source)}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_filename: newFilename }),
  })
}

export async function startRunFromConfig(
  configPath: string,
  overrides?: Record<string, unknown>,
): Promise<{ run_id: string; status: string }> {
  return json(`${BASE}/runs/from-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_path: configPath, overrides: overrides ?? null }),
  })
}

// ── Module Editor ──

export async function validateModuleCode(code: string, category?: string): Promise<CodeValidationResult> {
  return json(`${BASE}/modules/validate-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, category: category ?? null }),
  })
}

export async function saveModule(code: string, name: string, category: string): Promise<SaveModuleResult> {
  return json(`${BASE}/modules/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, name, category }),
  })
}

export async function fetchUserModules(): Promise<UserModule[]> {
  return json(`${BASE}/modules/user`)
}

export async function fetchUserModuleCode(name: string): Promise<{ name: string; code: string }> {
  return json(`${BASE}/modules/user/${name}`)
}

export async function deleteUserModule(name: string): Promise<{ deleted: boolean; name: string }> {
  return json(`${BASE}/modules/user/${name}`, { method: 'DELETE' })
}

export async function fetchTemplate(category: string, name: string): Promise<TemplateResult> {
  return json(`${BASE}/modules/template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, name }),
  })
}

export async function fetchTemplateCategories(): Promise<string[]> {
  return json(`${BASE}/modules/template-categories`)
}

// ── Preprocessing ──

export async function fetchPreprocBackends(): Promise<BackendInfo[]> {
  const r = await json<{ backends: BackendInfo[] }>(`${BASE}/preproc/backends`)
  return r.backends
}

export async function fetchManifests(): Promise<ManifestSummary[]> {
  const r = await json<{ manifests: ManifestSummary[] }>(`${BASE}/preproc/manifests`)
  return r.manifests
}

export async function rescanManifests(): Promise<ManifestSummary[]> {
  const r = await json<{ manifests: ManifestSummary[] }>(`${BASE}/preproc/manifests/rescan`, { method: 'POST' })
  return r.manifests
}

export async function fetchManifestDetail(subject: string): Promise<ManifestDetail> {
  return json(`${BASE}/preproc/manifests/${encodeURIComponent(subject)}`)
}

export async function validateManifest(
  subject: string,
  configFilename?: string,
): Promise<{ errors: string[] }> {
  return json(`${BASE}/preproc/manifests/${encodeURIComponent(subject)}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_filename: configFilename ?? null }),
  })
}

export async function collectPreprocOutputs(params: {
  backend: string
  output_dir: string
  subject: string
  task?: string
  sessions?: string[]
  bids_dir?: string
  run_map?: Record<string, string>
  backend_params?: Record<string, unknown>
}): Promise<CollectResult> {
  return json(`${BASE}/preproc/collect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function startPreprocRun(params: {
  backend: string
  output_dir: string
  subject: string
  bids_dir?: string
  raw_dir?: string
  work_dir?: string
  task?: string
  sessions?: string[]
  run_map?: Record<string, string>
  backend_params?: Record<string, unknown>
  confounds?: Record<string, unknown>
}): Promise<{ run_id: string; status: string }> {
  return json(`${BASE}/preproc/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function validatePreprocConfig(params: {
  backend: string
  output_dir: string
  subject: string
  bids_dir?: string
  raw_dir?: string
  backend_params?: Record<string, unknown>
}): Promise<{ valid: boolean; errors: string[] }> {
  return json(`${BASE}/preproc/validate-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function fetchPreprocConfigs(): Promise<PreprocConfigSummary[]> {
  return json(`${BASE}/preproc/configs`)
}

export async function fetchPreprocConfigDetail(filename: string): Promise<PreprocConfigDetail> {
  return json(`${BASE}/preproc/configs/${encodeURIComponent(filename)}`)
}

export async function runPreprocConfigFile(
  filename: string,
  overrides?: Record<string, unknown>,
): Promise<{ run_id: string; status: string; config: string }> {
  return json(`${BASE}/preproc/configs/${encodeURIComponent(filename)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(overrides || {}),
  })
}

export async function fetchPreprocRuns(
  includeFinished: boolean = true,
): Promise<PreprocRunSummary[]> {
  const qs = includeFinished ? '' : '?include_finished=false'
  const r = await json<{ runs: PreprocRunSummary[] }>(`${BASE}/preproc/runs${qs}`)
  return r.runs
}

export async function fetchPreprocRun(runId: string): Promise<PreprocRunSummary> {
  return json(`${BASE}/preproc/runs/${encodeURIComponent(runId)}`)
}

export async function cancelPreprocRun(runId: string): Promise<{ cancelled: boolean }> {
  return json(`${BASE}/preproc/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

// ── Error Knowledge Base ──

export async function fetchErrors(opts?: {
  stage?: string
  tag?: string
  q?: string
}): Promise<ErrorEntry[]> {
  const params = new URLSearchParams()
  if (opts?.stage) params.set('stage', opts.stage)
  if (opts?.tag) params.set('tag', opts.tag)
  if (opts?.q) params.set('q', opts.q)
  const qs = params.toString()
  const r = await json<{ errors: ErrorEntry[]; total: number }>(`${BASE}/errors${qs ? '?' + qs : ''}`)
  return r.errors
}

// ── WebSocket ──

export function connectRunWs(runId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${proto}//${window.location.host}/ws/runs/${runId}`)
}

export function connectPreprocWs(runId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${proto}//${window.location.host}/ws/preproc/${runId}`)
}

// ── DICOM-to-BIDS Conversion ────────────────────────────────────────────

export async function fetchConvertHeuristics(): Promise<HeuristicInfo[]> {
  const r = await json<{ heuristics: HeuristicInfo[] }>(`${BASE}/convert/heuristics`)
  return r.heuristics
}

export async function fetchHeuristicCode(name: string): Promise<string> {
  const r = await json<{ name: string; code: string }>(`${BASE}/convert/heuristics/${encodeURIComponent(name)}/code`)
  return r.code
}

export async function saveHeuristic(params: SaveHeuristicParams): Promise<{ saved: boolean; name: string; path: string }> {
  return json(`${BASE}/convert/heuristics/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function fetchHeuristicTemplate(name: string = 'my_study'): Promise<{ code: string; name: string }> {
  return json(`${BASE}/convert/heuristics/template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export async function deleteHeuristic(name: string): Promise<{ deleted: boolean; name: string }> {
  return json(`${BASE}/convert/heuristics/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export async function fetchConvertTools(): Promise<ToolStatus[]> {
  const r = await json<{ tools: ToolStatus[] }>(`${BASE}/convert/tools`)
  return r.tools
}

export async function fetchConvertManifests(): Promise<ConvertManifestSummary[]> {
  const r = await json<{ manifests: ConvertManifestSummary[] }>(`${BASE}/convert/manifests`)
  return r.manifests
}

export async function rescanConvertManifests(): Promise<ConvertManifestSummary[]> {
  const r = await json<{ manifests: ConvertManifestSummary[] }>(`${BASE}/convert/manifests/rescan`, { method: 'POST' })
  return r.manifests
}

export async function fetchConvertManifestDetail(subject: string): Promise<ConvertManifestDetail> {
  return json<ConvertManifestDetail>(`${BASE}/convert/manifests/${encodeURIComponent(subject)}`)
}

export async function validateConvertManifest(subject: string): Promise<{ errors: string[] }> {
  return json<{ errors: string[] }>(`${BASE}/convert/manifests/${encodeURIComponent(subject)}/validate`, { method: 'POST' })
}

export async function scanDicomDirectory(sourceDir: string): Promise<DicomScanResult> {
  return json<DicomScanResult>(`${BASE}/convert/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_dir: sourceDir }),
  })
}

export async function collectConvertOutputs(params: {
  bids_dir: string; subject: string; source_dir?: string; heuristic?: string;
  sessions?: string[]; dataset_name?: string;
}): Promise<{ manifest: ConvertManifestDetail; manifest_path: string }> {
  return json(`${BASE}/convert/collect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function startConvertRun(params: {
  source_dir: string; bids_dir: string; subject: string; heuristic: string;
  sessions?: string[]; dataset_name?: string; grouping?: string;
  minmeta?: boolean; overwrite?: boolean; validate_bids?: boolean;
}): Promise<{ run_id: string; status: string }> {
  return json(`${BASE}/convert/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export function connectConvertWs(runId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${proto}//${window.location.host}/ws/convert/${runId}`)
}

// ── Batch Conversion ─────────────────────────────────────────────────────

export async function startBatchConvert(params: BatchRunParams): Promise<{ batch_id: string; status: string; n_jobs: number }> {
  return json(`${BASE}/convert/batch/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function fetchBatchStatus(batchId: string): Promise<BatchSummary> {
  return json(`${BASE}/convert/batch/${encodeURIComponent(batchId)}`)
}

export async function retryFailedBatch(batchId: string): Promise<{ failed_jobs: Array<{ job_id: string; subject: string; session: string; error: string | null }> }> {
  return json(`${BASE}/convert/batch/${encodeURIComponent(batchId)}/retry-failed`, { method: 'POST' })
}

export async function parseBatchYaml(yamlText: string): Promise<BatchRunParams> {
  return json(`${BASE}/convert/batch/parse-yaml`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ yaml_text: yamlText }),
  })
}

export function connectBatchWs(batchId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${proto}//${window.location.host}/ws/convert/batch/${batchId}`)
}

// ── Saved Convert Configs ────────────────────────────────────────────────

export async function fetchSavedConvertConfigs(): Promise<SavedConvertConfig[]> {
  const r = await json<{ configs: SavedConvertConfig[] }>(`${BASE}/convert/configs`)
  return r.configs
}

export async function fetchSavedConvertConfig(filename: string): Promise<SavedConvertConfigDetail> {
  return json(`${BASE}/convert/configs/${encodeURIComponent(filename)}`)
}

export async function saveConvertRunConfig(params: {
  name?: string; description?: string; params: Record<string, unknown>
}): Promise<SavedConvertConfig> {
  return json(`${BASE}/convert/configs/save-run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function saveConvertBatchConfig(params: {
  name?: string; description?: string; params: Record<string, unknown>
}): Promise<SavedConvertConfig> {
  return json(`${BASE}/convert/configs/save-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function deleteSavedConvertConfig(filename: string): Promise<{ deleted: boolean }> {
  return json(`${BASE}/convert/configs/${encodeURIComponent(filename)}`, { method: 'DELETE' })
}

export async function runSavedConvertConfig(
  filename: string,
  overrides?: Record<string, unknown>,
): Promise<{ kind: 'single' | 'batch'; run_id?: string; batch_id?: string; status: string; config: string }> {
  return json(`${BASE}/convert/configs/${encodeURIComponent(filename)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(overrides || {}),
  })
}

// ── Autoflatten ────────────────────────────────────────────────────────

export async function fetchAutoflattenDoctor(): Promise<{ tools: { name: string; available: boolean; detail: string }[] }> {
  return json(`${BASE}/autoflatten/doctor`)
}

export async function fetchAutoflattenStatus(params: {
  subjects_dir: string; subject: string
}): Promise<{
  subject: string
  subject_dir_exists: boolean
  has_surfaces: boolean
  surfaces: Record<string, boolean>
  flat_patches: Record<string, string>
  has_flat_patches: boolean
  pycortex_surface: string | null
}> {
  return json(`${BASE}/autoflatten/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function fetchAutoflattenConfigs(): Promise<AutoflattenConfigSummary[]> {
  return json(`${BASE}/autoflatten/configs`)
}

export async function fetchAutoflattenConfigDetail(filename: string): Promise<AutoflattenConfigDetail> {
  return json(`${BASE}/autoflatten/configs/${encodeURIComponent(filename)}`)
}

export async function runAutoflattenConfig(
  filename: string,
  overrides?: Record<string, unknown>,
): Promise<{ run_id: string; status: string; config: string }> {
  return json(`${BASE}/autoflatten/configs/${encodeURIComponent(filename)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(overrides || {}),
  })
}

export async function startAutoflatten(params: {
  subjects_dir: string
  subject: string
  hemispheres?: string
  backend?: string
  parallel?: boolean
  overwrite?: boolean
  import_to_pycortex?: boolean
  pycortex_surface_name?: string
  flat_patch_lh?: string
  flat_patch_rh?: string
}): Promise<{ run_id: string; status: string }> {
  return json(`${BASE}/autoflatten/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
}

export async function fetchAutoflattenRun(runId: string): Promise<{
  run_id: string
  subject: string
  status: string
  result: {
    result: {
      subject: string
      source: string
      hemispheres: string[]
      flat_patches: Record<string, string>
      visualizations: Record<string, string>
      pycortex_surface: string | null
      elapsed_s: number
    }
    record: Record<string, unknown>
  } | null
  error: string | null
  started_at: number
  finished_at: number
  events: Array<{
    event: string
    level?: string
    message?: string
    error?: string
    timestamp?: number
    [key: string]: unknown
  }>
}> {
  return json(`${BASE}/autoflatten/runs/${runId}`)
}

export function connectAutoflattenWs(runId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${proto}//${window.location.host}/ws/autoflatten/${runId}`)
}

export function autoflattenImageUrl(path: string): string {
  return `${BASE}/autoflatten/image?path=${encodeURIComponent(path)}`
}

export async function fetchAutoflattenVisualizations(
  subjects_dir: string, subject: string,
): Promise<{ images: Record<string, string> }> {
  const qs = new URLSearchParams({ subjects_dir, subject }).toString()
  return json(`${BASE}/autoflatten/visualizations?${qs}`)
}
