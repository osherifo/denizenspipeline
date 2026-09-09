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
  ConvertManifestSummary,
  ConvertManifestDetail,
  DicomScanResult,
  BatchRunParams,
  BatchSummary,
  SavedConvertConfig,
  SavedConvertConfigDetail,
  PreprocRunSummary,
  AutoflattenConfigSummary,
  AutoflattenConfigDetail,
  ConvertRunSummary,
  AutoflattenRunSummary,
  AnalysisRunSummary,
  WorkflowConfigSummary,
  WorkflowConfigDetail,
  WorkflowRunSummary,
  HubSourcesSnapshot,
  HubCatalogItem,
  HubInstallResult,
  HubPublishResult,
  HubProvenanceMap,
  ConvertDecisionTable,
  ConvertFlow,
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

export interface ModuleCode {
  name: string
  category: string
  path: string
  code: string
  class_start: number | null
  class_end: number | null
}

export async function fetchModuleCode(category: string, name: string): Promise<ModuleCode> {
  return json(`${BASE}/modules/${encodeURIComponent(category)}/${encodeURIComponent(name)}/code`)
}

export interface SaveModuleCodeResult {
  saved: boolean
  name: string
  category: string
  path: string
  bytes: number
  restart_required: boolean
}

export async function saveModuleCode(
  category: string, name: string, code: string,
): Promise<SaveModuleCodeResult> {
  return json(`${BASE}/modules/${encodeURIComponent(category)}/${encodeURIComponent(name)}/code`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
}

export interface ReloadModuleResult {
  reloaded: boolean
  module: string
  replaced: boolean
}

export async function reloadModule(
  category: string, name: string,
): Promise<ReloadModuleResult> {
  return json(`${BASE}/modules/${encodeURIComponent(category)}/${encodeURIComponent(name)}/reload`, {
    method: 'POST',
  })
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

export async function fetchInFlightRuns(
  includeFinished: boolean = true,
): Promise<AnalysisRunSummary[]> {
  const qs = includeFinished ? '' : '?include_finished=false'
  const r = await json<{ runs: AnalysisRunSummary[] }>(`${BASE}/runs/in-flight${qs}`)
  return r.runs
}

export async function fetchInFlightRun(runId: string): Promise<AnalysisRunSummary> {
  return json(`${BASE}/runs/in-flight/${encodeURIComponent(runId)}`)
}

export async function cancelInFlightRun(runId: string): Promise<{ cancelled: boolean }> {
  return json(`${BASE}/runs/in-flight/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

export async function deleteInFlightRun(runId: string): Promise<{ deleted: boolean; removed_paths?: string[] }> {
  return json(`${BASE}/runs/in-flight/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
  })
}

// ── Workflows (end-to-end orchestration) ────────────────────────────────

export async function fetchWorkflowConfigs(): Promise<WorkflowConfigSummary[]> {
  return json(`${BASE}/workflows/configs`)
}

export async function fetchWorkflowConfigDetail(filename: string): Promise<WorkflowConfigDetail> {
  return json(`${BASE}/workflows/configs/${encodeURIComponent(filename)}`)
}

export async function runWorkflowConfig(
  filename: string,
): Promise<{ run_id: string; status: string; config: string }> {
  return json(`${BASE}/workflows/configs/${encodeURIComponent(filename)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
}

export async function saveWorkflowConfig(
  filename: string, yamlString: string,
): Promise<{ saved: boolean; path: string; errors: string[] }> {
  return json(`${BASE}/workflows/configs/${encodeURIComponent(filename)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ yaml_string: yamlString }),
  })
}

