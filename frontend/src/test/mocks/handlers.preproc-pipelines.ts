import { http, HttpResponse } from 'msw'
import type { MetricInfo, NodeUiCapabilities, PipelineDoc, PipelineRunDetail, PipelineTemplateSummary, PreprocNodeInfo, RunNodeRecord } from '../../api/types'

const NO_UI: NodeUiCapabilities = { inner_dag: false, checkpoints: false, log: false, report: null, structural_qc: null, summary: null, label_map: null, views: [] }

export const NODE_LIBRARY: PreprocNodeInfo[] = [
  {
    name: 'derivatives_source', kind: 'source', version: '0.1.0', description: 'preprocessed BOLD from a derivatives dir',
    source: 'built-in', container_bound: false,
    inputs: { derivatives_dir: { kind: 'dir', required: true }, subject: { kind: 'str' } },
    outputs: { bold: { kind: 'nifti' }, confounds: { kind: 'tsv' } },
    required_python: [], required_tools: [], required_env: [], params_schema: { file_pattern: { type: 'str', default: '*_bold.nii.gz' } }, checks: [], ui: NO_UI,
  },
  {
    name: 'smooth', kind: 'interface', version: '0.1.0', description: 'Gaussian smoothing', source: 'built-in', container_bound: false,
    inputs: { in_file: { kind: 'nifti', required: true } }, outputs: { out_file: { kind: 'nifti' } },
    required_python: [], required_tools: [], required_env: [], params_schema: { fwhm: { type: 'float', default: 5.0 } }, checks: [], ui: NO_UI,
  },
  {
    name: 'fmriprep', kind: 'container_app', version: '0.2.0', description: 'fmriprep', source: 'built-in', container_bound: true,
    inputs: { bids_dir: { kind: 'dir', required: true }, subject: { kind: 'str', required: true }, output_dir: { kind: 'dir' } },
    outputs: { bold_preproc: { kind: 'nifti' }, confounds: { kind: 'tsv' }, manifest: { kind: 'json' }, report_html: { kind: 'html' }, fs_subjects_dir: { kind: 'dir' } },
    required_python: [], required_tools: [], required_env: [],
    params_schema: { mode: { type: 'str', default: 'full', enum: ['full', 'anat_only'], group: 'Mode' }, nthreads: { type: 'int', default: null, group: 'Resources' } },
    checks: ['nu.mgz', 'T1.mgz'],
    ui: { inner_dag: true, checkpoints: true, log: true, report: 'report_html', structural_qc: 'fs_subjects_dir', summary: 'manifest', label_map: 'fmriprep', views: [] },
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
    errors: [], cause: null, crashes: [],
    nipype_status: { counts: { running: 0, ok: 0, failed: 0, completed_assumed: 0, total_seen: 0 }, recent_nodes: [] },
    job: { pipeline: TEMPLATE_PIPELINE, request: { subject: '01', output_dir: '/o' } },
    ...overrides,
  }
}

export function buildRunNode(overrides: Partial<RunNodeRecord> = {}): RunNodeRecord {
  return {
    run_id: 'pp_abc', node_id: 'smooth', node_type: 'smooth', kind: 'interface', status: 'ok', duration_s: 3, work_dir: '/w/derivatives_smooth__sub_01/smooth',
    outputs: { out_file: '/o/x.nii.gz' }, error: null, params: { fwhm: 5 }, ui: NO_UI, output_ports: { out_file: { kind: 'nifti' } },
    params_schema: { fwhm: { type: 'float', default: 5.0 } }, has_log: false, subject: '01', dataset: 'ds', workflow: 'derivatives_smooth__sub_01', run_status: 'done',
    ...overrides,
  }
}

export const FMRIPREP_RUN_NODE: RunNodeRecord = buildRunNode({
  node_id: 'fp', node_type: 'fmriprep', kind: 'container_app', has_log: true,
  outputs: { derivatives_dir: '/o', report_html: '/o/sub-01.html', fs_subjects_dir: '/o/sourcedata/freesurfer', manifest: '/w/fp/preproc_manifest.json' },
  params: { mode: 'anat_only' }, params_schema: NODE_LIBRARY[2].params_schema, output_ports: NODE_LIBRARY[2].outputs, ui: NODE_LIBRARY[2].ui,
})

