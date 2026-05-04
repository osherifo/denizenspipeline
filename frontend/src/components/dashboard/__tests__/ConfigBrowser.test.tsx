import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders, screen } from '../../../test/render'
import { ConfigBrowser } from '../ConfigBrowser'
import { buildConfigSummary } from '../../../test/factories'

const configs = [
  buildConfigSummary({ filename: 'reading/sub-01.yaml', group: 'reading', subject: 'sub-01', n_runs: 4 }),
  buildConfigSummary({ filename: 'reading/sub-02.yaml', group: 'reading', subject: 'sub-02', n_runs: 0 }),
  buildConfigSummary({ filename: 'movies/sub-09.yaml', group: 'movies', subject: 'sub-09', n_runs: 2 }),
]

describe('<ConfigBrowser />', () => {
  it('renders an empty state when there are no configs', () => {
    renderWithProviders(
      <ConfigBrowser
        configs={[]}
        selectedFilename={null}
        loading={false}
        onSelect={vi.fn()}
        onRescan={vi.fn()}
      />,
    )
    expect(screen.getByText('No configs found')).toBeInTheDocument()
  })

  it('groups configs by group field', () => {
    renderWithProviders(
      <ConfigBrowser
        configs={configs}
        selectedFilename={null}
        loading={false}
        onSelect={vi.fn()}
        onRescan={vi.fn()}
      />,
    )
    expect(screen.getByText('reading')).toBeInTheDocument()
    expect(screen.getByText('movies')).toBeInTheDocument()
  })

  it('filters configs by search', async () => {
    const { user } = renderWithProviders(
      <ConfigBrowser
        configs={configs}
        selectedFilename={null}
        loading={false}
        onSelect={vi.fn()}
        onRescan={vi.fn()}
      />,
    )
    const search = screen.getByPlaceholderText('Search configs...')
    await user.type(search, 'movies')
    expect(screen.queryByText('reading')).not.toBeInTheDocument()
    expect(screen.getByText('movies')).toBeInTheDocument()
  })

  it('triggers onSelect when a config is clicked', async () => {
    const onSelect = vi.fn()
    const { user } = renderWithProviders(
      <ConfigBrowser
        configs={configs}
        selectedFilename={null}
        loading={false}
        onSelect={onSelect}
        onRescan={vi.fn()}
      />,
    )
    await user.click(screen.getByText('reading/sub-01'))
    expect(onSelect).toHaveBeenCalledWith('reading/sub-01.yaml')
  })

  it('triggers onRescan when rescan button clicked', async () => {
    const onRescan = vi.fn()
    const { user } = renderWithProviders(
      <ConfigBrowser
        configs={configs}
        selectedFilename={null}
        loading={false}
        onSelect={vi.fn()}
        onRescan={onRescan}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Rescan' }))
    expect(onRescan).toHaveBeenCalled()
  })

  it('rescan button shows loading state and disables when loading', () => {
    renderWithProviders(
      <ConfigBrowser
        configs={configs}
        selectedFilename={null}
        loading={true}
        onSelect={vi.fn()}
        onRescan={vi.fn()}
      />,
    )
    const btn = screen.getByRole('button', { name: 'Scanning...' })
    expect(btn).toBeDisabled()
  })

  it('renders run count badge', () => {
    renderWithProviders(
      <ConfigBrowser
        configs={configs}
        selectedFilename={null}
        loading={false}
        onSelect={vi.fn()}
        onRescan={vi.fn()}
      />,
    )
    expect(screen.getByText('4 runs')).toBeInTheDocument()
    expect(screen.getByText('0 runs')).toBeInTheDocument()
  })

  it('toggles a group when its header is clicked', async () => {
    const { user } = renderWithProviders(
      <ConfigBrowser
        configs={configs}
        selectedFilename={null}
        loading={false}
        onSelect={vi.fn()}
        onRescan={vi.fn()}
      />,
    )
    expect(screen.getByText('reading/sub-01')).toBeInTheDocument()
    await user.click(screen.getByText('reading'))
    expect(screen.queryByText('reading/sub-01')).not.toBeInTheDocument()
  })
})
