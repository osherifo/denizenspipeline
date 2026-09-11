import { http, HttpResponse } from 'msw'
import type { AnalysisGraphDoc, AnalysisNodeInfo, AnalysisPortSpec, AnalysisPortType, ParamSchema } from '../../api/types'

const port = (type: string, extra: Partial<AnalysisPortSpec> = {}): AnalysisPortSpec => ({ type, ...extra })

function nodeInfo(
  type: string, stage: string, inputs: Record<string, AnalysisPortSpec>, outputs: Record<string, AnalysisPortSpec>,
  params_schema: ParamSchema = {}, error_policy = 'fail',
): AnalysisNodeInfo {
  const [category, module] = type.split(':')
  return {
    type, category, module, stage, description: `${module} node`, full_description: '', inputs, outputs,
    params_schema, error_policy, source: null, native: false, hidden: false, qa_stage: null, extra: {},
  }
}

export const ANALYSIS_NODES: AnalysisNodeInfo[] = [
  nodeInfo('stimulus_loader:skip', 'stimuli', {}, { stimuli: port('StimulusData') }),
  nodeInfo('response_loader:local', 'responses', {}, { responses: port('ResponseData') }, { path: { type: 'path', description: 'response file' } }),
  nodeInfo('feature_source:filesystem', 'features', { stimuli: port('StimulusData'), responses: port('ResponseData') }, { feature: port('FeatureSet') }),
  nodeInfo('utility:bundle_features', 'features', { features: port('FeatureSet', { required: true, multiple: true }) }, { features: port('FeatureData') }),
  nodeInfo('preparer:default', 'prepare', { responses: port('ResponseData', { required: true }), features: port('FeatureData', { required: true }) }, { prepared: port('PreparedData') }, { delays: { type: 'list[int]', default: [1, 2, 3, 4] } }),
  nodeInfo('model:bootstrap_ridge', 'model', { prepared: port('PreparedData', { required: true }) }, { result: port('ModelResult') }, { n_boots: { type: 'int', default: 50 } }),
  nodeInfo('model:himalaya_ridge', 'model', { prepared: port('PreparedData', { required: true }) }, { result: port('ModelResult') }, { alphas: { type: 'string', default: 'logspace(1,3,20)' } }),
  nodeInfo('feature_extractor:numwords', 'features', { stimuli: port('StimulusData', { required: true }), responses: port('ResponseData') }, { feature: port('FeatureSet') }, { feature_name: { type: 'string' } }),
  nodeInfo('reporter:metrics', 'report', { context: port('Context', { required: true, multiple: true }) }, { artifacts: port('Artifacts') }, {}, 'isolate'),
  nodeInfo('control:map_subjects', 'subject_fanout', {}, { group: port('GroupRun') }, {
    subjects: { type: 'list[string]', required: true }, body: { type: 'string' }, inputs: { type: 'dict' },
    subject_inputs: { type: 'dict' }, subject_template: { type: 'dict' }, subject_overrides: { type: 'dict' },
    max_workers: { type: 'int', default: 4 },
  }),
  nodeInfo('group_analyzer:voxelwise_mean', 'group_analyze', { group: port('GroupRun', { required: true }) }, { group: port('GroupRun') }),
  nodeInfo('group_reporter:group_summary_html', 'group_report', { group: port('GroupRun', { required: true }) }, { artifacts: port('Artifacts') }),
]

export const PORT_TYPES: AnalysisPortType[] = [
  'any', 'StimulusData', 'ResponseData', 'FeatureSet', 'FeatureData', 'PreparedData', 'ModelResult', 'Context', 'Artifacts',
  'GroupRun', 'StudyRun',
].map((name) => ({ name, parents: [], description: '' }))

export const ANALYZE_GRAPH: AnalysisGraphDoc = {
  schema_version: 1,
  name: 'analyze',
  description: 'test template',
  scope: 'subject',
  inputs: { subject: { kind: 'str' }, output_dir: { kind: 'dir' }, test_runs: { kind: 'list', required: false, default: ['run1'] } },
  globals: { subject: '$inputs.subject', reporting: { output_dir: '$inputs.output_dir' } },
  nodes: [
    { id: 'prepare', type: 'preparer:default', data: { params: {} }, position: { x: 0, y: 0 } },
    { id: 'bootstrap_ridge', type: 'model:bootstrap_ridge', data: { params: { n_boots: 5 } }, position: { x: 300, y: 0 } },
  ],
  edges: [{ id: 'e1', source: 'prepare', target: 'bootstrap_ridge', sourceHandle: 'prepared', targetHandle: 'prepared' }],
}

