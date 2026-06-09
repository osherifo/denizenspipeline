/** Study-run history store — backs the Study Runs view. */

import { create } from 'zustand'
import type { StudyRunListing, StudyRunDetail } from '../api/types'
import { fetchStudyRuns, fetchStudyRun } from '../api/client'

interface StudyRunsState {
  runs: StudyRunListing[]
  selected: StudyRunDetail | null
  selectedKey: string | null   // "<study_name>/<run_id>"
  loading: boolean
  loadingDetail: boolean
  error: string | null

  loadRuns: () => Promise<void>
  selectRun: (name: string, runId: string) => Promise<void>
  clearSelection: () => void
}

function selectionKey(name: string, runId: string): string {
  return `${name}/${runId}`
}

export const useStudyRunsStore = create<StudyRunsState>((set, get) => ({
  runs: [],
  selected: null,
  selectedKey: null,
  loading: false,
  loadingDetail: false,
  error: null,

  loadRuns: async () => {
    set({ loading: true, error: null })
    try {
      const runs = await fetchStudyRuns()
      set({ runs, loading: false })
    } catch (e) {
      set({ loading: false, error: (e as Error).message })
    }
  },

  selectRun: async (name: string, runId: string) => {
    const key = selectionKey(name, runId)
    if (get().selectedKey === key && get().selected) return
    set({ loadingDetail: true, selectedKey: key, error: null })
    try {
      const detail = await fetchStudyRun(name, runId)
      set({ selected: detail, loadingDetail: false })
    } catch (e) {
      set({ loadingDetail: false, error: (e as Error).message })
    }
  },

  clearSelection: () => set({ selected: null, selectedKey: null }),
}))
