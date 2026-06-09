/** Lane partitioning: shared upstream + per-run BOLD lanes. */

import { describe, it, expect } from 'vitest'
import type { NipypeNodeStatus } from '../../../api/types'
import { buildNipypeTree } from '../nipype_tree'
import { partitionLanes, _decodeFuncIdForTests } from '../nipype_lanes'


function leaf(node: string, status: NipypeNodeStatus['status'] = 'ok'): NipypeNodeStatus {
  const seg = node.split('.')
  return {
    node,
    leaf: seg[seg.length - 1],
    workflow: seg.slice(0, -1).join('.'),
    status,
    started_at: 0,
    finished_at: 0,
    elapsed: 0,
    crash_file: null,
    level: 'INFO',
  }
}


describe('_decodeFuncId', () => {
  it('decodes the full ses+task+run form', () => {
    expect(_decodeFuncIdForTests('func_preproc_ses_1_task_x_run_1_wf')).toEqual({
      ses: '1', task: 'x', run: '1',
    })
  })

  it('decodes task-only (no ses, no run)', () => {
    expect(_decodeFuncIdForTests('func_preproc_task_rest_wf')).toEqual({
      ses: null, task: 'rest', run: null,
    })
  })

  it('decodes task+run (no ses)', () => {
    expect(_decodeFuncIdForTests('func_preproc_task_story_run_3_wf')).toEqual({
      ses: null, task: 'story', run: '3',
    })
  })

  it('decodes ses+task (no run)', () => {
    expect(_decodeFuncIdForTests('func_preproc_ses_2_task_movie_wf')).toEqual({
      ses: '2', task: 'movie', run: null,
    })
  })

  it('decodes bare run (no ses, no task)', () => {
    expect(_decodeFuncIdForTests('func_preproc_run_1_wf')).toEqual({
      ses: null, task: null, run: '1',
    })
  })

  it('returns null for non-func_preproc workflows', () => {
    expect(_decodeFuncIdForTests('anat_preproc_wf')).toBeNull()
    expect(_decodeFuncIdForTests('sdc_estimate_wf')).toBeNull()
    expect(_decodeFuncIdForTests('bold_hmc_wf')).toBeNull()
  })
})


describe('partitionLanes — fmriprep subject with multiple BOLD runs', () => {
  function build() {
    return buildNipypeTree([
      // Shared upstream (anat + sdc).
      leaf('fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf.n4'),
      leaf('fmriprep_wf.single_subject_01_wf.anat_preproc_wf.surface_recon_wf.recon_all'),
      leaf('fmriprep_wf.single_subject_01_wf.sdc_estimate_wf.estimate'),
      // Three runs.
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_1_wf.bold_hmc_wf.mcflirt'),
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_1_wf.bold_confounds_wf.dvars'),
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_2_wf.bold_hmc_wf.mcflirt'),
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_3_wf.bold_hmc_wf.mcflirt'),
    ])
  }

  it('produces one shared lane + one lane per BOLD run', () => {
    const lanes = partitionLanes(build())
    expect(lanes.map((l) => l.id)).toEqual([
      'lane:shared', 'lane:run-1', 'lane:run-2', 'lane:run-3',
    ])
  })

  it('decodes BIDS entities into the run lane title', () => {
    const lanes = partitionLanes(build())
    expect(lanes[1].title).toBe('Run 1 · ses-1 task-x run-1')
    expect(lanes[2].title).toBe('Run 2 · ses-1 task-x run-2')
    expect(lanes[3].title).toBe('Run 3 · ses-1 task-x run-3')
  })

  it('shared lane contains anat + sdc roots and their descendants', () => {
    const lanes = partitionLanes(build())
    const shared = lanes[0]
    expect(shared.memberIds).toContain('fmriprep_wf.single_subject_01_wf.anat_preproc_wf')
    expect(shared.memberIds).toContain('fmriprep_wf.single_subject_01_wf.sdc_estimate_wf')
    // Deeper descendants included.
    expect(shared.memberIds).toContain(
      'fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf',
    )
  })

  it('run lanes contain only their own descendants — no cross-contamination', () => {
    const lanes = partitionLanes(build())
    const run1 = lanes.find((l) => l.id === 'lane:run-1')!
    const run2 = lanes.find((l) => l.id === 'lane:run-2')!
    expect(run1.memberIds.every((id) => id.includes('run_1'))).toBe(true)
    expect(run2.memberIds.every((id) => id.includes('run_2'))).toBe(true)
  })

  it('every input id ends up in exactly one lane (apart from the depth-1/2 ancestors)', () => {
    const tree = build()
    const lanes = partitionLanes(tree)
    const placed = new Set(lanes.flatMap((l) => l.memberIds))
    const expectedSkipped = new Set([
      'fmriprep_wf',
      'fmriprep_wf.single_subject_01_wf',
    ])
    for (const n of tree.nodes) {
      if (expectedSkipped.has(n.id)) {
        expect(placed.has(n.id)).toBe(false)
      } else {
        expect(placed.has(n.id)).toBe(true)
      }
    }
  })
})


