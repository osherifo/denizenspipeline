/** DICOM-to-BIDS conversion manager store. */
import { create } from 'zustand'
import type {
  HeuristicInfo,
  ConvertManifestSummary,
  ConvertManifestDetail,
  ConvertEvent,
  DicomScanResult,
  DicomScanProgress,
  BatchJobConfig,
  BatchRunParams,
  BatchJobStatus,
  BatchEvent,
  SavedConvertConfig,
} from '../api/types'
import {
  fetchConvertHeuristics,
  fetchHeuristicCode,
  saveHeuristic,
  fetchHeuristicTemplate,
  deleteHeuristic,
  fetchConvertManifests,
  rescanConvertManifests,
  fetchConvertManifestDetail,
  validateConvertManifest,
  startDicomScan,
  fetchDicomScan,
  cancelDicomScan,
  collectConvertOutputs,
  startConvertRun,
  connectConvertWs,
  startBatchConvert,
  connectBatchWs,
  parseBatchYaml,
  fetchSavedConvertConfigs,
  fetchSavedConvertConfig,
  saveConvertRunConfig,
  saveConvertBatchConfig,
  deleteSavedConvertConfig,
} from '../api/client'

type Tab = 'heuristics' | 'scan' | 'manifests' | 'configs' | 'convert' | 'batch'


export interface RunForm {
  sourceDir: string
  bidsDir: string
  subject: string
  heuristic: string
  session: string
  datasetName: string
  grouping: string
  minmeta: boolean
  overwrite: boolean
  validateBids: boolean
}

export const EMPTY_RUN_FORM: RunForm = {
  sourceDir: '', bidsDir: '', subject: '', heuristic: '', session: '', datasetName: '', grouping: '',
  minmeta: false, overwrite: false, validateBids: true,
}

/** The run-request params for the single form (what /convert/run and save-run take). */
export function runFormParams(f: RunForm): Record<string, unknown> {
  const params: Record<string, unknown> = {
    source_dir: f.sourceDir.trim(), bids_dir: f.bidsDir, subject: f.subject, heuristic: f.heuristic,
  }
  if (f.session.trim()) params.sessions = [f.session.trim()]
  if (f.datasetName.trim()) params.dataset_name = f.datasetName.trim()
  if (f.grouping.trim()) params.grouping = f.grouping.trim()
  if (f.minmeta) params.minmeta = true
  if (f.overwrite) params.overwrite = true
  if (!f.validateBids) params.validate_bids = false
  return params
}

/** The YAML the server would save for this form (a `convert:` config). */
export function runFormYaml(f: RunForm): string {
  const q = (v: string) => JSON.stringify(v)
  let y = 'convert:\n'
  y += `  source_dir: ${q(f.sourceDir.trim())}\n`
  y += `  bids_dir: ${q(f.bidsDir)}\n`
  y += `  subject: ${q(f.subject)}\n`
  y += `  heuristic: ${q(f.heuristic)}\n`
  if (f.session.trim()) y += `  sessions: [${q(f.session.trim())}]\n`
  if (f.datasetName.trim()) y += `  dataset_name: ${q(f.datasetName.trim())}\n`
  if (f.grouping.trim()) y += `  grouping: ${q(f.grouping.trim())}\n`
  if (f.minmeta) y += '  minmeta: true\n'
  if (f.overwrite) y += '  overwrite: true\n'
  if (!f.validateBids) y += '  validate_bids: false\n'
  return y
}

interface ConvertState {
  tab: Tab

  // Heuristics
  heuristics: HeuristicInfo[]
  heuristicsLoading: boolean

  // Heuristic editor
  editorCode: string
  editorName: string
  editorDirty: boolean
  editorLoading: boolean
  editorSaving: boolean
  editorError: string | null
  editorSaveSuccess: boolean

  // Manifests
  manifests: ConvertManifestSummary[]
  manifestsLoading: boolean
  selectedSubject: string | null
  selectedManifest: ConvertManifestDetail | null
  validationErrors: string[] | null
  validating: boolean

  // DICOM scan
  scanResult: DicomScanResult | null
  scanning: boolean
  scanError: string | null
  scanId: string | null
  scanProgress: DicomScanProgress | null
  cancelScan: () => Promise<void>

  // Collect
  collectResult: { manifest: ConvertManifestDetail; manifest_path: string } | null
  collecting: boolean
  collectError: string | null

  // Run
  runId: string | null
  runEvents: ConvertEvent[]
  runStartTime: number | null
  runError: string | null
  running: boolean

