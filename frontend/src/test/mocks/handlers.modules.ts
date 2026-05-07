import { http, HttpResponse } from 'msw'
import {
  buildModules,
  buildStages,
  buildUserModule,
  buildValidationResult,
} from '../factories'

export const modulesHandlers = [
  http.get('/api/modules', () => HttpResponse.json(buildModules())),

  http.post('/api/modules/validate-code', () =>
    HttpResponse.json(buildValidationResult()),
  ),

  http.post('/api/modules/save', () =>
    HttpResponse.json({
      saved: true,
      path: '/tmp/x.py',
      registered: true,
      module_name: 'my_module',
      class_name: 'MyExtractor',
      category: 'feature_extractors',
    }),
  ),

  http.get('/api/modules/user', () =>
    HttpResponse.json([buildUserModule(), buildUserModule({ name: 'other', registered: false })]),
  ),

  http.get('/api/modules/user/:name', ({ params }) =>
    HttpResponse.json({ name: params.name, code: 'class X: pass' }),
  ),

  http.delete('/api/modules/user/:name', ({ params }) =>
    HttpResponse.json({ deleted: true, name: params.name }),
  ),

  http.post('/api/modules/template', () =>
    HttpResponse.json({ code: '# template', filename: 't.py', category: 'feature_extractors' }),
  ),

  http.get('/api/modules/template-categories', () =>
    HttpResponse.json(['feature_extractors', 'stimulus_loaders']),
  ),

  http.get('/api/modules/:category/:name/code', ({ params }) =>
    HttpResponse.json({
      name: params.name,
      category: params.category,
      path: `/tmp/${params.name}.py`,
      code: 'class Mock: pass',
      class_start: 0,
      class_end: 1,
    }),
  ),

  http.put('/api/modules/:category/:name/code', () =>
    HttpResponse.json({
      saved: true,
      name: 'mock',
      category: 'feature_extractors',
      path: '/tmp/mock.py',
      bytes: 42,
      restart_required: false,
    }),
  ),

  http.post('/api/modules/:category/:name/reload', () =>
    HttpResponse.json({ reloaded: true, module: 'mock', replaced: true }),
  ),

  http.get('/api/modules/:category/:name', ({ params }) =>
    HttpResponse.json({
      name: params.name,
      docstring: 'Mock',
      category: params.category,
      stage: 'features',
      params: {},
      n_dims: 3,
    }),
  ),

  http.get('/api/stages', () => HttpResponse.json(buildStages())),
]
