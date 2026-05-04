import type {
  ModuleInfo,
  ModuleMetadata,
  StageInfo,
  PipelineConfig,
  RunSummary,
  RunEvent,
  ConfigSummary,
  ConfigDetail,
  UserModule,
  CodeValidationResult,
  ManifestSummary,
  PreprocRunSummary,
  AutoflattenRunSummary,
  ConvertRunSummary,
} from '../api/types'

let _id = 0
const nextId = (prefix: string) => `${prefix}-${String(++_id).padStart(4, '0')}`

export function buildModule(overrides: Partial<ModuleInfo> = {}): ModuleInfo {
  return {
    name: 'mock_module',
    docstring: 'Mock module',
    full_docstring: 'Full docstring',
    category: 'feature_extractors',
    stage: 'features',
    params: { delay: { type: 'int', default: 0, required: false } },
    n_dims: 3,
    ...overrides,
  }
}

export function buildModules(): ModuleMetadata {
  return {
    feature_extractors: [
      buildModule({ name: 'word_rate', stage: 'features' }),
      buildModule({ name: 'phoneme_rate', stage: 'features' }),
    ],
    stimulus_loaders: [
      buildModule({
        name: 'audio_loader',
        category: 'stimulus_loaders',
        stage: 'stimuli',
        n_dims: null,
      }),
    ],
    response_loaders: [
      buildModule({
        name: 'fmriprep_loader',
        category: 'response_loaders',
        stage: 'responses',
        n_dims: null,
      }),
    ],
    models: [
      buildModule({ name: 'ridge', category: 'models', stage: 'model', n_dims: null }),
    ],
  }
}

export function buildStages(): StageInfo[] {
  return [
    { name: 'stimuli', index: 0, description: 'Load stimuli', module_categories: ['stimulus_loaders'], color: '#0ff' },
    { name: 'responses', index: 1, description: 'Load responses', module_categories: ['response_loaders'], color: '#f0f' },
    { name: 'features', index: 2, description: 'Extract features', module_categories: ['feature_extractors'], color: '#ff0' },
    { name: 'prepare', index: 3, description: 'Prepare', module_categories: ['preparation'], color: '#0f0' },
    { name: 'model', index: 4, description: 'Fit', module_categories: ['models'], color: '#00f' },
    { name: 'analyze', index: 5, description: 'Analyze', module_categories: ['analyzers'], color: '#888' },
    { name: 'report', index: 6, description: 'Report', module_categories: ['reporters'], color: '#fff' },
  ]
}

export function buildPipelineConfig(overrides: Partial<PipelineConfig> = {}): PipelineConfig {
  return {
    experiment: 'reading_en',
    subject: 'sub-01',
    stimulus: { loader: 'audio_loader', language: 'en', modality: 'audio' },
    response: { loader: 'fmriprep_loader' },
    features: [{ name: 'word_rate', extractor: 'word_rate', params: {} }],
    preparation: { type: 'standard', steps: [] },
    model: { type: 'ridge', params: {} },
    analysis: [],
    reporting: { formats: ['html'], output_dir: 'results' },
    ...overrides,
  }
}

export function buildRunSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: nextId('run'),
    output_dir: '/tmp/runs/x',
    experiment: 'reading_en',
    subject: 'sub-01',
    started_at: '2026-05-04T12:00:00',
    finished_at: '2026-05-04T12:30:00',
    total_elapsed_s: 1800,
    status: 'done',
    mean_score: 0.12,
    stages: [
      { name: 'stimuli', status: 'ok', elapsed_s: 1, detail: '' },
      { name: 'responses', status: 'ok', elapsed_s: 2, detail: '' },
      { name: 'features', status: 'ok', elapsed_s: 3, detail: '' },
      { name: 'prepare', status: 'ok', elapsed_s: 4, detail: '' },
      { name: 'model', status: 'ok', elapsed_s: 60, detail: '' },
      { name: 'analyze', status: 'ok', elapsed_s: 120, detail: '' },
      { name: 'report', status: 'ok', elapsed_s: 5, detail: '' },
    ],
    ...overrides,
  }
}

