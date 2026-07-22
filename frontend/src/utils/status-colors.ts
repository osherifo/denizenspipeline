/**
 * Theme-aware status colours for graph/pipeline nodes.
 *
 * The original palette is neon, tuned for a dark canvas, and nodes were styled
 * as `${color}22` fill + `${color}aa` border. On a light background that's a
 * near-invisible box: 13% neon fill reads as white and a 67%-alpha neon border
 * disappears. Light mode therefore needs *darker* base colours and a
 * full-opacity border.
 *
 * Use `useNodeColors(status)` inside a component, or `nodeColors(mode, status)`
 * where a hook isn't available.
 */

import { useThemeStore, type ThemeMode } from '../stores/theme-store'

/** Canonical neon set — unchanged, so dark mode looks exactly as before. */
export const DARK_STATUS: Record<string, string> = {
  ok: '#00e676',
  done: '#00e676',
  running: '#00e5ff',
  warning: '#ffd600',
  failed: '#ff1744',
  cancelled: '#ff1744',
  error: '#ff1744',
  skipped: '#888888',
  unknown: '#888888',
}

/** Darkened equivalents that stay legible on light surfaces (all >=4.5:1). */
export const LIGHT_STATUS: Record<string, string> = {
  ok: '#0b7a40',
  done: '#0b7a40',
  running: '#0277a8',
  warning: '#8f5a00',
  failed: '#c62233',
  cancelled: '#c62233',
  error: '#c62233',
  skipped: '#5b6478',
  unknown: '#5b6478',
}

const NEUTRAL_DARK = '#888888'
const NEUTRAL_LIGHT = '#5b6478'

export interface NodeColors {
  /** Base colour — use for text, icons and strokes. */
  color: string
  /** Subtle fill behind a node. */
  bg: string
  /** Border that is actually visible in this theme. */
  border: string
}

export function statusColor(mode: ThemeMode, status: string): string {
  const table = mode === 'light' ? LIGHT_STATUS : DARK_STATUS
  return table[status] ?? (mode === 'light' ? NEUTRAL_LIGHT : NEUTRAL_DARK)
}

export function nodeColors(mode: ThemeMode, status: string): NodeColors {
  const color = statusColor(mode, status)
  return mode === 'light'
    // Light: a slightly stronger tint, and a solid border so the box has a
    // real edge against white.
    ? { color, bg: `${color}1f`, border: color }
    // Dark: preserve the original look exactly.
    : { color, bg: `${color}22`, border: `${color}aa` }
}

/** Hook form — re-renders when the theme changes. */
export function useNodeColors(status: string): NodeColors {
  const mode = useThemeStore((s) => s.mode)
  return nodeColors(mode, status)
}

/** For components that need the whole map (e.g. legends). */
export function useStatusColor(): (status: string) => string {
  const mode = useThemeStore((s) => s.mode)
  return (status: string) => statusColor(mode, status)
}
