/** Filter a `NipypeTree` to only the nodes visible at a given default
 * depth + a set of explicitly-expanded workflow ids.
 *
 * Used by the nipype DAG modal to render a conceptual view by default
 * (depth 3 → fmriprep_wf, single_subject_*_wf, and the major named
 * sub-workflows like anat_preproc_wf / func_preproc_*_wf) while
 * letting the user click individual workflow nodes to drill in.
 *
 * No node names are invented — every visible label is a real dotted-
 * path segment fmriprep already emits.
 */

import type { NipypeTree } from './nipype_tree'


export interface FilterResult {
  /** The filtered subgraph — fewer nodes + only edges between them. */
  tree: NipypeTree
  /** For each visible workflow node id, whether ANY descendant is
   *  hidden under the current filter. Drives the `+ / −` glyph on
   *  the workflow node renderer. Leaf nodes are never present here. */
  hasHidden: Map<string, boolean>
}


function _depth(id: string): number {
  return id ? id.split('.').length : 0
}


/** A node at depth D is visible iff:
 *   - D ≤ defaultDepth (it belongs to the always-on conceptual
 *     layer), OR
 *   - every ancestor at depth ≥ defaultDepth is explicitly
 *     expanded.
 *
 * The "≥ defaultDepth" condition is the subtle one: a depth-4 node's
 * direct parent sits at depth 3 (= defaultDepth in our default
 * config), and even though the parent is auto-visible, it must be
 * EXPANDED for its depth-4 children to appear. Without expansion,
 * the conceptual layer stops at depth 3.
 */
export function isNodeVisible(
  id: string,
  defaultDepth: number,
  expanded: ReadonlySet<string>,
): boolean {
  const segs = id.split('.')
  if (segs.length <= defaultDepth) return true
  // Walk up the path checking each ancestor at depth ≥ defaultDepth.
  // The node itself (segs.length) is not its own ancestor.
  for (let i = segs.length - 1; i >= defaultDepth; i--) {
    const ancestorId = segs.slice(0, i).join('.')
    if (!expanded.has(ancestorId)) return false
  }
  return true
}


/** Build the filtered view. */
export function filterVisible(
  tree: NipypeTree,
  defaultDepth: number,
  expanded: ReadonlySet<string>,
): FilterResult {
  const visibleNodes = tree.nodes.filter((n) =>
    isNodeVisible(n.id, defaultDepth, expanded),
  )
  const visibleIds = new Set(visibleNodes.map((n) => n.id))
  const visibleEdges = tree.edges.filter(
    (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
  )

  // For each visible workflow node, scan the full tree for any
  // descendant that didn't make it through the filter. We do this in
  // O(N) by walking once and bucketing by the longest visible
  // workflow ancestor prefix — simpler is to just check startsWith
  // against the visible workflow set, since the tree node count is
  // small (hundreds at worst for fmriprep).
  const hasHidden = new Map<string, boolean>()
  for (const n of visibleNodes) {
    if (n.kind !== 'workflow') continue
    const prefix = n.id + '.'
    let anyHidden = false
    for (const candidate of tree.nodes) {
      if (candidate.id.startsWith(prefix) && !visibleIds.has(candidate.id)) {
        anyHidden = true
        break
      }
    }
    hasHidden.set(n.id, anyHidden)
  }

  return { tree: { nodes: visibleNodes, edges: visibleEdges }, hasHidden }
}


/** Convenience for the "Expand all" toolbar action — every workflow
 * id in the tree (leaves can't be expanded since they have no
 * children). */
export function allWorkflowIds(tree: NipypeTree): string[] {
  return tree.nodes.filter((n) => n.kind === 'workflow').map((n) => n.id)
}


/** Depth of a node id (purely a count of dotted segments). Exposed for
 * the modal's "Depth ± 1" toolbar buttons. */
export function nodeDepth(id: string): number {
  return _depth(id)
}
