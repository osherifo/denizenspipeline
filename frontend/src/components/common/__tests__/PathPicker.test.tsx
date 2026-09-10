import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { PathField, PathPickerModal } from '../PathPicker'
import { server } from '../../../test/mocks/server'

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

describe('PathPickerModal files in directory mode', () => {
  it('lists files but only lets a folder be picked', async () => {
    const onPick = vi.fn()
    render(<PathPickerModal initialPath="/workspace/data/dicoms" onPick={onPick} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('README.txt')).toBeInTheDocument())
    expect(screen.getByText(/1 folders · 1 files/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('README.txt'))
    // a file click selects nothing in directory mode: the pick button still offers the directory
    expect(screen.getByText('Use this directory')).toBeInTheDocument()
    expect(screen.queryByText('Use selected')).toBeNull()
    fireEvent.click(screen.getByText('sub01'))
    fireEvent.click(screen.getByText('Use selected'))
    expect(onPick).toHaveBeenCalledWith('/workspace/data/dicoms/sub01')
  })
})

describe('PathPickerModal stale navigation', () => {
  it('a slower earlier open() cannot overwrite a faster later one\'s listing', async () => {
    let releaseSlow!: () => void
    const slow = new Promise<void>((resolve) => { releaseSlow = resolve })
    // Overrides the whole route (msw matches on the URL path, and every listing
    // request shares the same path with a different ?path= query param), so the
    // other two paths this test needs are reconstructed here rather than relying
    // on any fallthrough to the base handler.
    server.use(
      http.get('/api/fs/list', async ({ request }) => {
        const p = new URL(request.url).searchParams.get('path')
        if (p === '/workspace/data/dicoms') {
          await slow
          return HttpResponse.json({ path: p, parent: '/workspace/data', entries: [
            { name: 'sub01', path: '/workspace/data/dicoms/sub01', is_dir: true },
            { name: 'README.txt', path: '/workspace/data/dicoms/README.txt', is_dir: false, size: 12 },
          ], truncated: false })
        }
        if (p === '/workspace/data/bids') {
          return HttpResponse.json({ path: p, parent: '/workspace/data', entries: [
            { name: 'sub02', path: '/workspace/data/bids/sub02', is_dir: true },
          ], truncated: false })
        }
        if (p === '/workspace/data') {
          return HttpResponse.json({ path: p, parent: '/workspace', entries: [
            { name: 'dicoms', path: '/workspace/data/dicoms', is_dir: true },
            { name: 'bids', path: '/workspace/data/bids', is_dir: true },
          ], truncated: false })
        }
        return HttpResponse.json({ detail: 'path is outside the browsable roots' }, { status: 403 })
      }),
    )
    render(<PathPickerModal onPick={vi.fn()} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('dicoms')).toBeInTheDocument())

    fireEvent.doubleClick(screen.getByText('dicoms'))   // slow: still awaiting `slow` above
    fireEvent.doubleClick(screen.getByText('bids'))      // fast: resolves first
    await waitFor(() => expect(screen.getByText('sub02')).toBeInTheDocument())

    releaseSlow()
    await new Promise((r) => setTimeout(r, 30))
    // The listing must still be bids's — the stale dicoms response must not
    // have landed on top of it.
    expect(screen.getByText('sub02')).toBeInTheDocument()
    expect(screen.queryByText('README.txt')).toBeNull()
    expect(screen.getByText('/workspace/data/bids')).toBeInTheDocument()
  })
})

describe('PathPickerModal reopening on a file path', () => {
  it('opens the containing folder and preselects the file instead of erroring', async () => {
    const onPick = vi.fn()
    render(<PathPickerModal initialPath="/workspace/data/dicoms/README.txt" mode="any" onPick={onPick} onClose={() => {}} />)
    // The containing folder's listing, not a "not a directory" error.
    await waitFor(() => expect(screen.getByText('sub01')).toBeInTheDocument())
    expect(screen.queryByText(/not a directory/)).toBeNull()
    // The file itself is already selected — one click picks it, no extra navigation.
    fireEvent.click(screen.getByText('Use selected'))
    expect(onPick).toHaveBeenCalledWith('/workspace/data/dicoms/README.txt')
  })
})

describe('PathPickerModal roots', () => {
  it('shows no data/home chips, only extra roots', async () => {
    render(<PathPickerModal onPick={vi.fn()} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('dicoms')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'data' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'home' })).toBeNull()
  })
})

describe("PathPickerModal mode='any'", () => {
  it('lets either a file or a folder be picked', async () => {
    const onPick = vi.fn()
    render(<PathPickerModal initialPath="/workspace/data/dicoms" mode="any" onPick={onPick} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('README.txt')).toBeInTheDocument())
    expect(screen.getByText('Choose a file or folder')).toBeInTheDocument()

    // a file can be selected and picked (unlike plain 'dir' mode, where files are inert)
    fireEvent.click(screen.getByText('README.txt'))
    fireEvent.click(screen.getByText('Use selected'))
    expect(onPick).toHaveBeenCalledWith('/workspace/data/dicoms/README.txt')

    // a folder can also be selected and picked (unlike plain 'file' mode, which
    // disables the pick button once a directory is selected)
    onPick.mockClear()
    fireEvent.click(screen.getByText('sub01'))
    fireEvent.click(screen.getByText('Use selected'))
    expect(onPick).toHaveBeenCalledWith('/workspace/data/dicoms/sub01')
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
