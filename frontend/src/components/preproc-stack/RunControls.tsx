/**
 * Run binding form + Run/Cancel buttons.
 *
 * The stack itself is subject-agnostic; this panel collects the
 * subject + paths to bind it to a real run.
 */

import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'


const panelStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: 16,
  marginTop: 16,
}

const fieldRowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 12,
  marginBottom: 12,
}

const labelStyle: CSSProperties = {
  display: 'block',
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: 'var(--text-secondary)',
  marginBottom: 4,
}

const inputStyle: CSSProperties = {
  width: '100%',
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '8px 10px',
  fontSize: 13,
  fontFamily: 'inherit',
  borderRadius: 4,
}

const primaryButton: CSSProperties = {
  background: 'var(--accent-green)',
  color: 'var(--bg-primary)',
  border: 'none',
  padding: '10px 20px',
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer',
  borderRadius: 4,
}

const cancelButton: CSSProperties = {
  background: 'transparent',
  color: 'var(--accent-red)',
  border: '1px solid var(--accent-red)',
  padding: '10px 20px',
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer',
  borderRadius: 4,
}


export function RunControls() {
  const subject = usePreprocStackStore((s) => s.subject)
  const outputDir = usePreprocStackStore((s) => s.outputDir)
  const bidsDir = usePreprocStackStore((s) => s.bidsDir)
  const derivativesDir = usePreprocStackStore((s) => s.derivativesDir)
  const dataset = usePreprocStackStore((s) => s.dataset)
  const task = usePreprocStackStore((s) => s.task)
  const useCache = usePreprocStackStore((s) => s.useCache)
  const activeStatus = usePreprocStackStore((s) => s.activeStatus)
  const activeError = usePreprocStackStore((s) => s.activeError)
  const setRunBinding = usePreprocStackStore((s) => s.setRunBinding)
  const launch = usePreprocStackStore((s) => s.launch)
  const cancel = usePreprocStackStore((s) => s.cancel)

  const isRunning = activeStatus === 'running' || activeStatus === 'launching'
  const canLaunch = !isRunning && !!subject && !!outputDir

  return (
    <div style={panelStyle}>
      <div style={fieldRowStyle}>
        <div>
          <label style={labelStyle}>Subject *</label>
          <input
            style={inputStyle}
            value={subject}
            placeholder="sub01"
            onChange={(e) => setRunBinding({ subject: e.target.value })}
          />
        </div>
        <div>
          <label style={labelStyle}>Output dir *</label>
          <input
            style={inputStyle}
            value={outputDir}
            placeholder="/data/out/sub-01"
            onChange={(e) => setRunBinding({ outputDir: e.target.value })}
          />
        </div>
      </div>

      <div style={fieldRowStyle}>
        <div>
          <label style={labelStyle}>BIDS dir</label>
          <input
            style={inputStyle}
            value={bidsDir}
            placeholder="/data/bids"
            onChange={(e) => setRunBinding({ bidsDir: e.target.value })}
          />
        </div>
        <div>
          <label style={labelStyle}>Derivatives dir (for passthrough)</label>
          <input
            style={inputStyle}
            value={derivativesDir}
            placeholder="/data/derivatives"
            onChange={(e) => setRunBinding({ derivativesDir: e.target.value })}
          />
        </div>
      </div>

      <div style={fieldRowStyle}>
        <div>
          <label style={labelStyle}>Dataset</label>
          <input
            style={inputStyle}
            value={dataset}
            onChange={(e) => setRunBinding({ dataset: e.target.value })}
          />
        </div>
        <div>
          <label style={labelStyle}>Task</label>
          <input
            style={inputStyle}
            value={task}
            placeholder="story"
            onChange={(e) => setRunBinding({ task: e.target.value })}
          />
        </div>
      </div>

      <label
        style={{
          ...labelStyle,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 16,
          cursor: 'pointer',
        }}
      >
        <input
          type="checkbox"
          checked={useCache}
          onChange={(e) => setRunBinding({ useCache: e.target.checked })}
        />
        <span>Use cache (skip stages whose fingerprint matches)</span>
      </label>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <button
          style={{
            ...primaryButton,
            opacity: canLaunch ? 1 : 0.5,
            cursor: canLaunch ? 'pointer' : 'not-allowed',
          }}
          disabled={!canLaunch}
          onClick={() => void launch()}
        >
          {isRunning ? 'Running...' : 'Run pipeline'}
        </button>
        {isRunning && (
          <button style={cancelButton} onClick={() => void cancel()}>
            Cancel
          </button>
        )}
        {activeStatus && !isRunning && (
          <span
            style={{
              fontSize: 13,
              color:
                activeStatus === 'done'
                  ? 'var(--accent-green)'
                  : activeStatus === 'cancelled'
                  ? 'var(--accent-yellow)'
                  : 'var(--accent-red)',
            }}
          >
            {activeStatus}
          </span>
        )}
      </div>

      {activeError && (
        <div
          style={{
            marginTop: 10,
            padding: 8,
            background: 'var(--bg-input)',
            border: '1px solid var(--accent-red)',
            borderRadius: 4,
            fontSize: 12,
            color: 'var(--accent-red)',
          }}
        >
          {activeError}
        </div>
      )}
    </div>
  )
}