describe('partitionLanes — edge cases', () => {
  it('returns just a shared lane when the subject has no BOLD runs (anat-only)', () => {
    const tree = buildNipypeTree([
      leaf('fmriprep_wf.single_subject_01_wf.anat_preproc_wf.brain_extraction_wf.n4'),
    ])
    const lanes = partitionLanes(tree)
    expect(lanes.length).toBe(1)
    expect(lanes[0].id).toBe('lane:shared')
  })

  it('handles a single BOLD run + no anatomical', () => {
    const tree = buildNipypeTree([
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_1_wf.bold_hmc_wf.mcflirt'),
    ])
    const lanes = partitionLanes(tree)
    expect(lanes.length).toBe(1)
    expect(lanes[0].id).toBe('lane:run-1')
  })

  it('handles a func_preproc workflow with no ses entity', () => {
    const tree = buildNipypeTree([
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_task_rest_run_1_wf.bold_hmc_wf.mcflirt'),
    ])
    const lanes = partitionLanes(tree)
    expect(lanes[0].title).toBe('Run 1 · task-rest run-1')
  })

  it('falls back to one big "Workflow" lane for non-fmriprep trees', () => {
    const tree = buildNipypeTree([
      leaf('my_pipeline.step_a.task_1'),
      leaf('my_pipeline.step_b.task_2'),
    ])
    const lanes = partitionLanes(tree)
    expect(lanes.length).toBe(1)
    expect(lanes[0].id).toBe('lane:all')
    expect(lanes[0].title).toBe('Workflow')
    // Every node is a member.
    expect(lanes[0].memberIds.length).toBe(tree.nodes.length)
  })

  it('returns an empty array for an empty tree', () => {
    const tree = buildNipypeTree([])
    expect(partitionLanes(tree)).toEqual([])
  })
})


describe('partitionLanes — counts', () => {
  it('lane counts are the sum of the depth-3 roots inside that lane, not double-counted', () => {
    const tree = buildNipypeTree([
      // run-1 has two leaves
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_1_wf.bold_hmc_wf.mcflirt', 'ok'),
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_1_wf.bold_confounds_wf.dvars', 'failed'),
      // run-2 has one leaf
      leaf('fmriprep_wf.single_subject_01_wf.func_preproc_ses_1_task_x_run_2_wf.bold_hmc_wf.mcflirt', 'running'),
    ])
    const lanes = partitionLanes(tree)
    const run1 = lanes.find((l) => l.id === 'lane:run-1')!
    const run2 = lanes.find((l) => l.id === 'lane:run-2')!
    expect(run1.counts.total).toBe(2)
    expect(run1.counts.ok).toBe(1)
    expect(run1.counts.failed).toBe(1)
    expect(run2.counts.total).toBe(1)
    expect(run2.counts.running).toBe(1)
  })
})
