/** Filter logic: collapse-by-depth + per-node expansion. */

import { describe, it, expect } from 'vitest'
import type { NipypeNodeStatus } from '../../../api/types'
import { buildNipypeTree } from '../nipype_tree'
import {
  allWorkflowIds,
  filterVisible,
  isNodeVisible,
  nodeDepth,
} from '../nipype_tree_filter'


function leaf(node: string): NipypeNodeStatus {
  const seg = node.split('.')
  return {
    node,
    leaf: seg[seg.length - 1],
    workflow: seg.slice(0, -1).join('.'),
    status: 'ok',
    started_at: 0,
    finished_at: 0,
    elapsed: 0,
    crash_file: null,
    level: 'INFO',
  }
}


// Realistic-ish fmriprep subgraph: one subject, two BOLD runs,
// each run has a couple of named sub-workflows with leaves below.
function buildSubjectFixture() {
  return buildNipypeTree([
    leaf('fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf.n4'),
    leaf('fmriprep_wf.single_subject_01_wf.anat_preproc_wf.surface_recon_wf.recon_all'),
    leaf('fmriprep_wf.single_subject_01_wf.func_preproc_run_1_wf.bold_hmc_wf.mcflirt'),
    leaf('fmriprep_wf.single_subject_01_wf.func_preproc_run_1_wf.bold_confounds_wf.dvars'),
    leaf('fmriprep_wf.single_subject_01_wf.func_preproc_run_2_wf.bold_hmc_wf.mcflirt'),
    leaf('fmriprep_wf.single_subject_01_wf.func_preproc_run_2_wf.bold_confounds_wf.dvars'),
  ])
}


describe('nodeDepth', () => {
  it('counts dotted segments', () => {
    expect(nodeDepth('a')).toBe(1)
    expect(nodeDepth('a.b')).toBe(2)
    expect(nodeDepth('a.b.c.d.e')).toBe(5)
    expect(nodeDepth('')).toBe(0)
  })
})


describe('isNodeVisible', () => {
  it('shows everything at or below defaultDepth', () => {
    const e = new Set<string>()
    expect(isNodeVisible('a', 3, e)).toBe(true)
    expect(isNodeVisible('a.b', 3, e)).toBe(true)
    expect(isNodeVisible('a.b.c', 3, e)).toBe(true)
  })

  it('hides nodes deeper than defaultDepth unless every ancestor at or above default is expanded', () => {
    const e = new Set<string>()
    expect(isNodeVisible('a.b.c.d', 3, e)).toBe(false)
    // Depth-4 node — its direct parent 'a.b.c' sits AT defaultDepth=3
    // and must be expanded to reveal its children, even though the
    // parent itself is auto-visible.
    expect(isNodeVisible('a.b.c.d', 3, new Set(['a.b.c']))).toBe(true)
  })

  it('requires every ancestor at depth ≥ defaultDepth to be expanded', () => {
    // For depth-5 node 'a.b.c.d.e' with defaultDepth=3: BOTH
    // 'a.b.c' (depth 3) AND 'a.b.c.d' (depth 4) must be expanded.
    expect(
      isNodeVisible('a.b.c.d.e', 3, new Set(['a.b.c', 'a.b.c.d'])),
    ).toBe(true)
    // Missing either expansion hides it.
    expect(isNodeVisible('a.b.c.d.e', 3, new Set(['a.b.c.d']))).toBe(false)
    expect(isNodeVisible('a.b.c.d.e', 3, new Set(['a.b.c']))).toBe(false)
    expect(isNodeVisible('a.b.c.d.e', 3, new Set())).toBe(false)
  })
})


describe('filterVisible — defaults', () => {
  it('at depth 3 keeps the conceptual workflow layer and hides leaves below', () => {
    const tree = buildSubjectFixture()
    const { tree: filtered } = filterVisible(tree, 3, new Set())
    const ids = filtered.nodes.map((n) => n.id).sort()

    // Visible: fmriprep_wf (depth 1), single_subject_01_wf (depth 2),
    // and the four named sub-workflows at depth 3.
    expect(ids).toContain('fmriprep_wf')
    expect(ids).toContain('fmriprep_wf.single_subject_01_wf')
    expect(ids).toContain('fmriprep_wf.single_subject_01_wf.anat_preproc_wf')
    expect(ids).toContain('fmriprep_wf.single_subject_01_wf.func_preproc_run_1_wf')
    expect(ids).toContain('fmriprep_wf.single_subject_01_wf.func_preproc_run_2_wf')

    // Hidden: anything at depth ≥ 4 (the brain_extraction_wf,
    // bold_hmc_wf, etc. and their leaves).
    expect(ids).not.toContain(
      'fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf',
    )
    expect(ids).not.toContain(
      'fmriprep_wf.single_subject_01_wf.func_preproc_run_1_wf.bold_hmc_wf.mcflirt',
    )
  })

  it('per-run BOLD workflows appear as separate siblings at depth 3', () => {
    const tree = buildSubjectFixture()
    const { tree: filtered } = filterVisible(tree, 3, new Set())
    const runs = filtered.nodes
      .map((n) => n.id)
      .filter((id) => id.includes('func_preproc_run_'))
    expect(runs.length).toBe(2)
  })

  it('keeps only edges between visible endpoints', () => {
    const tree = buildSubjectFixture()
    const { tree: filtered } = filterVisible(tree, 3, new Set())
    const visibleIds = new Set(filtered.nodes.map((n) => n.id))
    for (const e of filtered.edges) {
      expect(visibleIds.has(e.source)).toBe(true)
      expect(visibleIds.has(e.target)).toBe(true)
    }
  })
})


