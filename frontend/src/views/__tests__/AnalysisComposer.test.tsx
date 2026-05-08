import { describe, it, expect } from 'vitest'
import { renderWithProviders, screen, waitFor } from '../../test/render'
import { AnalysisComposer } from '../AnalysisComposer'
import { useModuleStore } from '../../stores/module-store'
import { useConfigStore } from '../../stores/config-store'

async function loadModules() {
  await useModuleStore.getState().load()
}

describe('<AnalysisComposer />', () => {
  it('shows the loading placeholder before module metadata arrives', () => {
    useModuleStore.setState({ loaded: false, loading: true })
    renderWithProviders(<AnalysisComposer />)
    expect(screen.getByText(/Loading module metadata/)).toBeInTheDocument()
  })

  it('renders the header + the seven stage cards once loaded', async () => {
    await loadModules()
    renderWithProviders(<AnalysisComposer />)
    await waitFor(() => {
      expect(screen.getByText('Analysis Composer')).toBeInTheDocument()
    })
    // All seven stages appear (StageCard headers and the ghost graph
    // both render the labels — getAllByText handles the duplication).
    for (const name of ['Stimuli', 'Responses', 'Features', 'Preparation', 'Model', 'Analyze', 'Report']) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0)
    }
  })

  it('exposes the experiment + subject inputs at the top', async () => {
    await loadModules()
    renderWithProviders(<AnalysisComposer />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/reading_task/)).toBeInTheDocument()
      expect(screen.getByPlaceholderText(/sub-01/)).toBeInTheDocument()
    })
  })

  it('shows the validate / copy / reset action buttons', async () => {
    await loadModules()
    renderWithProviders(<AnalysisComposer />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Validate' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Copy YAML' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
    })
  })

  it('reflects features-stage badge when features exist', async () => {
    await loadModules()
    useConfigStore.setState({
      config: {
        ...useConfigStore.getState().config,
        features: [
          { name: 'numwords', source: 'compute', extractor: 'numwords' },
          { name: 'english1000', source: 'compute', extractor: 'english1000' },
        ],
      },
    })
    renderWithProviders(<AnalysisComposer />)
    await waitFor(() => {
      // The "(2)" badge appears at least once in the header and again
      // as a ghost-graph node label.
      expect(screen.getAllByText('(2)').length).toBeGreaterThan(0)
      expect(screen.getByText(/numwords, english1000/)).toBeInTheDocument()
    })
  })
})
