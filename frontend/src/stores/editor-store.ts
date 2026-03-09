/** Plugin editor store. */
import { create } from 'zustand'
import type { CodeValidationResult, UserPlugin, ParamSchema } from '../api/types'
import {
  validatePluginCode,
  savePlugin,
  fetchUserPlugins,
  fetchUserPluginCode,
  deleteUserPlugin,
  fetchTemplate,
  fetchTemplateCategories,
} from '../api/client'

interface EditorState {
  // Code
  code: string
  currentName: string
  currentCategory: string | null
  isDirty: boolean

  // Validation
  validation: CodeValidationResult | null
  validating: boolean

  // User plugins
  userPlugins: UserPlugin[]
  loadingPlugins: boolean

  // Templates
  templateCategories: string[]

  // Actions
  setCode: (code: string) => void
  setName: (name: string) => void
  setCategory: (category: string) => void
  validate: () => Promise<CodeValidationResult>
  save: () => Promise<void>
  loadUserPlugins: () => Promise<void>
  openPlugin: (name: string) => Promise<void>
  deletePlugin: (name: string) => Promise<void>
  newFromTemplate: (category: string, name: string) => Promise<void>
  loadTemplateCategories: () => Promise<void>
  reset: () => void

  // Status
  saveError: string | null
  saveSuccess: boolean
}

export const useEditorStore = create<EditorState>((set, get) => ({
  code: '',
  currentName: '',
  currentCategory: null,
  isDirty: false,
  validation: null,
  validating: false,
  userPlugins: [],
  loadingPlugins: false,
  templateCategories: [],
  saveError: null,
  saveSuccess: false,

  setCode: (code) => {
    set({ code, isDirty: true, saveSuccess: false })
  },

  setName: (name) => {
    set({ currentName: name, isDirty: true })
  },

  setCategory: (category) => {
    set({ currentCategory: category })
  },

  validate: async () => {
    set({ validating: true })
    try {
      const result = await validatePluginCode(get().code, get().currentCategory ?? undefined)
      set({ validation: result, validating: false })
      return result
    } catch (e) {
      const result: CodeValidationResult = {
        valid: false,
        errors: [String(e)],
        warnings: [],
        plugin_name: null,
        class_name: null,
        category: null,
        params: null,
      }
      set({ validation: result, validating: false })
      return result
    }
  },

  save: async () => {
    const { code, currentName, currentCategory, validation } = get()
    set({ saveError: null, saveSuccess: false })

    if (!currentName) {
      set({ saveError: 'Plugin name is required' })
      return
    }
    if (!currentCategory) {
      set({ saveError: 'Plugin category is required' })
      return
    }

    try {
      await savePlugin(code, currentName, currentCategory)
      set({ saveSuccess: true, isDirty: false })
      // Refresh list
      get().loadUserPlugins()
    } catch (e: any) {
      const detail = e?.message || String(e)
      set({ saveError: detail })
    }
  },

  loadUserPlugins: async () => {
    set({ loadingPlugins: true })
    try {
      const plugins = await fetchUserPlugins()
      set({ userPlugins: plugins, loadingPlugins: false })
    } catch {
      set({ loadingPlugins: false })
    }
  },

  openPlugin: async (name) => {
    try {
      const { code } = await fetchUserPluginCode(name)
      // Find the plugin to get category
      const plugin = get().userPlugins.find((p) => p.name === name)
      set({
        code,
        currentName: name,
        currentCategory: plugin?.category ?? null,
        isDirty: false,
        validation: null,
        saveError: null,
        saveSuccess: false,
      })
    } catch (e) {
      set({ saveError: String(e) })
    }
  },

  deletePlugin: async (name) => {
    try {
      await deleteUserPlugin(name)
      const { currentName } = get()
      if (currentName === name) {
        set({ code: '', currentName: '', currentCategory: null, isDirty: false, validation: null })
      }
      get().loadUserPlugins()
    } catch (e) {
      set({ saveError: String(e) })
    }
  },

  newFromTemplate: async (category, name) => {
    try {
      const result = await fetchTemplate(category, name)
      set({
        code: result.code,
        currentName: name,
        currentCategory: category,
        isDirty: true,
        validation: null,
        saveError: null,
        saveSuccess: false,
      })
    } catch (e) {
      set({ saveError: String(e) })
    }
  },

  loadTemplateCategories: async () => {
    try {
      const cats = await fetchTemplateCategories()
      set({ templateCategories: cats })
    } catch {
      // ignore
    }
  },

  reset: () => {
    set({
      code: '',
      currentName: '',
      currentCategory: null,
      isDirty: false,
      validation: null,
      saveError: null,
      saveSuccess: false,
    })
  },
}))
