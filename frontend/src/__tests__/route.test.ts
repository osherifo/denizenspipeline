import { describe, expect, it } from 'vitest'
import { getRoute } from '../App'

function at(hash: string) {
  window.location.hash = hash
  return getRoute()
}

describe('hash router', () => {
  it('maps top-level sections', () => {
    expect(at('#dashboard')).toBe('dashboard')
    expect(at('#workflows')).toBe('workflows')
    expect(at('#preproc')).toBe('preproc')
    expect(at('')).toBe('dashboard')
  })

  it('keeps the Preprocessing page for every one of its tabs', () => {
    for (const tab of ['build', 'runs', 'library', 'outputs']) {
      expect(at(`#preproc/${tab}`)).toBe('preproc')
    }
    expect(at('#/preproc/runs')).toBe('preproc')
  })

  it('folds the retired preprocessing tabs into the new page', () => {
    expect(at('#preproc-stack')).toBe('preproc')
    expect(at('#post-preproc')).toBe('preproc')
  })
})