export async function copyWorkflowConfig(
  source: string, newFilename: string,
): Promise<{ saved: boolean; path: string; filename: string; errors: string[] }> {
  return json(`${BASE}/workflows/configs/${encodeURIComponent(source)}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_filename: newFilename }),
  })
}

export async function fetchWorkflowRuns(
  includeFinished: boolean = true,
): Promise<WorkflowRunSummary[]> {
  const qs = includeFinished ? '' : '?include_finished=false'
  const r = await json<{ runs: WorkflowRunSummary[] }>(`${BASE}/workflows/runs${qs}`)
  return r.runs
}

export async function fetchWorkflowRun(runId: string): Promise<WorkflowRunSummary> {
  return json(`${BASE}/workflows/runs/${encodeURIComponent(runId)}`)
}

export async function cancelWorkflowRun(runId: string): Promise<{ cancelled: boolean }> {
  return json(`${BASE}/workflows/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

export async function deleteWorkflowRun(runId: string): Promise<{
  deleted: boolean
  stage_results?: Array<{ stage: string; run_id: string; deleted: boolean; reason?: string }>
}> {
  return json(`${BASE}/workflows/runs/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
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

export async function fetchTemplate(
  category: string, name: string, stage?: string,
): Promise<TemplateResult> {
  return json(`${BASE}/modules/template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, name, stage }),
  })
}

export async function fetchTemplateCategories(): Promise<string[]> {
  return json(`${BASE}/modules/template-categories`)
}

/** Map of stage → value-type for QA reporters. The frontend pairs
 *  this with ``fetchTemplateCategories()`` to gate the stage dropdown
 *  in the "+ New module" dialog. */
export async function fetchQaStages(): Promise<Record<string, string>> {
  return json(`${BASE}/modules/qa-stages`)
}

// ── Preprocessing ──

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

export async function fetchPreprocRunLive(
  runId: string, _cap: number = 200,
): Promise<import('./types').PreprocRunLive> {
  // Pipeline runs: the run detail carries nipype_status.
  return json(`${BASE}/preproc/runs/${encodeURIComponent(runId)}?nipype=true`)
}

export async function fetchLabelMap(
  version: string = '25',
): Promise<{ version: string; labels: Record<string, string> }> {
  return json(`${BASE}/preproc/label-map?version=${encodeURIComponent(version)}`)
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

export async function copyHeuristic(name: string, newName: string): Promise<{ copied: boolean; source: string; name: string; path: string }> {
  return json(`${BASE}/convert/heuristics/${encodeURIComponent(name)}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_name: newName }),
  })
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

export async function deleteConvertManifest(subject: string): Promise<{ deleted: boolean; subject: string; path: string }> {
  return json(`${BASE}/convert/manifests/${encodeURIComponent(subject)}`, { method: 'DELETE' })
}

export async function validateConvertManifest(subject: string): Promise<{ errors: string[] }> {
  return json<{ errors: string[] }>(`${BASE}/convert/manifests/${encodeURIComponent(subject)}/validate`, { method: 'POST' })
}

export async function startDicomScan(sourceDir: string): Promise<import('./types').DicomScanJob> {
  return json(`${BASE}/convert/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_dir: sourceDir }),
  })
}

export async function fetchDicomScan(scanId: string): Promise<import('./types').DicomScanJob> {
  return json(`${BASE}/convert/scan/${encodeURIComponent(scanId)}`)
}

export async function cancelDicomScan(scanId: string): Promise<{ cancelled: boolean; reason?: string }> {
  return json(`${BASE}/convert/scan/${encodeURIComponent(scanId)}/cancel`, { method: 'POST' })
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

export async function fetchConvertRuns(
  includeFinished: boolean = true,
): Promise<ConvertRunSummary[]> {
  const qs = includeFinished ? '' : '?include_finished=false'
  const r = await json<{ runs: ConvertRunSummary[] }>(`${BASE}/convert/runs${qs}`)
  return r.runs
}

export async function fetchConvertRun(runId: string): Promise<ConvertRunSummary> {
  return json(`${BASE}/convert/runs/${encodeURIComponent(runId)}`)
}

export async function cancelConvertRun(runId: string): Promise<{ cancelled: boolean }> {
  return json(`${BASE}/convert/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

export async function deleteConvertRun(runId: string): Promise<{ deleted: boolean; removed_paths?: string[] }> {
  return json(`${BASE}/convert/runs/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
  })
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

export async function fetchAutoflattenRunsList(
  includeFinished: boolean = true,
): Promise<AutoflattenRunSummary[]> {
  const qs = includeFinished ? '' : '?include_finished=false'
  const r = await json<{ runs: AutoflattenRunSummary[] }>(`${BASE}/autoflatten/runs${qs}`)
  return r.runs
}

export async function cancelAutoflattenRun(runId: string): Promise<{ cancelled: boolean }> {
  return json(`${BASE}/autoflatten/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

export async function deleteAutoflattenRun(runId: string): Promise<{ deleted: boolean }> {
  return json(`${BASE}/autoflatten/runs/${encodeURIComponent(runId)}`, {
    method: 'DELETE',
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

export async function saveAutoflattenConfig(
  filename: string,
  yamlString: string,
): Promise<{ saved: boolean; path: string; errors: string[] }> {
  return json(`${BASE}/autoflatten/configs/${encodeURIComponent(filename)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ yaml_string: yamlString }),
  })
}

