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
  // Older backends that pre-date the scope split omit this field; the
  // UI defaults missing scope to 'subject'. Keep optional so callers
  // are forced to handle the legacy shape.
  scope?: 'subject' | 'group' | 'study'
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

/** One entry in a group config's ``group_analyze`` / ``group_report`` stage. */
export interface GroupPluginConfig {
  name: string
  params?: Record<string, unknown>
}

/** One entry in a study config's ``study_analyze`` / ``study_report`` stage. */
export interface StudyPluginConfig {
  name: string
  params?: Record<string, unknown>
}

/** Reference to a saved group config from a study YAML.
 *
 * Field names match the backend schema (``validate_study_config``):
 * the unique per-group label key is ``name`` (not ``label``). */
export interface StudyGroupRef {
  name: string
  config: string
  // Optional subjects override (the YAML allows this but the composer
  // form defaults to leaving it empty).
  subjects?: string[]
}

export interface GroupConfig {
  group?: string
  subjects?: string[]
  // Subject-pipeline template shared across all subjects in the group.
  // The composer's right-pane YAML editor is the source of truth for
  // this slice; the form provides the scope-specific shortcuts only.
  subject_template?: Record<string, unknown>
  subject_overrides?: Record<string, Record<string, unknown>>
  intermediates?: Record<string, unknown>
  qa?: Record<string, unknown>
  group_analyze?: GroupPluginConfig[]
  group_report?: GroupPluginConfig[]
  output_dir?: string
  [key: string]: unknown
}

