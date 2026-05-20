/** Inferred human-readable names for fMRIPrep workflow node labels.
 *
 * The dotted nipype path segments (e.g. `anat_preproc_wf`,
 * `single_subject_01_wf`, `func_preproc_ses_1_task_x_run_1_wf`) are
 * unambiguous but cryptic. This helper returns a plain-English name
 * the modal can use either as the primary label (friendly mode) or
 * as a small subtitle (raw mode). If we can't infer anything
 * reasonable, we return `null` and the caller falls back to the raw
 * label.
 *
 * SOURCE RULE — every EXACT_NAMES entry must correspond 1:1 to a
 * section heading on https://fmriprep.org/en/stable/workflows.html
 * (or the equivalent stage name in fmriprep's CLI / docs). Do NOT
 * invent conceptual names. If a workflow id has no documented
 * conceptual stage, leave it out and let the caller fall back to
 * the raw id.
 *
 * Mapping is split into two layers:
 *   1. EXACT_NAMES — hand-curated for the well-known fmriprep
 *      workflow names (with the `_wf` suffix stripped for matching).
 *   2. PATTERN_RULES — regex matches for parameterised names like
 *      `single_subject_{id}_wf` or
 *      `func_preproc_ses_{x}_task_{y}_run_{z}_wf`, with the captured
 *      parts interpolated into the output. The captured parts are
 *      literal substrings of the real workflow id — re-spaced for
 *      reading, not renamed.
 *
 * Order: exact match first, then patterns, then null.
 */

const EXACT_NAMES: Record<string, string> = {
  // Top-level
  fmriprep:             'fMRIPrep',

  // Anatomical
  anat_preproc:         'Anatomical preprocessing',
  anat_norm:            'Spatial normalisation',
  brain_extraction:     'Brain extraction',
  surface_recon:        'Surface reconstruction',
  refinement:           'Brain mask refinement',

  // Functional (BOLD)
  func_preproc:         'Functional preprocessing',
  bold_preproc:         'BOLD preprocessing',
  bold_reference:       'BOLD reference image',
  bold_hmc:             'Head motion correction',
  bold_stc:             'Slice-timing correction',
  bold_reg:             'BOLD-to-T1 registration',
  bold_t1_trans:        'BOLD in T1 space',
  bold_std_trans:       'BOLD in standard space',
  bold_mni_trans:       'BOLD in MNI space',
  bold_confounds:       'Confounds',
  bold_carpetplot:      'Carpet plot',
  bold_surf:            'BOLD on surface',

  // Susceptibility / fieldmaps
  sdc:                  'Distortion correction',
  sdc_estimate:         'Distortion-correction estimate',
  bold_sdc:             'BOLD distortion correction',
  fmap:                 'Fieldmap',
}

// Each rule has a regex that matches the normalised label (after
// stripping `_wf`); the function turns the captures into a display
// name.
const PATTERN_RULES: Array<{
  re: RegExp
  fmt: (m: RegExpMatchArray) => string
}> = [
  {
    // single_subject_01 → "Subject 01"
    re: /^single_subject_(.+)$/,
    fmt: (m) => `Subject ${m[1]}`,
  },
  {
    // func_preproc_ses_1_task_x_run_1 → "Functional ses 1 task x run 1"
    re: /^func_preproc_(.+)$/,
    fmt: (m) => `Functional · ${m[1].replace(/_/g, ' ')}`,
  },
  {
    // bold_preproc_run_1 → "BOLD run 1"
    re: /^bold_preproc_(.+)$/,
    fmt: (m) => `BOLD · ${m[1].replace(/_/g, ' ')}`,
  },
]


function _normalise(label: string): string {
  let s = label.toLowerCase()
  s = s.replace(/_wf$/, '')
  return s
}


/** Return a short plain-English name for a nipype label, or null
 * if we have no useful guess. */
export function inferredName(label: string | undefined | null): string | null {
  if (!label) return null
  const key = _normalise(label)
  if (key in EXACT_NAMES) return EXACT_NAMES[key]
  for (const { re, fmt } of PATTERN_RULES) {
    const m = key.match(re)
    if (m) return fmt(m)
  }
  return null
}
