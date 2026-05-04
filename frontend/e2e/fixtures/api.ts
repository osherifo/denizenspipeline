/**
 * Playwright test fixture that registers route handlers mirroring the MSW
 * contract used by Vitest. Importing this fixture file's `test` export gives
 * you a Page where every /api/* call returns canned data — unless overridden
 * by the test itself via `page.route()`.
 */

import { test as base, type Page } from '@playwright/test'

export interface ApiFixture {
  apiPage: Page
}

const handlers: Array<{ url: string | RegExp; status?: number; body: unknown }> = [
  { url: /\/api\/modules$/, body: {
    feature_extractors: [
      { name: 'word_rate', docstring: 'Words per TR', category: 'feature_extractors', stage: 'features', params: {}, n_dims: 1 },
      { name: 'phoneme_rate', docstring: 'Phonemes per TR', category: 'feature_extractors', stage: 'features', params: {}, n_dims: 1 },
    ],
    stimulus_loaders: [
      { name: 'audio_loader', docstring: 'Audio', category: 'stimulus_loaders', stage: 'stimuli', params: {}, n_dims: null },
    ],
    response_loaders: [
      { name: 'fmriprep_loader', docstring: 'fmriprep', category: 'response_loaders', stage: 'responses', params: {}, n_dims: null },
    ],
    models: [
      { name: 'ridge', docstring: 'Ridge', category: 'models', stage: 'model', params: {}, n_dims: null },
    ],
  }},
  { url: /\/api\/stages$/, body: [
    { name: 'stimuli', index: 0, description: 'Load stimuli', module_categories: ['stimulus_loaders'], color: '#0ff' },
    { name: 'responses', index: 1, description: 'Load responses', module_categories: ['response_loaders'], color: '#f0f' },
    { name: 'features', index: 2, description: 'Extract features', module_categories: ['feature_extractors'], color: '#ff0' },
    { name: 'prepare', index: 3, description: 'Prepare', module_categories: [], color: '#0f0' },
    { name: 'model', index: 4, description: 'Fit', module_categories: ['models'], color: '#00f' },
    { name: 'analyze', index: 5, description: 'Analyze', module_categories: [], color: '#888' },
    { name: 'report', index: 6, description: 'Report', module_categories: [], color: '#fff' },
  ]},
  { url: /\/api\/configs\/field-values$/, body: { experiment: ['reading_en'], subject: ['sub-01'] }},
  { url: /\/api\/configs$/, body: [
    { filename: 'reading_en/sub-01.yaml', path: '/x.yaml', experiment: 'reading_en', subject: 'sub-01', model_type: 'ridge', features: ['word_rate'], output_dir: 'r', group: 'reading_en', preparation_type: 'standard', stimulus_loader: 'audio_loader', response_loader: 'fmriprep_loader', n_runs: 4 },
  ]},
  { url: /\/api\/runs$/, body: [] },
  { url: /\/api\/runs\/in-flight/, body: { runs: [] }},
  { url: /\/api\/preproc\/backends$/, body: { backends: [{ name: 'mock', available: true, detail: 'stub' }] }},
  { url: /\/api\/preproc\/manifests$/, body: { manifests: [] }},
  { url: /\/api\/preproc\/runs/, body: { runs: [] }},
  { url: /\/api\/autoflatten\/doctor$/, body: { tools: [] }},
  { url: /\/api\/autoflatten\/runs/, body: { runs: [] }},
  { url: /\/api\/convert\/tools$/, body: { tools: [] }},
  { url: /\/api\/convert\/heuristics$/, body: { heuristics: [] }},
  { url: /\/api\/convert\/manifests$/, body: { manifests: [] }},
  { url: /\/api\/convert\/runs/, body: { runs: [] }},
  { url: /\/api\/convert\/configs$/, body: { configs: [] }},
  { url: /\/api\/workflows\/configs$/, body: [] },
  { url: /\/api\/workflows\/runs/, body: { runs: [] }},
  { url: /\/api\/errors/, body: { errors: [], total: 0 }},
  { url: /\/api\/modules\/user$/, body: [] },
  { url: /\/api\/modules\/template-categories$/, body: ['feature_extractors'] },
  { url: /\/api\/preproc\/configs$/, body: [] },
  { url: /\/api\/autoflatten\/configs$/, body: [] },
]

export const test = base.extend<ApiFixture>({
  apiPage: async ({ page }, use) => {
    for (const h of handlers) {
      await page.route(h.url, (route) =>
        route.fulfill({
          status: h.status ?? 200,
          contentType: 'application/json',
          body: JSON.stringify(h.body),
        }),
      )
    }
    await use(page)
  },
})

export { expect } from '@playwright/test'
