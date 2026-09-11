import { describe, expect, it } from 'vitest'
import { checkConnection, compatible, latticeFrom, reaches } from '../connection'

const lattice = latticeFrom([
  { name: 'any', parents: [] },
  { name: 'FeatureSet', parents: [] },
  { name: 'FeatureData', parents: [] },
  { name: 'Parent', parents: [] },
  { name: 'Child', parents: ['Parent'] },
])

describe('port type compatibility', () => {
  it('follows the lattice like the backend', () => {
    expect(compatible(lattice, 'FeatureSet', 'FeatureSet')).toBe(true)
    expect(compatible(lattice, 'Child', 'Parent')).toBe(true)
    expect(compatible(lattice, 'Parent', 'Child')).toBe(false)
    expect(compatible(lattice, 'FeatureSet', 'FeatureData')).toBe(false)
    expect(compatible(lattice, 'any', 'FeatureData')).toBe(true)
    expect(compatible(lattice, 'FeatureSet', 'any')).toBe(true)
  })
})

describe('checkConnection', () => {
  const ports: Record<string, { in: Record<string, string>; out: Record<string, string> }> = {
    a: { in: {}, out: { feature: 'FeatureSet' } },
    b: { in: { features: 'FeatureSet', data: 'FeatureData' }, out: { features: 'FeatureData' } },
  }
  const portOf = (id: string, side: 'in' | 'out', port: string) => {
    const type = ports[id]?.[side][port]
    return type ? { type } : undefined
  }
  const conn = (targetHandle: string, extra = {}) => ({ source: 'a', target: 'b', sourceHandle: 'feature', targetHandle, ...extra })

  it('accepts matching types', () => {
    expect(checkConnection([], conn('features'), portOf, lattice)).toBeNull()
  })
  it('explains why a connection is refused', () => {
    expect(checkConnection([], conn('data'), portOf, lattice)).toBe('FeatureSet cannot feed FeatureData')
    expect(checkConnection([], conn('nope'), portOf, lattice)).toBe('b has no input nope')
    expect(checkConnection([], conn('features', { sourceHandle: 'nope' }), portOf, lattice)).toBe('a has no output nope')
    expect(checkConnection([], conn('features', { target: 'a' }), portOf, lattice)).toBe('a node cannot feed itself')
    expect(checkConnection([{ source: 'b', target: 'a' }], conn('features'), portOf, lattice)).toBe('this connection would make a cycle')
  })
  it('finds paths', () => {
    expect(reaches([{ source: 'x', target: 'y' }, { source: 'y', target: 'z' }], 'x', 'z')).toBe(true)
    expect(reaches([{ source: 'x', target: 'y' }], 'y', 'x')).toBe(false)
  })
})
