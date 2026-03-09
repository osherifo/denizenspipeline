/** Plugin metadata store — fetched once and cached. */
import { create } from 'zustand'
import type { PluginMetadata, StageInfo } from '../api/types'
import { fetchPlugins, fetchStages } from '../api/client'

interface PluginState {
  plugins: PluginMetadata
  stages: StageInfo[]
  loaded: boolean
  loading: boolean
  error: string | null
  load: () => Promise<void>
}

export const usePluginStore = create<PluginState>((set, get) => ({
  plugins: {},
  stages: [],
  loaded: false,
  loading: false,
  error: null,
  load: async () => {
    if (get().loaded || get().loading) return
    set({ loading: true, error: null })
    try {
      const [plugins, stages] = await Promise.all([fetchPlugins(), fetchStages()])
      set({ plugins, stages, loaded: true, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },
}))
