import { describe, it, expect } from 'vitest'
import { renderWithProviders, screen } from '../../../test/render'
import { NavBar } from '../NavBar'

describe('<NavBar />', () => {
  it('renders the logo', () => {
    renderWithProviders(<NavBar currentRoute="dashboard" />)
    expect(screen.getByText('fMRIflow')).toBeInTheDocument()
  })

  it('renders all top-level groups', () => {
    renderWithProviders(<NavBar currentRoute="dashboard" />)
    expect(screen.getByText('Pipeline')).toBeInTheDocument()
    expect(screen.getByText('Preprocessing')).toBeInTheDocument()
    expect(screen.getByText('Analysis')).toBeInTheDocument()
    expect(screen.getByText('Reference')).toBeInTheDocument()
  })

  it('auto-expands the group containing the current route', () => {
    renderWithProviders(<NavBar currentRoute="dashboard" />)
    expect(screen.getByText('Modules')).toBeInTheDocument()
    expect(screen.getByText('Composer')).toBeInTheDocument()
  })

  it('clicking a group toggles its visibility', async () => {
    const { user } = renderWithProviders(<NavBar currentRoute="dashboard" />)
    expect(screen.queryByText('Workflows')).not.toBeInTheDocument()
    await user.click(screen.getByText('Pipeline'))
    expect(screen.getByText('Workflows')).toBeInTheDocument()
  })

  it('marks active link with hash routing', () => {
    renderWithProviders(<NavBar currentRoute="dashboard" />)
    const link = screen.getByText('Dashboard').closest('a')
    expect(link).toHaveAttribute('href', '#dashboard')
  })

  it('all nav items are anchor tags with hash hrefs', () => {
    renderWithProviders(<NavBar currentRoute="dashboard" />)
    const links = screen.getAllByRole('link')
    for (const link of links) {
      expect(link.getAttribute('href')).toMatch(/^#/)
    }
  })
})
