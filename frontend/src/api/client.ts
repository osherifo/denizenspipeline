/** Typed API client for the Denizens Pipeline backend. */

import type {
  PluginMetadata,
  PluginInfo,
  StageInfo,
  PipelineConfig,
  ValidationResult,
  RunSummary,
  ParamSchema,
  CodeValidationResult,
  SavePluginResult,
  UserPlugin,
  TemplateResult,
  ConfigSummary,
  ConfigDetail,
  BackendInfo,
  ManifestSummary,
  ManifestDetail,
  CollectResult,
  ErrorEntry,
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

// ── Plugins ──

export async function fetchPlugins(): Promise<PluginMetadata> {
  return json(`${BASE}/plugins`)
}

export async function fetchPlugin(category: string, name: string): Promise<PluginInfo> {
  return json(`${BASE}/plugins/${category}/${name}`)
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

export async function fetchDefaults(category: string, plugin: string): Promise<{ params: Record<string, unknown> }> {
  return json(`${BASE}/config/defaults`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, plugin }),
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

// ── Plugin Editor ──

export async function validatePluginCode(code: string, category?: string): Promise<CodeValidationResult> {
  return json(`${BASE}/plugins/validate-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, category: category ?? null }),
  })
}

export async function savePlugin(code: string, name: string, category: string): Promise<SavePluginResult> {
  return json(`${BASE}/plugins/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, name, category }),
  })
}

export async function fetchUserPlugins(): Promise<UserPlugin[]> {
  return json(`${BASE}/plugins/user`)
}

export async function fetchUserPluginCode(name: string): Promise<{ name: string; code: string }> {
  return json(`${BASE}/plugins/user/${name}`)
}

export async function deleteUserPlugin(name: string): Promise<{ deleted: boolean; name: string }> {
  return json(`${BASE}/plugins/user/${name}`, { method: 'DELETE' })
}

export async function fetchTemplate(category: string, name: string): Promise<TemplateResult> {
  return json(`${BASE}/plugins/template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, name }),
  })
}

export async function fetchTemplateCategories(): Promise<string[]> {
  return json(`${BASE}/plugins/template-categories`)
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
