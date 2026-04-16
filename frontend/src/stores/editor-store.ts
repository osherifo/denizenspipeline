/** Module editor store. */
import { create } from 'zustand'
import type { CodeValidationResult, UserModule, ParamSchema } from '../api/types'
import {
  validateModuleCode,
  saveModule,
  fetchUserModules,
  fetchUserModuleCode,
  deleteUserModule,
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

  // User modules
  userModules: UserModule[]
  loadingModules: boolean

  // Templates
  templateCategories: string[]

  // Actions
  setCode: (code: string) => void
  setName: (name: string) => void
  setCategory: (category: string) => void
  validate: () => Promise<CodeValidationResult>
  save: () => Promise<void>
  loadUserModules: () => Promise<void>
  openModule: (name: string) => Promise<void>
  deleteModule: (name: string) => Promise<void>
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
  userModules: [],
  loadingModules: false,
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
      const result = await validateModuleCode(get().code, get().currentCategory ?? undefined)
      set({ validation: result, validating: false })
      return result
    } catch (e) {
      const result: CodeValidationResult = {
        valid: false,
        errors: [String(e)],
        warnings: [],
        module_name: null,
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
      set({ saveError: 'Module name is required' })
      return
    }
    if (!currentCategory) {
      set({ saveError: 'Module category is required' })
      return
    }

    try {
      await saveModule(code, currentName, currentCategory)
      set({ saveSuccess: true, isDirty: false })
      // Refresh list
      get().loadUserModules()
    } catch (e: any) {
      const detail = e?.message || String(e)
      set({ saveError: detail })
    }
  },

  loadUserModules: async () => {
    set({ loadingModules: true })
    try {
      const userMods = await fetchUserModules()
      set({ userModules: userMods, loadingModules: false })
    } catch {
      set({ loadingModules: false })
    }
  },

  openModule: async (name) => {
    try {
      const { code } = await fetchUserModuleCode(name)
      // Find the module to get category
      const module = get().userModules.find((p) => p.name === name)
      set({
        code,
        currentName: name,
        currentCategory: module?.category ?? null,
        isDirty: false,
        validation: null,
        saveError: null,
        saveSuccess: false,
      })
    } catch (e) {
      set({ saveError: String(e) })
    }
  },

  deleteModule: async (name) => {
    try {
      await deleteUserModule(name)
      const { currentName } = get()
      if (currentName === name) {
        set({ code: '', currentName: '', currentCategory: null, isDirty: false, validation: null })
      }
      get().loadUserModules()
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