  // Batch
  batchId: string | null
  batchJobs: BatchJobConfig[]
  batchShared: {
    heuristic: string
    bidsDir: string
    sourceRoot: string
    maxWorkers: number
    datasetName: string
    grouping: string
    minmeta: boolean
    overwrite: boolean
    validateBids: boolean
  }
  batchRunning: boolean
  batchEvents: BatchEvent[]
  batchJobStatuses: Record<string, BatchJobStatus>
  batchCounts: { queued: number; running: number; done: number; failed: number }
  batchError: string | null
  batchStartTime: number | null

  // Actions
  setTab: (tab: Tab) => void
  loadHeuristics: () => Promise<void>
  openHeuristic: (name: string) => Promise<void>
  newHeuristic: (name: string) => Promise<void>
  setEditorCode: (code: string) => void
  setEditorName: (name: string) => void
  saveHeuristic: () => Promise<void>
  deleteHeuristic: (name: string) => Promise<void>
  closeEditor: () => void
  loadManifests: () => Promise<void>
  rescan: () => Promise<void>
  selectManifest: (subject: string) => Promise<void>
  validateSelected: () => Promise<void>
  scanDicom: (sourceDir: string) => Promise<void>
  collect: (params: Parameters<typeof collectConvertOutputs>[0]) => Promise<void>
  startRun: (params: Parameters<typeof startConvertRun>[0]) => Promise<void>
  clearRun: () => void
  clearCollect: () => void
  clearScan: () => void

  // Batch actions
  addBatchJob: () => void
  removeBatchJob: (index: number) => void
  updateBatchJob: (index: number, patch: Partial<BatchJobConfig>) => void
  updateBatchShared: (patch: Partial<ConvertState['batchShared']>) => void
  startBatch: () => Promise<void>
  clearBatch: () => void
  loadBatchYaml: (yamlText: string) => Promise<void>

  // Single-run form (kept in the store so a saved config can load back into it)
  runForm: RunForm
  updateRunForm: (patch: Partial<RunForm>) => void
  resetRunForm: () => void
  runFormError: string | null
  // Saved configs
  savedConfigs: SavedConvertConfig[]
  savedConfigsLoading: boolean
  loadSavedConfigs: () => Promise<void>
  saveCurrentRunConfig: (name: string, description?: string, params?: Record<string, unknown>) => Promise<void>
  saveCurrentBatchConfig: (name: string, description?: string) => Promise<void>
  loadSavedConfig: (filename: string) => Promise<void>
  deleteSavedConfig: (filename: string) => Promise<void>
}

