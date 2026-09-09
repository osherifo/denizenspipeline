import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { useConvertStore } from '../convert-store'
import { installMockWebSocket, uninstallMockWebSocket, mockWsServer } from '../../test/ws'

describe('useConvertStore', () => {
  beforeEach(() => installMockWebSocket())
  afterEach(() => uninstallMockWebSocket())

  it('initial state', () => {
    const s = useConvertStore.getState()
    expect(s.tab).toBe('heuristics')
    expect(s.batchJobs).toHaveLength(1)
    expect(s.batchShared.maxWorkers).toBe(2)
  })

  it('setTab changes tab', () => {
    useConvertStore.getState().setTab('heuristics')
    expect(useConvertStore.getState().tab).toBe('heuristics')
  })

  it('loadHeuristics populates list', async () => {
    await useConvertStore.getState().loadHeuristics()
    expect(useConvertStore.getState().heuristics.length).toBe(1)
  })

  describe('heuristic editor', () => {
    it('openHeuristic loads code', async () => {
      await useConvertStore.getState().openHeuristic('reading_heuristic')
      const s = useConvertStore.getState()
      expect(s.editorCode).toContain('heuristic')
      expect(s.editorName).toBe('reading_heuristic')
      expect(s.editorDirty).toBe(false)
    })

    it('newHeuristic loads template + marks dirty', async () => {
      await useConvertStore.getState().newHeuristic('my_study')
      const s = useConvertStore.getState()
      expect(s.editorCode).toContain('template')
      expect(s.editorName).toBe('my_study')
      expect(s.editorDirty).toBe(true)
    })

    it('setEditorCode updates code', () => {
      useConvertStore.getState().setEditorCode('# foo')
      expect(useConvertStore.getState().editorCode).toBe('# foo')
      expect(useConvertStore.getState().editorDirty).toBe(true)
    })

    it('saveHeuristic refuses empty name', async () => {
      useConvertStore.getState().setEditorCode('# x')
      await useConvertStore.getState().saveHeuristic()
      expect(useConvertStore.getState().editorError).toMatch(/required/)
    })

    it('saveHeuristic saves on success', async () => {
      useConvertStore.getState().setEditorName('h')
      useConvertStore.getState().setEditorCode('# x')
      await useConvertStore.getState().saveHeuristic()
      expect(useConvertStore.getState().editorSaveSuccess).toBe(true)
      expect(useConvertStore.getState().editorDirty).toBe(false)
    })

    it('openHeuristic fills the metadata strip from the listing', async () => {
      await useConvertStore.getState().loadHeuristics()
      await useConvertStore.getState().openHeuristic('reading_heuristic')
      const m = useConvertStore.getState().editorMeta
      expect(m.description).toBe('Reads stories')
      expect(m.version).toBe('2.1')
      expect(m.tasks).toBe('story, rest')
    })

    it('saveHeuristic sends sidecar metadata with tasks split into a list', async () => {
      let sent: Record<string, unknown> | null = null
      server.use(
        http.post('/api/convert/heuristics/save', async ({ request }) => {
          sent = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({ saved: true, name: 'h', path: '/tmp/h.py' })
        }),
      )
      useConvertStore.getState().setEditorName('h')
      useConvertStore.getState().setEditorCode('# x')
      useConvertStore.getState().setEditorMeta({ description: 'd', version: '3', tasks: 'a, b,, c' })
      await useConvertStore.getState().saveHeuristic()
      expect(sent).toMatchObject({ name: 'h', description: 'd', version: '3', tasks: ['a', 'b', 'c'] })
    })

    it('copyHeuristic reloads the list and opens the copy', async () => {
      await useConvertStore.getState().copyHeuristic('reading_heuristic', 'reading_v2')
      const s = useConvertStore.getState()
      expect(s.editorName).toBe('reading_v2')
      expect(s.editorCode).toBe('# heuristic')
      expect(s.editorError).toBeNull()
    })

    it('deleteHeuristic clears editor when current heuristic is deleted', async () => {
      useConvertStore.getState().setEditorName('h')
      useConvertStore.getState().setEditorCode('# x')
      await useConvertStore.getState().deleteHeuristic('h')
      expect(useConvertStore.getState().editorName).toBe('')
    })

    it('closeEditor resets editor state', () => {
      useConvertStore.getState().setEditorCode('# x')
      useConvertStore.getState().closeEditor()
      expect(useConvertStore.getState().editorCode).toBe('')
      expect(useConvertStore.getState().editorDirty).toBe(false)
    })
  })

  describe('scan + collect + run', () => {
    it('scanDicom starts a job, polls it and populates scanResult', async () => {
      await useConvertStore.getState().scanDicom('/tmp/dicom')
      const st = useConvertStore.getState()
      expect(st.scanResult?.series.length).toBe(1)
      expect(st.scanResult?.series[0].manufacturer).toBe('Siemens')
      expect(st.scanProgress?.files_seen).toBe(10)
      expect(st.scanning).toBe(false)
    })

    it('a cancelled scan reports how far it got', async () => {
      server.use(
        http.get('/api/convert/scan/:id', () => HttpResponse.json({
          scan_id: 'scan_1', source_dir: '/tmp/dicom', status: 'cancelled', started_at: 0, finished_at: 1,
          progress: { files_seen: 42, dicoms_seen: 40, series_found: 2, current_dir: '' }, result: null, error: null,
        })),
      )
      await useConvertStore.getState().scanDicom('/tmp/dicom')
      expect(useConvertStore.getState().scanError).toMatch(/cancelled after 42 files/)
      expect(useConvertStore.getState().scanResult).toBeNull()
    })

    it('collect populates collectResult', async () => {
      await useConvertStore.getState().collect({
        bids_dir: '/tmp/bids',
        subject: 'sub-01',
      })
      expect(useConvertStore.getState().collectResult).not.toBeNull()
    })

    it('startRun sets runId via WS', async () => {
      mockWsServer('ws://localhost:5173/ws/convert/convert-1')
      await useConvertStore.getState().startRun({
        source_dir: '/tmp',
        bids_dir: '/tmp/bids',
        subject: 'sub-01',
        heuristic: 'h',
      })
      await new Promise((r) => setTimeout(r, 10))
      expect(useConvertStore.getState().runId).toBe('convert-1')
    })

    it('clearRun resets state', () => {
      useConvertStore.setState({ runId: 'x', running: true })
      useConvertStore.getState().clearRun()
      expect(useConvertStore.getState().runId).toBeNull()
      expect(useConvertStore.getState().running).toBe(false)
    })

    it('clearScan resets scan state', () => {
      useConvertStore.setState({ scanResult: { n_files: 1 } as any, scanError: 'e' })
      useConvertStore.getState().clearScan()
      expect(useConvertStore.getState().scanResult).toBeNull()
      expect(useConvertStore.getState().scanError).toBeNull()
    })
  })

  describe('batch', () => {
    it('addBatchJob appends an empty job', () => {
      useConvertStore.getState().addBatchJob()
      expect(useConvertStore.getState().batchJobs.length).toBe(2)
    })

    it('removeBatchJob removes by index', () => {
      useConvertStore.getState().addBatchJob()
      useConvertStore.getState().removeBatchJob(0)
      expect(useConvertStore.getState().batchJobs.length).toBe(1)
    })

    it('updateBatchJob applies patch', () => {
      useConvertStore.getState().updateBatchJob(0, { subject: 'sub-99' })
      expect(useConvertStore.getState().batchJobs[0].subject).toBe('sub-99')
    })

    it('updateBatchShared merges patch', () => {
      useConvertStore.getState().updateBatchShared({ maxWorkers: 8 })
      expect(useConvertStore.getState().batchShared.maxWorkers).toBe(8)
    })

    it('clearBatch resets batch state', () => {
      useConvertStore.setState({ batchId: 'b1', batchRunning: true })
      useConvertStore.getState().clearBatch()
      expect(useConvertStore.getState().batchId).toBeNull()
      expect(useConvertStore.getState().batchRunning).toBe(false)
    })

    it('loadBatchYaml populates batchJobs from parsed YAML', async () => {
      server.use(
        http.post('/api/convert/batch/parse-yaml', () =>
          HttpResponse.json({
            source_dir: '/tmp',
            bids_dir: '/tmp/bids',
            heuristic: 'h',
            jobs: [{ subject: 'sub-99', source_dir: '/x', session: 'ses-01' }],
          }),
        ),
      )
      await useConvertStore.getState().loadBatchYaml('jobs: []')
      expect(useConvertStore.getState().batchJobs[0].subject).toBe('sub-99')
    })
  })
})

