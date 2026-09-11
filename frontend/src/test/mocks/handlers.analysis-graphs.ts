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
  nodeInfo('reporter:metrics', 'report', { context: port('Context', { required: true, multiple: true }) }, { artifacts: port('Artifacts') }, {}, 'isolate'),
]

export const PORT_TYPES: AnalysisPortType[] = [
  'any', 'StimulusData', 'ResponseData', 'FeatureSet', 'FeatureData', 'PreparedData', 'ModelResult', 'Context', 'Artifacts',
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

/** Request bodies the handlers received, for assertions. */
export const analysisRequests: { saved?: unknown; run?: unknown; validate?: unknown } = {}

export const analysisGraphsHandlers = [
  http.get('/api/analysis/nodes', () => HttpResponse.json({ nodes: ANALYSIS_NODES })),
  http.get('/api/analysis/port-types', () => HttpResponse.json({ types: PORT_TYPES })),
  http.get('/api/analysis/graphs/templates', () => HttpResponse.json({
    templates: [{ name: 'analyze', tier: 'bundled', description: 'test template', n_nodes: 2, node_types: ['preparer:default', 'model:bootstrap_ridge'], inputs: ANALYZE_GRAPH.inputs, scope: 'subject', error: null }],
  })),
  http.get('/api/analysis/graphs/templates/:name', ({ params }) => (
    String(params.name) === 'analyze'
      ? HttpResponse.json({ graph: ANALYZE_GRAPH })
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
