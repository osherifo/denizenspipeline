import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MetricsPanel } from '../MetricsPanel'
import { DialogProvider } from '../../../common/Dialog'
import { userMetricCode } from '../../../../test/mocks/handlers.preproc-pipelines'

vi.mock('../../../editor/CodeEditor', () => ({
  CodeEditor: ({ code, onChange }: { code: string; onChange: (v: string) => void }) => (
    <textarea aria-label="code" value={code} onChange={(e) => onChange(e.target.value)} />
  ),
}))

const renderPanel = () => render(<DialogProvider><MetricsPanel /></DialogProvider>)

describe('<MetricsPanel />', () => {
  it('lists built-ins read-only and creates, edits, tries and deletes a user metric', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('nifti_stats')).toBeInTheDocument())
    const builtinRow = screen.getByText('nifti_stats').closest('tr')!
    expect(within(builtinRow).getByText('builtin')).toBeInTheDocument()
    expect(within(builtinRow).getByText('View')).toBeInTheDocument()
    expect(within(builtinRow).queryByText('Delete')).toBeNull()

    // duplicate a built-in: the decorator is re-pointed at the copy's name
    fireEvent.click(within(builtinRow).getByText('Duplicate'))
    await waitFor(() => expect(screen.getByDisplayValue('nifti_stats_copy')).toBeInTheDocument())
    expect((screen.getByLabelText('code') as HTMLTextAreaElement).value).toContain('checkpoint_metric("nifti_stats_copy")')
    fireEvent.click(screen.getByText('Save + reload'))
    await waitFor(() => expect(screen.getByText(/saved \/home\/x\/addons\/checks\/nifti_stats_copy\.py/)).toBeInTheDocument())
    expect(userMetricCode.nifti_stats_copy).toContain('nifti_stats_copy')

    // try it on a file after saving
    fireEvent.change(screen.getByPlaceholderText('/path/to/an/artifact'), { target: { value: '/data/x.nii.gz' } })
    fireEvent.click(screen.getByText('Run'))
    await waitFor(() => expect(screen.getByText(/"size_bytes": 5/)).toBeInTheDocument())
    fireEvent.click(screen.getByText('Close'))

    // the copy is listed as a user metric with Edit + Delete
    await waitFor(() => expect(screen.getByText('nifti_stats_copy')).toBeInTheDocument())
    const userRow = screen.getByText('nifti_stats_copy').closest('tr')!
    expect(within(userRow).getByText('user')).toBeInTheDocument()
    expect(within(userRow).getByText('Edit')).toBeInTheDocument()

    // a save that does not register the right name is refused with the server's message
    fireEvent.click(within(userRow).getByText('Edit'))
    await waitFor(() => expect(screen.getByLabelText('code')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('code'), { target: { value: 'def nothing(): pass' } })
    fireEvent.click(screen.getByText('Save + reload'))
    await waitFor(() => expect(screen.getByText(/must register @checkpoint_metric/)).toBeInTheDocument())
    fireEvent.click(screen.getByText('Close'))

    // delete goes through the confirm dialog
    fireEvent.click(screen.getByLabelText('delete metric nifti_stats_copy'))
    await waitFor(() => expect(screen.getByText(/Delete metric "nifti_stats_copy"/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /^(OK|Confirm|Yes|Delete)$/i }))
    await waitFor(() => expect(screen.queryByText('nifti_stats_copy')).toBeNull())
    expect(userMetricCode.nifti_stats_copy).toBeUndefined()
  })

  it('opens the scaffold for a new metric', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('+ New metric')).toBeInTheDocument())
    fireEvent.click(screen.getByText('+ New metric'))
    await waitFor(() => expect(screen.getByDisplayValue('my_metric')).toBeInTheDocument())
    expect((screen.getByLabelText('code') as HTMLTextAreaElement).value).toContain('checkpoint_metric("my_metric")')
  })
})
