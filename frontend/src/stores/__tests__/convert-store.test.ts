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
    expect(s.tab).toBe('tools')
    expect(s.tools).toEqual([])
    expect(s.batchJobs).toHaveLength(1)
    expect(s.batchShared.maxWorkers).toBe(2)
  })

  it('setTab changes tab', () => {
    useConvertStore.getState().setTab('heuristics')
    expect(useConvertStore.getState().tab).toBe('heuristics')
  })

  it('loadTools populates list', async () => {
    await useConvertStore.getState().loadTools()
    expect(useConvertStore.getState().tools.length).toBe(1)
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
    it('scanDicom populates scanResult', async () => {
      await useConvertStore.getState().scanDicom('/tmp/dicom')
      expect(useConvertStore.getState().scanResult?.series.length).toBe(1)
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
