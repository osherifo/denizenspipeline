import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders, screen } from '../../../test/render'
import { ModuleCard } from '../ModuleCard'
import { buildModule } from '../../../test/factories'

describe('<ModuleCard />', () => {
  it('renders the module name and category', () => {
    renderWithProviders(<ModuleCard module={buildModule({ name: 'word_rate' })} />)
    expect(screen.getByText('word_rate')).toBeInTheDocument()
    expect(screen.getByText('feature_extractors')).toBeInTheDocument()
  })

  it('shows n_dims badge when defined', () => {
    renderWithProviders(<ModuleCard module={buildModule({ n_dims: 10 })} />)
    expect(screen.getByText(/10 dims/)).toBeInTheDocument()
  })

  it('omits n_dims badge when null', () => {
    renderWithProviders(<ModuleCard module={buildModule({ n_dims: null })} />)
    expect(screen.queryByText(/dims/)).not.toBeInTheDocument()
  })

  it('shows the param count', () => {
    renderWithProviders(<ModuleCard module={buildModule()} />)
    expect(screen.getByText(/1 param/)).toBeInTheDocument()
  })

  it('clicking the card expands it to show the param table', async () => {
    const { user } = renderWithProviders(<ModuleCard module={buildModule()} />)
    expect(screen.queryByText('Param')).not.toBeInTheDocument()
    await user.click(screen.getByText('mock_module'))
    expect(screen.getByText('Param')).toBeInTheDocument()
    expect(screen.getByText('Type')).toBeInTheDocument()
  })

  it('clicking again collapses', async () => {
    const { user } = renderWithProviders(<ModuleCard module={buildModule()} />)
    await user.click(screen.getByText('mock_module'))
    await user.click(screen.getByText('mock_module'))
    expect(screen.queryByText('Param')).not.toBeInTheDocument()
  })

  it('shows "no parameters" when params are empty and expanded', async () => {
    const { user } = renderWithProviders(
      <ModuleCard module={buildModule({ params: {}, name: 'no_params' })} />,
    )
    await user.click(screen.getByText('no_params'))
    expect(screen.getByText('No parameters')).toBeInTheDocument()
  })

  it('triggers onEdit when Edit source clicked', async () => {
    const onEdit = vi.fn()
    const { user } = renderWithProviders(
      <ModuleCard module={buildModule({ name: 'm', category: 'feature_extractors' })} onEdit={onEdit} />,
    )
    await user.click(screen.getByText('m'))
    await user.click(screen.getByRole('button', { name: 'Edit source' }))
    expect(onEdit).toHaveBeenCalledWith('feature_extractors', 'm')
  })

  it('does not render Edit source when onEdit is not provided', async () => {
    const { user } = renderWithProviders(<ModuleCard module={buildModule()} />)
    await user.click(screen.getByText('mock_module'))
    expect(screen.queryByRole('button', { name: 'Edit source' })).not.toBeInTheDocument()
  })
})
