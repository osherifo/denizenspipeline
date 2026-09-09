import { useEffect, useState } from 'react'
import type { ManifestDetail } from '../../../api/types'
import { fetchRunNodeManifest } from '../../../api/preproc'

/** The node's preproc manifest JSON, re-read while the run is live. */
export function useNodeManifest(runId: string, nodeId: string, isRunning: boolean) {
  const [manifest, setManifest] = useState<ManifestDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = () => fetchRunNodeManifest(runId, nodeId)
      .then((m) => { if (!cancelled) { setManifest(m); setError(null) } })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    void load()
    if (!isRunning) return () => { cancelled = true }
    const id = setInterval(load, 5000)
    return () => { cancelled = true; clearInterval(id) }
  }, [runId, nodeId, isRunning])
  return { manifest, error }
}
