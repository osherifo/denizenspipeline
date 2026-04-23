import type { CSSProperties } from 'react'
/** DICOM-to-BIDS Converter — browse tools, heuristics, scan DICOMs, manifests, run conversion, batch. */
import { useConvertStore } from '../stores/convert-store'
import { ToolStatusPanel } from '../components/convert/ToolStatus'
import { HeuristicBrowser } from '../components/convert/HeuristicBrowser'
import { DicomScanner } from '../components/convert/DicomScanner'
import { ConvertManifestBrowser } from '../components/convert/ConvertManifestBrowser'
import { ConvertForm } from '../components/convert/ConvertForm'
import { BatchForm } from '../components/convert/BatchForm'
import { BatchProgress } from '../components/convert/BatchProgress'
import { ConvertConfigBrowser } from '../components/convert/ConvertConfigBrowser'

type Tab = 'tools' | 'heuristics' | 'scan' | 'manifests' | 'configs' | 'convert' | 'batch'

const tabs: { key: Tab; label: string }[] = [
  { key: 'tools', label: 'Tools' },
  { key: 'heuristics', label: 'Heuristics' },
  { key: 'scan', label: 'Scan' },
  { key: 'manifests', label: 'Manifests' },
  { key: 'configs', label: 'Configs' },
  { key: 'convert', label: 'Convert' },
  { key: 'batch', label: 'Batch' },
]

const tabBarStyle: CSSProperties = {
  display: 'flex',
  gap: 4,
  marginBottom: 16,
}

function tabStyle(active: boolean): CSSProperties {
  return {
    padding: '8px 20px',
    fontSize: 12,
    fontWeight: 600,
    fontFamily: 'inherit',
    border: active ? '1px solid var(--accent-cyan)' : '1px solid var(--border)',
    borderRadius: 6,
    cursor: 'pointer',
    backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
    color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  }
}

export function DicomBidsConverter() {
  const { tab, setTab, batchRunning, batchEvents } = useConvertStore()

  const hasBatchProgress = batchRunning || batchEvents.length > 0

  return (
    <div>
      <div style={tabBarStyle}>
        {tabs.map((t) => (
          <button key={t.key} style={tabStyle(tab === t.key)} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'tools' && <ToolStatusPanel />}
      {tab === 'heuristics' && <HeuristicBrowser />}
      {tab === 'scan' && <DicomScanner />}
      {tab === 'manifests' && <ConvertManifestBrowser />}
      {tab === 'configs' && <ConvertConfigBrowser />}
      {tab === 'convert' && <ConvertForm />}
      {tab === 'batch' && (
        <>
          <BatchForm />
          {hasBatchProgress && <BatchProgress />}
        </>
      )}
    </div>
  )
}