export const useConvertStore = create<ConvertState>((set, get) => ({
  tab: 'heuristics',
  runForm: { ...EMPTY_RUN_FORM },
  runFormError: null,
  updateRunForm: (patch) => set({ runForm: { ...get().runForm, ...patch } }),
  resetRunForm: () => set({ runForm: { ...EMPTY_RUN_FORM }, runFormError: null }),

  heuristics: [],
  heuristicsLoading: false,

  editorCode: '',
  editorName: '',
  editorDirty: false,
  editorLoading: false,
  editorSaving: false,
  editorError: null,
  editorSaveSuccess: false,

  manifests: [],
  manifestsLoading: false,
  selectedSubject: null,
  selectedManifest: null,
  validationErrors: null,
  validating: false,

  scanResult: null,
  scanning: false,
  scanError: null,
  scanId: null,
  scanProgress: null,

  collectResult: null,
  collecting: false,
  collectError: null,

  runId: null,
  runEvents: [],
  runStartTime: null,
  runError: null,
  running: false,

  // Batch initial state
  batchId: null,
  batchJobs: [{ subject: '', source_dir: '', session: '' }],
  batchShared: {
    heuristic: '',
    bidsDir: '',
    sourceRoot: '',
    maxWorkers: 2,
    datasetName: '',
    grouping: '',
    minmeta: false,
    overwrite: true,
    validateBids: true,
  },
  batchRunning: false,
  batchEvents: [],
  batchJobStatuses: {},
  batchCounts: { queued: 0, running: 0, done: 0, failed: 0 },
  batchError: null,
  batchStartTime: null,

  setTab: (tab) => set({ tab }),

  loadHeuristics: async () => {
    set({ heuristicsLoading: true })
    try {
      const heuristics = await fetchConvertHeuristics()
      set({ heuristics, heuristicsLoading: false })
    } catch {
      set({ heuristicsLoading: false })
    }
  },

  openHeuristic: async (name: string) => {
    set({ editorLoading: true, editorError: null, editorSaveSuccess: false })
    try {
      const code = await fetchHeuristicCode(name)
      set({ editorCode: code, editorName: name, editorDirty: false, editorLoading: false })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ editorLoading: false, editorError: msg })
    }
  },

  newHeuristic: async (name: string) => {
    set({ editorLoading: true, editorError: null, editorSaveSuccess: false })
    try {
      const result = await fetchHeuristicTemplate(name)
      set({ editorCode: result.code, editorName: name, editorDirty: true, editorLoading: false })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ editorLoading: false, editorError: msg })
    }
  },

  setEditorCode: (code: string) => {
    set({ editorCode: code, editorDirty: true, editorSaveSuccess: false })
  },

  setEditorName: (name: string) => {
    set({ editorName: name, editorDirty: true })
  },

  saveHeuristic: async () => {
    const { editorCode, editorName } = get()
    set({ editorSaving: true, editorError: null, editorSaveSuccess: false })
    if (!editorName.trim()) {
      set({ editorSaving: false, editorError: 'Heuristic name is required' })
      return
    }
    try {
      await saveHeuristic({ name: editorName, code: editorCode })
      set({ editorSaving: false, editorDirty: false, editorSaveSuccess: true })
      get().loadHeuristics()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ editorSaving: false, editorError: msg })
    }
  },

  deleteHeuristic: async (name: string) => {
    try {
      await deleteHeuristic(name)
      const { editorName } = get()
      if (editorName === name) {
        set({ editorCode: '', editorName: '', editorDirty: false, editorError: null, editorSaveSuccess: false })
      }
      get().loadHeuristics()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      set({ editorError: msg })
    }
  },

  closeEditor: () => {
    set({ editorCode: '', editorName: '', editorDirty: false, editorError: null, editorSaveSuccess: false })
  },

  loadManifests: async () => {
    set({ manifestsLoading: true })
    try {
      const manifests = await fetchConvertManifests()
      set({ manifests, manifestsLoading: false })
    } catch {
      set({ manifestsLoading: false })
    }
  },

  rescan: async () => {
    set({ manifestsLoading: true })
    try {
      const manifests = await rescanConvertManifests()
      set({ manifests, manifestsLoading: false })
    } catch {
      set({ manifestsLoading: false })
    }
  },

  selectManifest: async (subject) => {
    set({ selectedSubject: subject, selectedManifest: null, validationErrors: null })
    try {
      const detail = await fetchConvertManifestDetail(subject)
      set({ selectedManifest: detail })
    } catch {
      set({ selectedManifest: null })
    }
  },

  validateSelected: async () => {
    const subject = get().selectedSubject
    if (!subject) return
    set({ validating: true, validationErrors: null })
    try {
      const result = await validateConvertManifest(subject)
      set({ validationErrors: result.errors, validating: false })
    } catch (e) {
      set({ validationErrors: [String(e)], validating: false })
    }
  },

  scanDicom: async (sourceDir) => {
    set({ scanning: true, scanError: null, scanResult: null, scanProgress: null, scanId: null })
    try {
      let job = await startDicomScan(sourceDir)
      set({ scanId: job.scan_id, scanProgress: job.progress })
      while (job.status === 'running') {
        await new Promise((r) => setTimeout(r, 500))
        if (get().scanId !== job.scan_id) return       // superseded by a newer scan / cleared
        job = await fetchDicomScan(job.scan_id)
        set({ scanProgress: job.progress })
      }
      if (job.status === 'done') {
        set({ scanResult: job.result, scanning: false })
      } else if (job.status === 'cancelled') {
        set({ scanning: false, scanError: `Scan cancelled after ${job.progress.files_seen} files.` })
      } else {
        set({ scanning: false, scanError: job.error || 'Scan failed' })
      }
    } catch (e) {
      set({ scanError: String(e), scanning: false })
    }
  },

  cancelScan: async () => {
    const id = get().scanId
    if (!id) return
    try {
      await cancelDicomScan(id)
    } catch (e) {
      set({ scanError: String(e) })
    }
  },

  collect: async (params) => {
    set({ collecting: true, collectError: null, collectResult: null })
    try {
      const result = await collectConvertOutputs(params)
      set({ collectResult: result, collecting: false })
      get().rescan()
    } catch (e) {
      set({ collectError: String(e), collecting: false })
    }
  },

  startRun: async (params) => {
    set({ running: true, runError: null, runEvents: [], runStartTime: Date.now(), runId: null })
    try {
      const result = await startConvertRun(params)
      set({ runId: result.run_id })

      const ws = connectConvertWs(result.run_id)
      ws.onmessage = (msg) => {
        const event: ConvertEvent = JSON.parse(msg.data)
        set((s) => ({ runEvents: [...s.runEvents, event] }))
        if (event.event === 'done' || event.event === 'failed') {
          ws.close()
          set({
            running: false,
            runError: event.event === 'failed' ? (event.error || 'failed') : null,
          })
          get().rescan()
        }
      }
      ws.onerror = () => {
        set({ running: false, runError: 'WebSocket connection failed' })
      }
    } catch (e) {
      set({ running: false, runError: String(e) })
    }
  },

  clearRun: () => set({ runId: null, runEvents: [], runStartTime: null, runError: null, running: false }),

  clearCollect: () => set({ collectResult: null, collectError: null }),

  clearScan: () => set({ scanResult: null, scanError: null, scanId: null, scanProgress: null }),

  // ── Batch actions ──────────────────────────────────────────────

  addBatchJob: () => set((s) => ({
    batchJobs: [...s.batchJobs, { subject: '', source_dir: '', session: '' }],
  })),

  removeBatchJob: (index) => set((s) => ({
    batchJobs: s.batchJobs.filter((_, i) => i !== index),
  })),

  updateBatchJob: (index, patch) => set((s) => ({
    batchJobs: s.batchJobs.map((j, i) => i === index ? { ...j, ...patch } : j),
  })),

  updateBatchShared: (patch) => set((s) => ({
    batchShared: { ...s.batchShared, ...patch },
  })),

  startBatch: async () => {
    const { batchShared, batchJobs } = get()
    const validJobs = batchJobs.filter((j) => j.subject.trim() && j.source_dir.trim())
    if (validJobs.length === 0) return

    set({
      batchRunning: true,
      batchError: null,
      batchEvents: [],
      batchJobStatuses: {},
      batchCounts: { queued: validJobs.length, running: 0, done: 0, failed: 0 },
      batchStartTime: Date.now(),
      batchId: null,
    })

    try {
      const params: BatchRunParams = {
        heuristic: batchShared.heuristic,
        bids_dir: batchShared.bidsDir,
        source_root: batchShared.sourceRoot,
        max_workers: batchShared.maxWorkers,
        dataset_name: batchShared.datasetName,
        grouping: batchShared.grouping,
        minmeta: batchShared.minmeta,
        overwrite: batchShared.overwrite,
        validate_bids: batchShared.validateBids,
        jobs: validJobs,
      }

      const result = await startBatchConvert(params)
      set({ batchId: result.batch_id })

      const ws = connectBatchWs(result.batch_id)
      ws.onmessage = (msg) => {
        const event: BatchEvent = JSON.parse(msg.data)
        set((s) => {
          const newEvents = [...s.batchEvents, event]
          const newStatuses = { ...s.batchJobStatuses }
          let newCounts = { ...s.batchCounts }

          // Update per-job status from job events
          if (event.job_id && event.event === 'job_started') {
            newStatuses[event.job_id] = {
              job_id: event.job_id,
              subject: event.subject || '',
              session: event.session || '',
              status: 'running',
              error: null,
              started_at: event.timestamp || 0,
              finished_at: 0,
              run_id: (event as unknown as { run_id?: string }).run_id || null,
            }
          }

          // Update from individual job done/failed events forwarded from _BatchAwareRunHandle
          if (event.job_id && event.event === 'done') {
            const existing = newStatuses[event.job_id]
            if (existing) {
              newStatuses[event.job_id] = { ...existing, status: 'done', finished_at: event.timestamp || 0 }
            }
          }
          if (event.job_id && event.event === 'failed') {
            const existing = newStatuses[event.job_id]
            if (existing) {
              newStatuses[event.job_id] = { ...existing, status: 'failed', error: event.error || null, finished_at: event.timestamp || 0 }
            }
          }

          // Update counts from batch_progress events
          if (event.event === 'batch_progress' || event.event === 'batch_done') {
            newCounts = {
              queued: event.queued ?? newCounts.queued,
              running: event.running ?? newCounts.running,
              done: event.done ?? newCounts.done,
              failed: event.failed ?? newCounts.failed,
            }
          }

          return { batchEvents: newEvents, batchJobStatuses: newStatuses, batchCounts: newCounts }
        })

        if (event.event === 'batch_done') {
          ws.close()
          set({ batchRunning: false })
          get().rescan()
        }
      }

      ws.onerror = () => {
        set({ batchRunning: false, batchError: 'WebSocket connection failed' })
      }
    } catch (e) {
      set({ batchRunning: false, batchError: String(e) })
    }
  },

  clearBatch: () => set({
    batchId: null,
    batchEvents: [],
    batchJobStatuses: {},
    batchCounts: { queued: 0, running: 0, done: 0, failed: 0 },
    batchError: null,
    batchStartTime: null,
    batchRunning: false,
  }),

  loadBatchYaml: async (yamlText) => {
    try {
      const parsed = await parseBatchYaml(yamlText)
      set({
        batchShared: {
          heuristic: parsed.heuristic,
          bidsDir: parsed.bids_dir,
          sourceRoot: parsed.source_root,
          maxWorkers: parsed.max_workers,
          datasetName: parsed.dataset_name,
          grouping: parsed.grouping,
          minmeta: parsed.minmeta,
          overwrite: parsed.overwrite,
          validateBids: parsed.validate_bids,
        },
        batchJobs: parsed.jobs.map((j) => ({
          subject: j.subject,
          source_dir: j.source_dir,
          session: j.session || '',
        })),
      })
    } catch (e) {
      set({ batchError: String(e) })
    }
  },

  // ── Saved configs ──────────────────────────────────────────────

  savedConfigs: [],
  savedConfigsLoading: false,

  loadSavedConfigs: async () => {
    set({ savedConfigsLoading: true })
    try {
      const configs = await fetchSavedConvertConfigs()
      set({ savedConfigs: configs, savedConfigsLoading: false })
    } catch {
      set({ savedConfigsLoading: false })
    }
  },

  saveCurrentRunConfig: async (name: string, description?: string, params?: Record<string, unknown>) => {
    const body = params ?? runFormParams(get().runForm)
    set({ runFormError: null })
    try {
      await saveConvertRunConfig({ name, description, params: body })
      await get().loadSavedConfigs()
    } catch (e) {
      set({ runFormError: String(e) })
      throw e
    }
  },

  saveCurrentBatchConfig: async (name, description) => {
    const { batchShared, batchJobs } = get()
    const validJobs = batchJobs.filter((j) => j.subject.trim() && j.source_dir.trim())
    const params = {
      heuristic: batchShared.heuristic,
      bids_dir: batchShared.bidsDir,
      source_root: batchShared.sourceRoot,
      max_workers: batchShared.maxWorkers,
      dataset_name: batchShared.datasetName,
      grouping: batchShared.grouping,
      minmeta: batchShared.minmeta,
      overwrite: batchShared.overwrite,
      validate_bids: batchShared.validateBids,
      jobs: validJobs,
    }
    try {
      await saveConvertBatchConfig({ name, description, params })
      get().loadSavedConfigs()
    } catch (e) {
      set({ batchError: String(e) })
    }
  },

  loadSavedConfig: async (filename) => {
    try {
      const detail = await fetchSavedConvertConfig(filename)
      const config = detail.config as Record<string, unknown>

      if ('convert_batch' in config) {
        // Batch config — load into batch form
        const batch = config.convert_batch as Record<string, unknown>
        const jobs = (batch.jobs as Array<Record<string, string>>) || []
        set({
          tab: 'batch',
          batchShared: {
            heuristic: String(batch.heuristic || ''),
            bidsDir: String(batch.bids_dir || ''),
            sourceRoot: String(batch.source_root || ''),
            maxWorkers: Number.isFinite(Number(batch.max_workers)) ? Number(batch.max_workers) : 2,
            datasetName: String(batch.dataset_name || ''),
            grouping: String(batch.grouping || ''),
            minmeta: Boolean(batch.minmeta),
            overwrite: batch.overwrite !== false,
            validateBids: batch.validate_bids !== false,
          },
          batchJobs: jobs.map((j) => ({
            subject: j.subject || '',
            source_dir: j.source_dir || '',
            session: j.session || '',
          })),
        })
      }
      if ('convert' in config) {
        const c = config.convert as Record<string, unknown>
        const sessions = Array.isArray(c.sessions) ? (c.sessions as unknown[]) : []
        set({
          tab: 'convert',
          runForm: {
            sourceDir: String(c.source_dir || ''),
            bidsDir: String(c.bids_dir || ''),
            subject: String(c.subject || ''),
            heuristic: String(c.heuristic || ''),
            session: sessions.length ? String(sessions[0]) : '',
            datasetName: String(c.dataset_name || ''),
            grouping: String(c.grouping || ''),
            minmeta: Boolean(c.minmeta),
            overwrite: Boolean(c.overwrite),
            validateBids: c.validate_bids !== false,
          },
        })
      }
    } catch (e) {
      set({ batchError: String(e) })
    }
  },

  deleteSavedConfig: async (filename) => {
    try {
      await deleteSavedConvertConfig(filename)
      get().loadSavedConfigs()
    } catch {
      // silent
    }
  },
}))
