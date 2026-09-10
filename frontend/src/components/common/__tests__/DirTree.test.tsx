import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { DirTree } from '../DirTree'

describe('DirTree', () => {
  it('shows the root expanded and expands children on click', async () => {
    render(<DirTree path="/workspace/data/dicoms" />)
    await waitFor(() => expect(screen.getByText('sub01/')).toBeInTheDocument())
    expect(screen.getByText('README.txt')).toBeInTheDocument()
    fireEvent.click(screen.getByText('sub01/'))
    await waitFor(() => expect(screen.getByText('ses1/')).toBeInTheDocument())
  })

  it('says when the directory is gone', async () => {
    render(<DirTree path="/mnt/gone" title="BIDS directory" />)
    await waitFor(() => expect(screen.getByText(/no longer exists/)).toBeInTheDocument())
  })
})
