/** Connection checks for typed graphs, mirroring the backend port-type lattice:
 *  a source type fits a target type when either is ``any`` or the target is the
 *  source or one of its ancestors. */
export const ANY = 'any'

/** Port type name → parent type names. */
export type Lattice = Record<string, string[]>

export function latticeFrom(types: { name: string; parents?: string[] }[]): Lattice {
  return Object.fromEntries(types.map((t) => [t.name, t.parents ?? []]))
}

export function ancestors(lattice: Lattice, name: string): Set<string> {
  const seen = new Set<string>()
  const stack = [name]
  while (stack.length) {
    const cur = stack.pop() as string
    if (seen.has(cur)) continue
    seen.add(cur)
    stack.push(...(lattice[cur] ?? []))
  }
  return seen
}

export function compatible(lattice: Lattice, src: string, dst: string): boolean {
  if (src === ANY || dst === ANY) return true
  return ancestors(lattice, src).has(dst)
}

/** True when ``to`` can be reached from ``from`` along the edges. */
export function reaches(edges: { source: string; target: string }[], from: string, to: string): boolean {
  const seen = new Set<string>()
  const stack = [from]
  while (stack.length) {
    const cur = stack.pop() as string
    if (cur === to) return true
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const e of edges) if (e.source === cur) stack.push(e.target)
  }
  return false
}

export type PortLookup = (nodeId: string, side: 'in' | 'out', port: string) => { type?: string } | undefined

/** Why a connection is not allowed, or null when it is. */
export function checkConnection(
  edges: { source: string; target: string }[],
  conn: { source: string; target: string; sourceHandle: string; targetHandle: string },
  portOf: PortLookup,
  lattice: Lattice,
): string | null {
  if (conn.source === conn.target) return 'a node cannot feed itself'
  const out = portOf(conn.source, 'out', conn.sourceHandle)
  if (!out) return `${conn.source} has no output ${conn.sourceHandle}`
  const inp = portOf(conn.target, 'in', conn.targetHandle)
  if (!inp) return `${conn.target} has no input ${conn.targetHandle}`
  const s = out.type ?? ANY
  const d = inp.type ?? ANY
  if (!compatible(lattice, s, d)) return `${s} cannot feed ${d}`
  if (reaches(edges, conn.target, conn.source)) return 'this connection would make a cycle'
  return null
}
