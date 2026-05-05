/** Pure unit tests for the dotted-path → tree builder. */

import { describe, it, expect } from 'vitest'
import type { NipypeNodeStatus } from '../../../api/types'
import { buildNipypeTree } from '../nipype_tree'


function leaf(
  node: string,
  status: 'running' | 'ok' | 'failed' = 'ok',
  elapsed = 0,
): NipypeNodeStatus {
  const seg = node.split('.')
  return {
    node,
    leaf: seg[seg.length - 1],
    workflow: seg.slice(0, -1).join('.'),
    status,
    started_at: 0,
    finished_at: 0,
    elapsed,
    crash_file: null,
    level: 'INFO',
  }
}


describe('buildNipypeTree', () => {
  it('builds parents from dotted paths', () => {
    const tree = buildNipypeTree([
      leaf('fmriprep_wf.bold_preproc_wf.bold_split'),
      leaf('fmriprep_wf.bold_preproc_wf.bold_t1_trans_wf'),
      leaf('fmriprep_wf.sdc_estimate_wf.unwarp_wf'),
    ])
    const ids = tree.nodes.map((n) => n.id).sort()
    expect(ids).toContain('fmriprep_wf')
    expect(ids).toContain('fmriprep_wf.bold_preproc_wf')
    expect(ids).toContain('fmriprep_wf.sdc_estimate_wf')
    expect(ids).toContain('fmriprep_wf.bold_preproc_wf.bold_split')
    // 3 leaves + 3 unique ancestors (root + two sub).
    expect(tree.nodes).toHaveLength(6)
  })

  it('emits parent→child edges', () => {
    const tree = buildNipypeTree([leaf('a.b.c')])
    const ab = tree.edges.find((e) => e.source === 'a' && e.target === 'a.b')
    const abc = tree.edges.find((e) => e.source === 'a.b' && e.target === 'a.b.c')
    expect(ab).toBeDefined()
    expect(abc).toBeDefined()
  })

  it('rolls counts up to every ancestor', () => {
    const tree = buildNipypeTree([
      leaf('wf.x', 'ok'),
      leaf('wf.y', 'failed'),
      leaf('wf.z', 'running'),
    ])
    const root = tree.nodes.find((n) => n.id === 'wf')!
    expect(root.kind).toBe('workflow')
    expect(root.counts).toEqual({
      running: 1, ok: 1, failed: 1, completed_assumed: 0, total: 3,
    })
  })

  it('rolls counts up multiple levels', () => {
    const tree = buildNipypeTree([
      leaf('a.b.c.x', 'ok'),
      leaf('a.b.c.y', 'failed'),
      leaf('a.b.d.z', 'running'),
    ])
    const a = tree.nodes.find((n) => n.id === 'a')!
    const ab = tree.nodes.find((n) => n.id === 'a.b')!
    const abc = tree.nodes.find((n) => n.id === 'a.b.c')!
    expect(a.counts).toEqual({
      running: 1, ok: 1, failed: 1, completed_assumed: 0, total: 3,
    })
    expect(ab.counts).toEqual({
      running: 1, ok: 1, failed: 1, completed_assumed: 0, total: 3,
    })
    expect(abc.counts).toEqual({
      running: 0, ok: 1, failed: 1, completed_assumed: 0, total: 2,
    })
  })

  it('handles a single-segment path as a root leaf', () => {
    const tree = buildNipypeTree([leaf('only', 'ok')])
    expect(tree.nodes).toHaveLength(1)
    expect(tree.nodes[0].kind).toBe('leaf')
    expect(tree.nodes[0].parentId).toBeNull()
    expect(tree.edges).toHaveLength(0)
  })

  it('preserves leaf metadata on the corresponding tree node', () => {
    const tree = buildNipypeTree([leaf('wf.x', 'failed', 12.5)])
    const x = tree.nodes.find((n) => n.id === 'wf.x')!
    expect(x.kind).toBe('leaf')
    expect(x.status).toBe('failed')
    expect(x.elapsed).toBe(12.5)
    expect(x.full_node).toBe('wf.x')
    expect(x.level).toBe('INFO')
  })

  it('handles an empty input', () => {
    const tree = buildNipypeTree([])
    expect(tree.nodes).toEqual([])
    expect(tree.edges).toEqual([])
  })

  it('does not duplicate edges across multiple leaves under the same parent', () => {
    const tree = buildNipypeTree([
      leaf('wf.a'),
      leaf('wf.b'),
      leaf('wf.c'),
    ])
    // Three leaves all share parent `wf` — three distinct edges, none duplicated.
    const wfChildren = tree.edges.filter((e) => e.source === 'wf').map((e) => e.target).sort()
    expect(wfChildren).toEqual(['wf.a', 'wf.b', 'wf.c'])
  })
})
