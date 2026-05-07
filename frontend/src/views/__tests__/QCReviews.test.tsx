/** Cross-dataset Structural-QC reviews view: filters, table, modal hand-off. */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/mocks/server'
import { renderWithProviders, screen, waitFor } from '../../test/render'
import { QCReviews } from '../QCReviews'

vi.mock('@niivue/niivue', () => ({
  Niivue: vi.fn().mockImplementation(() => ({
    attachToCanvas: vi.fn(),
    loadVolumes: vi.fn().mockResolvedValue(undefined),
    loadMeshes: vi.fn().mockResolvedValue(undefined),
  })),
}))

const REVIEWS = [
  { dataset: 'ds-a', subject: 'sub01', status: 'approved',
    reviewer: 'omar', timestamp: '2026-05-04T12:00:00Z',
    notes: 'looks good', freeview_command_used: null },
  { dataset: 'ds-a', subject: 'sub02', status: 'needs_edits',
    reviewer: 'fatma', timestamp: '2026-05-03T12:00:00Z',
    notes: 'edit pial near temporal pole', freeview_command_used: null },
  { dataset: 'ds-b', subject: 'sub01', status: 'rejected',
    reviewer: 'omar', timestamp: '2026-05-02T12:00:00Z',
    notes: '', freeview_command_used: null },
]


function mockReviews(rows = REVIEWS) {
  server.use(
    http.get('/api/structural-qc/reviews', () => HttpResponse.json(rows)),
  )
}


describe('<QCReviews />', () => {
  it('renders one row per review across all datasets', async () => {
    mockReviews()
    renderWithProviders(<QCReviews />)
    await waitFor(() => {
      // Two ds-a/ds-b rows both name sub01 — there should be 2 matches.
      expect(screen.getAllByText('sub-sub01').length).toBe(2)
    })
    expect(screen.getByText('sub-sub02')).toBeInTheDocument()
    expect(screen.getByText('looks good')).toBeInTheDocument()
    expect(screen.getAllByText('ds-a').length).toBe(2)
    expect(screen.getAllByText('ds-b').length).toBe(1)
  })

  it('shows counts in the filter chips', async () => {
    mockReviews()
    renderWithProviders(<QCReviews />)
    await waitFor(() => expect(screen.getByText(/All \(3\)/)).toBeInTheDocument())
    expect(screen.getByText(/Approved \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/Needs edits \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/Rejected \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/Pending \(0\)/)).toBeInTheDocument()
  })

  it('filters rows by status when a chip is clicked', async () => {
    mockReviews()
    const { user } = renderWithProviders(<QCReviews />)
    await waitFor(() => expect(screen.getByText('sub-sub02')).toBeInTheDocument())

    await user.click(screen.getByText(/Approved \(1\)/))
    expect(screen.queryByText('sub-sub02')).not.toBeInTheDocument()
    expect(screen.getAllByText(/sub-sub01/).length).toBeGreaterThanOrEqual(1)
  })

  it('shows an empty-state row when filtered to a status with zero hits', async () => {
    mockReviews()
    const { user } = renderWithProviders(<QCReviews />)
    await waitFor(() => expect(screen.getByText('sub-sub02')).toBeInTheDocument())
    await user.click(screen.getByText(/Pending \(0\)/))
    expect(screen.getByText(/no reviews .*pending/i)).toBeInTheDocument()
  })

  it('opens the StructuralQC modal when a row is clicked', async () => {
    mockReviews()
    server.use(
      http.get('/api/preproc/subjects/sub02/structural-qc', () =>
        HttpResponse.json({
          dataset: 'ds-a', subject: 'sub02', status: 'needs_edits',
          reviewer: 'fatma', timestamp: '2026-05-03T12:00:00Z',
          notes: 'fix pial', freeview_command_used: null,
        }),
      ),
    )
    const { user } = renderWithProviders(<QCReviews />)
    await waitFor(() => expect(screen.getByText('sub-sub02')).toBeInTheDocument())
    await user.click(screen.getByText('sub-sub02'))
    // Modal renders the same `sub-<id>` label in its header.
    await waitFor(() => {
      expect(screen.getAllByText('sub-sub02').length).toBeGreaterThanOrEqual(2)
    })
  })

  it('surfaces a load error', async () => {
    server.use(
      http.get('/api/structural-qc/reviews',
        () => new HttpResponse('boom', { status: 500 }),
      ),
    )
    renderWithProviders(<QCReviews />)
    await waitFor(() => {
      expect(screen.getByText(/500/)).toBeInTheDocument()
    })
  })
})
