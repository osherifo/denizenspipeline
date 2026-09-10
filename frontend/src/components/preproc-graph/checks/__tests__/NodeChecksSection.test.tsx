import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { NodeChecksSection } from '../NodeChecksSection'
import { usePreprocPipelineStore } from '../../../../stores/preproc-pipeline-store'
import type { PipelineNodeDoc } from '../../../../api/types'

const node = (over: Partial<PipelineNodeDoc> = {}): PipelineNodeDoc => ({ id: 'smooth', type: 'smooth', kind: 'interface', data: { params: {} }, position: { x: 0, y: 0 }, ...over })

describe('<NodeChecksSection />', () => {
  it('adds a pipeline check, commits bounds, and tries it on a run', async () => {
    usePreprocPipelineStore.setState({ pipeline: { ...usePreprocPipelineStore.getState().pipeline, name: 'p', nodes: [node()] } })
    const { rerender } = render(<NodeChecksSection node={node()} />)
    await waitFor(() => expect(screen.getByText('+ Add check')).toBeInTheDocument())
    fireEvent.click(screen.getByText('+ Add check'))
    let n = usePreprocPipelineStore.getState().pipeline.nodes.find((x) => x.id === 'smooth')!
    expect(n.data.checks?.[0]).toMatchObject({ step: 'check_1', metric: 'nifti_stats', live: true })
    rerender(<NodeChecksSection node={n} />)
    fireEvent.change(screen.getByLabelText('artifact'), { target: { value: '{out_file}' } })
    fireEvent.change(screen.getByLabelText('hard bounds'), { target: { value: 'n_trs > 10' } })
    fireEvent.blur(screen.getByLabelText('hard bounds'))
    n = usePreprocPipelineStore.getState().pipeline.nodes.find((x) => x.id === 'smooth')!
    expect(n.data.checks?.[0]).toMatchObject({ artifact: '{out_file}', norms: { hard: { n_trs: ['>', 10] } } })
    rerender(<NodeChecksSection node={n} />)
    const select = screen.getByLabelText('run to try on')
    fireEvent.focus(select)
    await waitFor(() => expect(screen.getAllByRole('option').length).toBeGreaterThan(1))
    fireEvent.change(select, { target: { value: 'pp_abc' } })
    fireEvent.click(screen.getByText('Try'))
    await waitFor(() => expect(screen.getByText('suspicious')).toBeInTheDocument())
    expect(screen.getByText(/n_trs=6 outside/)).toBeInTheDocument()
  })

  it('lists an app node’s built-in checks and can untick one', async () => {
    const fp = node({ id: 'fp', type: 'fmriprep', kind: 'container_app' })
    usePreprocPipelineStore.setState({ pipeline: { ...usePreprocPipelineStore.getState().pipeline, nodes: [fp] } })
    render(<NodeChecksSection node={fp} />)
    await waitFor(() => expect(screen.getByText('nu.mgz')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('checkbox', { name: /nu\.mgz/ }))
    const n = usePreprocPipelineStore.getState().pipeline.nodes.find((x) => x.id === 'fp')!
    expect(n.data.checks).toEqual([{ step: 'nu.mgz', enabled: false }])
  })
})
