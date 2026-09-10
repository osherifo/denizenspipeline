import { describe, expect, it } from 'vitest'
import { formatBounds, parseBounds } from '../bounds'

describe('bounds text', () => {
  it('parses one bound per line, numbers and between', () => {
    const { bounds, errors } = parseBounds('n_trs > 100\nmean_mm between 2.0 3.2\nis_4d == true')
    expect(errors).toEqual([])
    expect(bounds).toEqual({ n_trs: ['>', 100], mean_mm: ['between', [2.0, 3.2]], is_4d: ['==', true] })
  })
  it('reports bad lines without dropping good ones', () => {
    const { bounds, errors } = parseBounds('n_trs >\nfoo ~ 3\nok < 1')
    expect(Object.keys(bounds)).toEqual(['ok'])
    expect(errors).toHaveLength(2)
  })
  it('round-trips through formatBounds', () => {
    const text = 'n_trs > 100\nmean_mm between 2 3.2'
    expect(formatBounds(parseBounds(text).bounds)).toBe(text)
  })
})
