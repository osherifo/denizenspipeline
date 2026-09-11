/** Analysis graph API: node catalog, port types, templates, saved graphs, validation, compilation, launch. */
import type {
  AnalysisGraphDoc,
  AnalysisGraphSummary,
  AnalysisNodeInfo,
  AnalysisPortType,
  AnalysisTemplateSummary,
} from './types'

const BASE = '/api'

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* not JSON */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const enc = encodeURIComponent

export function fetchAnalysisNodes(): Promise<{ nodes: AnalysisNodeInfo[] }> {
  return json(`${BASE}/analysis/nodes`)
}

export function fetchPortTypes(): Promise<{ types: AnalysisPortType[] }> {
  return json(`${BASE}/analysis/port-types`)
}

export function fetchAnalysisTemplates(): Promise<{ templates: AnalysisTemplateSummary[] }> {
  return json(`${BASE}/analysis/graphs/templates`)
}

export function fetchAnalysisTemplate(name: string): Promise<{ graph: AnalysisGraphDoc }> {
  return json(`${BASE}/analysis/graphs/templates/${enc(name)}`)
}

export function saveAnalysisTemplate(name: string, graph: AnalysisGraphDoc): Promise<{ saved: boolean; name: string; tier: 'user'; path: string; warnings: string[]; errors: string[] }> {
  return json(`${BASE}/analysis/graphs/templates`, { method: 'POST', body: JSON.stringify({ name, graph }) })
}

export function deleteAnalysisTemplate(name: string): Promise<{ deleted: boolean }> {
  return json(`${BASE}/analysis/graphs/templates/${enc(name)}`, { method: 'DELETE' })
}

export function fetchAnalysisGraphs(): Promise<{ graphs: AnalysisGraphSummary[]; root: string }> {
  return json(`${BASE}/analysis/graphs`)
}

export function fetchAnalysisGraph(name: string): Promise<{ name: string; graph: AnalysisGraphDoc; path: string }> {
  return json(`${BASE}/analysis/graphs/${enc(name)}`)
}

export function saveAnalysisGraph(name: string, graph: AnalysisGraphDoc): Promise<{ saved: boolean; name: string; path: string; errors: string[] }> {
  return json(`${BASE}/analysis/graphs/${enc(name)}`, { method: 'PUT', body: JSON.stringify({ graph }) })
}

export function deleteAnalysisGraph(name: string): Promise<{ deleted: boolean }> {
  return json(`${BASE}/analysis/graphs/${enc(name)}`, { method: 'DELETE' })
}

export function validateAnalysisGraph(graph: AnalysisGraphDoc, inputs: Record<string, unknown>): Promise<{ ok: boolean; errors: string[] }> {
  return json(`${BASE}/analysis/graphs/validate`, { method: 'POST', body: JSON.stringify({ graph, inputs }) })
}

/** The graph a subject stage config compiles to: a saved config by file name, or an inline config. */
export function compileAnalysisConfig(source: { filename?: string; config?: Record<string, unknown> }): Promise<{ graph: AnalysisGraphDoc }> {
  return json(`${BASE}/analysis/graphs/compile`, { method: 'POST', body: JSON.stringify(source) })
}

export function runAnalysisGraph(body: { graph?: AnalysisGraphDoc; graph_name?: string; inputs?: Record<string, unknown> }): Promise<{ run_id: string; status: string }> {
  return json(`${BASE}/analysis/graphs/run`, { method: 'POST', body: JSON.stringify(body) })
}
