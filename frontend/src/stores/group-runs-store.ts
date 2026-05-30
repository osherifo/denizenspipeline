/** Group-run history store — Phase 4 view backing. */

import { create } from 'zustand'
import type { GroupRunListing, GroupRunDetail } from '../api/types'
import { fetchGroupRuns, fetchGroupRun } from '../api/client'

interface GroupRunsState {
  runs: GroupRunListing[]
  selected: GroupRunDetail | null
  selectedName: string | null
  loading: boolean
  loadingDetail: boolean
  error: string | null

  loadRuns: () => Promise<void>
  selectRun: (name: string) => Promise<void>
  clearSelection: () => void
}

export const useGroupRunsStore = create<GroupRunsState>((set, get) => ({
  runs: [],
  selected: null,
  selectedName: null,
  loading: false,
  loadingDetail: false,
  error: null,

  loadRuns: async () => {
    set({ loading: true, error: null })
    try {
      const runs = await fetchGroupRuns()
      set({ runs, loading: false })
    } catch (e) {
      set({ loading: false, error: (e as Error).message })
    }
  },

  selectRun: async (name: string) => {
    if (get().selectedName === name && get().selected) return
    set({ loadingDetail: true, selectedName: name, error: null })
    try {
      const detail = await fetchGroupRun(name)
      set({ selected: detail, loadingDetail: false })
    } catch (e) {
      set({ loadingDetail: false, error: (e as Error).message })
    }
  },

  clearSelection: () => set({ selected: null, selectedName: null }),
}))
