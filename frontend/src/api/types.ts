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

export interface ModuleInfo {
  name: string
  docstring: string
  full_docstring?: string
  category: string
  stage: string
  params: ParamSchema
  n_dims?: number | null
}

export type ModuleMetadata = Record<string, ModuleInfo[]>

export interface StageInfo {
  name: string
  index: number
  description: string
  module_categories: string[]
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
  [key: string]: unknown
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
  preparation?: {
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

// ── Module Editor types ──

export interface CodeValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
  module_name: string | null
  class_name: string | null
  category: string | null
  params: ParamSchema | null
}

export interface SaveModuleResult {
  saved: boolean
  path: string
  registered: boolean
  module_name: string
  class_name: string
  category: string
}

export interface UserModule {
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
  preparation_type: string
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

export interface PreprocConfigSummary {
  filename: string
  path: string
  subject: string
  backend: string
  bids_dir: string
  output_dir: string
  container: string
  container_type: string
  mode: string
}

export interface PreprocConfigDetail {
  filename: string
  path: string
  config: Record<string, unknown>
  yaml_string: string
}

export interface PreprocRunSummary {
  run_id: string
  subject: string
  backend: string
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'lost' | string
  pid: number | null
  started_at: number
  finished_at: number
  is_reattached: boolean
  manifest_path: string | null
  error: string | null
  config_path: string | null
  log_path: string | null
  log_tail?: string
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

// ── DICOM-to-BIDS Conversion ────────────────────────────────────────────

export interface HeuristicInfo {
  name: string
  description: string | null
  scanner_pattern: string | null
  version: string | null
  tasks: string[] | null
  path: string
}

export interface SaveHeuristicParams {
  name: string
  code: string
  description?: string
  scanner_pattern?: string
  tasks?: string[]
}

export interface ToolStatus {
  name: string
  available: boolean
  version: string | null
  detail: string
}

export interface ConvertManifestSummary {
  subject: string
  path: string
  dataset: string
  heudiconv_version: string
  n_runs: number
  created: string
  bids_valid: boolean | null
}

export interface ConvertManifestDetail {
  subject: string
  dataset: string
  sessions: string[]
  runs: ConvertRunRecord[]
  heudiconv_version: string
  heuristic: { name: string; path: string; content_hash: string; scanner_pattern: string | null; description: string | null } | null
  parameters: Record<string, unknown>
  source_dir: string
  scanner: { manufacturer: string | null; model: string | null; field_strength: number | null; software_version: string | null; station_name: string | null; institution: string | null } | null
  bids_dir: string
  bids_valid: boolean | null
  bids_errors: string[]
  bids_warnings: string[]
  created: string
}

export interface ConvertRunRecord {
  run_name: string
  task: string
  session: string
  source_series: string
  output_file: string
  sidecar_file: string
  n_volumes: number
  modality: string
  shape: number[]
  tr: number | null
  notes: string | null
}

export interface DicomSeriesInfo {
  number: number
  description: string
  n_images: number
  modality_guess: string
}

export interface DicomScanResult {
  scanner: { manufacturer: string | null; model: string | null; field_strength: number | null; software_version: string | null; station_name: string | null; institution: string | null } | null
  series: DicomSeriesInfo[]
  matching_heuristic: string | null
}

export interface ConvertEvent {
  event: string
  message?: string
  error?: string
  timestamp?: number
  [key: string]: unknown
}

// ── Batch Conversion ────────────────────────────────────────────────────

export interface BatchJobConfig {
  subject: string
  source_dir: string
  session: string
}

export interface BatchRunParams {
  heuristic: string
  bids_dir: string
  jobs: BatchJobConfig[]
  source_root: string
  max_workers: number
  dataset_name: string
  grouping: string
  minmeta: boolean
  overwrite: boolean
  validate_bids: boolean
}

export interface BatchJobStatus {
  job_id: string
  subject: string
  session: string
  status: 'queued' | 'running' | 'done' | 'failed'
  error: string | null
  started_at: number
  finished_at: number
}

export interface BatchSummary {
  batch_id: string
  status: string
  n_jobs: number
  counts: { queued: number; running: number; done: number; failed: number }
  jobs: BatchJobStatus[]
}

export interface SavedConvertConfig {
  filename: string
  name: string
  type: 'single' | 'batch'
  created: string
  description: string
  heuristic: string
  bids_dir: string
  n_jobs?: number
  subject?: string
}

export interface SavedConvertConfigDetail {
  filename: string
  config: Record<string, unknown>
  yaml_string: string
}

export interface BatchEvent {
  event: string
  job_id?: string | null
  message?: string
  error?: string
  timestamp?: number
  subject?: string
  session?: string
  queued?: number
  running?: number
  done?: number
  failed?: number
  elapsed?: number
  [key: string]: unknown
}
