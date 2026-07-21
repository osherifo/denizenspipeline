/** Source tab must explain *why* there's nothing to show, rather than being a
 *  dead (disabled) tab that does nothing when clicked. */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../test/mocks/server'
import { renderWithProviders, screen, fireEvent } from '../../../test/render'
import { AnalysisNodePanel } from '../AnalysisNodePanel'
import type { GraphTarget, RunGraphNode } from '../../../api/run-graph'

const target: GraphTarget = { kind: 'subject', runId: 'run123' }

function node(overrides: Partial<RunGraphNode> = {}): RunGraphNode {
  return {
    id: 'model:bootstrap_ridge',
    label: 'bootstrap_ridge',
    kind: 'model',
    stage: 'model',
    status: 'ok',
    elapsed_s: 1,
    detail: '',
    source_path: null,
    plugin_name: 'bootstrap_ridge',
    params: {},
    children: [],
    outputs: [],
    ...overrides,
  }
}

describe('<AnalysisNodePanel /> source availability', () => {
  it('explains why there is no source instead of a dead tab', async () => {
    // Default tab falls back to outputs when there's no source; stub it so the
    // test isn't noisy about an unhandled request.
    server.use(
      http.get('/api/runs/:runId/node/:nodeId/outputs', () =>
        HttpResponse.json({ node_id: 'x', outputs: [] }),
      ),
    )
    renderWithProviders(
      <AnalysisNodePanel target={target} node={node()} onClose={vi.fn()} />,
    )

    const sourceTab = screen.getByRole('button', { name: /Source/ })
    // Must be clickable — a disabled tab is what made the click do nothing.
    expect(sourceTab).not.toBeDisabled()
    fireEvent.click(sourceTab)

    expect(await screen.findByText(/No source available/)).toBeInTheDocument()
    expect(screen.getByText(/isn't installed here/)).toBeInTheDocument()
  })

  it('loads the source when the node has one', async () => {
    server.use(
      http.get('/api/runs/:runId/node/:nodeId/source', () =>
        HttpResponse.json({
          path: '/pkg/fmriflow/modules/models/ridge.py',
          language: 'python',
          text: 'class BootstrapRidgeModel: pass',
          size: 31,
        }),
      ),
    )
    renderWithProviders(
      <AnalysisNodePanel
        target={target}
        node={node({ source_path: '/pkg/fmriflow/modules/models/ridge.py' })}
        onClose={vi.fn()}
      />,
    )
    // The source view renders (its path header proves the fetch resolved; the
    // code itself lives in Monaco, which doesn't render text in jsdom).
    expect(await screen.findByText('/pkg/fmriflow/modules/models/ridge.py'))
      .toBeInTheDocument()
    expect(screen.queryByText(/No source available/)).not.toBeInTheDocument()
  })
})
