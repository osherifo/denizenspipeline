/** Modal that wraps StructuralQCPanel for the Workflows-view drill-in. */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../test/mocks/server'
import { renderWithProviders, screen, waitFor } from '../../../test/render'
import { StructuralQCModal } from '../StructuralQCModal'


// niivue does WebGL — stub so the panel inside the modal mounts.
vi.mock('@niivue/niivue', () => ({
  Niivue: vi.fn().mockImplementation(() => ({
    attachToCanvas: vi.fn(),
    loadVolumes: vi.fn().mockResolvedValue(undefined),
    loadMeshes: vi.fn().mockResolvedValue(undefined),
  })),
}))


function mockReview(subject: string, status = 'pending') {
  server.use(
    http.get(`/api/preproc/subjects/${subject}/structural-qc`, () =>
      HttpResponse.json({
        dataset: 'ds-test', subject, status,
        reviewer: '', timestamp: '2026-05-05T00:00:00Z',
        notes: '', freeview_command_used: null,
      }),
    ),
  )
}


describe('<StructuralQCModal />', () => {
  it('renders the subject id in the header', async () => {
    mockReview('AN', 'pending')
    renderWithProviders(<StructuralQCModal subject="AN" onClose={vi.fn()} />)
    // sub-AN appears only in the modal header; "Structural QC" also
    // matches the underlying panel's section label so we don't assert it.
    expect(screen.getByText('sub-AN')).toBeInTheDocument()
  })

  it('hosts the underlying StructuralQCPanel for the subject', async () => {
    mockReview('AN', 'approved')
    renderWithProviders(<StructuralQCModal subject="AN" onClose={vi.fn()} />)
    await waitFor(() => {
      // Header-line status pill from the inner panel.
      expect(screen.getByText(/●\s*Approve/)).toBeInTheDocument()
    })
  })

  it('calls onClose when the Close button is clicked', async () => {
    mockReview('AN')
    const onClose = vi.fn()
    const { user } = renderWithProviders(
      <StructuralQCModal subject="AN" onClose={onClose} />,
    )
    await user.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when the backdrop is clicked', async () => {
    mockReview('AN')
    const onClose = vi.fn()
    const { container, user } = renderWithProviders(
      <StructuralQCModal subject="AN" onClose={onClose} />,
    )
    // First top-level child is the backdrop (z-index'd absolute).
    const backdrop = container.firstElementChild as HTMLElement
    await user.click(backdrop)
    expect(onClose).toHaveBeenCalledOnce()
  })
})
