/** Shared formatters used across views, graphs, and live-progress panels.
 *
 * The frontend used to have six near-identical ``formatElapsed`` /
 * ``formatDuration`` helpers, each handling a different subset of the
 * unit space (some s-only, some s+m, only one s+m+h, none with ms).
 * Plus a half-dozen inline ``${s.toFixed(1)}s`` literals in graph
 * nodes that always printed seconds even when the run took an hour.
 * All of them route through :func:`formatDuration` here so the unit
 * picks itself based on magnitude.
 */


/** Format a duration in seconds as the largest sensible unit.
 *
 * Rules — picked to match the most-used existing helpers in the
 * codebase and give graph nodes / stage timings legible labels:
 *
 *   < 0           → empty string (caller shouldn't have rendered)
 *   == 0          → "0s"
 *   < 1s          → ``"<n>ms"`` (integer ms)
 *   < 10s         → ``"<n.n>s"`` (one decimal)
 *   < 60s         → ``"<n>s"`` (integer seconds — past ~10s the
 *                   trailing .x is noise)
 *   < 3600s       → ``"<n.n>m"``
 *   ≥ 3600s       → ``"<n.n>h"``
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return ''
  if (seconds < 0) return ''
  if (seconds === 0) return '0s'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}


/** Compact two-part form ("1h 5m", "5m 30s") for places that want to
 *  surface the lower unit alongside the dominant one. Use when
 *  precision matters (e.g. detail panels, tooltips). Most call sites
 *  should prefer :func:`formatDuration` instead.
 */
export function formatDurationVerbose(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return ''
  if (seconds === 0) return '0s'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = Math.round(seconds % 60)
    return s ? `${m}m ${s}s` : `${m}m`
  }
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}
