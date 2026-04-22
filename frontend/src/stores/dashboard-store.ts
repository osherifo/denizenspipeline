/** Experiment dashboard store. */
import { create } from 'zustand'
import type { ConfigSummary, ConfigDetail, RunSummary, RunEvent, StageStatus } from '../api/types'
import {
  fetchConfigs,
  fetchConfigDetail,
  validateConfigFile,
  startRunFromConfig,
  fetchRuns,
  fetchRun,
  connectRunWs,
} from '../api/client'

const ALL_STAGES = ['stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report']

function deriveStageStatuses(events: RunEvent[]): Record<string, StageStatus> {
  const statuses: Record<string, StageStatus> = {}
  for (const stage of ALL_STAGES) {
    statuses[stage] = { status: 'pending', detail: '', elapsed_s: 0 }
  }
  for (const event of events) {
    if (!event.stage) continue
    if (event.event === 'stage_start') {
      statuses[event.stage] = { ...statuses[event.stage], status: 'running' }
    } else if (event.event === 'stage_done') {
      statuses[event.stage] = { status: 'done', detail: event.detail ?? '', elapsed_s: event.elapsed ?? 0 }
    } else if (event.event === 'stage_fail') {
      statuses[event.stage] = { status: 'failed', detail: event.error ?? '', elapsed_s: event.elapsed ?? 0 }
    } else if (event.event === 'stage_warn') {
      statuses[event.stage] = { status: 'warning', detail: event.detail ?? '', elapsed_s: event.elapsed ?? 0 }
    }
  }
  return statuses
}

interface DashboardState {
  // Configs
  configs: ConfigSummary[]
  selectedConfig: ConfigDetail | null
  selectedFilename: string | null
  configsLoading: boolean
  configsError: string | null

  // Validation
  validationErrors: string[] | null
  validating: boolean

  // Runs for selected config
  configRuns: RunSummary[]
  selectedRun: RunSummary | null
  runsLoading: boolean

  // Live run
  liveRunId: string | null
  liveEvents: RunEvent[]
  stageStatuses: Record<string, StageStatus>
  liveStartTime: number | null
  completedRun: RunSummary | null

  // Actions
  loadConfigs: () => Promise<void>
  selectConfig: (filename: string) => Promise<void>
  clearSelection: () => void
  loadConfigRuns: (experiment: string, subject: string) => Promise<void>
  selectRun: (runId: string) => Promise<void>
  clearRunSelection: () => void
  runConfig: (configPath: string, overrides?: Record<string, unknown>) => Promise<void>
  validateConfig: (filename: string) => Promise<void>
  rescan: () => Promise<void>
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  configs: [],
  selectedConfig: null,
  selectedFilename: null,
  configsLoading: false,
  configsError: null,
  validationErrors: null,
  validating: false,
  configRuns: [],
  selectedRun: null,
  runsLoading: false,
  liveRunId: null,
  liveEvents: [],
  stageStatuses: {},
  liveStartTime: null,
  completedRun: null,

  loadConfigs: async () => {
    set({ configsLoading: true, configsError: null })
    try {
      const configs = await fetchConfigs()
      set({ configs, configsLoading: false })
    } catch (e) {
      set({ configsError: String(e), configsLoading: false })
    }
  },

  selectConfig: async (filename) => {
    set({ selectedFilename: filename, validationErrors: null, selectedRun: null })
    try {
      const detail = await fetchConfigDetail(filename)
      set({ selectedConfig: detail })

      // Load runs for this config's experiment+subject
      const config = detail.config as Record<string, any>
      const experiment = config.experiment || ''
      const subject = config.subject || ''
      if (experiment || subject) {
        get().loadConfigRuns(experiment, subject)
      } else {
        set({ configRuns: [] })
      }
    } catch (e) {
      set({ selectedConfig: null, configsError: String(e) })
    }
  },

  clearSelection: () => {
    set({
      selectedConfig: null,
      selectedFilename: null,
      configRuns: [],
      selectedRun: null,
      validationErrors: null,
    })
  },

  loadConfigRuns: async (experiment, subject) => {
    set({ runsLoading: true })
    try {
      const runs = await fetchRuns({ experiment, subject, limit: 50 })
      set({ configRuns: runs, runsLoading: false })
    } catch {
      set({ configRuns: [], runsLoading: false })
    }
  },

  selectRun: async (runId) => {
    try {
      const run = await fetchRun(runId)
      set({ selectedRun: run })
    } catch {
      // ignore
    }
  },

  clearRunSelection: () => set({ selectedRun: null }),

  runConfig: async (configPath, overrides) => {
    try {
      const result = await startRunFromConfig(configPath, overrides)
      set({
        liveRunId: result.run_id,
        liveEvents: [],
        stageStatuses: deriveStageStatuses([]),
        liveStartTime: Date.now(),
        completedRun: null,
      })

      // Subscribe to WebSocket
      const ws = connectRunWs(result.run_id)
      ws.onmessage = (msg) => {
        const event: RunEvent = JSON.parse(msg.data)
        set((s) => {
          const events = [...s.liveEvents, event]
          return {
            liveEvents: events,
            stageStatuses: deriveStageStatuses(events),
          }
        })
        if (event.event === 'run_done' || event.event === 'run_failed') {
          ws.close()
          set({ liveRunId: null, liveStartTime: null })
          // Refresh configs (run counts) and runs, then auto-load the completed run
          get().loadConfigs()
          const cfg = get().selectedConfig
          if (cfg) {
            const config = cfg.config as Record<string, any>
            const experiment = config.experiment || ''
            const subject = config.subject || ''
            get().loadConfigRuns(experiment, subject).then(() => {
              // The newest run is first — fetch its full detail
              const runs = get().configRuns
              if (runs.length > 0) {
                fetchRun(runs[0].run_id).then((run) => {
                  set({ completedRun: run })
                }).catch(() => {})
              }
            })
          }
        }
      }
      ws.onerror = () => {
        set({ liveRunId: null, liveStartTime: null })
      }
    } catch (e) {
      set({ configsError: String(e) })
    }
  },

  validateConfig: async (filename) => {
    set({ validating: true, validationErrors: null })
    try {
      const result = await validateConfigFile(filename)
      set({ validationErrors: result.errors, validating: false })
    } catch (e) {
      set({ validationErrors: [String(e)], validating: false })
    }
  },

  rescan: async () => {
    set({ configsLoading: true })
    try {
      const configs = await fetchConfigs()
      set({ configs, configsLoading: false })
    } catch (e) {
      set({ configsError: String(e), configsLoading: false })
    }
  },
}))
