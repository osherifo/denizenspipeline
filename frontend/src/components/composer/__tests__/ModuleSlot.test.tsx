import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders, screen } from '../../../test/render'
import { ModuleSlot } from '../ModuleSlot'
import type { ModuleInfo } from '../../../api/types'

const ridge: ModuleInfo = {
  name: 'bootstrap_ridge',
  docstring: 'Ridge with bootstrapped alphas.',
  category: 'models',
  stage: 'model',
  params: { n_boots: { type: 'int', default: 50 } },
}

function render(selectedName: string, values: Record<string, unknown> = {}) {
  return renderWithProviders(
    <ModuleSlot
      label="Model"
      available={[ridge]}
      selectedName={selectedName}
      values={values}
      onSelect={vi.fn()}
      onParamChange={vi.fn()}
    />,
  )
}

describe('<ModuleSlot /> missing-module indication', () => {
  it('renders docstring + params for an installed module', () => {
    render('bootstrap_ridge')
    expect(screen.getByText('Ridge with bootstrapped alphas.')).toBeInTheDocument()
    expect(screen.queryByText(/isn’t installed on this system/)).not.toBeInTheDocument()
  })

  it('flags a module that is not installed on this system', () => {
    render('some_remote_model')
    // The configured name stays visible in the dropdown rather than blanking out.
    expect(screen.getByRole('option', { name: /some_remote_model — not installed/ }))
      .toBeInTheDocument()
    expect(screen.getByText(/isn’t installed on this system/)).toBeInTheDocument()
  })

  it('shows the configured params read-only when the module is missing', () => {
    render('some_remote_model', { alpha: 3, mode: 'fast' })
    expect(screen.getByText(/Configured values \(read-only\)/)).toBeInTheDocument()
    expect(screen.getByText('alpha')).toBeInTheDocument()
    expect(screen.getByText('mode')).toBeInTheDocument()
  })

  it('does not flag an empty selection', () => {
    render('')
    expect(screen.queryByText(/isn’t installed on this system/)).not.toBeInTheDocument()
  })
})
