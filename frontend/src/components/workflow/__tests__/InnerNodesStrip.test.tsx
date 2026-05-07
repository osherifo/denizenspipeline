/** Compact one-line strip with View DAG button. */

import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders, screen } from '../../../test/render'
import { InnerNodesStrip } from '../InnerNodesStrip'
import type {
  NipypeNodeStatus,
  NipypeStatusBlock,
} from '../../../api/types'


function nodes(statuses: ('running' | 'ok' | 'failed')[]): NipypeNodeStatus[] {
  return statuses.map((s, i) => ({
    node: `wf.n${i}`,
    leaf: `n${i}`,
    workflow: 'wf',
    status: s,
    started_at: 0,
    finished_at: 0,
    elapsed: 0,
    crash_file: null,
    level: s === 'failed' ? 'ERROR' : 'INFO',
  }))
}


function block(statuses: ('running' | 'ok' | 'failed')[]): NipypeStatusBlock {
  const counts = {
    running: 0, ok: 0, failed: 0,
    completed_assumed: 0, total_seen: statuses.length,
  }
  for (const s of statuses) counts[s] += 1
  return { counts, recent_nodes: nodes(statuses) }
}


describe('<InnerNodesStrip />', () => {
  it('renders the running/done/failed counts when nodes are present', () => {
    renderWithProviders(
      <InnerNodesStrip block={block(['running', 'running', 'ok', 'ok', 'ok', 'failed'])} />,
    )
    expect(screen.getByText('2 running')).toBeInTheDocument()
    expect(screen.getByText('3 done')).toBeInTheDocument()
    expect(screen.getByText('1 failed')).toBeInTheDocument()
    expect(screen.getByText('(6 seen)')).toBeInTheDocument()
  })

  it('renders the empty-state message when nothing has been parsed', () => {
    renderWithProviders(<InnerNodesStrip block={block([])} />)
    expect(screen.getByText('no nodes seen yet')).toBeInTheDocument()
  })

  it('shows the View DAG button only when nodes exist', () => {
    const onOpenDag = vi.fn()
    const { rerender } = renderWithProviders(
      <InnerNodesStrip block={block([])} onOpenDag={onOpenDag} />,
    )
    expect(screen.queryByRole('button', { name: /view dag/i })).not.toBeInTheDocument()

    rerender(<InnerNodesStrip block={block(['ok'])} onOpenDag={onOpenDag} />)
    expect(screen.getByRole('button', { name: /view dag/i })).toBeInTheDocument()
  })

  it('does not show the button when no callback is wired', () => {
    renderWithProviders(<InnerNodesStrip block={block(['ok'])} />)
    expect(screen.queryByRole('button', { name: /view dag/i })).not.toBeInTheDocument()
  })

  it('invokes the callback when View DAG is clicked', async () => {
    const onOpenDag = vi.fn()
    const { user } = renderWithProviders(
      <InnerNodesStrip block={block(['ok'])} onOpenDag={onOpenDag} />,
    )
    await user.click(screen.getByRole('button', { name: /view dag/i }))
    expect(onOpenDag).toHaveBeenCalledOnce()
  })

  it('only shows the categories that have a nonzero count', () => {
    renderWithProviders(<InnerNodesStrip block={block(['ok', 'ok'])} />)
    expect(screen.getByText('2 done')).toBeInTheDocument()
    expect(screen.queryByText(/running/)).not.toBeInTheDocument()
    expect(screen.queryByText(/failed/)).not.toBeInTheDocument()
  })
})