/** User-tier templates, mutated by the POST/DELETE template handlers below. */
export const userTemplates: PipelineTemplateSummary[] = []

const BUILTIN_METRICS: MetricInfo[] = [
  { name: 'nifti_stats', description: 'Shape, non-zero fraction, percentiles of any NIfTI', builtin: true, tier: 'builtin' },
  { name: 'volume_intensity', description: 'n_unique, modal fraction', builtin: true, tier: 'builtin' },
]
/** User metrics by name → code; mutated by the PUT/DELETE metric handlers. */
export const userMetricCode: Record<string, string> = {}
const allMetrics = (): MetricInfo[] => [
  ...BUILTIN_METRICS,
  ...Object.keys(userMetricCode).map((name) => ({ name, description: 'user metric', builtin: false, tier: 'user' as const, path: `/home/x/addons/checks/${name}.py` })),
]

export const preprocPipelinesHandlers = [
  http.get('/api/preproc/checks/metrics', () => HttpResponse.json({ metrics: allMetrics(), addons_dir: '/home/x/addons/checks' })),
  http.get('/api/preproc/checks/metrics/scaffold', () => HttpResponse.json({ code: '@checkpoint_metric("my_metric")\ndef my_metric(path): ...' })),
  http.get('/api/preproc/checks/metrics/:name', ({ params }) => {
    const m = allMetrics().find((x) => x.name === params.name)
    if (!m) return HttpResponse.json({ detail: 'unknown' }, { status: 404 })
    return HttpResponse.json({ ...m, source: userMetricCode[m.name] ?? `@checkpoint_metric("${m.name}")\ndef ${m.name}_metrics(path):\n    return {}, {}\n` })
  }),
  http.put('/api/preproc/checks/metrics/:name', async ({ params, request }) => {
    const { code } = (await request.json()) as { code: string }
    const name = String(params.name)
    if (BUILTIN_METRICS.some((m) => m.name === name)) return HttpResponse.json({ detail: `'${name}' is a built-in metric; duplicate it under another name` }, { status: 400 })
    if (!code.includes(`checkpoint_metric("${name}")`)) return HttpResponse.json({ detail: `the code must register @checkpoint_metric('${name}')` }, { status: 400 })
    userMetricCode[name] = code
    return HttpResponse.json({ saved: true, name, path: `/home/x/addons/checks/${name}.py`, metrics: allMetrics() })
  }),
  http.delete('/api/preproc/checks/metrics/:name', ({ params }) => {
    const name = String(params.name)
    if (!(name in userMetricCode)) return HttpResponse.json({ detail: 'no user metric' }, { status: 404 })
    delete userMetricCode[name]
    return HttpResponse.json({ deleted: true, metrics: allMetrics() })
  }),
  http.post('/api/preproc/checks/metrics/:name/run', async ({ params, request }) => {
    const { path } = (await request.json()) as { path: string }
    return HttpResponse.json({ name: params.name, path, ok: !path.includes('missing'), metrics: { size_bytes: 5 }, detail: {}, error: path.includes('missing') ? 'no such file' : undefined })
  }),
  http.get('/api/preproc/checks/norms', () => HttpResponse.json({ path: '/home/x/configs/norms.yaml', user: {}, rows: [
    { step: 'nu.mgz', kind: 'hard', metric: 'n_unique', op: '>', value: 100, source: 'builtin', builtin: ['>', 100] },
    { step: 'wm.mgz', kind: 'hard', metric: 'wm_volume_cm3', op: 'between', value: [200, 1000], source: 'user', builtin: ['between', [250, 900]] },
  ] })),
  http.put('/api/preproc/checks/norms', async ({ request }) => {
    const b = (await request.json()) as { norms: Record<string, unknown> }
    return HttpResponse.json({ saved: true, rows: Object.keys(b.norms).map((step) => ({ step, kind: 'hard', metric: 'x', op: '>', value: 1, source: 'user', builtin: null })) })
  }),
  http.get('/api/preproc/nodes/:name/checks', ({ params }) => HttpResponse.json({ checks: params.name === 'fmriprep'
    ? [{ step: 'nu.mgz', artifact: '{fs_subject_dir}/mri/nu.mgz', metric: 'volume_intensity', norms_key: null, live: true, thumbnail: 'volume' }]
    : [] })),
  http.post('/api/preproc/checks/evaluate', async ({ request }) => {
    const b = (await request.json()) as { check: { step: string; artifact: string } }
    return HttpResponse.json({ artifact: '/o/x.nii.gz', exists: true, context: {}, checkpoint: { stage: 'preproc', run_id: 'pp_abc', node: 'smooth', step: b.check.step, subject: '01', metrics: { n_trs: 6 }, expectations: {}, soft_expectations: {}, verdict: 'bad', thumbnail: null, detail: {}, t: 0, artifact: '/o/x.nii.gz', reasons: ['n_trs=6 violates > 10'] } })
  }),
  http.get('/api/preproc/runs/:id/nodes/:node/log', () => HttpResponse.json({ lines: ['a', 'b'], total: 2 })),
  http.get('/api/preproc/runs/:id/nodes/:node/inner', () => HttpResponse.json({ prefix: 'p.fp.', nipype_status: { counts: { running: 0, ok: 1, failed: 0, completed_assumed: 0, total_seen: 1 }, recent_nodes: [{ node: 'fmriprep_wf.a.n1', leaf: 'n1', workflow: 'fmriprep_wf.a', status: 'ok', started_at: 1, finished_at: 2, elapsed: 1, crash_file: null, level: 'INFO' }] } })),
  http.get('/api/preproc/runs/:id/nodes/:node/manifest', () => HttpResponse.json({ subject: '01', dataset: 'ds', backend: 'fmriprep', backend_version: '24.1.1', space: 'T1w', resolution: '', output_format: 'nifti', runs: [], confounds_applied: [], created: '2026-01-01T00:00:00Z', output_dir: '/o', sessions: [], additional_steps: [], freesurfer_subjects_dir: null })),
  http.get('/api/preproc/runs/:id/nodes/:node', ({ params }) => HttpResponse.json(params.node === 'fp' ? FMRIPREP_RUN_NODE : buildRunNode({ node_id: String(params.node), run_id: String(params.id) }))),

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
    templates: [
      { name: 'derivatives_smooth', tier: 'bundled', description: 'source → smooth', n_nodes: 2, node_types: ['derivatives_source', 'smooth'], inputs: TEMPLATE_PIPELINE.inputs },
      ...userTemplates,
    ],
  })),
  http.get('/api/preproc/pipelines/templates/:name', () => HttpResponse.json({ pipeline: TEMPLATE_PIPELINE })),
  http.post('/api/preproc/pipelines/templates', async ({ request }) => {
    const body = (await request.json()) as { name: string; pipeline: PipelineDoc }
    if (body.name === 'derivatives_smooth') return HttpResponse.json({ detail: `'${body.name}' is a bundled template; pick another name` }, { status: 400 })
    const warnings = body.pipeline.nodes.flatMap((n) => Object.entries(n.data.params)
      .filter(([, v]) => typeof v === 'string' && v.startsWith('/'))
      .map(([k, v]) => `${n.id}.${k} (param) holds a concrete path: ${v}`))
    const idx = userTemplates.findIndex((t) => t.name === body.name)
    const row: PipelineTemplateSummary = { name: body.name, tier: 'user', description: body.pipeline.description ?? '', n_nodes: body.pipeline.nodes.length, node_types: body.pipeline.nodes.map((n) => n.type), inputs: body.pipeline.inputs, error: null }
    if (idx >= 0) userTemplates[idx] = row; else userTemplates.push(row)
    return HttpResponse.json({ saved: true, name: body.name, tier: 'user', path: `/home/x/addons/pipelines/${body.name}.yaml`, warnings, errors: [] })
  }),
  http.delete('/api/preproc/pipelines/templates/:name', ({ params }) => {
    const idx = userTemplates.findIndex((t) => t.name === params.name)
    if (idx < 0) return HttpResponse.json({ detail: 'no user template' }, { status: 404 })
    userTemplates.splice(idx, 1)
    return HttpResponse.json({ deleted: true })
  }),
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
