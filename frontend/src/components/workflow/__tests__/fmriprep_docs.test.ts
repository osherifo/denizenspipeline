/** fmriprepDocUrl: maps nipype node labels to fmriprep docs URLs. */

import { describe, it, expect } from 'vitest'
import { fmriprepDocUrl } from '../fmriprep_docs'

const BASE = 'https://fmriprep.org/en/stable/workflows.html'

describe('fmriprepDocUrl', () => {
  it('maps a curated workflow name (with _wf suffix) to its anchor', () => {
    expect(fmriprepDocUrl('anat_preproc_wf')).toBe(
      `${BASE}#anatomical-data-preprocessing`,
    )
    expect(fmriprepDocUrl('bold_hmc_wf')).toBe(
      `${BASE}#head-motion-estimation`,
    )
    expect(fmriprepDocUrl('surface_recon_wf')).toBe(
      `${BASE}#cortical-surface-reconstruction`,
    )
  })

  it('matches even without the _wf suffix', () => {
    expect(fmriprepDocUrl('anat_preproc')).toBe(
      `${BASE}#anatomical-data-preprocessing`,
    )
  })

  it('strips a trailing index suffix like _01', () => {
    expect(fmriprepDocUrl('bold_hmc_wf_01')).toBe(
      `${BASE}#head-motion-estimation`,
    )
  })

  it('uses the prefix fallback for unmatched but topical labels', () => {
    // bold_split isn't in the curated map; bold_ prefix → bold-preprocessing.
    expect(fmriprepDocUrl('bold_split')).toBe(`${BASE}#bold-preprocessing`)
    // anat_random_thing → anatomical-data-preprocessing via anat_ prefix.
    expect(fmriprepDocUrl('anat_random_thing')).toBe(
      `${BASE}#anatomical-data-preprocessing`,
    )
  })

  it('falls back to the base workflows page for fully unknown labels', () => {
    expect(fmriprepDocUrl('inputnode')).toBe(BASE)
    expect(fmriprepDocUrl('some_internal_node')).toBe(BASE)
  })

  it('special-cases top-level fmriprep with the bare page URL', () => {
    expect(fmriprepDocUrl('fmriprep_wf')).toBe(BASE)
  })

  it('survives null / undefined / empty', () => {
    expect(fmriprepDocUrl(null)).toBe(BASE)
    expect(fmriprepDocUrl(undefined)).toBe(BASE)
    expect(fmriprepDocUrl('')).toBe(BASE)
  })
})
