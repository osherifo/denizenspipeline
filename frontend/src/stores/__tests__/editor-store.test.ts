import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { useEditorStore } from '../editor-store'

describe('useEditorStore', () => {
  it('initial state', () => {
    const s = useEditorStore.getState()
    expect(s.code).toBe('')
    expect(s.currentName).toBe('')
    expect(s.currentCategory).toBeNull()
    expect(s.isDirty).toBe(false)
    expect(s.validation).toBeNull()
    expect(s.userModules).toEqual([])
  })

  it('setCode updates code and marks dirty', () => {
    useEditorStore.getState().setCode('class X: pass')
    const s = useEditorStore.getState()
    expect(s.code).toBe('class X: pass')
    expect(s.isDirty).toBe(true)
    expect(s.saveSuccess).toBe(false)
  })

  it('setName updates name and marks dirty', () => {
    useEditorStore.getState().setName('my_mod')
    expect(useEditorStore.getState().currentName).toBe('my_mod')
    expect(useEditorStore.getState().isDirty).toBe(true)
  })

  it('setCategory updates category', () => {
    useEditorStore.getState().setCategory('feature_extractors')
    expect(useEditorStore.getState().currentCategory).toBe('feature_extractors')
  })

  it('validate calls API and stores result', async () => {
    useEditorStore.getState().setCode('class X: pass')
    const r = await useEditorStore.getState().validate()
    expect(r.valid).toBe(true)
    expect(useEditorStore.getState().validation).not.toBeNull()
    expect(useEditorStore.getState().validating).toBe(false)
  })

  it('validate handles fetch failure gracefully', async () => {
    server.use(
      http.post('/api/modules/validate-code', () =>
        HttpResponse.text('boom', { status: 500 }),
      ),
    )
    const r = await useEditorStore.getState().validate()
    expect(r.valid).toBe(false)
    expect(r.errors.length).toBeGreaterThan(0)
  })

  it('save fails when name missing', async () => {
    useEditorStore.getState().setCode('class X: pass')
    useEditorStore.getState().setCategory('feature_extractors')
    await useEditorStore.getState().save()
    expect(useEditorStore.getState().saveError).toBe('Module name is required')
  })

  it('save fails when category missing', async () => {
    useEditorStore.getState().setCode('class X: pass')
    useEditorStore.getState().setName('m')
    await useEditorStore.getState().save()
    expect(useEditorStore.getState().saveError).toBe('Module category is required')
  })

  it('save persists module on success and clears dirty', async () => {
    useEditorStore.getState().setCode('class X: pass')
    useEditorStore.getState().setName('m')
    useEditorStore.getState().setCategory('feature_extractors')
    await useEditorStore.getState().save()
    expect(useEditorStore.getState().saveSuccess).toBe(true)
    expect(useEditorStore.getState().isDirty).toBe(false)
  })

  it('save sets saveError on API error', async () => {
    server.use(
      http.post('/api/modules/save', () => HttpResponse.text('nope', { status: 400 })),
    )
    useEditorStore.getState().setCode('class X: pass')
    useEditorStore.getState().setName('m')
    useEditorStore.getState().setCategory('feature_extractors')
    await useEditorStore.getState().save()
    expect(useEditorStore.getState().saveError).toMatch(/400/)
    expect(useEditorStore.getState().saveSuccess).toBe(false)
  })

  it('loadUserModules populates list', async () => {
    await useEditorStore.getState().loadUserModules()
    expect(useEditorStore.getState().userModules.length).toBeGreaterThan(0)
  })

  it('openModule loads code and category', async () => {
    await useEditorStore.getState().loadUserModules()
    await useEditorStore.getState().openModule('my_module')
    const s = useEditorStore.getState()
    expect(s.code).toContain('class X')
    expect(s.currentName).toBe('my_module')
    expect(s.isDirty).toBe(false)
  })

  it('deleteModule clears editor when current module is deleted', async () => {
    await useEditorStore.getState().loadUserModules()
    await useEditorStore.getState().openModule('my_module')
    await useEditorStore.getState().deleteModule('my_module')
    expect(useEditorStore.getState().code).toBe('')
    expect(useEditorStore.getState().currentName).toBe('')
  })

  it('newFromTemplate populates code from template', async () => {
    await useEditorStore.getState().newFromTemplate('feature_extractors', 'foo')
    const s = useEditorStore.getState()
    expect(s.code).toContain('template')
    expect(s.currentName).toBe('foo')
    expect(s.isDirty).toBe(true)
  })

  it('loadTemplateCategories populates list', async () => {
    await useEditorStore.getState().loadTemplateCategories()
    expect(useEditorStore.getState().templateCategories).toContain('feature_extractors')
  })

  it('reset clears editor state', () => {
    useEditorStore.getState().setCode('x')
    useEditorStore.getState().setName('m')
    useEditorStore.getState().reset()
    const s = useEditorStore.getState()
    expect(s.code).toBe('')
    expect(s.currentName).toBe('')
    expect(s.isDirty).toBe(false)
  })
})
