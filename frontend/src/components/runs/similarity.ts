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

/** A single comparison row across N runs.
 *
 *  `perRun[runId]` is the chosen filename for that run, or null if no
 *  artifact in this row matches the run.
 */
export interface PairRow {
  /** Stable identifier for this row (used as drag-and-drop key). */
  id: string
  perRun: Record<string, string | null>
}

/** Greedy N-way alignment.
 *
 *  Strategy: while any names remain unconsumed, pick the run with the
 *  most remaining names as a "seed" and take its first one. For every
 *  other run, find the highest-similarity remaining name above
 *  `threshold` and add it to this row (or null if none).
 *
 *  Ordering of `runIds` is preserved in `perRun`; the row IDs are
 *  positional and not stable across re-runs of this function.
 */
export function autoAlignN(
  runIds: string[],
  namesByRun: Record<string, string[]>,
  threshold = 0.3,
): PairRow[] {
  const remaining: Record<string, Set<string>> = {}
  for (const rid of runIds) remaining[rid] = new Set(namesByRun[rid] || [])

  const rows: PairRow[] = []
  let counter = 0

  while (true) {
    // Pick the run with the most remaining names as the seed; bail if
    // every run is empty.
    let seedRun: string | null = null
    let maxSize = 0
    for (const rid of runIds) {
      if (remaining[rid].size > maxSize) {
        maxSize = remaining[rid].size
        seedRun = rid
      }
    }
    if (seedRun === null) break

    // Take the first remaining name from the seed run (deterministic
    // because Sets preserve insertion order).
    const seedName = remaining[seedRun].values().next().value as string
    remaining[seedRun].delete(seedName)

    const perRun: Record<string, string | null> = {}
    for (const rid of runIds) perRun[rid] = null
    perRun[seedRun] = seedName

    // For every other run: pick the highest-similarity remaining name
    // above the threshold.
    for (const rid of runIds) {
      if (rid === seedRun) continue
      let best: string | null = null
      let bestScore = threshold
      for (const candidate of remaining[rid]) {
        const s = jaccard(seedName, candidate)
        if (s > bestScore) {
          bestScore = s
          best = candidate
        }
      }
      if (best !== null) {
        perRun[rid] = best
        remaining[rid].delete(best)
      }
    }

    rows.push({ id: `pair-${counter++}-${seedRun}-${seedName}`, perRun })
  }

  return rows
}