export async function copyAutoflattenConfig(
  source: string,
  newFilename: string,
): Promise<{ saved: boolean; path: string; filename: string; errors: string[] }> {
  return json(`${BASE}/autoflatten/configs/${encodeURIComponent(source)}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_filename: newFilename }),
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

/** What the heuristic did with each DICOM series — reconstructed from the
 *  provenance heudiconv leaves behind. 404 when a dataset has none. */
export async function fetchConvertDecisionTable(
  bids_dir: string, subject: string, session?: string,
): Promise<ConvertDecisionTable> {
  const qs = new URLSearchParams({ bids_dir, subject }).toString()
  return json(`${BASE}/convert/decision-table?${qs}${session ? `&session=${encodeURIComponent(session)}` : ''}`)
}

export async function fetchConvertFlow(bids_dir: string): Promise<ConvertFlow> {
  const qs = new URLSearchParams({ bids_dir }).toString()
  return json(`${BASE}/convert/flow?${qs}`)
}

export async function fetchAutoflattenVisualizations(
  subjects_dir: string, subject: string,
): Promise<{ images: Record<string, string> }> {
  const qs = new URLSearchParams({ subjects_dir, subject }).toString()
  return json(`${BASE}/autoflatten/visualizations?${qs}`)
}

/** URL for a rendered flatmap of one hemisphere — the cortex alone, shaded
 *  by a per-vertex scalar. Not the CLI's .flat.patch.png, which is a QA
 *  figure bundling the outline, a distortion map and a histogram. */
export function autoflattenFlatRenderUrl(
  subjects_dir: string, subject: string, hemi: 'lh' | 'rh', scalar = 'curv',
): string {
  const qs = new URLSearchParams({ subjects_dir, subject, hemi, scalar }).toString()
  return `${BASE}/autoflatten/flatrender?${qs}`
}

export async function fetchAutoflattenFlatRenderInfo(
  subjects_dir: string, subject: string,
): Promise<{ hemispheres: Record<string, { scalars: string[] }> }> {
  const qs = new URLSearchParams({ subjects_dir, subject }).toString()
  return json(`${BASE}/autoflatten/flatrender-info?${qs}`)
}

// ── Triage (automatic error capture) ────────────────────────────────────

export async function fetchTriage(
  runId: string,
): Promise<import('./types').TriageRecord | null> {
  const res = await fetch(`${BASE}/triage/${encodeURIComponent(runId)}`)
  if (res.status === 404) return null
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

export async function rescanTriage(runId: string) {
  return json<import('./types').TriageRecord>(
    `${BASE}/triage/${encodeURIComponent(runId)}/rescan`,
    { method: 'POST' },
  )
}

export async function saveNewErrorFromCapture(body: {
  run_id: string
  title: string
  tags?: string[]
  root_cause?: string
  fix?: string
  references?: string[]
  slug?: string
}): Promise<import('./types').NewErrorFromCaptureResult> {
  return json(`${BASE}/errors/from-capture`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// ── Settings ──

export async function fetchSettings(): Promise<import('./types').SettingsSnapshot> {
  return json(`${BASE}/settings`)
}

export async function fetchVersion(): Promise<{ version: string }> {
  return json(`${BASE}/settings/version`)
}

export async function saveSettings(
  body: import('./types').SettingsUpdate,
): Promise<import('./types').SettingsSnapshot> {
  return json(`${BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// ── Result roots (read-only extra scan locations) ──

export async function fetchResultRoots(): Promise<import('./types').ResultRootsSnapshot> {
  return json(`${BASE}/settings/result-roots`)
}

export async function addResultRoot(path: string): Promise<import('./types').ResultRootsSnapshot> {
  return json(`${BASE}/settings/result-roots`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
}

export async function removeResultRoot(path: string): Promise<import('./types').ResultRootsSnapshot> {
  return json(`${BASE}/settings/result-roots`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
}

// ── Group runs ──

export async function fetchGroupRuns(
  opts: { name?: string } = {},
): Promise<import('./types').GroupRunListing[]> {
  const q = opts.name ? `?name=${encodeURIComponent(opts.name)}` : ''
  return json(`${BASE}/group-runs${q}`)
}

export async function fetchGroupRun(
  name: string,
  runId?: string,
): Promise<import('./types').GroupRunDetail> {
  const path = runId
    ? `${BASE}/group-runs/${encodeURIComponent(name)}/${encodeURIComponent(runId)}`
    : `${BASE}/group-runs/${encodeURIComponent(name)}`
  return json(path)
}

// ── Study runs ──

export async function fetchStudyRuns(
  opts: { name?: string } = {},
): Promise<import('./types').StudyRunListing[]> {
  const q = opts.name ? `?name=${encodeURIComponent(opts.name)}` : ''
  return json(`${BASE}/study-runs${q}`)
}

export async function fetchStudyRun(
  name: string,
  runId: string,
): Promise<import('./types').StudyRunDetail> {
  return json(
    `${BASE}/study-runs/${encodeURIComponent(name)}/${encodeURIComponent(runId)}`,
  )
}

// ── Artifact Hub ──

export async function fetchHubSources(): Promise<HubSourcesSnapshot> {
  return json(`${BASE}/hub/sources`)
}

export async function addHubSource(body: {
  name: string; url: string; tier: string; branch?: string; token?: string
}): Promise<HubSourcesSnapshot> {
  return json(`${BASE}/hub/sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function removeHubSource(sid: string): Promise<HubSourcesSnapshot> {
  return json(`${BASE}/hub/sources/${encodeURIComponent(sid)}`, { method: 'DELETE' })
}

export async function setHubToken(sid: string, token: string | null): Promise<HubSourcesSnapshot> {
  return json(`${BASE}/hub/sources/${encodeURIComponent(sid)}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
}

export async function syncHubSource(sid: string): Promise<{ synced: boolean; artifacts: number; warnings?: string[] }> {
  return json(`${BASE}/hub/sources/${encodeURIComponent(sid)}/sync`, { method: 'POST' })
}

export async function fetchHubBranches(sid: string): Promise<{ branches: string[] }> {
  return json(`${BASE}/hub/sources/${encodeURIComponent(sid)}/branches`)
}

export async function fetchHubLocalArtifacts(): Promise<{ artifacts: Record<string, string[]> }> {
  return json(`${BASE}/hub/local`)
}

export async function fetchHubCatalog(kind?: string): Promise<{ items: HubCatalogItem[]; total: number }> {
  const qs = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  return json(`${BASE}/hub/catalog${qs}`)
}

export async function fetchHubProvenance(): Promise<HubProvenanceMap> {
  return json(`${BASE}/hub/provenance`)
}

export async function fetchHubArtifact(sid: string, kind: string, name: string): Promise<HubCatalogItem> {
  return json(`${BASE}/hub/catalog/${encodeURIComponent(sid)}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`)
}

export interface HubInstallManyResult {
  installed: number
  skipped: number
  failed: { kind: string; name: string; error: string }[]
  names: string[]
  kind: string | null
}

/** Bulk install: omit `kind` for every kind, omit `source_id` for every source. */
export async function installHubMany(body: {
  source_id?: string; kind?: string
}): Promise<HubInstallManyResult> {
  return json(`${BASE}/hub/install-many`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function installHubArtifact(body: {
  source_id: string; kind: string; name: string
}): Promise<HubInstallResult> {
  return json(`${BASE}/hub/install`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function publishHubArtifact(body: {
  source_id: string; kind: string; name: string; description?: string
}): Promise<HubPublishResult> {
  return json(`${BASE}/hub/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function publishHubKind(body: {
  source_id: string; kind: string
}): Promise<HubPublishResult> {
  return json(`${BASE}/hub/publish-kind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
