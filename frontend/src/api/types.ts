/** TypeScript types matching the backend API responses. */

export interface ParamField {
  type: string
  default?: unknown
  required?: boolean
  min?: number
  max?: number
  enum?: string[]
  description?: string
}

export type ParamSchema = Record<string, ParamField>

export interface PluginInfo {
  name: string
  docstring: string
  full_docstring?: string
  category: string
  stage: string
  params: ParamSchema
  n_dims?: number | null
}

export type PluginMetadata = Record<string, PluginInfo[]>

export interface StageInfo {
  name: string
  index: number
  description: string
  plugin_categories: string[]
  color: string
}

export interface FeatureConfig {
  name: string
  source?: string
  extractor?: string
  params?: Record<string, unknown>
  path?: string
  paths?: Record<string, string>
  bucket?: string
  run_map?: Record<string, string>
  dataset?: string
}

export interface StepConfig {
  name: string
  params?: Record<string, unknown>
}

export interface AnalyzerConfig {
  name: string
  params?: Record<string, unknown>
}

export interface PipelineConfig {
  experiment?: string
  subject?: string
  subject_config?: Record<string, unknown>
  stimulus?: {
    loader?: string
    language?: string
    modality?: string
    [key: string]: unknown
  }
  response?: {
    loader?: string
    [key: string]: unknown
  }
  features?: FeatureConfig[]
  split?: {
    test_runs?: string[]
    train_runs?: string[] | 'auto'
  }
  preprocessing?: {
    type?: string
    steps?: StepConfig[]
    [key: string]: unknown
  }
  model?: {
    type?: string
    params?: Record<string, unknown>
  }
  analysis?: AnalyzerConfig[]
  reporting?: {
    formats?: string[]
    output_dir?: string
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface StageRecord {
  name: string
  status: string
  elapsed_s: number
  detail: string
}

export interface RunSummary {
  run_id: string
  output_dir: string
  experiment: string
  subject: string
  started_at: string
  finished_at: string
  total_elapsed_s: number
  status: string
  mean_score: number | null
  stages: StageRecord[]
  config_snapshot?: Record<string, unknown>
  artifacts?: Record<string, ArtifactInfo>
  log_tail?: string | null
}

export interface ArtifactInfo {
  name: string
  path: string
  size: number
  type: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
}

export interface RunEvent {
  event: string
  stage?: string
  elapsed?: number
  detail?: string
  error?: string
  timestamp?: number
}

// ── Plugin Editor types ──

export interface CodeValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
  plugin_name: string | null
  class_name: string | null
  category: string | null
  params: ParamSchema | null
}

export interface SavePluginResult {
  saved: boolean
  path: string
  registered: boolean
  plugin_name: string
  class_name: string
  category: string
}

export interface UserPlugin {
  name: string
  filename: string
  category: string | null
  registered: boolean
  path: string
}

export interface TemplateResult {
  code: string
  filename: string
  category: string
}

// ── Experiment Dashboard types ──

export interface ConfigSummary {
  filename: string
  path: string
  experiment: string
  subject: string
  model_type: string
  features: string[]
  output_dir: string
  group: string
  preprocessing_type: string
  stimulus_loader: string
  response_loader: string
  n_runs: number
}

export interface ConfigDetail {
  filename: string
  path: string
  config: Record<string, unknown>
  yaml_string: string
}

export interface StageStatus {
  status: 'pending' | 'running' | 'done' | 'warning' | 'failed'
  detail: string
  elapsed_s: number
}

// ── Preprocessing types ──

export interface BackendInfo {
  name: string
  available: boolean
  detail: string
}

export interface ManifestSummary {
  subject: string
  path: string
  backend: string
  backend_version: string
  space: string
  n_runs: number
  created: string
  dataset: string
}

export interface RunQC {
  mean_fd: number | null
  max_fd: number | null
  n_high_motion_trs: number | null
  tsnr_median: number | null
  n_outlier_trs: number | null
  notes: string | null
}

export interface ManifestRun {
  run_name: string
  source_file: string
  output_file: string
  n_trs: number
  n_voxels: number | null
  shape: number[]
  confounds_file: string | null
  qc: RunQC | null
}

export interface ManifestDetail {
  subject: string
  dataset: string
  sessions: string[]
  runs: ManifestRun[]
  backend: string
  backend_version: string
  parameters: Record<string, unknown>
  space: string
  resolution: string | null
  confounds_applied: string[]
  additional_steps: string[]
  output_dir: string
  output_format: string
  file_pattern: string
  created: string
  pipeline_version: string | null
  checksum: string | null
  manifest_version: number
}

export interface PreprocEvent {
  event: string
  message?: string
  error?: string
  manifest_path?: string
  n_runs?: number
  elapsed?: number
  timestamp?: number
}

export interface CollectResult {
  manifest: ManifestDetail
  manifest_path: string
}

// ── Error Knowledge Base types ──

export interface ErrorEntry {
  id: string | number
  title: string
  date: string
  author: string
  stage: string
  tags: string[]
  symptoms: string
  root_cause: string
  fix: string
  diagnosis: string
  config_note: string
  references: string[]
}
