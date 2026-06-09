/** localStorage-backed label mode preference. */

import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLabelMode } from '../use_label_mode'


describe('useLabelMode', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('defaults to friendly when nothing is stored', () => {
    const { result } = renderHook(() => useLabelMode())
    expect(result.current[0]).toBe('friendly')
  })

  it('reads an existing raw preference from localStorage', () => {
    window.localStorage.setItem('nipype.label_mode', 'raw')
    const { result } = renderHook(() => useLabelMode())
    expect(result.current[0]).toBe('raw')
  })

  it('persists the new mode to localStorage when updated', () => {
    const { result } = renderHook(() => useLabelMode())
    act(() => { result.current[1]('raw') })
    expect(result.current[0]).toBe('raw')
    expect(window.localStorage.getItem('nipype.label_mode')).toBe('raw')
  })

  it('rejects garbage stored values and falls back to friendly', () => {
    window.localStorage.setItem('nipype.label_mode', 'bogus-mode')
    const { result } = renderHook(() => useLabelMode())
    expect(result.current[0]).toBe('friendly')
  })

  it('round-trips friendly → raw → friendly', () => {
    const { result } = renderHook(() => useLabelMode())
    act(() => { result.current[1]('raw') })
    expect(result.current[0]).toBe('raw')
    act(() => { result.current[1]('friendly') })
    expect(result.current[0]).toBe('friendly')
    expect(window.localStorage.getItem('nipype.label_mode')).toBe('friendly')
  })
})
