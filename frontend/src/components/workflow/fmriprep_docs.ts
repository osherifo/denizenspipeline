/** Map a nipype/fMRIPrep workflow node label to an fMRIPrep docs URL.
 *
 * Each node in the nipype DAG has a `label` field — the last segment of
 * the dotted nipype path (e.g. `bold_hmc_wf`, `anat_preproc_wf`,
 * `bold_split`). We map the well-known workflow names to anchored
 * sections of fmriprep.org's `workflows.html` page (which has a TOC of
 * the conceptual processing stages).
 *
 * For labels we don't have a specific anchor for, the helper falls
 * back to the workflows.html page without an anchor — still useful
 * because it's the full workflow tour. No null returns — every node
 * gets a working URL.
 */

const WORKFLOWS_BASE = 'https://fmriprep.org/en/stable/workflows.html'

// Hand-curated label → anchor map. Keys are matched after stripping
// the trailing `_wf` (so `anat_preproc_wf` matches `anat_preproc`).
// Anchors come from the actual section IDs on workflows.html.
const ANCHOR_MAP: Record<string, string> = {
  // Anatomical
  anat_preproc:            'anatomical-data-preprocessing',
  anat_norm:               'spatial-normalization',
  brain_extraction:        'brain-extraction-brain-tissue-segmentation-and-spatial-normalization',
  surface_recon:           'cortical-surface-reconstruction',
  refinement:              'refinement-of-the-brain-mask',

  // Functional (BOLD)
  func_preproc:            'bold-preprocessing',
  bold:                    'bold-preprocessing',
  bold_preproc:            'bold-preprocessing',
  bold_reference:          'reference-image-estimation',
  bold_hmc:                'head-motion-estimation',
  bold_stc:                'slice-time-correction',
  bold_reg:                'eddy-current-and-head-motion-correction',
  bold_t1_trans:           'pre-processed-bold-in-a-different-space',
  bold_std_trans:          'pre-processed-bold-in-a-different-space',
  bold_mni_trans:          'pre-processed-bold-in-a-different-space',
  bold_confounds:          'confounds-estimation',
  bold_carpetplot:         'confounds-estimation',
  bold_surf:               'surface-resampling',

  // Susceptibility / fieldmaps
  sdc:                     'susceptibility-distortion-correction-sdc',
  sdc_estimate:            'susceptibility-distortion-correction-sdc',
  bold_sdc:                'susceptibility-distortion-correction-sdc',
  fmap:                    'susceptibility-distortion-correction-sdc',

  // Top-level
  fmriprep:                '', // no anchor — top of page
}

// Prefix patterns for labels that don't match a curated entry but share
// a clear topical prefix. Order matters — first hit wins.
const PREFIX_FALLBACKS: Array<[string, string]> = [
  ['anat_',  'anatomical-data-preprocessing'],
  ['bold_',  'bold-preprocessing'],
  ['func_',  'bold-preprocessing'],
  ['surf_',  'surface-resampling'],
  ['sdc_',   'susceptibility-distortion-correction-sdc'],
  ['fmap_',  'susceptibility-distortion-correction-sdc'],
]


/** Normalise a node label for map lookup:
 *   - lowercase
 *   - strip a trailing `_NN` (subject / run index, e.g. `_01`) first
 *     so that `bold_hmc_wf_01` reduces to `bold_hmc_wf`
 *   - then strip a trailing `_wf` so it becomes `bold_hmc`
 */
function _normalise(label: string): string {
  let s = label.toLowerCase()
  s = s.replace(/_\d+$/, '')
  s = s.replace(/_wf$/, '')
  return s
}


/** Resolve a node label to a fully-qualified fmriprep docs URL. */
export function fmriprepDocUrl(label: string | undefined | null): string {
  if (!label) return WORKFLOWS_BASE
  const key = _normalise(label)
  if (key in ANCHOR_MAP) {
    const anchor = ANCHOR_MAP[key]
    return anchor ? `${WORKFLOWS_BASE}#${anchor}` : WORKFLOWS_BASE
  }
  for (const [prefix, anchor] of PREFIX_FALLBACKS) {
    if (key.startsWith(prefix)) return `${WORKFLOWS_BASE}#${anchor}`
  }
  return WORKFLOWS_BASE
}
