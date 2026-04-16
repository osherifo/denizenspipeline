/** Viewer registry for run artifacts.
 *
 * Add a viewer by calling `registerViewer(...)` in any module that gets
 * imported at app startup. The registry is a module-level list ordered
 * by priority — higher priority wins.
 */
import type { ComponentType } from 'react'
import type { ArtifactInfo } from '../../api/types'

export interface ResultViewerProps {
  artifact: ArtifactInfo
  runId: string
}

export interface ResultViewer {
  /** Stable identifier for telemetry / debugging. */
  id: string
  /** Short human-readable label. */
  label: string
  /** Higher = preferred. Filename-specific viewers should use >= 100,
   *  extension-based viewers <= 50, fallback 0. */
  priority: number
  /** Return true if this viewer can render the given artifact. */
  matches: (artifact: ArtifactInfo) => boolean
  /** The component. */
  component: ComponentType<ResultViewerProps>
}

const _viewers: ResultViewer[] = []

export function registerViewer(viewer: ResultViewer): void {
  // Replace if same id already registered (for hot-reload / retroactive registration)
  const existing = _viewers.findIndex((v) => v.id === viewer.id)
  if (existing >= 0) {
    _viewers[existing] = viewer
  } else {
    _viewers.push(viewer)
  }
  _viewers.sort((a, b) => b.priority - a.priority)
}

export function findViewerFor(artifact: ArtifactInfo): ResultViewer | null {
  for (const v of _viewers) {
    try {
      if (v.matches(artifact)) return v
    } catch {
      // A broken matcher shouldn't kill the whole list.
    }
  }
  return null
}

export function listViewers(): ResultViewer[] {
  return [..._viewers]
}

// ── Matcher helpers ─────────────────────────────────────────────────────

export function matchesFilename(name: string): (artifact: ArtifactInfo) => boolean {
  return (a) => a.name === name || a.name.endsWith(`/${name}`)
}

export function matchesPattern(pattern: RegExp): (artifact: ArtifactInfo) => boolean {
  return (a) => pattern.test(a.name)
}

export function matchesExtension(...exts: string[]): (artifact: ArtifactInfo) => boolean {
  const lower = exts.map((e) => e.toLowerCase().replace(/^\./, ''))
  return (a) => {
    const dot = a.name.lastIndexOf('.')
    if (dot < 0) return false
    const ext = a.name.slice(dot + 1).toLowerCase()
    return lower.includes(ext)
  }
}
