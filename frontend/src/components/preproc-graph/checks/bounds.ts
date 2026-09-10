/** Bounds as the user types them, one per line: `n_trs > 100`, `mean_mm between 2.0 3.2`. */
import type { BoundJson } from '../../../api/types'

const OPS = new Set(['<', '<=', '>', '>=', '==', '!=', 'between'])

export function parseBounds(text: string): { bounds: Record<string, BoundJson>; errors: string[] } {
  const bounds: Record<string, BoundJson> = {}
  const errors: string[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const parts = line.split(/\s+/)
    const [metric, op, ...rest] = parts
    if (!metric || !op || !OPS.has(op)) { errors.push(`"${line}": expected <metric> <op> <value>`); continue }
    const num = (t: string) => { const v = Number(t); return Number.isFinite(v) ? v : t === 'true' ? true : t === 'false' ? false : t }
    if (op === 'between') {
      if (rest.length !== 2) { errors.push(`"${line}": between needs two values`); continue }
      bounds[metric] = ['between', [num(rest[0]), num(rest[1])]]
    } else {
      if (rest.length !== 1) { errors.push(`"${line}": one value expected`); continue }
      bounds[metric] = [op, num(rest[0])]
    }
  }
  return { bounds, errors }
}

export function formatBounds(bounds: Record<string, BoundJson> | undefined): string {
  if (!bounds) return ''
  return Object.entries(bounds).map(([m, [op, v]]) => op === 'between' && Array.isArray(v) ? `${m} between ${v[0]} ${v[1]}` : `${m} ${op} ${String(v)}`).join('\n')
}

export function formatBound(op: string, v: unknown): string {
  return op === 'between' && Array.isArray(v) ? `between ${v[0]} and ${v[1]}` : `${op} ${String(v)}`
}