export const GROUP_GRAPH: AnalysisGraphDoc = {
  schema_version: 1,
  name: 'group_mean',
  description: 'test group template',
  scope: 'group',
  inputs: { subjects: { kind: 'list' }, output_dir: { kind: 'dir' } },
  globals: { group: 'g', output_dir: '$inputs.output_dir' },
  nodes: [
    { id: 'subjects', type: 'control:map_subjects', data: { params: { subjects: ['S1', 'S2'], body: 'analyze', inputs: { output_dir: '/data/{subject}' } } }, position: { x: 0, y: 0 } },
    { id: 'mean', type: 'group_analyzer:voxelwise_mean', data: { params: {} }, position: { x: 300, y: 0 } },
  ],
  edges: [{ id: 'e1', source: 'subjects', target: 'mean', sourceHandle: 'group', targetHandle: 'group' }],
}

/** Request bodies the handlers received, for assertions. */
export const analysisRequests: { saved?: unknown; run?: unknown; validate?: unknown } = {}

export const analysisGraphsHandlers = [
  http.get('/api/analysis/nodes', () => HttpResponse.json({ nodes: ANALYSIS_NODES })),
  http.get('/api/analysis/port-types', () => HttpResponse.json({ types: PORT_TYPES })),
  http.get('/api/analysis/graphs/templates', () => HttpResponse.json({
    templates: [
      { name: 'analyze', tier: 'bundled', description: 'test template', n_nodes: 2, node_types: ['preparer:default', 'model:bootstrap_ridge'], inputs: ANALYZE_GRAPH.inputs, scope: 'subject', error: null },
      { name: 'group_mean', tier: 'bundled', description: 'test group template', n_nodes: 2, node_types: ['control:map_subjects', 'group_analyzer:voxelwise_mean'], inputs: GROUP_GRAPH.inputs, scope: 'group', error: null },
    ],
  })),
  http.get('/api/analysis/graphs/templates/:name', ({ params }) => (
    String(params.name) === 'analyze' ? HttpResponse.json({ graph: ANALYZE_GRAPH })
      : String(params.name) === 'group_mean' ? HttpResponse.json({ graph: GROUP_GRAPH })
        : HttpResponse.json({ detail: 'unknown template' }, { status: 404 })
  )),
  http.post('/api/analysis/graphs/templates', async ({ request }) => {
    const body = await request.json() as { name: string }
    return HttpResponse.json({ saved: true, name: body.name, tier: 'user', path: `/tmp/${body.name}.yaml`, warnings: [], errors: [] })
  }),
  http.delete('/api/analysis/graphs/templates/:name', () => HttpResponse.json({ deleted: true })),
  http.post('/api/analysis/graphs/validate', async ({ request }) => {
    const body = await request.json() as { inputs?: Record<string, unknown> }
    analysisRequests.validate = body
    const errors = body.inputs?.subject ? [] : ["graph input 'subject' needs a value"]
    return HttpResponse.json({ ok: errors.length === 0, errors })
  }),
  http.post('/api/analysis/graphs/compile', () => HttpResponse.json({ graph: { ...ANALYZE_GRAPH, name: 'compiled' } })),
  http.post('/api/analysis/graphs/run', async ({ request }) => {
    analysisRequests.run = await request.json()
    return HttpResponse.json({ run_id: 'graph-run-1', status: 'started' })
  }),
  http.get('/api/analysis/graphs', () => HttpResponse.json({
    graphs: [{ name: 'saved_graph', path: '/tmp/saved_graph.yaml', scope: 'subject', description: '', n_nodes: 2, node_types: ['preparer:default', 'model:bootstrap_ridge'], inputs: {}, error: null }],
    root: '/tmp',
  })),
  http.get('/api/analysis/graphs/:name', ({ params }) => HttpResponse.json({
    name: String(params.name), graph: { ...ANALYZE_GRAPH, run_defaults: { inputs: { subject: 'sub01' } } }, path: `/tmp/${String(params.name)}.yaml`,
  })),
  http.put('/api/analysis/graphs/:name', async ({ request, params }) => {
    analysisRequests.saved = await request.json()
    return HttpResponse.json({ saved: true, name: String(params.name), path: `/tmp/${String(params.name)}.yaml`, errors: [] })
  }),
  http.delete('/api/analysis/graphs/:name', () => HttpResponse.json({ deleted: true })),
]
