import { describe, it, expect } from 'vitest'
import { renderWithProviders, screen } from '../../../test/render'
import { StageTracker } from '../StageTracker'
import type { StageStatus } from '../../../api/types'

const empty: Record<string, StageStatus> = {}
function withStatus(name: string, status: StageStatus['status'], extras: Partial<StageStatus> = {}) {
  return { [name]: { status, detail: '', elapsed_s: 0, ...extras } } as Record<string, StageStatus>
}

describe('<StageTracker />', () => {
  it('renders all 7 stages even when statuses are missing', () => {
    renderWithProviders(<StageTracker stageStatuses={empty} />)
    for (const stage of ['stimuli', 'responses', 'features', 'prepare', 'model', 'analyze', 'report']) {
      expect(screen.getByText(stage)).toBeInTheDocument()
    }
  })

  it('renders a check for done stages', () => {
    renderWithProviders(<StageTracker stageStatuses={withStatus('stimuli', 'done')} />)
    expect(screen.getByText('✓')).toBeInTheDocument()
  })

  it('renders a cross for failed stages', () => {
    renderWithProviders(<StageTracker stageStatuses={withStatus('model', 'failed')} />)
    expect(screen.getByText('✗')).toBeInTheDocument()
  })

  it('renders running... text for running stages', () => {
    renderWithProviders(<StageTracker stageStatuses={withStatus('features', 'running')} />)
    expect(screen.getByText('running...')).toBeInTheDocument()
  })

  it('renders ! for warning stages', () => {
    renderWithProviders(<StageTracker stageStatuses={withStatus('analyze', 'warning')} />)
    expect(screen.getByText('!')).toBeInTheDocument()
  })

  it('formats elapsed under 1 second as ms', () => {
    renderWithProviders(
      <StageTracker stageStatuses={withStatus('stimuli', 'done', { elapsed_s: 0.42 })} />,
    )
    expect(screen.getByText('420ms')).toBeInTheDocument()
  })

  it('formats elapsed under 60 seconds as fixed-1', () => {
    renderWithProviders(
      <StageTracker stageStatuses={withStatus('stimuli', 'done', { elapsed_s: 12.34 })} />,
    )
    expect(screen.getByText('12.3s')).toBeInTheDocument()
  })

  it('formats elapsed over 60 seconds as min+sec', () => {
    renderWithProviders(
      <StageTracker stageStatuses={withStatus('model', 'done', { elapsed_s: 125 })} />,
    )
    expect(screen.getByText('2m 5s')).toBeInTheDocument()
  })

  it('renders detail text for non-running stages', () => {
    renderWithProviders(
      <StageTracker stageStatuses={withStatus('analyze', 'done', { detail: 'all good' })} />,
    )
    expect(screen.getByText('all good')).toBeInTheDocument()
  })
})
