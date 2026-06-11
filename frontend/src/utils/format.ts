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
 *   nullish / ≤ 0 → empty string (a duration that hasn't elapsed or
 *                   wasn't reported isn't worth a slot of UI noise —
 *                   callers can guard render with a truthy check)
 *   < 1s          → ``"<n>ms"`` (integer ms, truncated)
 *   < 10s         → ``"<n.n>s"`` (one decimal, truncated)
 *   < 60s         → ``"<n>s"`` (integer seconds, truncated — past
 *                   ~10s the trailing .x is noise)
 *   < 3600s       → ``"<n.n>m"`` (truncated to a tenth)
 *   ≥ 3600s       → ``"<n.n>h"`` (truncated to a tenth)
 *
 * Truncation (not rounding) so an in-range value never spills into
 * the next unit: 0.9996s → ``"999ms"`` (not ``"1000ms"``); 59.6s →
 * ``"59s"`` (not ``"60s"``); 3599.9s → ``"59.9m"`` (not ``"60.0m"``).
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return ''
  if (seconds < 1) return `${Math.floor(seconds * 1000)}ms`
  if (seconds < 10) return `${(Math.floor(seconds * 10) / 10).toFixed(1)}s`
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${(Math.floor(seconds / 6) / 10).toFixed(1)}m`
  return `${(Math.floor(seconds / 360) / 10).toFixed(1)}h`
}


/** Compact two-part form ("1h 5m", "5m 30s") for places that want to
 *  surface the lower unit alongside the dominant one. Use when
 *  precision matters (e.g. detail panels, tooltips). Most call sites
 *  should prefer :func:`formatDuration` instead.
 *
 *  Rounds to whole seconds once, then derives h/m/s — avoids the
 *  ``"1h 60m"`` / ``"5m 60s"`` carry bugs that a floor-then-round of
 *  the two parts independently produces at unit boundaries.
 */
export function formatDurationVerbose(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return ''
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  // Quantise to whole seconds first so 3599.6s and 7199.6s carry
  // through the unit boundary cleanly.
  const total = Math.round(seconds)
  if (total < 60) return `${total}s`
  if (total < 3600) {
    const m = Math.floor(total / 60)
    const s = total % 60
    return s ? `${m}m ${s}s` : `${m}m`
  }
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}
