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
  message?: string
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

export interface AutoflattenConfigSummary {
  filename: string
  path: string
  subject: string
  subjects_dir: string
  hemispheres: string
  backend: string
  output_dir: string
}

export interface AutoflattenConfigDetail {
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

export interface ConvertRunSummary {
  run_id: string
  subject: string
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'lost' | string
  pid: number | null
  started_at: number
  finished_at: number
  is_reattached: boolean
  manifest_path: string | null
  error: string | null
  log_path: string | null
  log_tail?: string
}

export interface AutoflattenResultPayload {
  subject: string
  source: 'autoflatten' | 'precomputed' | 'import_only' | string
  hemispheres: string[]
  flat_patches: Record<string, string>
  visualizations: Record<string, string>
  pycortex_surface: string | null
  elapsed_s: number
}

export interface AutoflattenRunSummary {
  run_id: string
  subject: string
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'lost' | string
  pid: number | null
  started_at: number
  finished_at: number
  is_reattached: boolean
  error: string | null
  log_path: string | null
  log_tail?: string
  result?: {
    result?: AutoflattenResultPayload
    record?: Record<string, unknown>
  } | null
  /** Backing FreeSurfer subjects dir — surfaced so the Results view
   *  can rescan surf/ for visualization PNGs when the completed run
   *  used the precomputed path and didn't write PNGs into result. */
  subjects_dir?: string
}

export interface AnalysisInnerStage {
  stage: string   // 'stimuli' | 'responses' | 'features' | 'prepare' | 'model' | 'analyze' | 'report'
  status: 'pending' | 'running' | 'ok' | 'warning' | 'failed' | string
  started_at: number
  finished_at: number
  elapsed: number
  detail: string
  error: string | null
}

export interface AnalysisRunSummary {
  run_id: string
  experiment: string
  subject: string
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'lost' | string
  pid: number | null
  started_at: number
  finished_at: number
  is_reattached: boolean
  error: string | null
  config_path: string | null
  output_dir: string | null
  log_path: string | null
  log_tail?: string
  inner_stages?: AnalysisInnerStage[]
}

export interface WorkflowConfigSummary {
  filename: string
  path: string
  name: string
  n_stages: number
  stage_names: string[]
}

export interface WorkflowConfigDetail {
  filename: string
  path: string
  config: Record<string, unknown>
  yaml_string: string
}

export interface WorkflowStageStatus {
  stage: 'convert' | 'preproc' | 'autoflatten' | 'analysis' | string
  config: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled' | string
  run_id: string | null
  started_at: number
  finished_at: number
  error: string | null
  // Populated client-side for the analysis stage when we've fetched its
  // inner-stage progression (stimuli / responses / features / prepare /
  // model / analyze / report).
  inner_stages?: AnalysisInnerStage[]
  // Populated client-side for the preproc stage when fmriprep is the
  // backend; the parent view polls /preproc/runs/{run_id}/live.
  nipype_status?: NipypeStatusBlock
}

export interface WorkflowRunSummary {
  run_id: string
  name: string
  status: 'running' | 'done' | 'failed' | 'cancelled' | string
  started_at: number
  finished_at: number
  error: string | null
  config_path: string | null
  stages: WorkflowStageStatus[]
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
  run_id: string | null
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
  legacy?: boolean
}

export interface SavedConvertConfigDetail {
  filename: string
  path?: string
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

// ── Triage (automatic error capture) ────────────────────────────────────

export interface TriageFingerprint {
  source: string
  hash: string
  snippet: string
}

export interface TriageCandidateMatch {
  id: number
  title: string
  confidence: number
  match_on: string
  matched_fingerprint_hashes: string[]
}

export interface TriageRecord {
  run_id: string
  kind: string
  stage: string
  backend: string | null
  captured_at: string
  failed_at: number | null
  symptom: string
  traceback_tail: string
  stdout_tail: string
  crash_files: string[]
  fingerprints: TriageFingerprint[]
  candidate_matches: TriageCandidateMatch[]
  tags: string[]
  capture_version: number
}

export interface NewErrorFromCaptureResult {
  saved: boolean
  id: number
  filename: string
  path: string
  proposed_dir: string
}

// ── Live nipype-node monitoring ───────────────────────────────────

export type NipypeNodeStatusKind =
  | 'running' | 'ok' | 'failed' | 'completed_assumed' | 'cached'

export interface NipypeWorkTree {
  work_dir: string | null
  leaves: string[]
}

export interface NipypeNodeStatus {
  node: string        // full dotted path
  leaf: string        // last segment
  workflow: string    // parent workflow path
  status: NipypeNodeStatusKind
  started_at: number
  finished_at: number
  elapsed: number
  crash_file: string | null
  level: string
}

export interface NipypeStatusCounts {
  running: number
  ok: number
  failed: number
  completed_assumed: number
  total_seen: number
}

export interface NipypeStatusBlock {
  counts: NipypeStatusCounts
  recent_nodes: NipypeNodeStatus[]
}

export interface PreprocRunLive extends PreprocRunSummary {
  nipype_status: NipypeStatusBlock
}

// ── Structural QC ────────────────────────────────────────────────

export type StructuralQCStatus = "pending" | "approved" | "needs_edits" | "rejected"

export interface StructuralQCReview {
  dataset: string
  subject: string
  status: StructuralQCStatus
  reviewer: string
  timestamp: string
  notes: string
  freeview_command_used: string | null
}

// ── Post-preproc ─────────────────────────────────────────────────

export interface NipypeNodeMeta {
  name: string
  docstring: string
  inputs: string[]
  outputs: string[]
  params: ParamSchema
}

export interface PostPreprocGraphNode {
  id: string
  type: string
  data: { params: Record<string, unknown> }
  position: { x: number; y: number }
}

export interface PostPreprocGraphEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
}

export interface PostPreprocGraph {
  nodes: PostPreprocGraphNode[]
  edges: PostPreprocGraphEdge[]
}

export interface PostPreprocRunHandle {
  run_id: string
  status: 'pending' | 'running' | 'done' | 'failed'
  output_dir: string
  error?: string | null
  manifest?: PostPreprocManifest | null
}

export interface PostPreprocManifest {
  subject: string
  dataset: string
  source_manifest_path: string
  graph: PostPreprocGraph
  nodes_run: Array<{
    node_id: string
    node_type: string
    params: Record<string, unknown>
    inputs: Record<string, string>
    outputs: Record<string, string>
    duration_s: number | null
  }>
  output_dir: string
  created: string
  manifest_version: number
}

// ── Post-preproc workflows (saved YAML) ───────────────────────────

export interface PostPreprocWorkflowSummary {
  name: string
  description: string
  inputs: string[]
  outputs: string[]
  n_nodes: number
}

export interface PostPreprocWorkflow {
  name: string
  description: string
  inputs: Record<string, { from: string }>
  outputs: Record<string, { from: string }>
  graph: PostPreprocGraph
}

// ── Per-node fmriprep outputs ────────────────────────────────────

export interface NodeOutputFile {
  name: string
  rel: string
  suffix: string
  size: number
  kind: 'view' | 'pickle' | 'link'
}

export interface NodeOutputCrash {
  name: string
  path: string
  size: number
}

export interface NodeOutputsList {
  node: string
  leaf_dir: string
  exists: boolean
  files: NodeOutputFile[]
  crashes: NodeOutputCrash[]
}

export interface NodePickleResponse {
  name: string
  type?: string
  value?: unknown
  error?: string
}
