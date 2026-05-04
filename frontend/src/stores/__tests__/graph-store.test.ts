import { describe, it, expect } from 'vitest'
import { useGraphStore, isValidConnection, graphToYaml, yamlToGraph, TEMPLATES } from '../graph-store'

describe('graph-store: connection rules', () => {
  it('allows matching handle types', () => {
    const conn = {
      source: 'a',
      target: 'b',
      sourceHandle: 'output-bids',
      targetHandle: 'input-bids',
    }
    expect(isValidConnection(conn, [])).toBe(true)
  })

  it('rejects mismatched handle types', () => {
    const conn = {
      source: 'a',
      target: 'b',
      sourceHandle: 'output-bids',
      targetHandle: 'input-features',
    }
    expect(isValidConnection(conn, [])).toBe(false)
  })

  it('rejects self-connections', () => {
    const conn = {
      source: 'a',
      target: 'a',
      sourceHandle: 'output-bids',
      targetHandle: 'input-bids',
    }
    expect(isValidConnection(conn, [])).toBe(false)
  })

  it('rejects missing handles', () => {
    expect(isValidConnection({ source: 'a', target: 'b', sourceHandle: null, targetHandle: 'x' }, [])).toBe(
      false,
    )
  })

  it('bold output may target manifest', () => {
    expect(
      isValidConnection(
        { source: 'a', target: 'b', sourceHandle: 'output-bold', targetHandle: 'input-manifest' },
        [],
      ),
    ).toBe(true)
  })
})

describe('graph-store: YAML round-trip', () => {
  it('exports a template graph and re-imports identical structure', () => {
    const t = TEMPLATES[0].build()
    const yaml = graphToYaml(t.nodes, t.edges, 'demo')
    const back = yamlToGraph(yaml)
    expect(back.nodes.map((n) => n.id).sort()).toEqual(t.nodes.map((n) => n.id).sort())
    expect(back.edges.length).toBe(t.edges.length)
    expect(back.workflow).toBe('demo')
  })

  it('yamlToGraph throws on invalid root', () => {
    expect(() => yamlToGraph('- a\n- b')).toThrow()
  })

  it('yamlToGraph throws when nodes mapping missing', () => {
    expect(() => yamlToGraph('foo: bar')).toThrow(/nodes/)
  })
})

describe('useGraphStore', () => {
  it('initial state is empty', () => {
    const s = useGraphStore.getState()
    expect(s.nodes).toEqual([])
    expect(s.edges).toEqual([])
    expect(s.selectedNodeId).toBeNull()
  })

  it('loadTemplate populates graph', () => {
    useGraphStore.getState().loadTemplate('Full Pipeline')
    expect(useGraphStore.getState().nodes.length).toBeGreaterThan(0)
  })

  it('selectNode opens detail panel', () => {
    useGraphStore.getState().loadTemplate('Full Pipeline')
    const id = useGraphStore.getState().nodes[0].id
    useGraphStore.getState().selectNode(id)
    expect(useGraphStore.getState().selectedNodeId).toBe(id)
    expect(useGraphStore.getState().detailOpen).toBe(true)
  })

  it('closeDetail clears selection', () => {
    useGraphStore.getState().loadTemplate('Full Pipeline')
    useGraphStore.getState().selectNode('source')
    useGraphStore.getState().closeDetail()
    expect(useGraphStore.getState().selectedNodeId).toBeNull()
    expect(useGraphStore.getState().detailOpen).toBe(false)
  })

  it('updateNodeConfig applies config', () => {
    useGraphStore.getState().loadTemplate('Full Pipeline')
    useGraphStore.getState().updateNodeConfig('source', { path: '/new/path' })
    const node = useGraphStore.getState().nodes.find((n) => n.id === 'source')!
    expect((node.data as any).config.path).toBe('/new/path')
  })

  it('addNode appends a new node', () => {
    const before = useGraphStore.getState().nodes.length
    useGraphStore.getState().addNode('features', 'Extra Features')
    expect(useGraphStore.getState().nodes.length).toBe(before + 1)
  })

  it('removeNode also removes connected edges', () => {
    useGraphStore.getState().loadTemplate('Full Pipeline')
    const before = useGraphStore.getState().edges.length
    useGraphStore.getState().removeNode('preproc')
    expect(useGraphStore.getState().nodes.find((n) => n.id === 'preproc')).toBeUndefined()
    expect(useGraphStore.getState().edges.length).toBeLessThan(before)
  })

  it('setYamlDirect enters yaml editing mode', () => {
    useGraphStore.getState().setYamlDirect('nodes: {}')
    expect(useGraphStore.getState().yamlEditing).toBe(true)
  })

  it('applyYaml commits parsed graph', () => {
    useGraphStore.getState().loadTemplate('Analysis Only')
    const yaml = graphToYaml(useGraphStore.getState().nodes, useGraphStore.getState().edges, 'demo')
    useGraphStore.getState().setYamlDirect(yaml)
    useGraphStore.getState().applyYaml()
    expect(useGraphStore.getState().yamlErrors).toEqual([])
    expect(useGraphStore.getState().yamlEditing).toBe(false)
  })

  it('applyYaml records yamlErrors on bad yaml', () => {
    useGraphStore.getState().setYamlDirect('NOT VALID YAML: : :')
    useGraphStore.getState().applyYaml()
    expect(useGraphStore.getState().yamlErrors.length).toBeGreaterThan(0)
  })
})
