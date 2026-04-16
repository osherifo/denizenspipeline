/** Tiny line-by-line diff for two YAML strings.
 *
 * Not a true LCS diff — just classifies each line as 'unchanged' / 'changed' /
 * 'added' / 'removed' by aligning on line index. Good enough for short
 * configs where structure is roughly parallel after a few edits.
 */
import yaml from 'js-yaml'

export interface DiffLine {
  kind: 'unchanged' | 'changed' | 'added' | 'removed' | 'placeholder'
  left: string
  right: string
}

/** Pretty-print a config object as YAML for display. */
export function dumpYaml(obj: unknown): string {
  if (obj == null) return ''
  try {
    return yaml.dump(obj, { indent: 2, lineWidth: 100, noRefs: true, sortKeys: true })
  } catch {
    return String(obj)
  }
}

/** Diff two YAML strings line-by-line. Both sides padded to the same length. */
export function diffYaml(leftYaml: string, rightYaml: string): DiffLine[] {
  const left = leftYaml.split('\n')
  const right = rightYaml.split('\n')
  const max = Math.max(left.length, right.length)
  const out: DiffLine[] = []

  for (let i = 0; i < max; i++) {
    const l = i < left.length ? left[i] : null
    const r = i < right.length ? right[i] : null

    if (l === null) {
      out.push({ kind: 'added', left: '', right: r ?? '' })
    } else if (r === null) {
      out.push({ kind: 'removed', left: l, right: '' })
    } else if (l === r) {
      out.push({ kind: 'unchanged', left: l, right: r })
    } else {
      out.push({ kind: 'changed', left: l, right: r })
    }
  }

  return out
}

/** Count diff stats for a header summary. */
export function diffStats(lines: DiffLine[]): { changed: number; added: number; removed: number } {
  let changed = 0
  let added = 0
  let removed = 0
  for (const l of lines) {
    if (l.kind === 'changed') changed++
    else if (l.kind === 'added') added++
    else if (l.kind === 'removed') removed++
  }
  return { changed, added, removed }
}
