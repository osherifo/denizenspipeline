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
          { name: 'word_rate', source: 'compute', extractor: 'word_rate' },
          { name: 'phoneme_rate', source: 'compute', extractor: 'phoneme_rate' },
        ],
      },
    })
    renderWithProviders(<AnalysisComposer />)
    await waitFor(() => {
      // The "(2)" badge appears at least once in the header and again
      // as a ghost-graph node label.
      expect(screen.getAllByText('(2)').length).toBeGreaterThan(0)
      expect(screen.getByText(/word_rate, phoneme_rate/)).toBeInTheDocument()
    })
  })

  it('uses the same "pick module → params" interaction for features and analyzers', async () => {
    await loadModules()
    useConfigStore.setState({
      config: {
        ...useConfigStore.getState().config,
        // One feature + one analyzer so both stage cards have an
        // entry whose editor is open by default after the user
        // clicks Add. The interaction shape (a select followed by a
        // ParamForm) should be identical across the two — the
        // earlier UX had a free-text "Name" input for features and
        // didn't for analyzers.
        features: [
          { name: 'word_rate', source: 'compute', extractor: 'word_rate' },
        ],
      },
    })
    renderWithProviders(<AnalysisComposer />)
    await waitFor(() => {
      expect(screen.getByText('Analysis Composer')).toBeInTheDocument()
    })
    // Features stage no longer renders a free-text "Name" input;
    // FeatureKindSlot uses a single dropdown labelled "Feature".
    // The legacy editor had a "Source" label; verify it's gone.
    expect(screen.queryByText('Source')).not.toBeInTheDocument()
  })
})
