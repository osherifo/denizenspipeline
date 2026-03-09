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

// ── WebSocket ──

export function connectRunWs(runId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return new WebSocket(`${proto}//${window.location.host}/ws/runs/${runId}`)
}
