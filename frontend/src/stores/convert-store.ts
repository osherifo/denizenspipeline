/** DICOM-to-BIDS conversion manager store. */
import { create } from 'zustand'
import type {
  ToolStatus,
  HeuristicInfo,
  ConvertManifestSummary,
  ConvertManifestDetail,
  ConvertEvent,
  DicomScanResult,
  BatchJobConfig,
  BatchRunParams,
  BatchJobStatus,
  BatchEvent,
  SavedConvertConfig,
} from '../api/types'
import {
  fetchConvertTools,
  fetchConvertHeuristics,
  fetchConvertManifests,
  rescanConvertManifests,
  fetchConvertManifestDetail,
  validateConvertManifest,
  scanDicomDirectory,
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

type Tab = 'tools' | 'heuristics' | 'scan' | 'manifests' | 'convert' | 'batch'

interface ConvertState {
  tab: Tab

  // Tools
  tools: ToolStatus[]
  toolsLoading: boolean

  // Heuristics
  heuristics: HeuristicInfo[]
  heuristicsLoading: boolean

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
  loadTools: () => Promise<void>
  loadHeuristics: () => Promise<void>
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
  tab: 'tools',

  tools: [],
  toolsLoading: false,

  heuristics: [],
  heuristicsLoading: false,

  manifests: [],
  manifestsLoading: false,
  selectedSubject: null,
  selectedManifest: null,
  validationErrors: null,
  validating: false,

  scanResult: null,
  scanning: false,
  scanError: null,

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

  loadTools: async () => {
    set({ toolsLoading: true })
    try {
      const tools = await fetchConvertTools()
      set({ tools, toolsLoading: false })
    } catch {
      set({ toolsLoading: false })
    }
  },

  loadHeuristics: async () => {
    set({ heuristicsLoading: true })
    try {
      const heuristics = await fetchConvertHeuristics()
      set({ heuristics, heuristicsLoading: false })
    } catch {
      set({ heuristicsLoading: false })
    }
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
    set({ scanning: true, scanError: null, scanResult: null })
    try {
      const result = await scanDicomDirectory(sourceDir)
      set({ scanResult: result, scanning: false })
    } catch (e) {
      set({ scanError: String(e), scanning: false })
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

  clearScan: () => set({ scanResult: null, scanError: null }),

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
    // This is called from ConvertForm with the current form values.
    // The caller passes the params directly; avoid saving an empty config.
    if (!params) {
      return
    }
    try {
      await saveConvertRunConfig({ name, description, params })
      get().loadSavedConfigs()
    } catch (e) {
      // silently fail — UI will show the error via the save button
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
            maxWorkers: Number(batch.max_workers) || 2,
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
      // Single run configs could be loaded into the convert form in the future
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
