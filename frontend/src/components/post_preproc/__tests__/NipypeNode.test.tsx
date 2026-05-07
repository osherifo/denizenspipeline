/** Render the post-preproc canvas's custom node renderer. */

import { describe, it, expect } from 'vitest'
import { ReactFlowProvider } from '@xyflow/react'
import { renderWithProviders, screen } from '../../../test/render'
import { NipypeNode } from '../NipypeNode'
import type { NipypeNodeData } from '../NipypeNode'


function buildData(overrides: Partial<NipypeNodeData> = {}): NipypeNodeData {
  return {
    label: 'smooth (n1)',
    nodeType: 'smooth',
    inputs: ['in_file'],
    outputs: ['out_file'],
    iterating: false,
    ...overrides,
  }
}


function renderNode(data: NipypeNodeData) {
  // XYFlow's <Handle> requires a ReactFlow context to mount.
  return renderWithProviders(
    <ReactFlowProvider>
      <NipypeNode
        id="n1"
        type="nipype"
        data={data as any}
        dragging={false}
        selectable={false}
        deletable={false}
        draggable={false}
        selected={false}
        isConnectable={false}
        positionAbsoluteX={0}
        positionAbsoluteY={0}
        zIndex={0}
      />
    </ReactFlowProvider>,
  )
}


describe('<NipypeNode />', () => {
  it('renders the nodeType label', () => {
    renderNode(buildData({ nodeType: 'smooth' }))
    expect(screen.getByText('smooth')).toBeInTheDocument()
  })

  it('renders one labelled input handle per declared INPUT', () => {
    renderNode(buildData({
      nodeType: 'mask_apply',
      inputs: ['in_file', 'mask_file'],
      outputs: ['out_file'],
    }))
    expect(screen.getByText('in_file')).toBeInTheDocument()
    expect(screen.getByText('mask_file')).toBeInTheDocument()
    expect(screen.getByText('out_file')).toBeInTheDocument()
  })

  it('renders the map badge when iterating is true', () => {
    renderNode(buildData({ iterating: true }))
    expect(screen.getByText('map')).toBeInTheDocument()
  })

  it('omits the map badge by default', () => {
    renderNode(buildData({ iterating: false }))
    expect(screen.queryByText('map')).not.toBeInTheDocument()
  })

  it('handles a node with no inputs (source-only)', () => {
    renderNode(buildData({
      nodeType: 'preproc_run',
      inputs: [],
      outputs: ['out_file'],
    }))
    expect(screen.getByText('preproc_run')).toBeInTheDocument()
    expect(screen.getByText('out_file')).toBeInTheDocument()
  })
})
