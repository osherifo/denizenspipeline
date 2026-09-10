/**
 * A literal typed into an iterated (×N) input port is the list to iterate over:
 * one item per iteration. `0, 1, 2` and `[0, 1, 2]` both work; numbers become
 * numbers, everything else stays a string.
 */
export function parseIterLiteral(text: string): unknown[] {
  const t = text.trim()
  if (!t) return []
  if (t.startsWith('[')) {
    try {
      const v = JSON.parse(t)
      if (Array.isArray(v)) return v
    } catch { /* fall through to the comma form */ }
  }
  return t.split(',').map((s) => s.trim()).filter((s) => s !== '').map(coerce)
}

export function formatIterLiteral(value: unknown): string {
  // JSON, not a comma-join: a comma-joined string is not a round trip for an
  // array whose items themselves contain commas ("a,b" as one item vs two),
  // and a leading-zero numeric string ("001") re-parses through parseIterLiteral
  // as the number 1 — either way a save-then-reopen would silently change the
  // list. JSON.stringify/parseIterLiteral's `[`-prefixed branch recover it exactly.
  if (Array.isArray(value)) return JSON.stringify(value)
  return value == null ? '' : String(value)
}

function coerce(s: string): unknown {
  return /^-?\d+(\.\d+)?$/.test(s) ? Number(s) : s
}
