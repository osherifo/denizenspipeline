import { describe, it, expect } from 'vitest'
import { renderWithProviders, screen, waitFor } from '../../test/render'
import { ModuleBrowser } from '../ModuleBrowser'
import { useModuleStore } from '../../stores/module-store'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'

async function loadModules() {
  await useModuleStore.getState().load()
}

describe('<ModuleBrowser />', () => {
  it('shows loading state before data arrives', () => {
    useModuleStore.setState({ loaded: false, loading: true })
    renderWithProviders(<ModuleBrowser />)
    expect(screen.getByText('Loading modules...')).toBeInTheDocument()
  })

  it('shows error state on failure', () => {
    useModuleStore.setState({ loaded: false, loading: false, error: 'boom' })
    renderWithProviders(<ModuleBrowser />)
    expect(screen.getByText(/Error loading modules: boom/)).toBeInTheDocument()
  })

  it('renders the header + module count after load', async () => {
    await loadModules()
    renderWithProviders(<ModuleBrowser />)
    await waitFor(() => {
      expect(screen.getByText('Module Browser')).toBeInTheDocument()
    })
    expect(screen.getByText(/modules across/)).toBeInTheDocument()
  })

  it('renders module cards grouped by stage', async () => {
    await loadModules()
    renderWithProviders(<ModuleBrowser />)
    await waitFor(() => {
      expect(screen.getByText('word_rate')).toBeInTheDocument()
      expect(screen.getByText('phoneme_rate')).toBeInTheDocument()
    })
  })

  it('search filters by module name', async () => {
    await loadModules()
    const { user } = renderWithProviders(<ModuleBrowser />)
    await waitFor(() => screen.getByText('word_rate'))
    const search = screen.getByPlaceholderText(/Search modules/)
    await user.type(search, 'word_rate')
    expect(screen.getByText('word_rate')).toBeInTheDocument()
    expect(screen.queryByText('phoneme_rate')).not.toBeInTheDocument()
  })

  it('handles empty modules gracefully', async () => {
    server.use(http.get('/api/modules', () => HttpResponse.json({})))
    await loadModules()
    renderWithProviders(<ModuleBrowser />)
    await waitFor(() => {
      expect(screen.getByText('Module Browser')).toBeInTheDocument()
    })
  })
})
