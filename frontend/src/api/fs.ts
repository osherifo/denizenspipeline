/** Server-side directory browsing — paths as the server (container) sees them. */
export interface FsRoot { label: string; path: string; kind: 'data' | 'home' | 'extra' }
export interface FsEntry { name: string; path: string; is_dir: boolean; size?: number; is_symlink?: boolean; dangling?: boolean; link_target?: string }
export interface FsListing { path: string; parent: string | null; entries: FsEntry[]; truncated: boolean }

const BASE = '/api'

async function json<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    const text = await res.text()
    let detail = text
    try { const p = JSON.parse(text); if (typeof p.detail === 'string') detail = p.detail } catch { /* text */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

export async function fetchFsRoots(): Promise<{ roots: FsRoot[]; extra_roots_env: string }> {
  return json(`${BASE}/fs/roots`)
}

export async function fetchFsListing(path: string, showFiles = true): Promise<FsListing> {
  return json(`${BASE}/fs/list?path=${encodeURIComponent(path)}&show_files=${showFiles ? 'true' : 'false'}`)
}

export async function fetchFsExists(path: string): Promise<{ path: string; exists: boolean; is_dir: boolean; resolved: string | null }> {
  return json(`${BASE}/fs/exists?path=${encodeURIComponent(path)}`)
}

export async function createFsDir(parent: string, name: string): Promise<{ created: boolean; path: string }> {
  const res = await fetch(`${BASE}/fs/mkdir`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ parent, name }) })
  if (!res.ok) {
    const text = await res.text()
    let detail = text
    try { const p = JSON.parse(text); if (typeof p.detail === 'string') detail = p.detail } catch { /* text */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}
