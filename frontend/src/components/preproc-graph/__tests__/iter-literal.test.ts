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
  it('formats lists back to text as JSON, not a comma-join', () => {
    expect(formatIterLiteral([0, 1, 'x'])).toBe('[0,1,"x"]')
    expect(formatIterLiteral('/a.nii')).toBe('/a.nii')
    expect(formatIterLiteral(undefined)).toBe('')
  })
  it('round-trips exactly through format -> parse, even with commas or leading zeros in an item', () => {
    // A comma-joined format would turn 'a,b' into two items on reparse, and
    // '001' into the number 1 — this is the exact save-then-reopen corruption
    // it must not have.
    const value = ['001', 'a,b', 2]
    expect(parseIterLiteral(formatIterLiteral(value))).toEqual(value)
  })
})
