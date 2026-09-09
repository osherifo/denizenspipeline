import { http, HttpResponse } from 'msw'
import type { PipelineDoc, PipelineRunDetail, PreprocNodeInfo } from '../../api/types'

export const NODE_LIBRARY: PreprocNodeInfo[] = [
  {
    name: 'derivatives_source', kind: 'source', version: '0.1.0', description: 'preprocessed BOLD from a derivatives dir',
    source: 'built-in', container_bound: false,
    inputs: { derivatives_dir: { kind: 'dir', required: true }, subject: { kind: 'str' } },
    outputs: { bold: { kind: 'nifti' }, confounds: { kind: 'tsv' } },
    required_python: [], required_tools: [], required_env: [], params_schema: { file_pattern: { type: 'str', default: '*_bold.nii.gz' } }, checks: [],
  },
  {
    name: 'smooth', kind: 'interface', version: '0.1.0', description: 'Gaussian smoothing', source: 'built-in', container_bound: false,
    inputs: { in_file: { kind: 'nifti', required: true } }, outputs: { out_file: { kind: 'nifti' } },
    required_python: [], required_tools: [], required_env: [], params_schema: { fwhm: { type: 'float', default: 5.0 } }, checks: [],
  },
  {
    name: 'fmriprep', kind: 'container_app', version: '0.2.0', description: 'fmriprep', source: 'built-in', container_bound: true,
    inputs: { bids_dir: { kind: 'dir', required: true }, subject: { kind: 'str', required: true }, output_dir: { kind: 'dir' } },
    outputs: { bold_preproc: { kind: 'nifti' }, confounds: { kind: 'tsv' }, manifest: { kind: 'json' } },
    required_python: [], required_tools: [], required_env: [],
    params_schema: { mode: { type: 'str', default: 'full', enum: ['full', 'anat_only'], group: 'Mode' }, nthreads: { type: 'int', default: null, group: 'Resources' } },
    checks: ['nu.mgz', 'T1.mgz'],
  },
]

export const TEMPLATE_PIPELINE: PipelineDoc = {
  schema_version: 1,
  name: 'derivatives_smooth',
  description: 'source → smooth',
  inputs: { derivatives_dir: { kind: 'dir' }, subject: { kind: 'str' } },
  nodes: [
    { id: 'source', type: 'derivatives_source', kind: 'source', data: { params: {}, bindings: { derivatives_dir: '$inputs.derivatives_dir', subject: '$inputs.subject' } }, position: { x: 0, y: 0 } },
    { id: 'smooth', type: 'smooth', kind: 'interface', data: { params: { fwhm: 5 }, iter: { handle: 'in_file' } }, position: { x: 300, y: 0 } },
  ],
  edges: [{ id: 'e1', source: 'source', target: 'smooth', sourceHandle: 'bold', targetHandle: 'in_file' }],
  manifest: { backend_node: 'source', bold_from: 'smooth.out_file' },
}

export function buildRunDetail(overrides: Partial<PipelineRunDetail> = {}): PipelineRunDetail {
  return {
    run_id: 'pp_abc', kind: 'preproc', backend: 'derivatives_source', subject: '01', status: 'running', pid: 1,
    started_at: 1_700_000_000, finished_at: 0, manifest_path: null, error: null, pipeline: 'derivatives_smooth',
    nodes: [{ id: 'source', type: 'derivatives_source', kind: 'source' }, { id: 'smooth', type: 'smooth', kind: 'interface' }],
    n_nodes: 2, work_dir: '/w', workflow: 'derivatives_smooth__sub_01', output_dir: '/o', use_cache: true, resumed_from: null,
    config_path: null, result: null, checkpoints: { n: 0, counts: {}, worst: null },
    nipype_status: { counts: { running: 0, ok: 0, failed: 0, completed_assumed: 0, total_seen: 0 }, recent_nodes: [] },
    job: { pipeline: TEMPLATE_PIPELINE, request: { subject: '01', output_dir: '/o' } },
    ...overrides,
  }
}

