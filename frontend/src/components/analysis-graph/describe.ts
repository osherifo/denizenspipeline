/** How an analysis node looks on the canvas: a category tag and colour, ports coloured by type, run status. */
import type { AnalysisNodeInfo, AnalysisPortSpec } from '../../api/types'
import type { GraphBadge, GraphNodeCardData, NodeRunStatus } from '../graph/GraphNodeCard'

export const CATEGORY_ORDER = [
  'stimulus_loader', 'response_loader', 'feature_extractor', 'feature_source', 'utility', 'preparer', 'model',
  'analyzer', 'reporter', 'qa_reporter', 'group_analyzer', 'group_reporter', 'study_analyzer', 'study_reporter',
]

export const CATEGORY_COLORS: Record<string, string> = {
  stimulus_loader: '#f59e0b', response_loader: '#f97316', feature_extractor: '#10b981', feature_source: '#14b8a6',
  utility: '#9ca3af', preparer: '#3b82f6', model: '#8b5cf6', analyzer: '#ec4899', reporter: '#06b6d4',
  qa_reporter: '#64748b', group_analyzer: '#e11d48', group_reporter: '#0891b2', study_analyzer: '#be123c',
  study_reporter: '#0e7490', control: '#eab308',
}

/** Short tag on the node card. */
export const CATEGORY_LABELS: Record<string, string> = {
  stimulus_loader: 'stimuli', response_loader: 'responses', feature_extractor: 'extract', feature_source: 'features',
  utility: 'utility', preparer: 'prepare', model: 'model', analyzer: 'analyze', reporter: 'report', qa_reporter: 'qa',
  group_analyzer: 'group', group_reporter: 'group report', study_analyzer: 'study', study_reporter: 'study report',
  control: 'control',
}

/** Group heading in the palette. */
export const CATEGORY_GROUPS: Record<string, string> = {
  stimulus_loader: 'stimulus loaders', response_loader: 'response loaders', feature_extractor: 'feature extractors',
  feature_source: 'feature sources', utility: 'utilities', preparer: 'preparers', model: 'models', analyzer: 'analyzers',
  reporter: 'reporters', qa_reporter: 'QA reporters', group_analyzer: 'group analyzers', group_reporter: 'group reporters',
  study_analyzer: 'study analyzers', study_reporter: 'study reporters', control: 'fan-out',
}

export const PORT_TYPE_COLORS: Record<string, string> = {
  StimulusData: '#f59e0b', ResponseData: '#f97316', FeatureSet: '#10b981', FeatureData: '#14b8a6',
  PreparedData: '#3b82f6', ModelResult: '#8b5cf6', Context: '#ec4899', Artifacts: '#06b6d4', Array: '#a3a3a3',
  VariancePartition: '#d946ef', WeightAnalysis: '#a855f7', SemanticSubspace: '#6366f1',
  SubjectRun: '#84cc16', GroupRun: '#22c55e', StudyRun: '#15803d',
}

/** The catalog node type of a module as listed by /api/modules, whose categories are plural. */
export function nodeTypeForModule(module: { category: string; name: string; stage?: string }): string {
  const category = module.category.replace(/s$/, '')
  return category === 'qa_reporter' ? `qa_reporter:${module.stage}.${module.name}` : `${category}:${module.name}`
}

/** Default node id for a node type: the module name (``model:bootstrap_ridge`` → ``bootstrap_ridge``). */
export function nodeIdFor(type: string): string {
  const tail = type.includes(':') ? type.slice(type.indexOf(':') + 1) : type
  return tail.includes('.') ? tail.slice(tail.lastIndexOf('.') + 1) : tail
}

export function categoryOf(type: string): string {
  return type.includes(':') ? type.slice(0, type.indexOf(':')) : type
}

export function portTitle(spec: AnalysisPortSpec): string {
  const parts = [spec.type ?? 'any']
  if (spec.required) parts.push('required')
  if (spec.multiple) parts.push('takes several connections, in order')
  if (spec.description) parts.push(spec.description)
  return parts.join(' · ')
}

export function describeAnalysisNode(
  catalog: Map<string, AnalysisNodeInfo>,
  statusByNode: Record<string, NodeRunStatus> = {},
): (node: { id: string; type: string }) => GraphNodeCardData {
  return (node) => {
    const info = catalog.get(node.type)
    const category = categoryOf(node.type)
    const st = statusByNode[node.id]
    const badges: GraphBadge[] = []
    if (!info) badges.push({ key: 'unknown', content: '?', title: `unknown node type ${node.type}`, color: '#ef4444' })
    else if (info.error_policy === 'isolate') badges.push({ key: 'isolate', content: '◇', title: 'a failure here is recorded and the run continues' })
    if (st?.error) badges.push({ key: 'error', content: '!', title: st.error, color: '#ef4444' })
    const ports = (specs: Record<string, AnalysisPortSpec> | undefined) => Object.entries(specs ?? {}).map(([name, spec]) => ({
      name, color: PORT_TYPE_COLORS[spec.type ?? 'any'], title: portTitle(spec),
    }))
    return {
      label: node.id,
      title: node.type,
      tag: CATEGORY_LABELS[category] ?? category,
      tagColor: CATEGORY_COLORS[category] ?? '#9ca3af',
      inputs: ports(info?.inputs),
      outputs: ports(info?.outputs),
      status: st?.status ?? null,
      durationS: st?.durationS ?? null,
      badges,
    }
  }
}
