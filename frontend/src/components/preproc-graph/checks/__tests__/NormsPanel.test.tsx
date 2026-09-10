import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { server } from '../../../../test/mocks/server'
import { NormsPanel } from '../NormsPanel'

describe('<NormsPanel />', () => {
  it('shows built-in and user rows, and saves an edited overlay', async () => {
    let sent: { norms: Record<string, unknown> } | null = null
    server.use(http.put('/api/preproc/checks/norms', async ({ request }) => {
      sent = (await request.json()) as typeof sent
      return HttpResponse.json({ saved: true, rows: [] })
    }))
    render(<NormsPanel />)
    await waitFor(() => expect(screen.getByLabelText('nu.mgz hard n_unique')).toBeInTheDocument())
    expect(screen.getByText('override')).toBeInTheDocument()   // the wm.mgz user row
    fireEvent.change(screen.getByLabelText('nu.mgz hard n_unique'), { target: { value: '> 150' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(sent).not.toBeNull())
    expect(sent!.norms).toEqual({ 'nu.mgz': { hard: { n_unique: ['>', 150] } }, 'wm.mgz': { hard: { wm_volume_cm3: ['between', [200, 1000]] } } })
  })
})
