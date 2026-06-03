/** Group-run history store — Phase 4 view backing. */

import { create } from 'zustand'
import type { GroupRunListing, GroupRunDetail } from '../api/types'
import { fetchGroupRuns, fetchGroupRun } from '../api/client'

interface GroupRunsState {
  runs: GroupRunListing[]
  selected: GroupRunDetail | null
  selectedKey: string | null   // "<group_name>/<run_id>" or "<group_name>" for legacy
  loading: boolean
  loadingDetail: boolean
  error: string | null

  loadRuns: () => Promise<void>
  selectRun: (name: string, runId: string) => Promise<void>
  clearSelection: () => void
}

function selectionKey(name: string, runId: string): string {
  return runId ? `${name}/${runId}` : name
}

export const useGroupRunsStore = create<GroupRunsState>((set, get) => ({
  runs: [],
  selected: null,
  selectedKey: null,
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

  selectRun: async (name: string, runId: string) => {
    const key = selectionKey(name, runId)
    if (get().selectedKey === key && get().selected) return
    set({ loadingDetail: true, selectedKey: key, error: null })
    try {
      const detail = await fetchGroupRun(name, runId || undefined)
      set({ selected: detail, loadingDetail: false })
    } catch (e) {
      set({ loadingDetail: false, error: (e as Error).message })
    }
  },

  clearSelection: () => set({ selected: null, selectedKey: null }),
}))
