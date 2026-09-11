import { describe, expect, it } from 'vitest'
import {
  addNodeTo, connect, disconnect, moveFanInEdge, moveNodeTo, removeNodeFrom, setNodeParams, topoOrder, uniqueId,
} from '../graph-edit-slice'

const node = (id: string) => ({ id, type: 't', position: { x: 0, y: 0 }, data: { params: {} } })
const doc = { nodes: [node('a'), node('b'), node('c')], edges: [] as { id: string; source: string; target: string; sourceHandle: string; targetHandle: string }[] }
const edge = (source: string, target: string, targetHandle = 'in') => ({ source, target, sourceHandle: 'out', targetHandle })

describe('graph edit helpers', () => {
  it('replaces the feed of a single input and keeps every feed of a fan-in input', () => {
    let d = connect(doc, edge('a', 'c'))
    d = connect(d, edge('b', 'c'))
    expect(d.edges.map((e) => e.source)).toEqual(['b'])
    let f = connect(doc, edge('a', 'c'), { fanIn: true })
    f = connect(f, edge('b', 'c'), { fanIn: true })
    expect(f.edges.map((e) => e.source)).toEqual(['a', 'b'])
    expect(connect(f, edge('b', 'c'), { fanIn: true })).toBe(f)
    expect(doc.edges).toEqual([])
  })

  it('reorders fan-in edges among the edges into the same input', () => {
    let d = connect(doc, edge('a', 'c'), { fanIn: true })
    d = connect(d, edge('b', 'c'), { fanIn: true })
    d = connect(d, edge('a', 'b'))
    const second = d.edges.find((e) => e.source === 'b' && e.target === 'c')!
    const moved = moveFanInEdge(d, second.id, -1)
    expect(moved.edges.filter((e) => e.target === 'c').map((e) => e.source)).toEqual(['b', 'a'])
    expect(moveFanInEdge(moved, second.id, -1)).toBe(moved)
  })

  it('removes a node with its edges and edits nodes immutably', () => {
    let d = connect(connect(doc, edge('a', 'b')), edge('b', 'c'))
    expect(topoOrder(d).map((n) => n.id)).toEqual(['a', 'b', 'c'])
    d = removeNodeFrom(d, 'b')
    expect(d.nodes.map((n) => n.id)).toEqual(['a', 'c'])
    expect(d.edges).toEqual([])
    const p = setNodeParams(doc, 'a', { k: 1 })
    expect(p.nodes[0].data.params).toEqual({ k: 1 })
    expect(doc.nodes[0].data.params).toEqual({})
    expect(moveNodeTo(doc, 'c', { x: 5, y: 6 }).nodes[2].position).toEqual({ x: 5, y: 6 })
    expect(addNodeTo(doc, node('d')).nodes).toHaveLength(4)
    const withEdge = connect(doc, edge('a', 'b'))
    expect(disconnect(withEdge, withEdge.edges[0].id).edges).toEqual([])
  })

  it('makes unique ids', () => {
    expect(uniqueId('x', new Set())).toBe('x')
    expect(uniqueId('x', new Set(['x', 'x_2']))).toBe('x_3')
  })
})
