import { describe, expect, it } from 'vitest'
import { usePreprocPipelineStore, topoOrder } from '../preproc-pipeline-store'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
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

  it('loads a template into the editor', async () => {
    await usePreprocPipelineStore.getState().loadTemplate('derivatives_smooth')
    const st = usePreprocPipelineStore.getState()
    expect(st.pipeline.nodes).toHaveLength(2)
    expect(st.dirty).toBe(true)
    expect(st.selectedNodeId).toBe('source')
  })

  it('adds, wires, edits and removes nodes', async () => {
    const s = usePreprocPipelineStore.getState()
    await s.loadLibrary()
    await s.loadTemplate('derivatives_smooth')
    const id = usePreprocPipelineStore.getState().addNode('smooth')
    expect(id).toBe('smooth_2')
    usePreprocPipelineStore.getState().addEdge({ source: 'smooth', target: 'smooth_2', sourceHandle: 'out_file', targetHandle: 'in_file' })
    let st = usePreprocPipelineStore.getState()
    expect(st.pipeline.edges.some((e) => e.source === 'smooth' && e.target === 'smooth_2' && e.targetHandle === 'in_file')).toBe(true)
    expect(topoOrder(st.pipeline).map((n) => n.id)).toEqual(['source', 'smooth', 'smooth_2'])

    st.updateNodeParams('smooth_2', { fwhm: 8 })
    expect(usePreprocPipelineStore.getState().pipeline.nodes.find((n) => n.id === 'smooth_2')?.data.params).toEqual({ fwhm: 8 })

    // One feed per input port: a second edge into smooth_2.in_file replaces the first.
    st.addEdge({ source: 'source', target: 'smooth_2', sourceHandle: 'bold', targetHandle: 'in_file' })
    st = usePreprocPipelineStore.getState()
    expect(st.pipeline.edges.filter((e) => e.target === 'smooth_2')).toHaveLength(1)
    expect(st.pipeline.edges.find((e) => e.target === 'smooth_2')?.source).toBe('source')

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

  it('saves the run panel as run_defaults and restores it on load', async () => {
    let sent: { pipeline: { run_defaults?: Record<string, unknown> } } | null = null
    server.use(
      http.put('/api/preproc/pipelines/:name', async ({ request, params }) => {
        sent = (await request.json()) as typeof sent
        return HttpResponse.json({ saved: true, name: params.name, path: `/c/${params.name}.yaml`, errors: [] })
      }),
      http.get('/api/preproc/pipelines/:name', ({ params }) => HttpResponse.json({
        name: params.name, path: `/c/${params.name}.yaml`,
        pipeline: { ...TEMPLATE_PIPELINE, name: String(params.name), run_defaults: { subject: '07', output_dir: '/o', plugin: 'MultiProc', n_procs: 4, use_cache: false } },
      })),
    )
    const s = usePreprocPipelineStore.getState()
    await s.loadTemplate('derivatives_smooth')
    s.setBinding({ subject: '01', output_dir: '/out', bids_dir: '', work_dir: '/w', plugin: 'Linear', use_cache: true })
    await usePreprocPipelineStore.getState().save('mine')
    expect(sent!.pipeline.run_defaults).toEqual({ subject: '01', output_dir: '/out', work_dir: '/w', dataset: 'unknown', plugin: 'Linear', use_cache: true, abort_on_bad: false })

    await usePreprocPipelineStore.getState().loadPipeline('mine')
    const b = usePreprocPipelineStore.getState().binding
    expect(b.subject).toBe('07')
    expect(b.output_dir).toBe('/o')
    expect(b.plugin).toBe('MultiProc')
    expect(b.n_procs).toBe(4)
    expect(b.use_cache).toBe(false)
    expect(b.bids_dir).toBe('')
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

  it('saves the editor as a user template and lists it with its tier', async () => {
    const s = usePreprocPipelineStore.getState()
    await s.loadTemplate('derivatives_smooth')
    usePreprocPipelineStore.getState().updateNodeParams('smooth', { fwhm: 5, mask: '/data/mask.nii.gz' })
    const warnings = await usePreprocPipelineStore.getState().saveTemplate('my_smooth')
    expect(warnings).toEqual(['smooth.mask (param) holds a concrete path: /data/mask.nii.gz'])
    const st = usePreprocPipelineStore.getState()
    expect(st.templates.map((t) => [t.name, t.tier])).toEqual([['derivatives_smooth', 'bundled'], ['my_smooth', 'user']])
    // the editor is untouched: still an unsaved draft
    expect(st.pipelineName).toBeNull()

    await st.removeTemplate('my_smooth')
    expect(usePreprocPipelineStore.getState().templates.map((t) => t.name)).toEqual(['derivatives_smooth'])
  })

  it('refuses a bundled template name', async () => {
    const s = usePreprocPipelineStore.getState()
    await s.loadTemplate('derivatives_smooth')
    const warnings = await usePreprocPipelineStore.getState().saveTemplate('derivatives_smooth')
    expect(warnings).toBeNull()
    expect(usePreprocPipelineStore.getState().error).toMatch(/bundled template/)
  })
})
