/**
 * Artifact Hub — browse local + remote artifacts across tiers and install
 * or publish them. Advisory install layer: installing copies an artifact into
 * your local user tier (the pipeline resolves it exactly like your own files).
 *
 * Self-contained: delete this file + stores/hub-store.ts and remove the nav
 * entry to fully remove the feature.
 */

import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { useHubStore } from '../stores/hub-store'
import type { HubCatalogItem, HubTier, HubTokenStorage } from '../api/types'

// Bulk-publish sentinel for the artifact dropdown. Contains "/", which can
// never be a real artifact name (names are filename stems), so it can't
// collide with an actual artifact called "__all__".
const ALL_SENTINEL = '__all__/'

const KIND_LABELS: Record<string, string> = {
  error: 'Error KB',
  module: 'Module',
  analysis_config: 'Analysis config',
  workflow_config: 'Workflow config',
  convert_config: 'DICOM→BIDS config',
  preproc_config: 'Preproc config',
  autoflatten_config: 'Autoflatten config',
  stack_preset: 'Preproc preset',
  heuristic: 'Heuristic',
  transform: 'Transform',
  workflow: 'Workflow',
  feature_array: 'Feature array',
}

function tierBadge(tier: HubTier): CSSProperties {
  const c = tier === 'community'
    ? { color: 'var(--accent-green)', bg: 'rgba(0,230,118,0.10)' }
    : { color: 'var(--accent-cyan)', bg: 'rgba(0,229,255,0.10)' }
  return {
    fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 12,
    color: c.color, backgroundColor: c.bg, border: `1px solid ${c.color}`,
    textTransform: 'uppercase', letterSpacing: 0.5,
  }
}

