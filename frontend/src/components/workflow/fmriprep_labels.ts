/** Inferred human-readable names for fMRIPrep workflow node labels.
 *
 * Source of truth: fmriflow/builtin/label_maps/fmriprep_{major}.yaml
 *
 * This file embeds the v25 map as the compile-time default. At runtime
 * the modal can fetch the label map for the actual fmriprep version
 * via GET /api/preproc/label-map?version={major} and pass it to
 * ``setRuntimeMap`` — after that, ``inferredName`` uses the runtime
 * map first, falling back to the embedded default.
 *
 * Lookup order: runtime map → embedded exact → pattern rules → null.
 */

// ── Embedded default (fmriprep 25) ────────────────────────────────────
// Key = normalised label (lowercase, trailing _wf stripped).

const EMBEDDED: Record<string, string> = {
  // Top-level orchestration
  fmriprep:                        'preprocess dataset',
  bidssrc:                         'find subject files',
  bids_info:                       'read subject metadata',
  summary:                         'write run summary',
  about:                           'write version info',

  // Anatomical (sMRIPrep)
  anat_preproc:                    'prepare anatomy',
  anat_template:                   'build T1w reference',
  brain_extraction:                'skull-strip T1w',
  t1w_dseg:                        'segment tissues',
  anat_norm:                       'register T1w → MNI',
  surface_recon:                   'reconstruct surfaces',
  refine_brain_mask:               'refine brain mask',

  // BOLD fit
  bold_fit:                        'estimate BOLD transforms',
  raw_boldref:                     'build BOLD reference',
  enhance_and_skullstrip_bold:     'mask BOLD reference',
  bold_hmc:                        'estimate head motion',
  unwarp:                          'estimate distortion correction',
  bold_reg:                        'register BOLD → T1w',
  fsl_bbr:                         'register BOLD → T1w (FSL)',
  bbreg:                           'register BOLD → T1w (FS)',
  hmc_boldref:                     'motion reference',
  coreg_boldref:                   'registration reference',
  bold_mask:                       'BOLD brain mask',
  motion_xfm:                      'per-volume motion transforms',
  boldref2anat_xfm:               'BOLD → anat transform',
  boldref2fmap_xfm:               'BOLD → fieldmap transform',
  dummy_scans:                     'non-steady-state count',

  // BOLD native resampling
  bold_native:                     'apply BOLD corrections',
  bold_stc:                        'correct slice timing',
  boldbuffer:                      'select STC or raw',
  bold_native_resample:            'resample BOLD native',
  metadata:                        'updated BOLD sidecar',
  bold_echos:                      'corrected echo series',
  t2star_map:                      'T2* map',

  // BOLD volumetric resampling
  bold_volumetric_resample:        'resample BOLD → space',
  bold_anat:                       'resample BOLD → anat space',
  bold_std:                        'resample BOLD → template space',
  bold_file:                       'BOLD in target space',
  resampling_reference:            'target space grid',

  // Surface / CIFTI
  bold_surf:                       'resample BOLD → surfaces',
  bold_fslr_resampling:            'resample BOLD → fsLR',
  bold_grayords:                   'build CIFTI grayordinates',

  // Confounds and QC — workflows
  bold_confs:                      'compute nuisance regressors',
  bold_confounds:                  'compute nuisance regressors',
  carpetplot:                      'render carpet plot',
  bold_carpetplot:                 'render carpet plot',

  // Confounds and QC — internal nodes (aCompCor mask prep, MapNode iterations)
  acc_msk_tfm:                     'resample tissue prob → BOLD',
  acc_msk_bin:                     'binarize tissue prob',
  acc_msk_brain:                   'intersect with brain mask',
  anat2std_tpms:                   'resample tissue prob → template',
  fsl_to_lta:                      'convert FSL → LTA affine',
  gen_ref:                         'build resampling grid',
  mask_anat:                       'mask anatomy with BOLD mask',
  subtract_mask:                   'subtract tissue masks',

  // Confounds and QC — outputs
  confounds_file:                  'nuisance regressors table',
  confounds_metadata:              'nuisance regressors sidecar',
  acompcor_masks:                  'aCompCor masks',
  tcompcor_mask:                   'tCompCor mask',
  crown_mask:                      'brain boundary mask',
  rois_report:                     'CompCor ROIs report',

  // Susceptibility / fieldmaps
  sdc:                             'distortion correction',
  sdc_estimate:                    'estimate distortion correction',
  bold_sdc:                        'BOLD distortion correction',
  fmap:                            'fieldmap',

  // Datasinks — anatomical
  ds_t1w_preproc:                  'save T1w preprocessed',
  ds_t1w_mask:                     'save T1w brain mask',
  ds_t1w_dseg:                     'save tissue segmentation',
  ds_t1w_tpms:                     'save tissue probabilities',
  ds_std_t1w:                      'save T1w in MNI',
  ds_std_mask:                     'save brain mask in MNI',
  ds_t1w_mni_xfm:                 'save T1w → MNI transform',
  ds_report_t1_2_mni:             'save report: MNI registration',
  ds_report_seg:                   'save report: segmentation',
  ds_report_t1w_dseg_mask:        'save report: brain mask overlay',

  // Datasinks — BOLD fit
  ds_boldref:                      'save BOLD reference',
  ds_boldmask:                     'save BOLD brain mask',
  ds_hmc_xfm:                     'save motion transforms',
  ds_coreg_xfm:                   'save BOLD → anat transform',
  ds_report_validation:            'save report: BOLD validation',
  ds_report_bold_rois:             'save report: CompCor ROIs',
  ds_report_reg:                   'save report: BOLD → anat',
  ds_report_sdc:                   'save report: distortion correction',

  // Datasinks — BOLD resampled
  ds_bold_native:                  'save BOLD in native space',
  ds_bold_t1:                      'save BOLD in anat space',
  ds_bold_std:                     'save BOLD in template',
  ds_bold_std_ref:                 'save BOLD ref in template',
  ds_bold_mask_std:                'save brain mask in template',

  // Datasinks — confounds/QC
  ds_confounds:                    'save nuisance regressors',
  ds_report_bold_conf:             'save report: confounds',
  ds_report_carpetplot:            'save report: carpet plot',

  // Datasinks — run-level
  ds_report_summary:               'save report: run summary',
  ds_report_about:                 'save report: version info',

  // Nipype mechanics
  inputnode:                        'inputs',
  outputnode:                       'outputs',
}

