/** DICOM-to-BIDS conversion manager store. */
import { create } from 'zustand'
import type {
  ToolStatus,
  HeuristicInfo,
  ConvertManifestSummary,
  ConvertManifestDetail,
  ConvertEvent,
  DicomScanResult,
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
} from '../api/client'

type Tab = 'tools' | 'heuristics' | 'scan' | 'manifests' | 'convert'

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
}))
