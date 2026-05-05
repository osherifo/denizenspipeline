/** Drawer that shows a node's work_dir contents. */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../../test/mocks/server'
import { renderWithProviders, screen, waitFor } from '../../../test/render'
import { NodeOutputsPanel } from '../NodeOutputsPanel'

vi.mock('@niivue/niivue', () => ({
  Niivue: vi.fn().mockImplementation(() => ({
    attachToCanvas: vi.fn(),
    loadVolumes: vi.fn().mockResolvedValue(undefined),
  })),
}))


function mockOutputs(rows: any) {
  server.use(
    http.get('/api/preproc/runs/:run/node/:node/files', () =>
      HttpResponse.json(rows),
    ),
  )
}


describe('<NodeOutputsPanel />', () => {
  it('renders the file list with the node leaf in the header', async () => {
    mockOutputs({
      node: 'fmriprep_wf.anat_wf.smooth',
      leaf_dir: '/work/.../smooth',
      exists: true,
      crashes: [],
      files: [
        { name: 'command.txt', rel: 'command.txt', suffix: '.txt',
          size: 100, kind: 'view' },
        { name: 'result.pklz', rel: 'result.pklz', suffix: '.pklz',
          size: 200, kind: 'pickle' },
      ],
    })
    renderWithProviders(
      <NodeOutputsPanel runId="r1" node="fmriprep_wf.anat_wf.smooth"
                        onClose={vi.fn()} />,
    )
    await waitFor(() => {
      expect(screen.getByText('smooth')).toBeInTheDocument()
    })
    expect(screen.getByText('command.txt')).toBeInTheDocument()
    expect(screen.getByText('result.pklz')).toBeInTheDocument()
    expect(screen.getByText(/\.txt · 100 B · view/)).toBeInTheDocument()
    expect(screen.getByText(/\.pklz · 200 B · pickle/)).toBeInTheDocument()
  })

  it('expands a text file inline when clicked', async () => {
    mockOutputs({
      node: 'wf.x',
      leaf_dir: '/w',
      exists: true,
      crashes: [],
      files: [{ name: 'a.txt', rel: 'a.txt', suffix: '.txt',
                size: 7, kind: 'view' }],
    })
    server.use(
      http.get('/api/preproc/runs/r1/node/wf.x/file', () =>
        new HttpResponse('hello\n', {
          status: 200, headers: { 'content-type': 'text/plain' },
        }),
      ),
    )
    const { user } = renderWithProviders(
      <NodeOutputsPanel runId="r1" node="wf.x" onClose={vi.fn()} />,
    )
    await waitFor(() => expect(screen.getByText('a.txt')).toBeInTheDocument())
    await user.click(screen.getByText('a.txt'))
    await waitFor(() => {
      expect(screen.getByText(/hello/)).toBeInTheDocument()
    })
  })

  it('decodes a pickle on expand', async () => {
    mockOutputs({
      node: 'wf.x',
      leaf_dir: '/w',
      exists: true,
      crashes: [],
      files: [{ name: 'r.pklz', rel: 'r.pklz', suffix: '.pklz',
                size: 100, kind: 'pickle' }],
    })
    server.use(
      http.get('/api/preproc/runs/r1/node/wf.x/pickle', () =>
        HttpResponse.json({
          name: 'r.pklz',
          type: 'dict',
          value: { fwhm: 5, n_iter: 3 },
        }),
      ),
    )
    const { user } = renderWithProviders(
      <NodeOutputsPanel runId="r1" node="wf.x" onClose={vi.fn()} />,
    )
    await waitFor(() => expect(screen.getByText('r.pklz')).toBeInTheDocument())
    await user.click(screen.getByText('r.pklz'))
    await waitFor(() => {
      expect(screen.getByText(/n_iter/)).toBeInTheDocument()
    })
    expect(screen.getByText(/fwhm/)).toBeInTheDocument()
  })

  it('shows a friendly empty state when leaf_dir does not exist', async () => {
    mockOutputs({
      node: 'wf.x', leaf_dir: '/w/missing',
      exists: false, crashes: [], files: [],
    })
    renderWithProviders(
      <NodeOutputsPanel runId="r1" node="wf.x" onClose={vi.fn()} />,
    )
    await waitFor(() => {
      expect(screen.getByText(/No work_dir on disk for this node/i))
        .toBeInTheDocument()
    })
  })

  it('surfaces crash files at the top of the list', async () => {
    mockOutputs({
      node: 'wf.boom', leaf_dir: '/w/boom',
      exists: true,
      files: [],
      crashes: [{
        name: 'crash-20260505-boom-abc.txt',
        path: '/log/crash-20260505-boom-abc.txt',
        size: 1024,
      }],
    })
    renderWithProviders(
      <NodeOutputsPanel runId="r1" node="wf.boom" onClose={vi.fn()} />,
    )
    await waitFor(() => {
      expect(screen.getByText(/Crashes \(1\)/i)).toBeInTheDocument()
    })
    expect(screen.getByText('crash-20260505-boom-abc.txt')).toBeInTheDocument()
  })

  it('calls onClose when Close is clicked', async () => {
    mockOutputs({
      node: 'wf.x', leaf_dir: '/w', exists: true, files: [], crashes: [],
    })
    const onClose = vi.fn()
    const { user } = renderWithProviders(
      <NodeOutputsPanel runId="r1" node="wf.x" onClose={onClose} />,
    )
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