describe('single-run form in the store', () => {
  it('builds run params and YAML from the form', async () => {
    const { runFormParams, runFormYaml, EMPTY_RUN_FORM } = await import('../convert-store')
    const f = { ...EMPTY_RUN_FORM, sourceDir: ' /d/sub01 ', bidsDir: '/b', subject: '01', heuristic: 'h', session: '02', minmeta: true, validateBids: false }
    expect(runFormParams(f)).toEqual({ source_dir: '/d/sub01', bids_dir: '/b', subject: '01', heuristic: 'h', sessions: ['02'], minmeta: true, validate_bids: false })
    const y = runFormYaml(f)
    expect(y.startsWith('convert:\n')).toBe(true)
    expect(y).toContain('source_dir: "/d/sub01"')
    expect(y).toContain('sessions: ["02"]')
    expect(y).toContain('validate_bids: false')
    expect(y).not.toContain('overwrite')
  })

  it('saves the form and loads a saved single config back into it', async () => {
    const { http, HttpResponse } = await import('msw')
    const { server } = await import('../../test/mocks/server')
    const { useConvertStore } = await import('../convert-store')
    let saved: Record<string, unknown> | null = null
    server.use(
      http.post('/api/convert/configs/save-run', async ({ request }) => {
        saved = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ filename: 'mine.yaml', name: 'mine', type: 'single', created: '', description: '', heuristic: 'h', bids_dir: '/b' })
      }),
      http.get('/api/convert/configs/mine.yaml', () => HttpResponse.json({
        filename: 'mine.yaml', name: 'mine', type: 'single', created: '', description: '', heuristic: 'h', bids_dir: '/b',
        config: { convert: { source_dir: '/d', bids_dir: '/b', subject: '01', heuristic: 'h', sessions: ['02'], overwrite: true } },
        yaml_string: '',
      })),
    )
    useConvertStore.getState().updateRunForm({ sourceDir: '/d', bidsDir: '/b', subject: '01', heuristic: 'h' })
    await useConvertStore.getState().saveCurrentRunConfig('mine')
    expect((saved as unknown as { params: Record<string, unknown> })?.params.subject).toBe('01')

    useConvertStore.getState().resetRunForm()
    await useConvertStore.getState().loadSavedConfig('mine.yaml')
    const st = useConvertStore.getState()
    expect(st.tab).toBe('convert')
    expect(st.runForm).toMatchObject({ sourceDir: '/d', bidsDir: '/b', subject: '01', heuristic: 'h', session: '02', overwrite: true, validateBids: true })
  })
})
