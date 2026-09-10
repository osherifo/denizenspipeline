import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { NodePopup } from '../NodePopup'

vi.mock('@niivue/niivue', () => ({
  Niivue: vi.fn().mockImplementation(() => ({ attachToCanvas: vi.fn(), loadVolumes: vi.fn().mockResolvedValue(undefined), loadMeshes: vi.fn().mockResolvedValue(undefined) })),
}))

describe('<NodePopup />', () => {
  it('a plain node shows the generic tabs and its overview', async () => {
    render(<NodePopup runId="pp_abc" nodeId="smooth" onClose={() => {}} />)
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument())
    expect(screen.getByRole('tab', { name: 'Outputs' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Report' })).toBeNull()
    expect(screen.queryByRole('tab', { name: 'Inner DAG' })).toBeNull()
    expect(screen.getByText('fwhm')).toBeInTheDocument()
    expect(screen.getByText('out_file')).toBeInTheDocument()
  })

  it('an fmriprep node gets the app tabs and honours initialTab', async () => {
    render(<NodePopup runId="pp_abc" nodeId="fp" onClose={() => {}} initialTab="log" />)
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Structural QC' })).toBeInTheDocument())
    for (const name of ['Summary', 'Report', 'Inner DAG', 'Log', 'Checkpoints']) {
      expect(screen.getByRole('tab', { name })).toBeInTheDocument()
    }
    expect(screen.getByRole('tab', { name: 'Log' })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(screen.getByText(/last 2 of 2 lines/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('tab', { name: 'Summary' }))
    await waitFor(() => expect(screen.getByText('fmriprep 24.1.1')).toBeInTheDocument())
  })

  it('Close and Escape call onClose', async () => {
    const onClose = vi.fn()
    render(<NodePopup runId="pp_abc" nodeId="smooth" onClose={onClose} />)
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument())
    fireEvent.click(screen.getByLabelText('Close'))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
