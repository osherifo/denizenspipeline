import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { PhysioTab } from '../PhysioTab'
import { buildRunNode } from '../../../../test/mocks/handlers.preproc-pipelines'

const ctx = (nodeId: string) => ({ runId: 'pp_abc', nodeId, record: buildRunNode({ node_id: nodeId, node_type: nodeId }), checkpoints: [], isRunning: false })

describe('<PhysioTab />', () => {
  it('shows the pairing table with trigger/TR deltas, skipped runs, and the regressor strip on demand', async () => {
    render(<PhysioTab ctx={ctx('physio_regressors')} />)
    await waitFor(() => expect(screen.getByText('sub-01_ses-01_task-a_bold.nii.gz')).toBeInTheDocument())
    expect(screen.getByText('+1')).toBeInTheDocument()            // 311 triggers for 310 TRs
    expect(screen.getByText('17:13:52')).toBeInTheDocument()      // acquisition time
    expect(screen.getByText(/left out.*ses-00_task-test/)).toBeInTheDocument()
    fireEvent.click(screen.getAllByText('Show')[0])
    expect(screen.getByAltText('regressors for sub-01_ses-01_task-a_bold.nii.gz')).toHaveAttribute('src', '/api/preproc/runs/pp_abc/nodes/physio_regressors/physio/0/image.png')
  })
  it('shows the cleaning table with variance removed and the map on demand', async () => {
    render(<PhysioTab ctx={ctx('physio_clean')} />)
    await waitFor(() => expect(screen.getByText('12.0 %')).toBeInTheDocument())
    expect(screen.getByText('31.0 %')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Show map'))
    expect(screen.getByAltText(/clean for sub-01_task-x_run-1/)).toBeInTheDocument()
  })
})
