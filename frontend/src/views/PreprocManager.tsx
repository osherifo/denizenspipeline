import type { CSSProperties } from 'react'
/** Preprocessing Manager — browse backends, manifests, collect outputs, run preprocessing. */
import { usePreprocStore } from '../stores/preproc-store'
import { BackendStatus } from '../components/preproc/BackendStatus'
import { ManifestBrowser } from '../components/preproc/ManifestBrowser'
import { CollectForm } from '../components/preproc/CollectForm'
import { RunForm } from '../components/preproc/RunForm'

type Tab = 'backends' | 'manifests' | 'collect' | 'run'

const tabs: { key: Tab; label: string }[] = [
  { key: 'backends', label: 'Backends' },
  { key: 'manifests', label: 'Manifests' },
  { key: 'collect', label: 'Collect' },
  { key: 'run', label: 'Run' },
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

export function PreprocManager() {
  const { tab, setTab } = usePreprocStore()

  return (
    <div>
      <div style={tabBarStyle}>
        {tabs.map((t) => (
          <button key={t.key} style={tabStyle(tab === t.key)} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'backends' && <BackendStatus />}
      {tab === 'manifests' && <ManifestBrowser />}
      {tab === 'collect' && <CollectForm />}
      {tab === 'run' && <RunForm />}
    </div>
  )
}
