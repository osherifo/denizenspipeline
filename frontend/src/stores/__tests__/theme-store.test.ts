import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useThemeStore } from '../theme-store'

const STORAGE_KEY = 'fmriflow:theme'

describe('theme-store', () => {
  beforeEach(() => {
    localStorage.clear()
    useThemeStore.setState({ mode: 'dark' })
    document.documentElement.removeAttribute('data-theme')
  })

  it('applies the mode to <html> so CSS can target it', () => {
    useThemeStore.getState().setMode('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })

  it('persists the choice across reloads', () => {
    useThemeStore.getState().setMode('light')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('light')
  })

  it('toggles between dark and light', () => {
    expect(useThemeStore.getState().mode).toBe('dark')
    useThemeStore.getState().toggle()
    expect(useThemeStore.getState().mode).toBe('light')
    useThemeStore.getState().toggle()
    expect(useThemeStore.getState().mode).toBe('dark')
  })

  it('survives localStorage being unavailable (private mode)', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceeded')
    })
    expect(() => useThemeStore.getState().setMode('light')).not.toThrow()
    // The in-memory mode and the DOM still update even if persistence fails.
    expect(useThemeStore.getState().mode).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    spy.mockRestore()
  })
})