// ── Runtime override ───────────────────────────────────────────────────

let _runtimeMap: Record<string, string> | null = null

export function setRuntimeMap(map: Record<string, string>): void {
  const cleaned: Record<string, string> = {}
  for (const [k, v] of Object.entries(map)) {
    cleaned[_normalise(k)] = v.replace(/_/g, ' ')
  }
  _runtimeMap = cleaned
}

// ── BIDS entity pairing ────────────────────────────────────────────────
// "ses_01_task_rest_run_3" → "ses-01 task-rest run-3"

const BIDS_ENTITIES = new Set([
  'ses', 'task', 'run', 'acq', 'echo', 'dir', 'rec', 'space',
])

function _pairBidsEntities(raw: string): string {
  const tokens = raw.split('_')
  const parts: string[] = []
  let i = 0
  while (i < tokens.length) {
    if (BIDS_ENTITIES.has(tokens[i]) && i + 1 < tokens.length) {
      parts.push(`${tokens[i]}-${tokens[i + 1]}`)
      i += 2
    } else {
      parts.push(tokens[i])
      i++
    }
  }
  return parts.join(' ')
}

// ── Per-run subworkflow prefix map ─────────────────────────────────────
// When a per-run bold workflow contains a known subworkflow, we want to
// show e.g. "estimate head motion · ses-01_task-rest" instead of the
// raw nipype name. These prefixes are tried IN ORDER against the
// normalised label; the first match wins.

const PER_RUN_SUBWORKFLOW_PREFIXES: Array<{
  prefix: string
  friendly: string
}> = [
  { prefix: 'bold_fit_',         friendly: 'estimate BOLD transforms' },
  { prefix: 'bold_native_',      friendly: 'apply BOLD corrections' },
  { prefix: 'bold_confounds_',   friendly: 'compute nuisance regressors' },
  { prefix: 'bold_confs_',       friendly: 'compute nuisance regressors' },
  { prefix: 'carpetplot_',       friendly: 'render carpet plot' },
]

// ── Pattern rules ──────────────────────────────────────────────────────

const PATTERN_RULES: Array<{
  re: RegExp
  fmt: (m: RegExpMatchArray) => string
}> = [
  {
    re: /^single_subject_(.+)$/,
    fmt: (m) => `preprocess subject ${m[1]}`,
  },
  {
    // Per-run BOLD workflow: bold_ses_01_task_rest → preprocess run · ses-01_task-rest
    re: /^bold_((ses|task|run|acq|echo|dir|rec)_.+)$/,
    fmt: (m) => `preprocess run · ${_pairBidsEntities(m[1])}`,
  },
  {
    re: /^func_preproc_(.+)$/,
    fmt: (m) => `functional · ${m[1].replace(/_/g, ' ')}`,
  },
  {
    re: /^bold_preproc_(.+)$/,
    fmt: (m) => `BOLD · ${m[1].replace(/_/g, ' ')}`,
  },
  {
    // ds_report_* not already matched
    re: /^ds_report_(.+)$/,
    fmt: (m) => `save report: ${m[1].replace(/_/g, ' ')}`,
  },
  {
    // ds_* not already matched
    re: /^ds_(.+)$/,
    fmt: (m) => `save ${m[1].replace(/_/g, ' ')}`,
  },
]


function _normalise(label: string): string {
  let s = label.toLowerCase()
  s = s.replace(/_wf$/, '')
  return s
}

function _tryPerRunSubworkflow(key: string): string | null {
  for (const { prefix, friendly } of PER_RUN_SUBWORKFLOW_PREFIXES) {
    if (key.startsWith(prefix)) {
      const entities = key.slice(prefix.length)
      if (entities && BIDS_ENTITIES.has(entities.split('_')[0])) {
        return `${friendly} · ${_pairBidsEntities(entities)}`
      }
    }
  }
  return null
}


export function inferredName(label: string | undefined | null): string | null {
  if (!label) return null
  const key = _normalise(label)
  // Strip trailing MapNode index (e.g. _acc_msk_tfm0 → acc_msk_tfm)
  const keyNoIdx = key.replace(/\d+$/, '')
  if (_runtimeMap) {
    if (key in _runtimeMap) return _runtimeMap[key]
    if (keyNoIdx !== key && keyNoIdx in _runtimeMap) return _runtimeMap[keyNoIdx]
  }
  if (key in EMBEDDED) return EMBEDDED[key]
  if (keyNoIdx !== key && keyNoIdx in EMBEDDED) return EMBEDDED[keyNoIdx]
  const perRun = _tryPerRunSubworkflow(key)
  if (perRun) return perRun
  for (const { re, fmt } of PATTERN_RULES) {
    const m = key.match(re)
    if (m) return fmt(m)
  }
  return null
}