describe('filterVisible — expansion', () => {
  it('expanding one workflow node reveals its direct children only', () => {
    const tree = buildSubjectFixture()
    const expanded = new Set([
      'fmriprep_wf.single_subject_01_wf.anat_preproc_wf',
    ])
    const { tree: filtered } = filterVisible(tree, 3, expanded)
    const ids = filtered.nodes.map((n) => n.id)

    // Direct children of anat_preproc_wf now visible:
    expect(ids).toContain(
      'fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf',
    )
    expect(ids).toContain(
      'fmriprep_wf.single_subject_01_wf.anat_preproc_wf.surface_recon_wf',
    )

    // Grandchildren (the actual leaves) still hidden — those need
    // their parent (brain_extraction_wf etc.) ALSO expanded.
    expect(ids).not.toContain(
      'fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf.n4',
    )

    // Other branches (func_preproc_*) unaffected — still collapsed.
    expect(ids).not.toContain(
      'fmriprep_wf.single_subject_01_wf.func_preproc_run_1_wf.bold_hmc_wf',
    )
  })

  it('expand-then-collapse returns to default view', () => {
    const tree = buildSubjectFixture()
    const a = filterVisible(tree, 3, new Set()).tree.nodes.map((n) => n.id).sort()
    const b = filterVisible(
      tree,
      3,
      new Set(['fmriprep_wf.single_subject_01_wf.anat_preproc_wf']),
    ).tree.nodes.map((n) => n.id).sort()
    const c = filterVisible(tree, 3, new Set()).tree.nodes.map((n) => n.id).sort()
    expect(a).toEqual(c)
    expect(a).not.toEqual(b)
  })

  it('"expand all" == every workflow id in the expanded set restores the full tree', () => {
    const tree = buildSubjectFixture()
    const expanded = new Set(allWorkflowIds(tree))
    const { tree: filtered } = filterVisible(tree, 3, expanded)
    const ids = filtered.nodes.map((n) => n.id).sort()
    const allIds = tree.nodes.map((n) => n.id).sort()
    expect(ids).toEqual(allIds)
  })
})


describe('filterVisible — hasHidden flags', () => {
  it('marks workflow nodes with hidden descendants', () => {
    const tree = buildSubjectFixture()
    const { hasHidden } = filterVisible(tree, 3, new Set())
    // anat_preproc_wf has hidden children (brain_extraction_wf etc.)
    expect(
      hasHidden.get('fmriprep_wf.single_subject_01_wf.anat_preproc_wf'),
    ).toBe(true)
    // After expanding it, the grandchildren are still hidden, so it
    // STILL has hidden descendants (depth-5 leaves).
    const { hasHidden: hh2 } = filterVisible(
      tree,
      3,
      new Set(['fmriprep_wf.single_subject_01_wf.anat_preproc_wf']),
    )
    expect(
      hh2.get('fmriprep_wf.single_subject_01_wf.anat_preproc_wf'),
    ).toBe(true)
  })

  it('marks nothing hidden when everything is expanded', () => {
    const tree = buildSubjectFixture()
    const expanded = new Set(allWorkflowIds(tree))
    const { hasHidden } = filterVisible(tree, 3, expanded)
    for (const [, h] of hasHidden) expect(h).toBe(false)
  })

  it('leaf nodes are not present in the hasHidden map', () => {
    const tree = buildSubjectFixture()
    const expanded = new Set(allWorkflowIds(tree))
    const { hasHidden } = filterVisible(tree, 3, expanded)
    for (const id of hasHidden.keys()) {
      const node = tree.nodes.find((n) => n.id === id)
      expect(node?.kind).toBe('workflow')
    }
  })
})
