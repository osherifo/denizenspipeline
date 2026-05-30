/** inferredName: human-readable label for a fmriprep nipype node. */

import { describe, it, expect } from 'vitest'
import { inferredName } from '../fmriprep_labels'

describe('inferredName', () => {
  it('returns the curated name for an exact match', () => {
    expect(inferredName('anat_preproc_wf')).toBe('prepare anatomy')
    expect(inferredName('bold_hmc_wf')).toBe('estimate head motion')
    expect(inferredName('surface_recon_wf')).toBe('reconstruct surfaces')
  })

  it('matches without the _wf suffix', () => {
    expect(inferredName('anat_preproc')).toBe('prepare anatomy')
  })

  it('infers subject names with the id preserved', () => {
    expect(inferredName('single_subject_01_wf')).toBe('preprocess subject 01')
    expect(inferredName('single_subject_AN_wf')).toBe('preprocess subject an')
  })

  it('infers functional preprocessing with the ses/task/run suffix', () => {
    expect(inferredName('func_preproc_ses_1_task_x_run_1_wf')).toBe(
      'functional · ses 1 task x run 1',
    )
    expect(inferredName('func_preproc_task_rest_wf')).toBe(
      'functional · task rest',
    )
  })

  it('infers bold_preproc with the run suffix', () => {
    expect(inferredName('bold_preproc_run_1_wf')).toBe('BOLD · run 1')
  })

  it('maps top-level fmriprep', () => {
    expect(inferredName('fmriprep_wf')).toBe('preprocess dataset')
  })

  it('maps nipype mechanics', () => {
    expect(inferredName('inputnode')).toBe('inputs')
    expect(inferredName('outputnode')).toBe('outputs')
  })

  it('maps datasinks via exact match', () => {
    expect(inferredName('ds_report_carpetplot')).toBe('save report: carpet plot')
    expect(inferredName('ds_boldref')).toBe('save BOLD reference')
  })

  it('maps unknown datasinks via pattern', () => {
    expect(inferredName('ds_report_something_new')).toBe('save report: something new')
    expect(inferredName('ds_some_unknown')).toBe('save some unknown')
  })

  it('maps confound internal nodes', () => {
    expect(inferredName('acc_msk_tfm')).toBe('resample tissue prob → BOLD')
    expect(inferredName('acc_msk_bin')).toBe('binarize tissue prob')
    expect(inferredName('gen_ref')).toBe('build resampling grid')
  })

  it('strips MapNode numeric suffix for internal nodes', () => {
    expect(inferredName('acc_msk_tfm0')).toBe('resample tissue prob → BOLD')
    expect(inferredName('acc_msk_tfm2')).toBe('resample tissue prob → BOLD')
    expect(inferredName('fsl_to_lta1')).toBe('convert FSL → LTA affine')
  })

  it('pairs BIDS entities for per-run BOLD workflows', () => {
    expect(inferredName('bold_ses_01_task_rest_wf')).toBe(
      'preprocess run · ses-01 task-rest',
    )
    expect(inferredName('bold_ses_02_task_movie_run_3_wf')).toBe(
      'preprocess run · ses-02 task-movie run-3',
    )
    expect(inferredName('bold_task_nback_acq_mb4_run_1_wf')).toBe(
      'preprocess run · task-nback acq-mb4 run-1',
    )
  })

  it('pairs BIDS entities for per-run subworkflows', () => {
    expect(inferredName('bold_fit_ses_01_task_rest_wf')).toBe(
      'estimate BOLD transforms · ses-01 task-rest',
    )
    expect(inferredName('bold_native_ses_01_task_rest_wf')).toBe(
      'apply BOLD corrections · ses-01 task-rest',
    )
    expect(inferredName('bold_confounds_ses_01_task_rest_wf')).toBe(
      'compute nuisance regressors · ses-01 task-rest',
    )
    expect(inferredName('carpetplot_ses_01_task_rest_wf')).toBe(
      'render carpet plot · ses-01 task-rest',
    )
  })

  it('returns null for fully unknown labels', () => {
    expect(inferredName('some_random_node')).toBeNull()
  })

  it('returns null for null / undefined / empty', () => {
    expect(inferredName(null)).toBeNull()
    expect(inferredName(undefined)).toBeNull()
    expect(inferredName('')).toBeNull()
  })

  it('curated dictionary snapshot — guards against accidental adds', () => {
    const probes = [
      'fmriprep_wf',
      'anat_preproc_wf',
      'anat_norm_wf',
      'brain_extraction_wf',
      'surface_recon_wf',
      'bold_fit_wf',
      'bold_hmc_wf',
      'bold_stc_wf',
      'bold_reg_wf',
      'bold_native_wf',
      'bold_volumetric_resample_wf',
      'bold_confs_wf',
      'bold_carpetplot_wf',
      'bold_surf_wf',
      'sdc_wf',
      'sdc_estimate_wf',
      'bold_sdc_wf',
      'fmap_wf',
    ]
    const mapping = Object.fromEntries(probes.map((p) => [p, inferredName(p)]))
    expect(mapping).toMatchSnapshot()
  })
})