function fmtSize(n: number): string {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(1)} GB`
}

export function HubView() {
  const {
    sources, envOverride, preflight, keyringAvailable, catalog, kindFilter, loading, error, busy, notice,
    localArtifacts, loadSources, addSource, removeSource, sync, syncAll, loadCatalog, install, publish,
    installMany, loadLocalArtifacts, publishLocal, publishKind, setKindFilter, clearNotice,
  } = useHubStore()

  const [form, setForm] = useState({ name: '', url: '', tier: 'lab', branch: 'main', token: '' })
  const [showAdd, setShowAdd] = useState(false)
  const [pub, setPub] = useState({ sourceId: '', kind: '', name: '' })

  useEffect(() => { loadSources(); loadCatalog(); loadLocalArtifacts() }, [loadSources, loadCatalog, loadLocalArtifacts])

  const kinds = useMemo(
    () => Array.from(new Set(catalog.map((i) => i.kind))).sort(),
    [catalog],
  )

  const submitAdd = async () => {
    if (!form.name.trim() || !form.url.trim()) return
    await addSource({
      name: form.name.trim(), url: form.url.trim(), tier: form.tier,
      branch: form.branch.trim() || 'main', token: form.token || undefined,
    })
    setForm({ name: '', url: '', tier: 'lab', branch: 'main', token: '' })
    setShowAdd(false)
  }

  const pubBranch = sources.find((s) => s.id === pub.sourceId)?.branch
  const pubAll = pub.name === ALL_SENTINEL
  const pubBusy = busy === `pub:${pub.sourceId}:${pub.kind}:${pub.name}`
    || busy === `pubkind:${pub.sourceId}:${pub.kind}`
  const submitPublish = () => {
    if (!pub.sourceId || !pub.kind || !pub.name) return
    if (pubAll) publishKind(pub.sourceId, pub.kind)
    else publishLocal(pub.sourceId, pub.kind, pub.name)
  }

  return (
    <div style={container}>
      <style>{'@keyframes hubspin { to { transform: rotate(360deg); } }'}</style>
      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>Artifact Hub</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>
        Browse and install artifacts shared by your lab and the community. Installing copies an
        item into your local tier — the pipeline then uses it like your own files.
      </div>

      {preflight.length > 0 && (
        <div style={banner('warning')}>{preflight.join(' ')} Install it to use git sources.</div>
      )}
      {error && <div style={banner('warning')}>{error}</div>}
      {notice && (
        <button type="button" style={noticeBtn} onClick={clearNotice} title="Dismiss">
          {notice}
        </button>
      )}

      {/* ── Sources ── */}
      <div style={sectionHeader}>
        <span>Sources</span>
        <span style={{ flex: 1 }} />
        <button style={btnSm} disabled={!!busy} onClick={syncAll}>{busy ? <><Spinner /> Working…</> : 'Sync all'}</button>
        {!envOverride && (
          <button style={btnSm} onClick={() => setShowAdd((v) => !v)}>{showAdd ? 'Cancel' : '+ Add source'}</button>
        )}
      </div>

      {envOverride && (
        <div style={banner('info')}>
          <code>$FMRIFLOW_HUB_SOURCES</code> is set in the environment and overrides this list.
        </div>
      )}

      {showAdd && (
        <div style={addCard}>
          <input style={input} placeholder="Name (e.g. My Lab)" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input style={input} placeholder="Git URL (https://… or a file:// path)" value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })} />
          <div style={{ display: 'flex', gap: 8 }}>
            <select style={{ ...input, flex: '0 0 130px' }} value={form.tier}
              onChange={(e) => setForm({ ...form, tier: e.target.value })}>
              <option value="lab">Within-lab</option>
              <option value="community">Community</option>
            </select>
            <input style={{ ...input, flex: '0 0 130px' }} placeholder="Branch (main)" value={form.branch}
              onChange={(e) => setForm({ ...form, branch: e.target.value })} />
            <input style={{ ...input, flex: 1 }} type="password" placeholder="Personal Access Token (optional, for private/push)"
              value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} />
          </div>
          <div style={tokenHelp}>
            <strong>Branch</strong>: an empty repo has none yet — leave it <code>main</code> and your
            first publish creates it. <br />
            <strong>Token</strong>: use a <strong>Personal Access Token</strong> — classic (scope <code>repo</code>) or
            fine-grained (Contents: Read; Read&nbsp;and&nbsp;write to publish). <strong>Not</strong> a
            GitHub-CLI token (<code>gho_…</code> from <code>gh</code>), which expires and fails to authenticate.
            {keyringAvailable
              ? ' It will be stored in your OS keyring (secure), not in a plaintext file.'
              : ' No OS keyring detected — it will be stored in ~/.config/fmriflow/settings.json (plaintext); prefer setting FMRIFLOW_HUB_TOKEN_<ID> in the environment instead.'}
            {' '}Leave blank for public or <code>file://</code> sources. Sources you add are saved — you only enter this once.
          </div>
          <button style={btn} disabled={busy === 'add'} onClick={submitAdd}>Add source</button>
        </div>
      )}

      {sources.length === 0 && <div style={emptyHint}>No sources yet. Add a lab or community git repo to get started.</div>}
      {sources.map((s) => (
        <div key={s.id} style={sourceRow}>
          <span style={tierBadge(s.tier)}>{s.tier === 'community' ? 'community' : 'lab'}</span>
          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{s.name}</span>
          <code style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{s.url}</code>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>@{s.branch}</span>
          {s.synced && <span style={{ fontSize: 11, color: 'var(--accent-green)' }}>✓ synced</span>}
          {s.has_token && <TokenChip storage={s.token_storage} />}
          <span style={{ flex: 1 }} />
          <button style={btnSm} disabled={!!busy} onClick={() => sync(s.id)}>
            {busy === s.id ? <><Spinner /> Syncing…</> : 'Sync'}
          </button>
          {!envOverride && <button style={btnSm} disabled={!!busy} onClick={() => removeSource(s.id)}>Remove</button>}
        </div>
      ))}

      {/* ── Publish a local artifact ── */}
      {sources.length > 0 && Object.keys(localArtifacts).length > 0 && (
        <>
          <div style={sectionHeader}><span>↑ Publish to a store (send your local artifacts)</span></div>
          <div style={{ ...addCard, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center' }}>
            <select style={{ ...input, flex: '0 0 180px' }} value={pub.sourceId}
              onChange={(e) => setPub({ ...pub, sourceId: e.target.value })}>
              <option value="">To source…</option>
              {sources.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.tier})</option>)}
            </select>
            <select style={{ ...input, flex: '0 0 160px' }} value={pub.kind}
              onChange={(e) => setPub({ ...pub, kind: e.target.value, name: '' })}>
              <option value="">Kind…</option>
              {Object.keys(localArtifacts).map((k) => (
                <option key={k} value={k}>{KIND_LABELS[k] ?? k}</option>
              ))}
            </select>
            <select style={{ ...input, flex: 1, minWidth: 160 }} value={pub.name}
              disabled={!pub.kind}
              onChange={(e) => setPub({ ...pub, name: e.target.value })}>
              <option value="">Artifact…</option>
              {pub.kind && (localArtifacts[pub.kind] ?? []).length > 0 && (
                <option value={ALL_SENTINEL}>
                  ▸ All {KIND_LABELS[pub.kind] ?? pub.kind} ({(localArtifacts[pub.kind] ?? []).length})
                </option>
              )}
              {(localArtifacts[pub.kind] ?? []).map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button style={btn}
              disabled={!pub.sourceId || !pub.kind || !pub.name || !!busy}
              onClick={submitPublish}>
              {pubBusy ? <><Spinner /> Publishing…</> : (pubAll ? 'Publish all' : 'Publish')}
            </button>
          </div>
          <div style={tokenHelp}>
            Pushes your local artifact into the store, updates <code>hub.json</code>, and pushes a
            branch (the first publish to an empty store initialises it on{' '}
            <code>{pubBranch || 'its base branch'}</code>). Needs a token with write access on that source.
          </div>
        </>
      )}

      {/* ── Catalog ── */}
      <div style={sectionHeader}>
        <span>Catalog</span>
        <span style={{ flex: 1 }} />
        {catalog.some((i) => !i.installed) && (
          <>
            {kindFilter && (
              <button style={btnSm} disabled={!!busy}
                title={`Install every ${KIND_LABELS[kindFilter] ?? kindFilter} from the store onto this system`}
                onClick={() => installMany(kindFilter)}>
                {busy === `installmany:${kindFilter}`
                  ? <><Spinner /> Installing…</>
                  : `↓ Install all ${KIND_LABELS[kindFilter] ?? kindFilter}`}
              </button>
            )}
            <button style={btnSm} disabled={!!busy}
              title="Install every artifact in the catalog onto this system"
              onClick={() => installMany(null)}>
              {busy === 'installmany:all' ? <><Spinner /> Installing…</> : '↓ Install everything'}
            </button>
          </>
        )}
      </div>
      <div style={legendStyle}>
        <strong>↓ Install</strong> copies an artifact <em>from the store onto this system</em>.{' '}
        <strong>↑ Publish mine</strong> pushes <em>your local version up to the store</em> (on an
        existing store that opens a branch/PR — it won't appear in the catalog until that's merged).
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        <button style={chip(kindFilter === null)} onClick={() => setKindFilter(null)}>All</button>
        {kinds.map((k) => (
          <button key={k} style={chip(kindFilter === k)} onClick={() => setKindFilter(k)}>
            {KIND_LABELS[k] ?? k}
          </button>
        ))}
      </div>

      {loading && <div style={emptyHint}>Loading…</div>}
      {!loading && catalog.length === 0 && (
        <div style={emptyHint}>Nothing in the catalog yet — add a source and hit Sync.</div>
      )}
      {catalog.map((item) => (
        <ArtifactRow key={`${item.source_id}:${item.kind}:${item.name}`} item={item}
          busy={busy === `${item.source_id}:${item.kind}:${item.name}`}
          anyBusy={!!busy}
          onInstall={() => install(item)} onPublish={() => publish(item)} />
      ))}
    </div>
  )
}

function Spinner() {
  // Decorative — the button keeps its "Syncing…/Publishing…" text label, so
  // hide the glyph from assistive tech to keep the accessible name clean.
  return <span aria-hidden style={{ display: 'inline-block', animation: 'hubspin 0.7s linear infinite' }}>⟳</span>
}

function TokenChip({ storage }: { storage: HubTokenStorage }) {
  const map: Record<HubTokenStorage, { label: string; color: string; title: string }> = {
    keyring: { label: '🔒 keyring', color: 'var(--accent-green)', title: 'Token stored securely in the OS keyring' },
    env: { label: '🔑 env', color: 'var(--accent-cyan)', title: 'Token from a FMRIFLOW_HUB_TOKEN_<ID> environment variable' },
    settings: { label: '⚠️ plaintext', color: 'var(--accent-yellow)', title: 'Token stored in ~/.config/fmriflow/settings.json (plaintext) — no OS keyring available' },
    none: { label: '', color: '', title: '' },
  }
  const m = map[storage]
  if (!m.label) return null
  return <span style={{ fontSize: 10, color: m.color }} title={m.title}>{m.label}</span>
}

function ArtifactRow({ item, busy, anyBusy, onInstall, onPublish }: {
  item: HubCatalogItem; busy: boolean; anyBusy: boolean; onInstall: () => void; onPublish: () => void
}) {
  return (
    <div style={artifactRow}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
        <span style={kindPill}>{KIND_LABELS[item.kind] ?? item.kind}</span>
        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{item.name}</span>
        <span style={tierBadge(item.tier)}>{item.source_name}</span>
        {item.installed && <span style={installedBadge}>installed</span>}
        {item.lfs && <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>LFS {fmtSize(item.size)}</span>}
      </div>
      {item.description && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>{item.description}</div>
      )}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {item.tags.map((t) => <span key={t} style={tag}>{t}</span>)}
        <span style={{ flex: 1 }} />
        <button style={btnSm} disabled={anyBusy || item.installed} onClick={onInstall}
          title="Copy this artifact from the store onto this system">
          {item.installed ? '✓ Installed' : busy ? <><Spinner /> Installing…</> : '↓ Install'}
        </button>
        <button style={btnSm} disabled={anyBusy} onClick={onPublish}
          title="Push YOUR local version of this artifact up to the store (opens a branch/PR)">
          {busy ? <><Spinner /> Publishing…</> : '↑ Publish mine'}
        </button>
      </div>
    </div>
  )
}

// ── styles ──
const container: CSSProperties = { maxWidth: 960, padding: '24px 32px' }
const sectionHeader: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 700,
  color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: 0.5,
  marginTop: 28, marginBottom: 12,
}
const sourceRow: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
  border: '1px solid var(--border)', borderRadius: 8, marginBottom: 8, backgroundColor: 'var(--bg-card)',
}
const artifactRow: CSSProperties = {
  padding: '10px 14px', border: '1px solid var(--border)', borderRadius: 8,
  marginBottom: 8, backgroundColor: 'var(--bg-card)',
}
const addCard: CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 8, padding: 12,
  border: '1px solid var(--border)', borderRadius: 8, marginBottom: 12, backgroundColor: 'var(--bg-secondary)',
}
const input: CSSProperties = {
  padding: '7px 10px', fontSize: 13, fontFamily: 'inherit', backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-primary)', outline: 'none',
}
const btn: CSSProperties = {
  padding: '7px 16px', fontSize: 13, fontWeight: 600, border: '1px solid var(--accent-cyan)',
  borderRadius: 6, background: 'rgba(0,229,255,0.1)', color: 'var(--accent-cyan)', cursor: 'pointer',
  alignSelf: 'flex-start',
}
const btnSm: CSSProperties = {
  padding: '4px 10px', fontSize: 12, border: '1px solid var(--border)', borderRadius: 6,
  background: 'var(--bg-input)', color: 'var(--text-primary)', cursor: 'pointer',
}
const chip = (active: boolean): CSSProperties => ({
  padding: '4px 12px', fontSize: 12, borderRadius: 14, cursor: 'pointer',
  border: `1px solid ${active ? 'var(--accent-cyan)' : 'var(--border)'}`,
  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  background: active ? 'rgba(0,229,255,0.1)' : 'transparent',
})
const kindPill: CSSProperties = {
  fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
  color: 'var(--text-secondary)', border: '1px solid var(--border)', textTransform: 'uppercase',
}
const installedBadge: CSSProperties = {
  fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 12,
  color: 'var(--accent-green)', background: 'rgba(0,230,118,0.10)', border: '1px solid var(--accent-green)',
}
const tag: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 10, padding: '1px 8px' }
const emptyHint: CSSProperties = { fontSize: 13, color: 'var(--text-secondary)', padding: '12px 0' }
const legendStyle: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 12,
}
const tokenHelp: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5, marginTop: -2 }
const banner = (kind: 'info' | 'warning'): CSSProperties => {
  const c = kind === 'warning'
    ? { color: 'var(--accent-yellow)', bg: 'rgba(255,184,108,0.10)' }
    : { color: 'var(--accent-cyan)', bg: 'rgba(0,229,255,0.08)' }
  return { padding: '10px 14px', borderRadius: 6, fontSize: 12, color: c.color, background: c.bg, border: `1px solid ${c.color}`, marginBottom: 14 }
}
// Dismissible notice as an accessible <button> (keyboard-focusable, announced).
const noticeBtn: CSSProperties = {
  ...banner('info'), display: 'block', width: '100%', textAlign: 'left',
  font: 'inherit', fontSize: 12, cursor: 'pointer',
}
