/** Reviewer flow: load existing review, change status, save, copy command. */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../test/mocks/server'
import { renderWithProviders, screen, waitFor } from '../../../test/render'
import { StructuralQCPanel } from '../StructuralQCPanel'


// niivue is heavy and DOM-WebGL — stub it so the panel mounts cleanly.
vi.mock('@niivue/niivue', () => {
  return {
    Niivue: vi.fn().mockImplementation(() => ({
      attachToCanvas: vi.fn(),
      loadVolumes: vi.fn().mockResolvedValue(undefined),
      loadMeshes: vi.fn().mockResolvedValue(undefined),
    })),
  }
})


function mockReview(status = 'pending', reviewer = '', notes = '') {
  server.use(
    http.get('/api/preproc/subjects/sub01/structural-qc', () =>
      HttpResponse.json({
        dataset: 'ds-test',
        subject: 'sub01',
        status,
        reviewer,
        timestamp: '2026-05-04T00:00:00Z',
        notes,
        freeview_command_used: null,
      }),
    ),
  )
}


describe('<StructuralQCPanel />', () => {
  it('loads and displays an existing review', async () => {
    mockReview('approved', 'omar', 'looks good')
    renderWithProviders(<StructuralQCPanel subject="sub01" />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('omar')).toBeInTheDocument()
    })
    expect(screen.getByDisplayValue('looks good')).toBeInTheDocument()
    // Header dot reflects the loaded status (rendered as `● Approve`).
    expect(screen.getByText(/●\s*Approve/)).toBeInTheDocument()
  })

  it('saves a status change with reviewer + notes', async () => {
    mockReview('pending', '', '')
    let captured: any = null
    server.use(
      http.post('/api/preproc/subjects/sub01/structural-qc', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({
          saved: true,
          path: '/r.yaml',
          review: {
            dataset: 'ds-test', subject: 'sub01',
            status: captured.status, reviewer: captured.reviewer,
            notes: captured.notes, timestamp: '2026-05-04',
            freeview_command_used: captured.freeview_command_used ?? null,
          },
        })
      }),
    )

    const { user } = renderWithProviders(<StructuralQCPanel subject="sub01" />)
    await waitFor(() => expect(screen.getByPlaceholderText(/reviewer/i)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /^approve$/i }))
    await user.type(screen.getByPlaceholderText(/reviewer/i), 'omar')
    await user.type(screen.getByPlaceholderText(/notes/i), 'all good')
    await user.click(screen.getByRole('button', { name: /save review/i }))

    await waitFor(() => expect(captured).not.toBeNull())
    expect(captured.status).toBe('approved')
    expect(captured.reviewer).toBe('omar')
    expect(captured.notes).toBe('all good')
  })

  it('shows the freeview button only when status is needs_edits', async () => {
    mockReview('approved', 'omar', '')
    const { user } = renderWithProviders(<StructuralQCPanel subject="sub01" />)
    await waitFor(() => expect(screen.getByDisplayValue('omar')).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: /copy freeview command/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /needs edits/i }))
    expect(screen.getByRole('button', { name: /copy freeview command/i })).toBeInTheDocument()
  })

  it('toggles the fmriprep report iframe', async () => {
    mockReview()
    const { user } = renderWithProviders(<StructuralQCPanel subject="sub01" />)
    await waitFor(() => expect(screen.getByPlaceholderText(/reviewer/i)).toBeInTheDocument())

    expect(screen.queryByTitle('fmriprep report')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /show fmriprep report/i }))
    expect(screen.getByTitle('fmriprep report')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /hide fmriprep report/i }))
    expect(screen.queryByTitle('fmriprep report')).not.toBeInTheDocument()
  })

  it('toggles the niivue 3D viewer', async () => {
    mockReview()
    const { user } = renderWithProviders(<StructuralQCPanel subject="sub01" />)
    await waitFor(() => expect(screen.getByPlaceholderText(/reviewer/i)).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: /show 3d viewer/i }))
    // Toggle button label flips when the viewer is open.
    expect(screen.getByRole('button', { name: /hide 3d viewer/i })).toBeInTheDocument()
  })
})