export interface StudyConfig {
  study?: string
  groups?: StudyGroupRef[]
  intermediates?: Record<string, unknown>
  qa?: Record<string, unknown>
  study_analyze?: StudyPluginConfig[]
  study_report?: StudyPluginConfig[]
  output_dir?: string
  [key: string]: unknown
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
  // Attached to `run_failed` events: last ~200 lines of pipeline.log so
  // the UI can show the actual failure when no run_summary.json was
  // produced (and therefore no completedRun is fetched). Also a
  // Python traceback when the run_manager wrapper itself raised.
  log_tail?: string
  log_path?: string
  traceback?: string
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
  // 'subject' for a single-subject pipeline yaml; 'group' for a
  // GroupOrchestrator config (top-level 'group:' + 'subjects:' list);
  // 'study' for a StudyOrchestrator config (top-level 'study:' + 'groups:').
  kind?: 'subject' | 'group' | 'study'
  // For group configs only: list of subject IDs in the subjects: block.
  group_subjects?: string[]
  // For study configs only: list of study-scope group labels.
  study_groups?: string[]
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

// ── Settings ──

export type SettingsKey =
  | 'FMRIFLOW_HOME'
  | 'FMRIFLOW_DATA'
  | 'FS_LICENSE'
  | 'FMRIFLOW_SINGULARITY_BIN'

export interface SettingValue {
  env: string | null
  persisted: string | null
  effective: string
  source: 'env' | 'persisted' | 'default'
}

export interface SettingsSnapshot {
  runtime_config_path: string
  values: Record<SettingsKey, SettingValue>
  resolved: Record<string, string>
  license_file_exists: boolean
  subjects_db_exists: boolean
  subjects_db_count?: number | null
  restart_required?: boolean
  created?: string[]
}

export type SettingsUpdate = Partial<Record<SettingsKey, string>> & {
  create_missing?: boolean
}

// ── Result roots (read-only extra scan locations) ──

export interface ResultRoot {
  root_id: string
  path: string
  is_primary: boolean
  read_only: boolean
  reachable: boolean
}

export interface ResultRootsSnapshot {
  roots: ResultRoot[]
  configured: string[]
  // True when $FMRIFLOW_RESULT_ROOTS is set in the environment, which
  // overrides the persisted list — the UI locks add/remove in that case.
  env_override?: boolean
}

// ── Artifact Hub ─────────────────────────────────────────────────────

export type HubTier = 'lab' | 'community'

export type HubTokenStorage = 'env' | 'keyring' | 'settings' | 'none'

export interface HubSource {
  id: string
  name: string
  tier: HubTier
  url: string
  backend: string
  branch: string
  enabled: boolean
  has_token: boolean
  token_storage: HubTokenStorage
  synced: boolean
}

export interface HubSourcesSnapshot {
  sources: HubSource[]
  env_override: boolean
  preflight: string[]        // missing-prerequisite messages ([] if ready)
  keyring_available: boolean // OS keyring present → tokens stored securely
}

export interface HubCatalogItem {
  source_id: string
  source_name: string
  tier: HubTier
  kind: string
  name: string
  version: string
  description: string
  author: string
  tags: string[]
  size: number
  lfs: boolean
  sha256: string
  files: string[]
  metadata: Record<string, unknown>
  installed: boolean
  preview?: string | null    // present only on the detail endpoint
  verified?: boolean
}

export interface HubInstallResult {
  installed: boolean
  kind: string
  name: string
  path?: string
  paths?: string[]
  category?: string
  note?: string
}

export interface HubPublishResult {
  branch: string
  pushed: boolean
  pr_url?: string | null
  initialized?: boolean       // first publish to an empty repo → created the branch
  kind: string
  name?: string
  count?: number              // number published (bulk publish-kind)
  names?: string[]
  detail?: string
}

/** Origin of an installed artifact, keyed `<kind>:<key>` in the ledger. */
export interface HubProvenance {
  source_id: string
  source_name: string
  tier: HubTier
  artifact_name: string
  sha256: string
  installed_at: string
}

export type HubProvenanceMap = Record<string, HubProvenance>

// ── Preproc stack ────────────────────────────────────────────────────

export type BootstrapKind = 'fmriprep' | 'nipype' | 'custom' | 'bids_app' | 'passthrough'

export interface WorkflowInfo {
  name: string
  version: string
  description: string
  source: string                // "built-in" | "user" | "pip:<name>"
  container_bound: boolean
  required_python: string[]
  required_tools: string[]
  required_env: string[]
  params_schema: ParamSchema
}

export interface TransformInfo extends WorkflowInfo {
  inputs: string[]
  outputs: string[]
}

export interface PreflightResult {
  ok: boolean
  errors: string[]
  warnings: string[]
}

export interface BootstrapStageBody {
  kind: BootstrapKind
  workflow?: string | null
  params?: Record<string, unknown>
}

export interface TransformStageBody {
  name: string
  params?: Record<string, unknown>
}

export interface PreprocStackBody {
  bootstrap: BootstrapStageBody
  transforms: TransformStageBody[]
}

export interface StackRunBody {
  stack: PreprocStackBody
  subject: string
  output_dir: string
  bids_dir?: string | null
  derivatives_dir?: string | null
  dataset?: string
  sessions?: string[]
  task?: string | null
  use_cache?: boolean
  /** "Run from here": stages with index >= this value always
   *  re-execute even if the cache would hit. */
  force_from_stage?: number | null
}

export interface StackStepRecord {
  name: string
  version: string
  params: Record<string, unknown>
  input_stage: number
  output_dir: string
  duration_s: number
  fingerprint: string
}

export interface StackStageManifest {
  subject: string
  dataset: string
  sessions: string[]
  runs: unknown[]
  backend: string
  backend_version: string
  space: string
  output_dir: string
  additional_steps: StackStepRecord[]
}

export interface StackResultPayload {
  status: 'completed' | 'failed'
  bootstrap_fingerprint: string | null
  stage_cache_hits: boolean[]
  duration_s: number
  errors: string[]
  n_stages: number
  stage_manifests: StackStageManifest[]
}

export interface StackRunSummary {
  run_id: string
  kind: string
  backend: string
  subject: string
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'lost' | string
  pid: number | null
  started_at: number
  finished_at: number
  manifest_path: string | null
  error: string | null
  params: Record<string, unknown>
  result: StackResultPayload | null
}

export interface PresetSummary {
  name: string
  description: string
  n_transforms: number
  bootstrap_kind: string
}

export interface PresetDetail {
  name: string
  description: string
  stack: PreprocStackBody
}

export interface StackEvent {
  event:
    | 'started'
    | 'stage_start'
    | 'stage_done'
    | 'stage_failed'
    | 'completed'
    | 'failed'
    | '_close'
    | string
  timestamp?: number
  stage_index?: number
  stage_name?: string
  kind?: 'bootstrap' | 'transform' | string
  cache_hit?: boolean
  duration_s?: number
  fingerprint?: string
  error?: string
  errors?: string[]
  subject?: string
  n_stages?: number
  bootstrap_kind?: string
  status?: string
}

// ── Group runs ───────────────────────────────────────────────────

export interface GroupStatusCounts {
  ok: number
  warning: number
  failed: number
  unknown: number
}

export interface GroupRunListing {
  group_name: string
  run_id: string                  // empty string for legacy (pre-run-id) layout
  run_dir: string
  root_id?: string                // which result root this run lives in
  root_path?: string
  is_primary_root?: boolean
  subjects: string[]
  n_subjects: number
  status_counts: GroupStatusCounts
  started_at: string
  finished_at: string
  total_elapsed_s: number
  has_html_report: boolean
  has_log: boolean
}

export interface GroupSubjectStage {
  name: string
  status: string
  elapsed_s: number
  detail: string
}

export interface GroupSubjectSummary {
  experiment: string
  subject: string
  started_at: string
  finished_at: string
  total_elapsed_s: number
  stages: GroupSubjectStage[]
  config_snapshot: Record<string, unknown>
}

export interface GroupArtifacts {
  group: string[]                       // file paths relative to <run_dir>
  subjects: Record<string, string[]>    // subject -> file paths
}

export interface GroupRunDetail {
  group_name: string
  run_id: string
  subjects: string[]
  started_at: string
  finished_at: string
  total_elapsed_s: number
  subject_summaries: GroupSubjectSummary[]
  group_stages: GroupSubjectStage[]
  config_snapshot: Record<string, unknown>
  run_dir: string
  html_report?: string
  group_log?: string
  artifacts: GroupArtifacts
}

// ── Study runs (one scope up from group runs) ────────────────────

export interface StudyStatusCounts {
  ok: number
  warning?: number
  failed: number
}

export interface StudyRunListing {
  study_name: string
  run_id: string
  run_dir: string
  root_id?: string                // which result root this run lives in
  root_path?: string
  is_primary_root?: boolean
  group_labels: string[]
  n_groups: number
  status_counts: StudyStatusCounts
  // Server-computed overall outcome (ok | warning | failed). Older
  // backends pre-date this field — UI should fall back to deriving
  // from status_counts when absent.
  status?: 'ok' | 'warning' | 'failed'
  started_at: string
  finished_at: string
  total_elapsed_s: number
  has_html_report: boolean
  has_log: boolean
}

export interface StudyArtifacts {
  study: string[]                                  // files at run_dir top level
  groups: Record<string, string[]>                 // group_label → file paths
  // group_label → subject → per-subject file paths (plots etc.)
  subjects?: Record<string, Record<string, string[]>>
}

export interface StudyRunDetail {
  study_name: string
  run_id: string
  group_labels: string[]
  started_at: string
  finished_at: string
  total_elapsed_s: number
  group_summaries: Array<Record<string, unknown>>  // nested GroupRunSummary dicts
  study_stages: GroupSubjectStage[]
  config_snapshot: Record<string, unknown>
  run_dir: string
  html_report?: string
  study_log?: string
  artifacts: StudyArtifacts
}

// ── Convert decision table ──────────────────────────────────────────

export interface ConvertSeriesDecision {
  series_number: number
  series_id: string
  description: string
  protocol: string
  sequence: string
  n_files: number
  dims: number[]
  tr: number | null
  te: number | null
  is_derived: boolean
  image_type: string[]
  /** Resolved BIDS paths. Several when one series fans out (e.g. a GRE
   *  fieldmap producing magnitude1, magnitude2 and phasediff). */
  outputs: string[]
  /** Templates that claimed this series, parallel to `outputs`. */
  rules: string[]
  dropped: boolean
  /** 'ok' | 'dropped' | 'fan-out xN' */
  status: string
}

export interface ConvertCoverageRow {
  subject: string
  /** Output count per key, parallel to ConvertCoverage.keys. */
  cells: number[]
}

export interface ConvertCoverage {
  bids_dir: string
  subjects: string[]
  keys: string[]
  matrix: ConvertCoverageRow[]
  /** Keys declared by a heuristic but produced for no subject — rule bugs. */
  never_matched: string[]
  errors: Record<string, string>
}

export interface ConvertFlowLink {
  source: string
  target: string
  value: number
}

export interface ConvertFlow {
  bids_dir: string
  n_series: number
  n_dropped: number
  links: ConvertFlowLink[]
}

export interface ConvertDecisionTable {
  subject: string
  bids_dir: string
  n_series: number
  n_mapped: number
  n_dropped: number
  series: ConvertSeriesDecision[]
  warnings: string[]
}
