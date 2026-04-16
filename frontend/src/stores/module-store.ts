/** Module metadata store — fetched once and cached. */
import { create } from 'zustand'
import type { ModuleMetadata, StageInfo } from '../api/types'
import type { FieldValues } from '../api/client'
import { fetchModules, fetchStages, fetchFieldValues } from '../api/client'

interface ModuleState {
  modules: ModuleMetadata
  stages: StageInfo[]
  fieldValues: FieldValues
  loaded: boolean
  loading: boolean
  error: string | null
  load: () => Promise<void>
}

export const useModuleStore = create<ModuleState>((set, get) => ({
  modules: {},
  stages: [],
  fieldValues: {},
  loaded: false,
  loading: false,
  error: null,
  load: async () => {
    if (get().loaded || get().loading) return
    set({ loading: true, error: null })
    try {
      const [modules, stages] = await Promise.all([fetchModules(), fetchStages()])
      set({ modules, stages, loaded: true, loading: false })
      // Fetch field values in background — non-critical, don't block module load
      fetchFieldValues().then((fv) => set({ fieldValues: fv })).catch(() => {})
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },
}))
