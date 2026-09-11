import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ConfigDetail } from '../ConfigDetail'
import { DialogProvider } from '../../common/Dialog'
import { useAnalysisGraphStore } from '../../../stores/analysis-graph-store'
import { GROUP_GRAPH } from '../../../test/mocks/handlers.analysis-graphs'

const props = { validationErrors: null, validating: false, onRun: () => {}, onValidate: () => {}, isRunning: false }

describe('ConfigDetail: Open in Builder', () => {
  it('compiles a stage config and opens the graph in the builder', async () => {
    window.location.hash = ''
    render(
      <DialogProvider>
        <ConfigDetail {...props} config={{ filename: 'stage.yaml', path: '/tmp/stage.yaml', config: { experiment: 'e' }, yaml_string: 'experiment: e\n' }} />
      </DialogProvider>,
    )
    fireEvent.click(screen.getByText('Open in Builder'))
    await waitFor(() => expect(window.location.hash).toBe('#builder'))
    expect(useAnalysisGraphStore.getState().graph.name).toBe('compiled')
    expect(useAnalysisGraphStore.getState().dirty).toBe(true)
  })

  it('opens a graph config as it is, under its file name', () => {
    window.location.hash = ''
    render(
      <DialogProvider>
        <ConfigDetail {...props} config={{ filename: 'group_mean.yaml', path: '/tmp/group_mean.yaml', config: GROUP_GRAPH as unknown as Record<string, unknown>, yaml_string: '' }} />
      </DialogProvider>,
    )
    fireEvent.click(screen.getByText('Open in Builder'))
    expect(window.location.hash).toBe('#builder')
    const state = useAnalysisGraphStore.getState()
    expect(state.graphName).toBe('group_mean')
    expect(state.graph.scope).toBe('group')
    expect(state.dirty).toBe(false)
  })
})
