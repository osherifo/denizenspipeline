/** RunDetail in a modal — the Workflows view opens the preproc stage's run here. */
import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocRunsStore } from '../../stores/preproc-runs-store'
import { RunDetail } from './RunDetail'

const backdrop: CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 900, display: 'flex', alignItems: 'center', justifyContent: 'center' }
const card: CSSProperties = { width: 'min(1200px, 96vw)', maxHeight: '92vh', overflow: 'auto', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: 14 }

interface Props {
  runId: string
  onClose: () => void
}

export function RunDetailModal({ runId, onClose }: Props) {
  const select = usePreprocRunsStore((s) => s.select)
  const disconnect = usePreprocRunsStore((s) => s.disconnect)
  useEffect(() => {
    void select(runId)
    return () => disconnect()
  }, [runId, select, disconnect])
  return (
    <div style={backdrop} onClick={onClose}>
      <div style={card} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 14 }}>✕</button>
        </div>
        <RunDetail compact />
      </div>
    </div>
  )
}
