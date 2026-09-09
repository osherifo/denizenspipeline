import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PipelineGraph } from '../PipelineGraph'
import { NODE_LIBRARY, TEMPLATE_PIPELINE } from '../../../test/mocks/handlers.preproc-pipelines'

describe('PipelineGraph', () => {
  it('renders one card per node with its ports and kind', () => {
    render(<PipelineGraph pipeline={TEMPLATE_PIPELINE} library={NODE_LIBRARY} />)
    // 'source' is both the node id and its kind tag.
    expect(screen.getAllByText('source').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('smooth')).toBeInTheDocument()
    expect(screen.getByText('derivatives_dir')).toBeInTheDocument()
    expect(screen.getByText('out_file')).toBeInTheDocument()
    expect(screen.getAllByText('node').length).toBeGreaterThan(0)
    expect(screen.getByText('×N')).toBeInTheDocument()       // smooth iterates
    expect(screen.getByText('★')).toBeInTheDocument()        // source is the backend node
  })

  it('shows a checkpoint badge with the worst verdict', () => {
    render(
      <PipelineGraph
        pipeline={TEMPLATE_PIPELINE}
        library={NODE_LIBRARY}
        statusByNode={{ smooth: { status: 'ok', durationS: 3 } }}
        checkpointsByNode={{ smooth: { worst: 'bad', count: 2 } }}
      />,
    )
    expect(screen.getByTitle('2 checkpoint(s), worst: bad')).toBeInTheDocument()
    expect(screen.getByText('3.0s')).toBeInTheDocument()
  })
})
