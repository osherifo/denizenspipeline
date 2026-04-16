/** Cheap string-similarity helpers used to auto-align artifacts in the
 *  run comparison view.
 *
 *  Filenames are split on `_-./` into tokens, then compared by Jaccard
 *  similarity on the token set. Cheap, predictable, and good enough for
 *  filenames like 'prediction_accuracy_flatmap.png' vs
 *  'prediction_flatmap_v2.png'.
 */

function tokens(name: string): Set<string> {
  return new Set(
    name
      .toLowerCase()
      .replace(/\.(png|jpg|jpeg|svg|gif|webp)$/i, '')
      .split(/[_\-./\s]+/)
      .filter(Boolean),
  )
}

export function jaccard(a: string, b: string): number {
  if (a === b) return 1
  const ta = tokens(a)
  const tb = tokens(b)
  if (ta.size === 0 && tb.size === 0) return 0
  let inter = 0
  for (const t of ta) if (tb.has(t)) inter++
  return inter / (ta.size + tb.size - inter)
}

/** A single comparison row, possibly unpaired on one side. */
export interface PairRow {
  /** Stable identifier for this row (used as drag-and-drop key + storage key). */
  id: string
  /** Filename on the left (Run A); null = no selection. */
  leftName: string | null
  /** Filename on the right (Run B); null = no selection. */
  rightName: string | null
}

/** Greedy bipartite matching by similarity, then leftover items on each side
 *  get their own unpaired rows. */
export function autoAlign(
  leftNames: string[],
  rightNames: string[],
  threshold = 0.3,
): PairRow[] {
  // Score every left × right pair.
  const scored: { l: string; r: string; s: number }[] = []
  for (const l of leftNames) {
    for (const r of rightNames) {
      const s = jaccard(l, r)
      if (s >= threshold) scored.push({ l, r, s })
    }
  }
  // Greedy: highest-similarity pairs first, with each name used at most once.
  scored.sort((a, b) => b.s - a.s)

  const usedL = new Set<string>()
  const usedR = new Set<string>()
  const rows: PairRow[] = []
  let counter = 0

  for (const { l, r } of scored) {
    if (usedL.has(l) || usedR.has(r)) continue
    usedL.add(l)
    usedR.add(r)
    rows.push({ id: `pair-${counter++}-${l}-${r}`, leftName: l, rightName: r })
  }
  // Leftovers on each side become unpaired rows.
  for (const l of leftNames) {
    if (!usedL.has(l)) {
      rows.push({ id: `pair-${counter++}-${l}-`, leftName: l, rightName: null })
    }
  }
  for (const r of rightNames) {
    if (!usedR.has(r)) {
      rows.push({ id: `pair-${counter++}--${r}`, leftName: null, rightName: r })
    }
  }
  return rows
}
