/** Experiment dashboard store. */
import { create } from 'zustand'
import type {
  ConfigSummary, ConfigDetail, RunSummary, RunEvent, StageStatus,
  GroupRunListing, StudyRunListing,
} from '../api/types'
import {
  fetchConfigs,
  fetchConfigDetail,
  validateConfigFile,
  startRunFromConfig,
  fetchRuns,
  fetchRun,
  fetchGroupRuns,
  fetchStudyRuns,
  fetchInFlightRun,
  connectRunWs,
} from '../api/client'

const ALL_STAGES = ['stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report']

// Tracks the WebSocket of the run we're currently attached to. If
// attachToInFlightRun() fires again before the prior run finishes,
// we close the old socket so its replayed/incoming events don't bleed
// into the new run's liveEvents stream.
let activeWs: WebSocket | null = null
let activeWsRunId: string | null = null

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
  // Group-invocation listings for the selected group config. Empty when
  // the selected config is a subject config.
  groupConfigRuns: GroupRunListing[]
  // Study-invocation listings for the selected study config. Empty when
  // the selected config is not a study config.
  studyConfigRuns: StudyRunListing[]
  selectedRun: RunSummary | null
  runsLoading: boolean

  // Live run
  liveRunId: string | null
  // The actual run_id of the most recent run, preserved AFTER
  // run_done/run_failed (when liveRunId is cleared so the polling
  // stops). Used by panels that need to keep referring to the
  // finished run — e.g. TriageMatches polling /api/triage/<id>.
  lastRunId: string | null
  liveEvents: RunEvent[]
  stageStatuses: Record<string, StageStatus>
  liveStartTime: number | null
  completedRun: RunSummary | null

  // Actions
  loadConfigs: () => Promise<void>
  selectConfig: (filename: string) => Promise<void>
  clearSelection: () => void
  loadConfigRuns: (experiment: string, subject: string) => Promise<void>
  loadGroupConfigRuns: (groupName: string) => Promise<void>
  loadStudyConfigRuns: (studyName: string) => Promise<void>
  selectRun: (runId: string) => Promise<void>
  clearRunSelection: () => void
  runConfig: (configPath: string, overrides?: Record<string, unknown>) => Promise<void>
  attachToInFlightRun: (runId: string) => void
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
  groupConfigRuns: [],
  studyConfigRuns: [],
  selectedRun: null,
  runsLoading: false,
  liveRunId: null,
  lastRunId: null,
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
    // Wipe ALL run-scoped state on a config switch — otherwise the
    // previously-selected config's completed-run panel, live-event
    // stream, stage tracker, etc. bleed into the new selection's UI
    // until something else overwrites them.
    set({
      selectedFilename: filename,
      validationErrors: null,
      selectedRun: null,
      configRuns: [],
      groupConfigRuns: [],
      studyConfigRuns: [],
      liveEvents: [],
      stageStatuses: {},
      completedRun: null,
      // Selecting a different config detaches from any in-flight run
      // bound to the previous config: clear liveRunId so we stop
      // accepting new WS events as "live" for this view, and clear
      // lastRunId so the run-history bindings on the new config start
      // fresh. The WS socket itself is closed in attachToInFlightRun
      // (or via run_done/run_failed) — see comment there.
      liveRunId: null,
      lastRunId: null,
      liveStartTime: null,
    })
    try {
      const detail = await fetchConfigDetail(filename)
      set({ selectedConfig: detail })

      const config = detail.config as Record<string, any>
      const isStudy =
        typeof config.study === 'string' && Array.isArray(config.groups)
      const isGroup = !isStudy
        && typeof config.group === 'string'
        && Array.isArray(config.subjects)
      if (isStudy) {
        // Study configs: list one row per study invocation
        // (`study_runs/<name>/<timestamp>/`).
        get().loadStudyConfigRuns(config.study || '')
      } else if (isGroup) {
        // Group configs: list one row per group invocation
        // (`group_runs/<name>/<timestamp>/`) — NOT per-subject results.
        get().loadGroupConfigRuns(config.group || '')
      } else {
        const experiment = config.experiment || ''
        const subject = config.subject || ''
        if (experiment || subject) {
          get().loadConfigRuns(experiment, subject)
        }
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
      groupConfigRuns: [],
      studyConfigRuns: [],
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

  loadGroupConfigRuns: async (groupName) => {
    set({ runsLoading: true })
    try {
      const runs = await fetchGroupRuns({ name: groupName })
      set({ groupConfigRuns: runs, runsLoading: false })
    } catch {
      set({ groupConfigRuns: [], runsLoading: false })
    }
  },

  loadStudyConfigRuns: async (studyName) => {
    set({ runsLoading: true })
    try {
      const runs = await fetchStudyRuns({ name: studyName })
      set({ studyConfigRuns: runs, runsLoading: false })
    } catch {
      set({ studyConfigRuns: [], runsLoading: false })
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
        lastRunId: result.run_id,
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
            const isStudy =
              typeof config.study === 'string' && Array.isArray(config.groups)
            const isGroup = !isStudy
              && typeof config.group === 'string'
              && Array.isArray(config.subjects)
            if (isStudy) {
              get().loadStudyConfigRuns(config.study || '')
            } else if (isGroup) {
              get().loadGroupConfigRuns(config.group || '')
            } else {
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
      }
      ws.onerror = () => {
        set({ liveRunId: null, liveStartTime: null })
      }
    } catch (e) {
      set({ configsError: String(e) })
    }
  },

  attachToInFlightRun: (runId) => {
    // Latch onto a run already in flight (e.g. CLI-launched group /
    // study run, or one started in another tab). The backend WS at
    // /ws/runs/{run_id} replays handle.events on connect and then
    // streams new events as they happen — both flow into liveEvents.
    //
    // Two things to get right so it doesn't look like a re-run:
    //   1. liveStartTime is the *actual* started_at, not Date.now(),
    //      so the elapsed timer reads correctly from second 1.
    //   2. Replayed historical events arrive as separate WS messages
    //      back-to-back; we batch them with a microtask so React only
    //      re-renders once with the final state instead of animating
    //      pending → running → done for every stage in real time.
    //
    // Seed liveStartTime to "now" up front (overwritten as soon as
    // fetchInFlightRun resolves) so the live panel renders something
    // meaningful even before the detail call lands.
    set({
      liveRunId: runId,
      lastRunId: runId,
      liveEvents: [],
      stageStatuses: deriveStageStatuses([]),
      liveStartTime: Date.now(),
      completedRun: null,
    })

    fetchInFlightRun(runId).then((detail) => {
      const startMs = (detail.started_at || 0) * 1000
      if (startMs > 0) set({ liveStartTime: startMs })
    }).catch(() => { /* keep the Date.now() fallback */ })

    // If a previous attach hasn't finished, close its socket so its
    // events can't keep landing in liveEvents.
    if (activeWs && activeWsRunId !== runId) {
      try { activeWs.close() } catch { /* ignore */ }
    }
    const ws = connectRunWs(runId)
    activeWs = ws
    activeWsRunId = runId
    let pending: RunEvent[] = []
    let scheduled = false

    const flush = () => {
      scheduled = false
      if (pending.length === 0) return
      const batch = pending
      pending = []
      set((s) => {
        const events = [...s.liveEvents, ...batch]
        return {
          liveEvents: events,
          stageStatuses: deriveStageStatuses(events),
        }
      })
    }

    ws.onmessage = (msg) => {
      // If the user has moved on to a different run, drop the event.
      // Defensive: ws.close() above should prevent further messages,
      // but the close handshake can race the next batch of replays.
      if (activeWsRunId !== runId) return
      const event: RunEvent = JSON.parse(msg.data)
      pending.push(event)
      if (!scheduled) {
        scheduled = true
        // Microtask-ish batching: the WS replay sprays N historical
        // events back-to-back; a single 0ms timeout coalesces them
        // into one React update. New live events still feel responsive
        // (sub-frame latency).
        setTimeout(flush, 0)
      }
      if (event.event === 'run_done' || event.event === 'run_failed') {
        // Drain anything still in the buffer + then tear down.
        setTimeout(() => {
          flush()
          ws.close()
          if (activeWs === ws) { activeWs = null; activeWsRunId = null }
          set({ liveRunId: null, liveStartTime: null })
          get().loadConfigs()
        }, 0)
      }
    }
    ws.onerror = () => {
      if (activeWs === ws) { activeWs = null; activeWsRunId = null }
      set({ liveRunId: null, liveStartTime: null })
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
