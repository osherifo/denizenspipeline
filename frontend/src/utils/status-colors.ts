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

import { useThemeStore, getThemeMode, type ThemeMode } from '../stores/theme-store'

/** Canonical neon set — unchanged, so dark mode looks exactly as before. */
export const DARK_STATUS: Record<string, string> = {
  ok: '#00e676',
  done: '#00e676',
  running: '#00e5ff',
  warning: '#ffd600',
  failed: '#ff1744',
  cancelled: '#ff1744',
  lost: '#ff1744',
  error: '#ff1744',
  pending: '#6b7280',
  cached: '#888888',
  completed_assumed: '#52c98f',
  skipped: '#888888',
  unknown: '#888888',
}

/** Darkened equivalents that stay legible on light surfaces (all >=4.5:1). */
export const LIGHT_STATUS: Record<string, string> = {
  ok: '#0b7a40',
  done: '#0b7a40',
  running: '#026d99',
  warning: '#8f5a00',
  failed: '#c62233',
  cancelled: '#c62233',
  lost: '#c62233',
  error: '#c62233',
  pending: '#5b6478',
  cached: '#5b6478',
  // Dark mode distinguishes "assumed finished" from "ok" by making it a paler
  // green; on white, paler means illegible — so shift the hue to teal instead.
  completed_assumed: '#2a6b60',
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

/**
 * The palette for the *current* theme, as a plain record.
 *
 * For the graph components, whose status lookups sit in module-level helpers
 * rather than components: call it per paint — `STATUS().failed` — so a theme
 * switch is picked up. An unknown key yields `undefined`, exactly as the
 * hand-rolled tables it replaces did, so existing `?? fallback` chains are
 * unaffected.
 */
export function statusPalette(mode: ThemeMode = getThemeMode()): Record<string, string> {
  return mode === 'light' ? LIGHT_STATUS : DARK_STATUS
}

/* ── Identity colours ────────────────────────────────────────────────────────
 *
 * Stage/kind colours (Stimuli cyan, Model blue, Preproc green …) are *identity*
 * markers, not status: their hue carries the meaning, so unlike the status
 * table they can't be swapped for a hand-picked light set without losing what
 * they encode. Instead we keep the hue and walk lightness down until the colour
 * clears 4.5:1 against the light page, which is the same colour "meaning" at a
 * legible weight. Dark mode returns the original untouched.
 */

const PAGE_LIGHT = '#e8ebf2'
const lightCache = new Map<string, string>()

function relLuminance(hex: string): number {
  const h = expand(hex)
  const ch = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const [r, g, b] = ch.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const la = relLuminance(a)
  const lb = relLuminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

function expand(hex: string): string {
  const h = hex.replace('#', '')
  return h.length === 3 ? h.split('').map((c) => c + c).join('') : h.slice(0, 6)
}

function toHsl(hex: string): [number, number, number] {
  const h = expand(hex)
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  const hue =
    max === r ? ((g - b) / d + (g < b ? 6 : 0))
    : max === g ? (b - r) / d + 2
    : (r - g) / d + 4
  return [hue / 6, s, l]
}

function toHex(hh: number, s: number, l: number): string {
  const f = (n: number) => {
    const k = (n + hh * 12) % 12
    const a = s * Math.min(l, 1 - l)
    const v = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return Math.round(v * 255).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

/** Darken an identity colour until it is legible on the light surfaces. */
export function forLight(hex: string): string {
  const hit = lightCache.get(hex)
  if (hit) return hit
  const [hh, s0, l] = toHsl(hex)
  // Achromatic inputs (white/grey) have no hue to preserve — keep them neutral
  // rather than letting rounding noise tint them.
  const s = s0 < 0.12 ? 0 : s0
  let out = '#1c2030'
  for (let i = 0; i <= 100; i++) {
    const cand = toHex(hh, s, Math.max(0, l - i * 0.01))
    if (contrast(cand, PAGE_LIGHT) >= 4.5) { out = cand; break }
  }
  lightCache.set(hex, out)
  return out
}

/**
 * A stage/kind identity colour, resolved for the current theme.
 * Dark mode is a pass-through, so nothing about it changes.
 */
export function identityColor(hex: string, mode: ThemeMode = getThemeMode()): string {
  // Call sites fall back to `var(--…)` or '' when a stage has no colour; those
  // are already theme-correct, so pass anything that isn't a literal through.
  if (!hex.startsWith('#')) return hex
  return mode === 'light' ? forLight(hex) : hex
}

/** Hook form — re-renders when the theme changes. */
export function useIdentityColor(): (hex: string) => string {
  const mode = useThemeStore((s) => s.mode)
  return (hex: string) => identityColor(hex, mode)
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
