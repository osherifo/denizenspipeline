import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AnalysisBuilder } from '../AnalysisBuilder'
import { DialogProvider } from '../../components/common/Dialog'
import { useAnalysisGraphStore } from '../../stores/analysis-graph-store'

describe('AnalysisBuilder', () => {
  it('lists templates and saved graphs, and opens a template on the canvas', async () => {
    render(<DialogProvider><AnalysisBuilder /></DialogProvider>)
    expect(await screen.findByText('saved_graph')).toBeInTheDocument()
    fireEvent.click(await screen.findByText('analyze'))
    // bootstrap_ridge is in the palette and, once the template is open, on the canvas too.
    await waitFor(() => expect(screen.getAllByText('bootstrap_ridge').length).toBeGreaterThanOrEqual(2))
    expect(screen.getAllByText('model').length).toBeGreaterThan(0)
    expect(screen.getAllByText('test_runs').length).toBeGreaterThan(0)
  })

  it('offers group node types for a group graph and edits its subject fan-out', async () => {
    render(<DialogProvider><AnalysisBuilder /></DialogProvider>)
    fireEvent.click(await screen.findByText('+ New group graph'))
    await waitFor(() => expect(screen.getAllByText('voxelwise_mean').length).toBeGreaterThan(0))
    expect(screen.queryByText('bootstrap_ridge')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByText('group_mean'))
    await waitFor(() => expect(useAnalysisGraphStore.getState().graph.name).toBe('group_mean'))
    useAnalysisGraphStore.getState().selectNode('subjects')
    expect(await screen.findByText('Run for each subject')).toBeInTheDocument()
    expect(await screen.findByLabelText('output_dir for every subject')).toHaveValue('/data/{subject}')
  })
})