export function buildRunEvent(overrides: Partial<RunEvent> = {}): RunEvent {
  return { event: 'stage_start', stage: 'features', ...overrides }
}

export function buildConfigSummary(overrides: Partial<ConfigSummary> = {}): ConfigSummary {
  return {
    filename: 'reading_en/sub-01.yaml',
    path: '/tmp/configs/reading_en/sub-01.yaml',
    experiment: 'reading_en',
    subject: 'sub-01',
    model_type: 'ridge',
    features: ['word_rate'],
    output_dir: 'results',
    group: 'reading_en',
    preparation_type: 'standard',
    stimulus_loader: 'audio_loader',
    response_loader: 'fmriprep_loader',
    n_runs: 4,
    ...overrides,
  }
}

export function buildConfigDetail(overrides: Partial<ConfigDetail> = {}): ConfigDetail {
  const cfg = buildPipelineConfig()
  return {
    filename: 'reading_en/sub-01.yaml',
    path: '/tmp/configs/reading_en/sub-01.yaml',
    config: cfg as Record<string, unknown>,
    yaml_string: 'experiment: reading_en\nsubject: sub-01\n',
    ...overrides,
  }
}

export function buildUserModule(overrides: Partial<UserModule> = {}): UserModule {
  return {
    name: 'my_module',
    filename: 'my_module.py',
    category: 'feature_extractors',
    registered: true,
    path: '/tmp/plugins/my_module.py',
    ...overrides,
  }
}

export function buildValidationResult(
  overrides: Partial<CodeValidationResult> = {},
): CodeValidationResult {
  return {
    valid: true,
    errors: [],
    warnings: [],
    module_name: 'my_module',
    class_name: 'MyExtractor',
    category: 'feature_extractors',
    params: { delay: { type: 'int', default: 0 } },
    ...overrides,
  }
}

export function buildManifestSummary(overrides: Partial<ManifestSummary> = {}): ManifestSummary {
  return {
    subject: 'sub-01',
    path: '/tmp/manifest.json',
    backend: 'fmriprep',
    backend_version: '24.0.0',
    space: 'MNI152NLin2009cAsym',
    n_runs: 4,
    created: '2026-05-04T10:00:00',
    dataset: 'reading_en',
    ...overrides,
  }
}

export function buildPreprocRun(overrides: Partial<PreprocRunSummary> = {}): PreprocRunSummary {
  return {
    run_id: nextId('preproc'),
    subject: 'sub-01',
    backend: 'fmriprep',
    status: 'done',
    pid: 12345,
    started_at: 1700000000,
    finished_at: 1700000600,
    is_reattached: false,
    manifest_path: '/tmp/manifest.json',
    error: null,
    config_path: '/tmp/preproc.yaml',
    log_path: '/tmp/preproc.log',
    ...overrides,
  }
}

export function buildAutoflattenRun(
  overrides: Partial<AutoflattenRunSummary> = {},
): AutoflattenRunSummary {
  return {
    run_id: nextId('autoflatten'),
    subject: 'sub-01',
    status: 'done',
    pid: 23456,
    started_at: 1700000000,
    finished_at: 1700001000,
    is_reattached: false,
    error: null,
    log_path: null,
    ...overrides,
  }
}

export function buildConvertRun(overrides: Partial<ConvertRunSummary> = {}): ConvertRunSummary {
  return {
    run_id: nextId('convert'),
    subject: 'sub-01',
    status: 'done',
    pid: 34567,
    started_at: 1700000000,
    finished_at: 1700000300,
    is_reattached: false,
    manifest_path: '/tmp/convert-manifest.json',
    error: null,
    log_path: null,
    ...overrides,
  }
}
