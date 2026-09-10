import { describe, expect, it } from 'vitest'
import { formatIterLiteral, parseIterLiteral } from '../iter-literal'

describe('iter literal', () => {
  it('parses comma lists with number coercion', () => {
    expect(parseIterLiteral('0, 1, 2')).toEqual([0, 1, 2])
    expect(parseIterLiteral('a,b , c')).toEqual(['a', 'b', 'c'])
    expect(parseIterLiteral(' 1.5,x ')).toEqual([1.5, 'x'])
    expect(parseIterLiteral('')).toEqual([])
  })
  it('parses JSON arrays and falls back on bad JSON', () => {
    expect(parseIterLiteral('[0, "run-1", 2]')).toEqual([0, 'run-1', 2])
    expect(parseIterLiteral('[0, 1')).toEqual(['[0', 1])
  })
  it('formats lists back to text', () => {
    expect(formatIterLiteral([0, 1, 'x'])).toBe('0, 1, x')
    expect(formatIterLiteral('/a.nii')).toBe('/a.nii')
    expect(formatIterLiteral(undefined)).toBe('')
  })
})
