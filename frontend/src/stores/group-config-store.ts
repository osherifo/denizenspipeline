/** Group config store — backs the GroupComposer view.
 *
 * Shape matches the YAML the orchestrator expects:
 *
 *   group: <name>
 *   subjects: [s1, s2, …]
 *   subject_template: { …subject pipeline… }
 *   subject_overrides: { s1: {…}, … }
 *   group_analyze: [{ name, params }]
 *   group_report: [{ name, params }]
 *   output_dir: <path>
 *
 * The right-pane YAML editor is the source of truth for
 * ``subject_template`` and ``subject_overrides`` in this MVP — the
 * scope-specific fields (group, subjects, output_dir, group_analyze,
 * group_report) get structured form controls. Later phases can lift
 * the subject_template into the full subject-stage composer.
 */
import { create } from 'zustand'
import type { GroupConfig, GroupPluginConfig } from '../api/types'
import { validateConfig, configToYaml, configFromYaml } from '../api/client'


const EMPTY_GROUP: GroupConfig = {
  group: '',
  subjects: [],
  subject_template: {},
  subject_overrides: {},
  group_analyze: [],
  group_report: [],
  output_dir: './results',
}

interface GroupConfigState {
  config: GroupConfig
  yamlString: string
  validationErrors: string[]
  yamlErrors: string[]
  isDirty: boolean
  yamlSyncing: boolean
  yamlEditing: boolean

  setField: (path: string, value: unknown) => void
  setConfig: (config: GroupConfig) => void

  addGroupAnalyzer: (plugin: GroupPluginConfig) => void
  removeGroupAnalyzer: (index: number) => void
  updateGroupAnalyzer: (index: number, plugin: GroupPluginConfig) => void

  addGroupReporter: (plugin: GroupPluginConfig) => void
  removeGroupReporter: (index: number) => void
  updateGroupReporter: (index: number, plugin: GroupPluginConfig) => void

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

export const useGroupConfigStore = create<GroupConfigState>((set, get) => ({
  config: { ...EMPTY_GROUP },
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

  addGroupAnalyzer: (plugin) => {
    const config = { ...get().config }
    config.group_analyze = [...(config.group_analyze || []), plugin]
    set({ config, isDirty: true })
  },
  removeGroupAnalyzer: (index) => {
    const config = { ...get().config }
    config.group_analyze = (config.group_analyze || []).filter((_, i) => i !== index)
    set({ config, isDirty: true })
  },
  updateGroupAnalyzer: (index, plugin) => {
    const config = { ...get().config }
    const arr = [...(config.group_analyze || [])]
    arr[index] = plugin
    config.group_analyze = arr
    set({ config, isDirty: true })
  },

  addGroupReporter: (plugin) => {
    const config = { ...get().config }
    config.group_report = [...(config.group_report || []), plugin]
    set({ config, isDirty: true })
  },
  removeGroupReporter: (index) => {
    const config = { ...get().config }
    config.group_report = (config.group_report || []).filter((_, i) => i !== index)
    set({ config, isDirty: true })
  },
  updateGroupReporter: (index, plugin) => {
    const config = { ...get().config }
    const arr = [...(config.group_report || [])]
    arr[index] = plugin
    config.group_report = arr
    set({ config, isDirty: true })
  },

  importYaml: async (yaml) => {
    const result = await configFromYaml(yaml)
    if (result.errors.length > 0) {
      set({ validationErrors: result.errors })
    } else {
      set({
        config: result.config as GroupConfig,
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
          config: result.config as GroupConfig,
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
    config: { ...EMPTY_GROUP },
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
