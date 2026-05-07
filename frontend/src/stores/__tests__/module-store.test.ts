import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { useModuleStore } from '../module-store'

describe('useModuleStore', () => {
  it('initial state is empty + not loaded', () => {
    const s = useModuleStore.getState()
    expect(s.modules).toEqual({})
    expect(s.stages).toEqual([])
    expect(s.fieldValues).toEqual({})
    expect(s.loaded).toBe(false)
    expect(s.loading).toBe(false)
  })

  it('load fetches modules + stages and marks loaded', async () => {
    await useModuleStore.getState().load()
    const s = useModuleStore.getState()
    expect(s.loaded).toBe(true)
    expect(s.loading).toBe(false)
    expect(Object.keys(s.modules).length).toBeGreaterThan(0)
    expect(s.stages).toHaveLength(7)
  })

  it('load eventually populates fieldValues in background', async () => {
    await useModuleStore.getState().load()
    await new Promise((r) => setTimeout(r, 0))
    const s = useModuleStore.getState()
    expect(s.fieldValues.experiment).toContain('reading_en')
  })

  it('load is idempotent — second call is a no-op', async () => {
    let calls = 0
    server.use(
      http.get('/api/modules', () => {
        calls++
        return HttpResponse.json({})
      }),
    )
    await useModuleStore.getState().load()
    await useModuleStore.getState().load()
    expect(calls).toBe(1)
  })

  it('load sets error on fetch failure', async () => {
    server.use(http.get('/api/modules', () => HttpResponse.text('boom', { status: 500 })))
    await useModuleStore.getState().load()
    const s = useModuleStore.getState()
    expect(s.error).toMatch(/500/)
    expect(s.loading).toBe(false)
    expect(s.loaded).toBe(false)
  })
})
