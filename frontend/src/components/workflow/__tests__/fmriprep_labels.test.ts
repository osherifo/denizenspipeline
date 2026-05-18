/** inferredName: human-readable label for a fmriprep nipype node. */

import { describe, it, expect } from 'vitest'
import { inferredName } from '../fmriprep_labels'

describe('inferredName', () => {
  it('returns the curated name for an exact match', () => {
    expect(inferredName('anat_preproc_wf')).toBe('Anatomical preprocessing')
    expect(inferredName('bold_hmc_wf')).toBe('Head motion correction')
    expect(inferredName('surface_recon_wf')).toBe('Surface reconstruction')
  })

  it('matches without the _wf suffix', () => {
    expect(inferredName('anat_preproc')).toBe('Anatomical preprocessing')
  })

  it('infers subject names with the id preserved', () => {
    expect(inferredName('single_subject_01_wf')).toBe('Subject 01')
    expect(inferredName('single_subject_AN_wf')).toBe('Subject an')
  })

  it('infers functional preprocessing with the ses/task/run suffix', () => {
    expect(inferredName('func_preproc_ses_1_task_x_run_1_wf')).toBe(
      'Functional · ses 1 task x run 1',
    )
    expect(inferredName('func_preproc_task_rest_wf')).toBe(
      'Functional · task rest',
    )
  })

  it('infers bold_preproc with the run suffix', () => {
    expect(inferredName('bold_preproc_run_1_wf')).toBe('BOLD · run 1')
  })

  it('special-cases top-level fmriprep', () => {
    expect(inferredName('fmriprep_wf')).toBe('fMRIPrep')
  })

  it('returns null for fully unknown labels', () => {
    expect(inferredName('inputnode')).toBeNull()
    expect(inferredName('some_random_node')).toBeNull()
  })

  it('returns null for null / undefined / empty', () => {
    expect(inferredName(null)).toBeNull()
    expect(inferredName(undefined)).toBeNull()
    expect(inferredName('')).toBeNull()
  })
})
