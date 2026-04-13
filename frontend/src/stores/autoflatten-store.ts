/** Autoflatten manager store. */
import { create } from 'zustand'
import {
  fetchAutoflattenDoctor,
  fetchAutoflattenStatus,
  runAutoflatten,
} from '../api/client'

type Tab = 'status' | 'run' | 'import'

interface ToolInfo {
  name: string
  available: boolean
  detail: string
}

interface SubjectStatus {
  subject: string
  subject_dir_exists: boolean
  has_surfaces: boolean
  surfaces: Record<string, boolean>
  flat_patches: Record<string, string>
  has_flat_patches: boolean
  pycortex_surface: string | null
}

interface RunResult {
  subject: string
  source: string
  hemispheres: string[]
  flat_patches: Record<string, string>
  visualizations: Record<string, string>
  pycortex_surface: string | null
  elapsed_s: number
}

interface AutoflattenState {
  tab: Tab

  // Doctor
  tools: ToolInfo[]
  toolsLoading: boolean

  // Status
  subjectStatus: SubjectStatus | null
  statusLoading: boolean
  statusError: string | null

  // Run
  running: boolean
  runResult: RunResult | null
  runError: string | null

  // Actions
  setTab: (tab: Tab) => void
  loadTools: () => Promise<void>
  checkStatus: (subjectsDir: string, subject: string) => Promise<void>
  startRun: (params: Parameters<typeof runAutoflatten>[0]) => Promise<void>
  clearRun: () => void
  clearStatus: () => void
}

export const useAutoflattenStore = create<AutoflattenState>((set) => ({
  tab: 'status',

  tools: [],
  toolsLoading: false,

  subjectStatus: null,
  statusLoading: false,
  statusError: null,

  running: false,
  runResult: null,
  runError: null,

  setTab: (tab) => set({ tab }),

  loadTools: async () => {
    set({ toolsLoading: true })
    try {
      const data = await fetchAutoflattenDoctor()
      set({ tools: data.tools, toolsLoading: false })
    } catch {
      set({ toolsLoading: false })
    }
  },

  checkStatus: async (subjectsDir, subject) => {
    set({ statusLoading: true, statusError: null, subjectStatus: null })
    try {
      const status = await fetchAutoflattenStatus({ subjects_dir: subjectsDir, subject })
      set({ subjectStatus: status, statusLoading: false })
    } catch (e) {
      set({ statusError: String(e), statusLoading: false })
    }
  },

  startRun: async (params) => {
    set({ running: true, runError: null, runResult: null })
    try {
      const data = await runAutoflatten(params)
      set({ runResult: data.result, running: false })
    } catch (e) {
      set({ runError: String(e), running: false })
    }
  },

  clearRun: () => set({ runResult: null, runError: null, running: false }),
  clearStatus: () => set({ subjectStatus: null, statusError: null }),
}))
