import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { AnalysisBuilder } from '../AnalysisBuilder'
import { DialogProvider } from '../../components/common/Dialog'

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
})
