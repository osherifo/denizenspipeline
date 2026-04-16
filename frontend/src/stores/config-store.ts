/** Pipeline config store for the composer view. */
import { create } from 'zustand'
import type { PipelineConfig, FeatureConfig, StepConfig, AnalyzerConfig } from '../api/types'
import { validateConfig, configToYaml, configFromYaml } from '../api/client'

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

const EMPTY_CONFIG: PipelineConfig = {
  experiment: '',
  subject: '',
  stimulus: { loader: 'textgrid', language: 'en', modality: 'reading' },
  response: { loader: 'local' },
  features: [],
  split: { test_runs: [] },
  preparation: { type: 'default', trim_start: 5, trim_end: 5, delays: [1, 2, 3, 4], zscore: true },
  model: { type: 'bootstrap_ridge', params: {} },
  reporting: { formats: ['metrics'], output_dir: './results' },
}

interface ConfigState {
  config: PipelineConfig
  yamlString: string
  validationErrors: string[]
  yamlErrors: string[]
  isDirty: boolean
  yamlSyncing: boolean
  yamlEditing: boolean  // true while user is editing YAML directly

  setField: (path: string, value: unknown) => void
  setConfig: (config: PipelineConfig) => void

  addFeature: (feature: FeatureConfig) => void
  removeFeature: (index: number) => void
  updateFeature: (index: number, feature: FeatureConfig) => void
  reorderFeatures: (from: number, to: number) => void

  addStep: (step: StepConfig) => void
  removeStep: (index: number) => void
  updateStep: (index: number, step: StepConfig) => void
  reorderSteps: (from: number, to: number) => void

  addAnalyzer: (analyzer: AnalyzerConfig) => void
  removeAnalyzer: (index: number) => void
  updateAnalyzer: (index: number, analyzer: AnalyzerConfig) => void

  toggleReporter: (format: string) => void

  importYaml: (yaml: string) => Promise<void>
  setYamlDirect: (yaml: string) => void
  applyYaml: () => Promise<void>
  exportYaml: () => Promise<string>
  validate: () => Promise<string[]>
  reset: () => void
  syncYaml: () => Promise<void>
}

export const useConfigStore = create<ConfigState>((set, get) => ({
  config: { ...EMPTY_CONFIG },
  yamlString: '',
  validationErrors: [],
  yamlErrors: [],
  isDirty: false,
  yamlSyncing: false,
  yamlEditing: false,

  setField: (path, value) => {
    const newConfig = deepSet(get().config, path, value)
    set({ config: newConfig, isDirty: true })
  },

  setConfig: (config) => {
    set({ config, isDirty: true })
  },

  addFeature: (feature) => {
    const config = { ...get().config }
    config.features = [...(config.features || []), feature]
    set({ config, isDirty: true })
  },

  removeFeature: (index) => {
    const config = { ...get().config }
    config.features = (config.features || []).filter((_, i) => i !== index)
    set({ config, isDirty: true })
  },

  updateFeature: (index, feature) => {
    const config = { ...get().config }
    const features = [...(config.features || [])]
    features[index] = feature
    config.features = features
    set({ config, isDirty: true })
  },

  reorderFeatures: (from, to) => {
    const config = { ...get().config }
    const features = [...(config.features || [])]
    const [item] = features.splice(from, 1)
    features.splice(to, 0, item)
    config.features = features
    set({ config, isDirty: true })
  },

  addStep: (step) => {
    const config = { ...get().config }
    const prep = { ...(config.preparation || {}), type: 'pipeline' }
    prep.steps = [...(prep.steps || []), step]
    config.preparation = prep
    set({ config, isDirty: true })
  },

  removeStep: (index) => {
    const config = { ...get().config }
    const prep = { ...(config.preparation || {}) }
    prep.steps = (prep.steps || []).filter((_, i) => i !== index)
    config.preparation = prep
    set({ config, isDirty: true })
  },

  updateStep: (index, step) => {
    const config = { ...get().config }
    const prep = { ...(config.preparation || {}) }
    const steps = [...(prep.steps || [])]
    steps[index] = step
    prep.steps = steps
    config.preparation = prep
    set({ config, isDirty: true })
  },

  reorderSteps: (from, to) => {
    const config = { ...get().config }
    const prep = { ...(config.preparation || {}) }
    const steps = [...(prep.steps || [])]
    const [item] = steps.splice(from, 1)
    steps.splice(to, 0, item)
    prep.steps = steps
    config.preparation = prep
    set({ config, isDirty: true })
  },

  addAnalyzer: (analyzer) => {
    const config = { ...get().config }
    config.analysis = [...(config.analysis || []), analyzer]
    set({ config, isDirty: true })
  },

  removeAnalyzer: (index) => {
    const config = { ...get().config }
    config.analysis = (config.analysis || []).filter((_, i) => i !== index)
    set({ config, isDirty: true })
  },

  updateAnalyzer: (index, analyzer) => {
    const config = { ...get().config }
    const analysis = [...(config.analysis || [])]
    analysis[index] = analyzer
    config.analysis = analysis
    set({ config, isDirty: true })
  },

  toggleReporter: (format) => {
    const config = { ...get().config }
    const reporting = { ...(config.reporting || {}) }
    const formats = [...(reporting.formats || [])]
    const idx = formats.indexOf(format)
    if (idx >= 0) {
      formats.splice(idx, 1)
    } else {
      formats.push(format)
    }
    reporting.formats = formats
    config.reporting = reporting
    set({ config, isDirty: true })
  },

  importYaml: async (yaml) => {
    const result = await configFromYaml(yaml)
    if (result.errors.length > 0) {
      set({ validationErrors: result.errors })
    } else {
      set({ config: result.config, yamlString: yaml, isDirty: false, validationErrors: [], yamlErrors: [], yamlEditing: false })
    }
  },

  setYamlDirect: (yaml) => {
    set({ yamlString: yaml, yamlEditing: true, yamlErrors: [] })
  },

  applyYaml: async () => {
    const yaml = get().yamlString
    try {
      const result = await configFromYaml(yaml)
      if (result.errors.length > 0) {
        set({ yamlErrors: result.errors })
      } else {
        set({ config: result.config, isDirty: false, yamlErrors: [], yamlEditing: false, validationErrors: [] })
      }
    } catch (e) {
      set({ yamlErrors: [String(e)] })
    }
  },

  exportYaml: async () => {
    const yaml = await configToYaml(get().config)
    set({ yamlString: yaml })
    return yaml
  },

  validate: async () => {
    const result = await validateConfig(get().config)
    set({ validationErrors: result.errors })
    return result.errors
  },

  reset: () => {
    set({ config: { ...EMPTY_CONFIG }, yamlString: '', validationErrors: [], yamlErrors: [], isDirty: false, yamlEditing: false })
  },

  syncYaml: async () => {
    if (get().yamlSyncing) return
    set({ yamlSyncing: true })
    try {
      const yaml = await configToYaml(get().config)
      set({ yamlString: yaml, yamlSyncing: false })
    } catch {
      set({ yamlSyncing: false })
    }
  },
}))
