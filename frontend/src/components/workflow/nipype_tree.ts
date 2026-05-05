/** Build a ReactFlow-shape tree from a flat list of NipypeNodeStatus.
 *
 * The dotted node paths from nipype already form an implicit hierarchy
 * (e.g. `fmriprep_wf.single_subject_01_wf.bold_preproc_wf.bold_split`).
 * We use that hierarchy as a tree of parents → leaves; edges connect
 * each parent to its direct children. Parents aren't "real" nipype
 * nodes — they're virtual summary boxes whose counts roll up children.
 *
 * Output is intentionally framework-light (just `{nodes, edges}`); the
 * caller hands it to dagre + XYFlow.
 */

import type { NipypeNodeStatus } from '../../api/types'


export type TreeNodeKind = 'workflow' | 'leaf'


export interface NipypeTreeNode {
  id: string             // dotted path
  label: string          // last segment
  parentId: string | null
  kind: TreeNodeKind
  // Leaf-only fields (mirrored from NipypeNodeStatus for rendering).
  status?: 'running' | 'ok' | 'failed' | 'completed_assumed'
  elapsed?: number
  level?: string
  full_node?: string
  // Workflow-only summaries.
  counts?: {
    running: number
    ok: number
    failed: number
    completed_assumed: number
    total: number
  }
}


export interface NipypeTreeEdge {
  id: string
  source: string
  target: string
}


export interface NipypeTree {
  nodes: NipypeTreeNode[]
  edges: NipypeTreeEdge[]
}


function _segments(node: string): string[] {
  return node ? node.split('.') : []
}


/** Build the tree. Stable across calls when input is stable. */
export function buildNipypeTree(leaves: NipypeNodeStatus[]): NipypeTree {
  const all = new Map<string, NipypeTreeNode>()
  const edges: NipypeTreeEdge[] = []
  const edgeKeys = new Set<string>()

  function ensure(path: string, kind: TreeNodeKind): NipypeTreeNode {
    let existing = all.get(path)
    if (existing) return existing
    const segs = _segments(path)
    const label = segs.length ? segs[segs.length - 1] : path
    const parentId = segs.length > 1 ? segs.slice(0, -1).join('.') : null
    existing = {
      id: path,
      label,
      parentId,
      kind,
      counts: kind === 'workflow'
        ? { running: 0, ok: 0, failed: 0, completed_assumed: 0, total: 0 }
        : undefined,
    }
    all.set(path, existing)
    if (parentId) {
      ensure(parentId, 'workflow')
      const key = `${parentId}->${path}`
      if (!edgeKeys.has(key)) {
        edgeKeys.add(key)
        edges.push({ id: `e-${edges.length}`, source: parentId, target: path })
      }
    }
    return existing
  }

  for (const leaf of leaves) {
    const node = ensure(leaf.node, 'leaf')
    node.status = leaf.status
    node.elapsed = leaf.elapsed
    node.level = leaf.level
    node.full_node = leaf.node
    // Roll up counts on every ancestor.
    let parent = node.parentId
    while (parent) {
      const p = ensure(parent, 'workflow')
      if (p.counts) {
        p.counts.total += 1
        if (leaf.status === 'running') p.counts.running += 1
        else if (leaf.status === 'ok') p.counts.ok += 1
        else if (leaf.status === 'failed') p.counts.failed += 1
        else if (leaf.status === 'completed_assumed') p.counts.completed_assumed += 1
      }
      parent = p.parentId
    }
  }

  return { nodes: Array.from(all.values()), edges }
}
