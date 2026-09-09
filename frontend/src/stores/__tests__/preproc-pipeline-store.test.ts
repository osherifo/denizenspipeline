import { describe, expect, it } from 'vitest'
import { usePreprocPipelineStore, isLinear, topoOrder } from '../preproc-pipeline-store'
import { TEMPLATE_PIPELINE } from '../../test/mocks/handlers.preproc-pipelines'

describe('preproc pipeline store', () => {
  it('loads the library, templates and saved pipelines', async () => {
    const s = usePreprocPipelineStore.getState()
    await Promise.all([s.loadLibrary(), s.loadTemplates(), s.loadPipelines()])
    const st = usePreprocPipelineStore.getState()
    expect(st.library.map((n) => n.name)).toEqual(['derivatives_source', 'smooth', 'fmriprep'])
    expect(st.templates[0].name).toBe('derivatives_smooth')
    expect(st.pipelines[0].name).toBe('saved_one')
    expect(st.legacy).toHaveLength(1)
  })

  it('loads a template into the editor and picks the simple view for a chain', async () => {
    await usePreprocPipelineStore.getState().loadTemplate('derivatives_smooth')
    const st = usePreprocPipelineStore.getState()
    expect(st.pipeline.nodes).toHaveLength(2)
    expect(st.view).toBe('simple')
    expect(st.dirty).toBe(true)
    expect(st.selectedNodeId).toBe('source')
  })

  it('adds, wires, edits and removes nodes', async () => {
    const s = usePreprocPipelineStore.getState()
    await s.loadLibrary()
    await s.loadTemplate('derivatives_smooth')
    const id = usePreprocPipelineStore.getState().appendAfter('smooth', 'smooth')
    expect(id).toBe('smooth_2')
    let st = usePreprocPipelineStore.getState()
    expect(st.pipeline.edges.some((e) => e.source === 'smooth' && e.target === 'smooth_2' && e.targetHandle === 'in_file')).toBe(true)
    expect(isLinear(st.pipeline)).toBe(true)
    expect(topoOrder(st.pipeline).map((n) => n.id)).toEqual(['source', 'smooth', 'smooth_2'])

    st.updateNodeParams('smooth_2', { fwhm: 8 })
    expect(usePreprocPipelineStore.getState().pipeline.nodes.find((n) => n.id === 'smooth_2')?.data.params).toEqual({ fwhm: 8 })

    // One feed per input port: a second edge into smooth_2.in_file replaces the first.
    st.addEdge({ source: 'source', target: 'smooth_2', sourceHandle: 'bold', targetHandle: 'in_file' })
    st = usePreprocPipelineStore.getState()
    expect(st.pipeline.edges.filter((e) => e.target === 'smooth_2')).toHaveLength(1)
    expect(st.pipeline.edges.find((e) => e.target === 'smooth_2')?.source).toBe('source')
    expect(isLinear(st.pipeline)).toBe(false)

    st.removeNode('smooth_2')
    st = usePreprocPipelineStore.getState()
    expect(st.pipeline.nodes.map((n) => n.id)).toEqual(['source', 'smooth'])
    expect(st.pipeline.edges).toHaveLength(1)
  })

  it('removing the backend node clears its manifest role', async () => {
    await usePreprocPipelineStore.getState().loadTemplate('derivatives_smooth')
    usePreprocPipelineStore.getState().removeNode('source')
    expect(usePreprocPipelineStore.getState().pipeline.manifest.backend_node).toBeUndefined()
  })

  it('validates against the server and reports errors', async () => {
    const s = usePreprocPipelineStore.getState()
    s.setPipeline({ ...TEMPLATE_PIPELINE, edges: [{ ...TEMPLATE_PIPELINE.edges[0], targetHandle: 'bogus' }] })
    await usePreprocPipelineStore.getState().validate()
    const v = usePreprocPipelineStore.getState().validation
    expect(v?.ok).toBe(false)
    expect(v?.errors[0]).toMatch(/bogus/)
  })

  it('saves under a name and launches with the binding', async () => {
    const s = usePreprocPipelineStore.getState()
    await s.loadTemplate('derivatives_smooth')
    await usePreprocPipelineStore.getState().save('mine')
    expect(usePreprocPipelineStore.getState().pipelineName).toBe('mine')
    expect(usePreprocPipelineStore.getState().dirty).toBe(false)
    usePreprocPipelineStore.getState().setBinding({ subject: '01', output_dir: '/out', derivatives_dir: '/d' })
    const runId = await usePreprocPipelineStore.getState().launch()
    expect(runId).toBe('pp_new')
    expect(usePreprocPipelineStore.getState().lastRunId).toBe('pp_new')
  })
})
