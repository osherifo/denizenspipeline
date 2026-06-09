/** Study config store — backs the StudyComposer view.
 *
 * Shape matches the YAML the study orchestrator expects:
 *
 *   study: <name>
 *   groups: [{ name, config: <path>, subjects?: […] }, …]
 *   study_analyze: [{ name, params }]
 *   study_report: [{ name, params }]
 *   output_dir: <path>
 */
import { create } from 'zustand'
import type { StudyConfig, StudyGroupRef, StudyPluginConfig } from '../api/types'
import { validateConfig, configToYaml, configFromYaml } from '../api/client'


const EMPTY_STUDY: StudyConfig = {
  study: '',
  groups: [],
  study_analyze: [],
  study_report: [],
  output_dir: './results',
}

interface StudyConfigState {
  config: StudyConfig
  yamlString: string
  validationErrors: string[]
  yamlErrors: string[]
  isDirty: boolean
  yamlSyncing: boolean
  yamlEditing: boolean

  setField: (path: string, value: unknown) => void
  setConfig: (config: StudyConfig) => void

  addGroupRef: (ref: StudyGroupRef) => void
  removeGroupRef: (index: number) => void
  updateGroupRef: (index: number, ref: StudyGroupRef) => void
  reorderGroupRefs: (from: number, to: number) => void

  addStudyAnalyzer: (plugin: StudyPluginConfig) => void
  removeStudyAnalyzer: (index: number) => void
  updateStudyAnalyzer: (index: number, plugin: StudyPluginConfig) => void

  addStudyReporter: (plugin: StudyPluginConfig) => void
  removeStudyReporter: (index: number) => void
  updateStudyReporter: (index: number, plugin: StudyPluginConfig) => void

  importYaml: (yaml: string) => Promise<void>
  setYamlDirect: (yaml: string) => void
  applyYaml: () => Promise<void>
  exportYaml: () => Promise<string>
  validate: () => Promise<string[]>
  reset: () => void
  syncYaml: () => Promise<void>
}

function deepSet(obj: any, path: string, value: unknown): any {
  const copy = JSON.parse(JSON.stringify(obj))
  const keys = path.split('.')
  let cur = copy
  for (let i = 0; i < keys.length - 1; i++) {
    if (!(keys[i] in cur)) cur[keys[i]] = {}
    cur = cur[keys[i]]
  }
  cur[keys[keys.length - 1]] = value
  return copy
}

export const useStudyConfigStore = create<StudyConfigState>((set, get) => ({
  config: { ...EMPTY_STUDY },
  yamlString: '',
  validationErrors: [],
  yamlErrors: [],
  isDirty: false,
  yamlSyncing: false,
  yamlEditing: false,

  setField: (path, value) => {
    set({ config: deepSet(get().config, path, value), isDirty: true })
  },
  setConfig: (config) => set({ config, isDirty: true }),

  addGroupRef: (ref) => {
    const config = { ...get().config }
    config.groups = [...(config.groups || []), ref]
    set({ config, isDirty: true })
  },
  removeGroupRef: (index) => {
    const config = { ...get().config }
    config.groups = (config.groups || []).filter((_, i) => i !== index)
    set({ config, isDirty: true })
  },
  updateGroupRef: (index, ref) => {
    const config = { ...get().config }
    const arr = [...(config.groups || [])]
    arr[index] = ref
    config.groups = arr
    set({ config, isDirty: true })
  },
  reorderGroupRefs: (from, to) => {
    const config = { ...get().config }
    const arr = [...(config.groups || [])]
    const [m] = arr.splice(from, 1)
    arr.splice(to, 0, m)
    config.groups = arr
    set({ config, isDirty: true })
  },

  addStudyAnalyzer: (plugin) => {
    const config = { ...get().config }
    config.study_analyze = [...(config.study_analyze || []), plugin]
    set({ config, isDirty: true })
  },
  removeStudyAnalyzer: (index) => {
    const config = { ...get().config }
    config.study_analyze = (config.study_analyze || []).filter((_, i) => i !== index)
    set({ config, isDirty: true })
  },
  updateStudyAnalyzer: (index, plugin) => {
    const config = { ...get().config }
    const arr = [...(config.study_analyze || [])]
    arr[index] = plugin
    config.study_analyze = arr
    set({ config, isDirty: true })
  },

  addStudyReporter: (plugin) => {
    const config = { ...get().config }
    config.study_report = [...(config.study_report || []), plugin]
    set({ config, isDirty: true })
  },
  removeStudyReporter: (index) => {
    const config = { ...get().config }
    config.study_report = (config.study_report || []).filter((_, i) => i !== index)
    set({ config, isDirty: true })
  },
  updateStudyReporter: (index, plugin) => {
    const config = { ...get().config }
    const arr = [...(config.study_report || [])]
    arr[index] = plugin
    config.study_report = arr
    set({ config, isDirty: true })
  },

  importYaml: async (yaml) => {
    const result = await configFromYaml(yaml)
    if (result.errors.length > 0) {
      set({ validationErrors: result.errors })
    } else {
      set({
        config: result.config as StudyConfig,
        yamlString: yaml,
        isDirty: false,
        validationErrors: [],
        yamlErrors: [],
        yamlEditing: false,
      })
    }
  },

  setYamlDirect: (yaml) => set({ yamlString: yaml, yamlEditing: true, yamlErrors: [] }),

  applyYaml: async () => {
    const yaml = get().yamlString
    try {
      const result = await configFromYaml(yaml)
      if (result.errors.length > 0) {
        set({ yamlErrors: result.errors })
      } else {
        set({
          config: result.config as StudyConfig,
          isDirty: false,
          yamlErrors: [],
          yamlEditing: false,
          validationErrors: [],
        })
      }
    } catch (e) {
      set({ yamlErrors: [String(e)] })
    }
  },

  exportYaml: async () => {
    const yaml = await configToYaml(get().config as unknown as Record<string, unknown>)
    set({ yamlString: yaml })
    return yaml
  },

  validate: async () => {
    const result = await validateConfig(get().config as unknown as Record<string, unknown>)
    set({ validationErrors: result.errors })
    return result.errors
  },

  reset: () => set({
    config: { ...EMPTY_STUDY },
    yamlString: '',
    validationErrors: [],
    yamlErrors: [],
    isDirty: false,
    yamlEditing: false,
  }),

  syncYaml: async () => {
    if (get().yamlSyncing) return
    set({ yamlSyncing: true })
    try {
      const yaml = await configToYaml(get().config as unknown as Record<string, unknown>)
      set({ yamlString: yaml, yamlSyncing: false })
    } catch {
      set({ yamlSyncing: false })
    }
  },
}))
