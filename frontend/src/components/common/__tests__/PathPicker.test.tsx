import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { PathField, PathPickerModal } from '../PathPicker'

describe('PathPickerModal', () => {
  it('opens at the first root, navigates into a directory and picks it', async () => {
    const onPick = vi.fn()
    render(<PathPickerModal onPick={onPick} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('dicoms')).toBeInTheDocument())
    fireEvent.doubleClick(screen.getByText('dicoms'))
    await waitFor(() => expect(screen.getByText('sub01')).toBeInTheDocument())
    expect(screen.getByText('README.txt')).toBeInTheDocument()
    fireEvent.doubleClick(screen.getByText('sub01'))
    await waitFor(() => expect(screen.getByText('ses1')).toBeInTheDocument())
    fireEvent.click(screen.getByText('ses1'))
    fireEvent.click(screen.getByText('Use selected'))
    expect(onPick).toHaveBeenCalledWith('/workspace/data/dicoms/sub01/ses1')
  })

  it('uses the current directory when nothing is selected', async () => {
    const onPick = vi.fn()
    render(<PathPickerModal initialPath="/workspace/data/dicoms" onPick={onPick} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('sub01')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Use this directory'))
    expect(onPick).toHaveBeenCalledWith('/workspace/data/dicoms')
  })
})

describe('PathField', () => {
  it('warns when the server cannot see a typed path', async () => {
    const onChange = vi.fn()
    const { rerender } = render(<PathField value="" onChange={onChange} />)
    rerender(<PathField value="/mnt/host/only/path" onChange={onChange} />)
    await waitFor(() => expect(screen.getByText(/cannot see this path/)).toBeInTheDocument(), { timeout: 2000 })
    rerender(<PathField value="/workspace/data/bids" onChange={onChange} />)
    await waitFor(() => expect(screen.queryByText(/cannot see this path/)).not.toBeInTheDocument(), { timeout: 2000 })
  })
})


describe('PathField with a base dir', () => {
  it('opens under the base and stores the pick relative to it', async () => {
    const onChange = vi.fn()
    render(<PathField value="" onChange={onChange} baseDir="/workspace/data/dicoms" compact />)
    fireEvent.click(screen.getByText('…'))
    await waitFor(() => expect(screen.getByText('sub01')).toBeInTheDocument())
    fireEvent.click(screen.getByText('sub01'))
    fireEvent.click(screen.getByText('Use selected'))
    expect(onChange).toHaveBeenCalledWith('sub01')
  })
})
