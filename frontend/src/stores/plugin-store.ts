/** Plugin metadata store — fetched once and cached. */
import { create } from 'zustand'
import type { PluginMetadata, StageInfo } from '../api/types'
import type { FieldValues } from '../api/client'
import { fetchPlugins, fetchStages, fetchFieldValues } from '../api/client'

interface PluginState {
  plugins: PluginMetadata
  stages: StageInfo[]
  fieldValues: FieldValues
  loaded: boolean
  loading: boolean
  error: string | null
  load: () => Promise<void>
}

export const usePluginStore = create<PluginState>((set, get) => ({
  plugins: {},
  stages: [],
  fieldValues: {},
  loaded: false,
  loading: false,
  error: null,
  load: async () => {
    if (get().loaded || get().loading) return
    set({ loading: true, error: null })
    try {
      const [plugins, stages] = await Promise.all([fetchPlugins(), fetchStages()])
      set({ plugins, stages, loaded: true, loading: false })
      // Fetch field values in background — non-critical, don't block plugin load
      fetchFieldValues().then((fv) => set({ fieldValues: fv })).catch(() => {})
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },
}))
