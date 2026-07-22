/**
 * Theme store — dark (default) / light, persisted in localStorage.
 *
 * The whole UI is styled through the CSS custom properties defined in
 * App.tsx, so switching themes is just swapping that variable block; almost
 * no component needs to know a theme exists. Components that must branch
 * (Monaco's `theme` prop, niivue's canvas colour) read `mode` from here.
 *
 * Resolution order on first load: saved preference > OS `prefers-color-scheme`
 * > dark.
 */

import { create } from 'zustand'

export type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'fmriflow:theme'

function initialMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'dark' || saved === 'light') return saved
    if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light'
  } catch {
    /* SSR / private-mode: fall through to the default */
  }
  return 'dark'
}

/** Expose the mode on <html> so plain CSS can target it too. */
function applyToDocument(mode: ThemeMode): void {
  try {
    document.documentElement.setAttribute('data-theme', mode)
    document.documentElement.style.colorScheme = mode
  } catch {
    /* no document in tests without jsdom */
  }
}

interface ThemeState {
  mode: ThemeMode
  setMode: (mode: ThemeMode) => void
  toggle: () => void
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  mode: initialMode(),

  setMode: (mode) => {
    try {
      localStorage.setItem(STORAGE_KEY, mode)
    } catch { /* non-fatal */ }
    applyToDocument(mode)
    set({ mode })
  },

  toggle: () => get().setMode(get().mode === 'dark' ? 'light' : 'dark'),
}))

// Apply the resolved mode before first paint so there's no dark flash.
applyToDocument(useThemeStore.getState().mode)