export const preprocPipelinesHandlers = [
  http.get('/api/preproc/nodes', () => HttpResponse.json({ nodes: NODE_LIBRARY, shadowed: [] })),
  http.get('/api/preproc/nodes/scaffold/:kind', ({ params }) => HttpResponse.json({ kind: params.kind, code: `@preproc_node("my_node") # ${params.kind}` })),
  http.get('/api/preproc/nodes/:name', ({ params }) => {
    const n = NODE_LIBRARY.find((x) => x.name === params.name)
    return n ? HttpResponse.json({ ...n, source_code: 'class X: pass', module: 'm' }) : new HttpResponse(null, { status: 404 })
  }),
  http.get('/api/preproc/nodes/:name/preflight', () => HttpResponse.json({ ok: true, errors: [], warnings: [] })),
  http.post('/api/preproc/nodes', () => HttpResponse.json({ saved: true, path: '/home/x/addons/nodes/my.py' })),
  http.post('/api/preproc/nodes/import', () => HttpResponse.json({ imported: true, node: 'imp', shape: 'build_function', path: '/p', inputs: ['a'], outputs: ['b'], warnings: [] })),
  http.post('/api/preproc/nodes/rescan', () => HttpResponse.json({ n_nodes: NODE_LIBRARY.length, shadowed: 0 })),

  http.get('/api/preproc/pipelines', () => HttpResponse.json({
    pipelines: [{ name: 'saved_one', path: '/c/saved_one.yaml', description: '', n_nodes: 2, node_types: ['derivatives_source', 'smooth'], inputs: {}, mtime: 0, error: null }],
    legacy: [{ name: 'old', path: '/c/old.yaml', hint: 'migrate' }],
    root: '/c',
  })),
  http.get('/api/preproc/pipelines/templates', () => HttpResponse.json({
    templates: [{ name: 'derivatives_smooth', description: 'source → smooth', n_nodes: 2, node_types: ['derivatives_source', 'smooth'], inputs: TEMPLATE_PIPELINE.inputs }],
  })),
  http.get('/api/preproc/pipelines/templates/:name', () => HttpResponse.json({ pipeline: TEMPLATE_PIPELINE })),
  http.post('/api/preproc/pipelines/validate', async ({ request }) => {
    const body = (await request.json()) as { pipeline: PipelineDoc }
    const bad = body.pipeline.edges.filter((e) => e.targetHandle === 'bogus').map((e) => `edge ${e.id}: target handle 'bogus' not in smooth.INPUTS`)
    return HttpResponse.json({ ok: bad.length === 0, errors: bad, is_linear: true })
  }),
  http.post('/api/preproc/pipelines/run', () => HttpResponse.json({ run_id: 'pp_new', status: 'running' })),
  http.get('/api/preproc/pipelines/:name', ({ params }) => HttpResponse.json({ name: params.name, pipeline: { ...TEMPLATE_PIPELINE, name: String(params.name) }, path: `/c/${params.name}.yaml` })),
  http.put('/api/preproc/pipelines/:name', ({ params }) => HttpResponse.json({ saved: true, name: params.name, path: `/c/${params.name}.yaml`, errors: [] })),
  http.delete('/api/preproc/pipelines/:name', () => HttpResponse.json({ deleted: true })),

  http.get('/api/preproc/runs', () => HttpResponse.json({ runs: [buildRunDetail()] })),
  http.get('/api/preproc/runs/:id', ({ params }) => HttpResponse.json(buildRunDetail({ run_id: String(params.id) }))),
  http.get('/api/preproc/runs/:id/checkpoints', () => HttpResponse.json({ checkpoints: [], summary: { n: 0, counts: {}, worst: null } })),
  http.get('/api/preproc/runs/:id/events', () => HttpResponse.json({ events: [], offset: 0 })),
  http.get('/api/preproc/runs/:id/log', () => HttpResponse.json({ lines: ['hello'], total: 1 })),
  http.post('/api/preproc/runs/:id/cancel', () => HttpResponse.json({ cancelled: true })),
  http.post('/api/preproc/runs/:id/resume', ({ params }) => HttpResponse.json({ run_id: 'pp_resumed', resumed_from: params.id })),
  http.post('/api/preproc/runs/:id/restart', ({ params }) => HttpResponse.json({ run_id: 'pp_restarted', restarted_from: params.id })),
  http.delete('/api/preproc/runs/:id', () => HttpResponse.json({ deleted: true })),
]
