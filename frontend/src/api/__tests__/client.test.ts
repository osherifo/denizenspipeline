import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import {
  fetchModules,
  fetchModule,
  fetchStages,
  validateConfig,
  configFromYaml,
  configToYaml,
  fetchDefaults,
  fetchRuns,
  fetchRun,
  startRun,
  artifactUrl,
  fetchConfigs,
  fetchConfigDetail,
  validateConfigFile,
  saveConfigFile,
  copyConfigFile,
  startRunFromConfig,
  validateModuleCode,
  saveModule,
  fetchUserModules,
  fetchUserModuleCode,
  deleteUserModule,
  fetchTemplate,
  fetchTemplateCategories,
  fetchPreprocBackends,
  fetchManifests,
  fetchManifestDetail,
  fetchErrors,
  connectRunWs,
  connectPreprocWs,
  fetchTriage,
} from '../client'
import { buildPipelineConfig } from '../../test/factories'

describe('API client', () => {
  describe('modules', () => {
    it('fetchModules returns module metadata', async () => {
      const m = await fetchModules()
      expect(Object.keys(m)).toContain('feature_extractors')
      expect(m.feature_extractors[0].name).toBe('word_rate')
    })

    it('fetchModule returns single module info', async () => {
      const m = await fetchModule('feature_extractors', 'word_rate')
      expect(m.name).toBe('word_rate')
      expect(m.category).toBe('feature_extractors')
    })

    it('fetchStages returns 7 stages', async () => {
      const stages = await fetchStages()
      expect(stages).toHaveLength(7)
      expect(stages[0].name).toBe('stimuli')
    })

    it('throws on server error', async () => {
      server.use(http.get('/api/modules', () => HttpResponse.text('boom', { status: 500 })))
      await expect(fetchModules()).rejects.toThrow(/500/)
    })
  })

  describe('config', () => {
    it('validateConfig returns valid', async () => {
      const r = await validateConfig(buildPipelineConfig())
      expect(r.valid).toBe(true)
      expect(r.errors).toEqual([])
    })

    it('configFromYaml parses yaml', async () => {
      const r = await configFromYaml('experiment: reading_en\n')
      expect(r.config.experiment).toBe('reading_en')
    })

    it('configFromYaml returns errors on bad yaml', async () => {
      const r = await configFromYaml('INVALID')
      expect(r.errors).toContain('bad yaml')
    })

    it('configToYaml returns yaml string', async () => {
      const yaml = await configToYaml(buildPipelineConfig())
      expect(yaml).toContain('reading_en')
    })

    it('fetchDefaults returns params', async () => {
      const r = await fetchDefaults('feature_extractors', 'word_rate')
      expect(r.params).toEqual({ delay: 0 })
    })
  })

  describe('runs', () => {
    it('fetchRuns returns run list', async () => {
      const runs = await fetchRuns()
      expect(runs.length).toBeGreaterThan(0)
    })

    it('fetchRuns passes filters via querystring', async () => {
      let received: URL | null = null
      server.use(
        http.get('/api/runs', ({ request }) => {
          received = new URL(request.url)
          return HttpResponse.json([])
        }),
      )
      await fetchRuns({ experiment: 'reading_en', subject: 'sub-01', limit: 10 })
      expect(received!.searchParams.get('experiment')).toBe('reading_en')
      expect(received!.searchParams.get('subject')).toBe('sub-01')
      expect(received!.searchParams.get('limit')).toBe('10')
    })

    it('fetchRun returns single run', async () => {
      const r = await fetchRun('run-1')
      expect(r.run_id).toBe('run-1')
    })

    it('startRun returns run id', async () => {
      const r = await startRun(buildPipelineConfig())
      expect(r.run_id).toBe('run-launched')
      expect(r.status).toBe('started')
    })

    it('startRunFromConfig forwards config_path + overrides', async () => {
      let body: unknown = null
      server.use(
        http.post('/api/runs/from-config', async ({ request }) => {
          body = await request.json()
          return HttpResponse.json({ run_id: 'r1', status: 'started' })
        }),
      )
      await startRunFromConfig('reading_en/sub-01.yaml', { foo: 'bar' })
      expect(body).toEqual({ config_path: 'reading_en/sub-01.yaml', overrides: { foo: 'bar' } })
    })

    it('artifactUrl produces correct URL', () => {
      expect(artifactUrl('r1', 'plot.png')).toBe('/api/runs/r1/artifacts/plot.png')
    })
  })

  describe('experiment configs', () => {
    it('fetchConfigs returns summary list', async () => {
      const c = await fetchConfigs()
      expect(c.length).toBe(2)
    })

    it('fetchConfigDetail returns full detail', async () => {
      const d = await fetchConfigDetail('reading_en/sub-01.yaml')
      expect(d.filename).toBe('reading_en/sub-01.yaml')
    })

    it('validateConfigFile reports validity', async () => {
      const r = await validateConfigFile('reading_en/sub-01.yaml')
      expect(r.valid).toBe(true)
    })

    it('saveConfigFile sends yaml body', async () => {
      let body: unknown = null
      server.use(
        http.put('/api/configs/:filename', async ({ request }) => {
          body = await request.json()
          return HttpResponse.json({ saved: true, path: '/x', errors: [] })
        }),
      )
      await saveConfigFile('foo.yaml', 'experiment: x')
      expect(body).toEqual({ yaml_string: 'experiment: x' })
    })

    it('copyConfigFile sends new filename in body', async () => {
      let body: unknown = null
      server.use(
        http.post('/api/configs/:filename/copy', async ({ request }) => {
          body = await request.json()
          return HttpResponse.json({ saved: true, path: '/x', filename: 'b.yaml', errors: [] })
        }),
      )
      const r = await copyConfigFile('a.yaml', 'b.yaml')
      expect(body).toEqual({ new_filename: 'b.yaml' })
      expect(r.filename).toBe('b.yaml')
    })
  })

  describe('module editor', () => {
    it('validateModuleCode returns validation result', async () => {
      const r = await validateModuleCode('class X: pass')
      expect(r.valid).toBe(true)
    })

    it('saveModule returns save result', async () => {
      const r = await saveModule('class X: pass', 'my_mod', 'feature_extractors')
      expect(r.saved).toBe(true)
      expect(r.registered).toBe(true)
    })

    it('fetchUserModules returns list', async () => {
      const list = await fetchUserModules()
      expect(list.length).toBe(2)
    })

    it('fetchUserModuleCode returns code', async () => {
      const r = await fetchUserModuleCode('my_module')
      expect(r.code).toContain('class X')
    })

    it('deleteUserModule returns success', async () => {
      const r = await deleteUserModule('my_module')
      expect(r.deleted).toBe(true)
    })

    it('fetchTemplate returns template body', async () => {
      const r = await fetchTemplate('feature_extractors', 'my_mod')
      expect(r.code).toContain('template')
    })

    it('fetchTemplateCategories returns list', async () => {
      const r = await fetchTemplateCategories()
      expect(r).toContain('feature_extractors')
    })
  })

  describe('preprocessing', () => {
    it('fetchPreprocBackends returns backend list', async () => {
      const r = await fetchPreprocBackends()
      expect(r.length).toBe(2)
      expect(r[0].name).toBe('fmriprep')
    })

    it('fetchManifests returns manifest list', async () => {
      const r = await fetchManifests()
      expect(r.length).toBe(1)
    })

    it('fetchManifestDetail returns detail', async () => {
      const r = await fetchManifestDetail('sub-01')
      expect(r.subject).toBe('sub-01')
    })
  })

  describe('errors / triage', () => {
    it('fetchErrors returns entries unwrapped from envelope', async () => {
      const r = await fetchErrors()
      expect(r.length).toBe(1)
      expect(r[0].title).toBe('Mock error')
    })

    it('fetchTriage returns null on 404', async () => {
      const r = await fetchTriage('missing')
      expect(r).toBeNull()
    })
  })

  describe('websockets', () => {
    it('connectRunWs builds correct url', () => {
      const ws = connectRunWs('abc')
      expect(ws.url).toContain('/ws/runs/abc')
      ws.close()
    })

    it('connectPreprocWs uses ws scheme on http page', () => {
      const ws = connectPreprocWs('xyz')
      expect(ws.url.startsWith('ws://')).toBe(true)
      ws.close()
    })
  })
})
