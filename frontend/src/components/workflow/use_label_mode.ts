/** localStorage-backed preference for the nipype DAG modal's label mode.
 *
 * Friendly = lead with the conceptual fmriprep name ("Head motion
 *            correction"), demote the raw id to a subtitle.
 * Raw      = lead with the raw nipype workflow id (`bold_hmc_wf`),
 *            keep the conceptual name as an italic subtitle (the
 *            pre-2026-05 rendering).
 */

import { useCallback, useEffect, useState } from 'react'

export type LabelMode = 'friendly' | 'raw'

const STORAGE_KEY = 'nipype.label_mode'
const DEFAULT_MODE: LabelMode = 'friendly'


function _read(): LabelMode {
  if (typeof window === 'undefined') return DEFAULT_MODE
  try {
    const v = window.localStorage.getItem(STORAGE_KEY)
    return v === 'raw' ? 'raw' : v === 'friendly' ? 'friendly' : DEFAULT_MODE
  } catch {
    return DEFAULT_MODE
  }
}


export function useLabelMode(): [LabelMode, (m: LabelMode) => void] {
  const [mode, setModeState] = useState<LabelMode>(() => _read())

  // Cross-tab sync: if the user toggles the mode in another tab,
  // pick up the change here too.
  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key !== STORAGE_KEY) return
      const next = e.newValue === 'raw' ? 'raw' : 'friendly'
      setModeState(next)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const setMode = useCallback((m: LabelMode) => {
    setModeState(m)
    try { window.localStorage.setItem(STORAGE_KEY, m) } catch { /* ignore */ }
  }, [])

  return [mode, setMode]
}
