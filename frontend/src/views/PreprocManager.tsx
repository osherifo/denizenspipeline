import type { CSSProperties } from 'react'
/** Preprocessing Manager — read-side only after Stage 7d-A.
 *
 * The launch surface (Run tab + Configs tab + RunForm +
 * PreprocConfigBrowser) was hard-removed. What stays:
 *
 * - Backends: backend availability check.
 * - Manifests: browse existing PreprocManifest files.
 * - Collect: build a manifest from existing preprocessed outputs.
 *
 * Banner at the top points users at the new preproc-stack page.
 */
import { usePreprocStore } from '../stores/preproc-store'
import { BackendStatus } from '../components/preproc/BackendStatus'
import { ManifestBrowser } from '../components/preproc/ManifestBrowser'
import { CollectForm } from '../components/preproc/CollectForm'
import { InFlightRuns } from '../components/preproc/InFlightRuns'

type Tab = 'backends' | 'manifests' | 'collect'

const tabs: { key: Tab; label: string }[] = [
  { key: 'backends', label: 'Backends' },
  { key: 'manifests', label: 'Manifests' },
  { key: 'collect', label: 'Collect' },
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

const noticeBannerStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--accent-cyan)',
  borderRadius: 6,
  padding: '10px 14px',
  marginBottom: 14,
  fontSize: 12,
  color: 'var(--text-primary)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
}

const bannerLinkStyle: CSSProperties = {
  color: 'var(--bg-primary)',
  background: 'var(--accent-cyan)',
  fontWeight: 700,
  textDecoration: 'none',
  padding: '6px 12px',
  borderRadius: 4,
  fontSize: 11,
  whiteSpace: 'nowrap',
}


export function PreprocManager() {
  const { tab, setTab } = usePreprocStore()

  return (
    <div>
      <div style={noticeBannerStyle}>
        <div>
          <strong style={{ color: 'var(--accent-cyan)' }}>
            Run preprocessing on the new Preproc (stack) page
          </strong>
          <div style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
            This page now does only manifest browsing, backend status
            checks, and collecting existing outputs into manifests.
            Launching preprocessing runs moved to the stack page —
            with cached re-runs, mid-pipeline transforms, and
            schema-driven param forms.
          </div>
        </div>
        <a href="#preproc-stack" style={bannerLinkStyle}>
          Open Preproc (stack) →
        </a>
      </div>

      <div style={tabBarStyle}>
        {tabs.map((t) => (
          <button key={t.key} style={tabStyle(tab === t.key)} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'backends' && <BackendStatus />}
      {tab === 'manifests' && (
        <>
          <ManifestBrowser />
          <InFlightRuns />
        </>
      )}
      {tab === 'collect' && <CollectForm />}
    </div>
  )
}
