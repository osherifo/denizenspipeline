import { describe, it, expect } from 'vitest'
import { useConfigStore } from '../config-store'

describe('useConfigStore', () => {
  it('initial state has empty config + not dirty', () => {
    const s = useConfigStore.getState()
    expect(s.config.experiment).toBe('')
    expect(s.config.subject).toBe('')
    expect(s.isDirty).toBe(false)
  })

  describe('setField', () => {
    it('sets top-level field', () => {
      useConfigStore.getState().setField('experiment', 'reading_en')
      expect(useConfigStore.getState().config.experiment).toBe('reading_en')
      expect(useConfigStore.getState().isDirty).toBe(true)
    })

    it('sets nested field via dot path', () => {
      useConfigStore.getState().setField('stimulus.modality', 'audio')
      expect((useConfigStore.getState().config.stimulus as any).modality).toBe('audio')
    })

    it('creates intermediate keys when missing', () => {
      useConfigStore.getState().setField('new.deep.path', 'x')
      expect(((useConfigStore.getState().config as any).new.deep.path)).toBe('x')
    })
  })

  describe('features', () => {
    it('addFeature appends', () => {
      useConfigStore.getState().addFeature({ name: 'word_rate' })
      expect(useConfigStore.getState().config.features?.length).toBe(1)
    })

    it('removeFeature removes by index', () => {
      useConfigStore.getState().addFeature({ name: 'a' })
      useConfigStore.getState().addFeature({ name: 'b' })
      useConfigStore.getState().removeFeature(0)
      expect(useConfigStore.getState().config.features?.[0].name).toBe('b')
    })

    it('updateFeature replaces at index', () => {
      useConfigStore.getState().addFeature({ name: 'a' })
      useConfigStore.getState().updateFeature(0, { name: 'a2' })
      expect(useConfigStore.getState().config.features?.[0].name).toBe('a2')
    })

    it('reorderFeatures swaps positions', () => {
      useConfigStore.getState().addFeature({ name: 'a' })
      useConfigStore.getState().addFeature({ name: 'b' })
      useConfigStore.getState().addFeature({ name: 'c' })
      useConfigStore.getState().reorderFeatures(0, 2)
      const names = useConfigStore.getState().config.features!.map((f) => f.name)
      expect(names).toEqual(['b', 'c', 'a'])
    })
  })

  describe('preprocessing steps', () => {
    it('addStep flips preparation type to pipeline', () => {
      useConfigStore.getState().addStep({ name: 'detrend' })
      expect(useConfigStore.getState().config.preparation?.type).toBe('pipeline')
      expect(useConfigStore.getState().config.preparation?.steps?.[0].name).toBe('detrend')
    })

    it('removeStep removes by index', () => {
      useConfigStore.getState().addStep({ name: 'a' })
      useConfigStore.getState().addStep({ name: 'b' })
      useConfigStore.getState().removeStep(0)
      expect(useConfigStore.getState().config.preparation?.steps?.[0].name).toBe('b')
    })

    it('reorderSteps moves between indices', () => {
      useConfigStore.getState().addStep({ name: 'a' })
      useConfigStore.getState().addStep({ name: 'b' })
      useConfigStore.getState().reorderSteps(0, 1)
      expect(useConfigStore.getState().config.preparation?.steps?.[0].name).toBe('b')
    })
  })

  describe('analyzers', () => {
    it('addAnalyzer appends', () => {
      useConfigStore.getState().addAnalyzer({ name: 'noise_ceiling' })
      expect(useConfigStore.getState().config.analysis?.length).toBe(1)
    })

    it('removeAnalyzer removes by index', () => {
      useConfigStore.getState().addAnalyzer({ name: 'a' })
      useConfigStore.getState().addAnalyzer({ name: 'b' })
      useConfigStore.getState().removeAnalyzer(0)
      expect(useConfigStore.getState().config.analysis?.[0].name).toBe('b')
    })
  })

  describe('reporters', () => {
    it('toggleReporter adds when missing', () => {
      useConfigStore.getState().toggleReporter('html')
      expect(useConfigStore.getState().config.reporting?.formats).toContain('html')
    })

    it('toggleReporter removes when present', () => {
      useConfigStore.getState().toggleReporter('metrics')
      expect(useConfigStore.getState().config.reporting?.formats).not.toContain('metrics')
    })
  })

  describe('YAML', () => {
    it('importYaml loads parsed config', async () => {
      await useConfigStore.getState().importYaml('experiment: reading_en\n')
      expect(useConfigStore.getState().config.experiment).toBe('reading_en')
      expect(useConfigStore.getState().isDirty).toBe(false)
    })

    it('importYaml stores errors on bad yaml', async () => {
      await useConfigStore.getState().importYaml('INVALID')
      expect(useConfigStore.getState().validationErrors).toContain('bad yaml')
    })

    it('setYamlDirect enters yaml editing mode', () => {
      useConfigStore.getState().setYamlDirect('foo: bar')
      expect(useConfigStore.getState().yamlString).toBe('foo: bar')
      expect(useConfigStore.getState().yamlEditing).toBe(true)
    })

    it('applyYaml commits yaml edits', async () => {
      useConfigStore.getState().setYamlDirect('experiment: reading_en\n')
      await useConfigStore.getState().applyYaml()
      expect(useConfigStore.getState().yamlEditing).toBe(false)
      expect(useConfigStore.getState().config.experiment).toBe('reading_en')
    })

    it('applyYaml reports yamlErrors on bad yaml', async () => {
      useConfigStore.getState().setYamlDirect('INVALID')
      await useConfigStore.getState().applyYaml()
      expect(useConfigStore.getState().yamlErrors).toContain('bad yaml')
    })

    it('exportYaml serializes config', async () => {
      const yaml = await useConfigStore.getState().exportYaml()
      expect(yaml).toContain('reading_en')
    })

    it('syncYaml updates yamlString', async () => {
      await useConfigStore.getState().syncYaml()
      expect(useConfigStore.getState().yamlString).toContain('reading_en')
    })
  })

  it('validate stores returned errors', async () => {
    await useConfigStore.getState().validate()
    expect(useConfigStore.getState().validationErrors).toEqual([])
  })

  it('reset clears state', () => {
    useConfigStore.getState().setField('experiment', 'x')
    useConfigStore.getState().reset()
    expect(useConfigStore.getState().config.experiment).toBe('')
    expect(useConfigStore.getState().isDirty).toBe(false)
  })
})
