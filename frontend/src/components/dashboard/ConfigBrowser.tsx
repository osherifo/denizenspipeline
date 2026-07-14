/** Config browser sidebar with grouping and filters. */
import { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { ConfigSummary } from '../../api/types'
import { HubBadge } from '../hub/HubBadge'

interface ConfigBrowserProps {
  configs: ConfigSummary[]
  selectedFilename: string | null
  loading: boolean
  onSelect: (filename: string) => void
  onRescan: () => void
}

const sidebarStyle: CSSProperties = {
  width: 260,
  minWidth: 260,
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const searchInput: CSSProperties = {
  margin: '12px',
  padding: '8px 12px',
  fontSize: 12,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
  outline: 'none',
}

const configItem = (active: boolean): CSSProperties => ({
  padding: '8px 16px 8px 24px',
  fontSize: 12,
  cursor: 'pointer',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
})

const configName: CSSProperties = {
  fontWeight: 600,
  color: 'var(--text-primary)',
  marginBottom: 2,
}

const configMeta: CSSProperties = {
  fontSize: 10,
  color: 'var(--text-secondary)',
  display: 'flex',
  gap: 8,
  alignItems: 'center',
}

const runBadge = (n: number): CSSProperties => ({
  fontSize: 10,
  padding: '1px 5px',
  borderRadius: 3,
  backgroundColor: n > 0 ? 'rgba(0, 230, 118, 0.12)' : 'rgba(136, 136, 170, 0.12)',
  color: n > 0 ? 'var(--accent-green)' : 'var(--text-secondary)',
})

const rescanBtn: CSSProperties = {
  margin: '8px 12px 12px',
  padding: '6px',
  fontSize: 11,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

const tabBar: CSSProperties = {
  display: 'flex',
  margin: '0 12px 8px',
  borderBottom: '1px solid var(--border)',
}

const tabBtn = (active: boolean): CSSProperties => ({
  flex: 1,
  padding: '8px 6px',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 1,
  background: 'transparent',
  border: 'none',
  borderBottom: active
    ? '2px solid var(--accent-cyan)'
    : '2px solid transparent',
  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'inherit',
})

type Tab = 'subject' | 'group' | 'study'

export function ConfigBrowser({ configs, selectedFilename, loading, onSelect, onRescan }: ConfigBrowserProps) {
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<Tab>('subject')

  // Tally per-kind counts up front (independent of search) so the tab
  // labels always show the total available.
  const counts = useMemo(() => {
    let subj = 0, grp = 0, stu = 0
    for (const c of configs) {
      const k = c.kind ?? 'subject'
      if (k === 'study') stu += 1
      else if (k === 'group') grp += 1
      else subj += 1
    }
    return { subject: subj, group: grp, study: stu }
  }, [configs])

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return configs.filter((c) => {
      const kind = c.kind ?? 'subject'
      if (kind !== tab) return false
      if (!q) return true
      return (
        c.filename.toLowerCase().includes(q) ||
        c.experiment.toLowerCase().includes(q) ||
        c.subject.toLowerCase().includes(q) ||
        c.model_type.toLowerCase().includes(q) ||
        (c.group_subjects ?? []).some((s) => s.toLowerCase().includes(q)) ||
        (c.study_groups ?? []).some((g) => g.toLowerCase().includes(q))
      )
    })
  }, [configs, search, tab])

  // Flat alphabetical list — no longer grouped by filename prefix.
  const sortedConfigs = useMemo(
    () => [...filtered].sort((a, b) => a.filename.localeCompare(b.filename)),
    [filtered],
  )

  return (
    <div style={sidebarStyle}>
      <input
        type="text"
        placeholder="Search configs..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={searchInput}
      />

      <div style={tabBar}>
        <button
          style={tabBtn(tab === 'subject')}
          onClick={() => setTab('subject')}
        >
          Subject ({counts.subject})
        </button>
        <button
          style={tabBtn(tab === 'group')}
          onClick={() => setTab('group')}
        >
          Group ({counts.group})
        </button>
        <button
          style={tabBtn(tab === 'study')}
          onClick={() => setTab('study')}
        >
          Study ({counts.study})
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {sortedConfigs.map((c) => {
          const kind = c.kind ?? 'subject'
          // Left meta — what's actually informative per kind:
          //   subject  → which subject this config runs
          //   group    → how many subjects fan out
          //   study    → study-scope group labels
          // Model name was redundant here (it's in the config card),
          // so it's no longer surfaced in the sidebar.
          let leftLabel: string
          if (kind === 'study') {
            leftLabel = (c.study_groups ?? []).join(' · ') || '?'
          } else if (kind === 'group') {
            leftLabel = `${(c.group_subjects ?? []).length} subj`
          } else {
            leftLabel = c.subject || '?'
          }
          return (
            <div
              key={c.filename}
              style={configItem(selectedFilename === c.filename)}
              onClick={() => onSelect(c.filename)}
            >
              <div style={configName}>
                {c.filename.replace('.yaml', '')}
                {' '}<HubBadge kind="analysis_config" name={c.filename} />
              </div>
              <div style={configMeta}>
                <span>{leftLabel}</span>
                <span style={runBadge(c.n_runs)}>
                  {c.n_runs} run{c.n_runs !== 1 ? 's' : ''}
                </span>
              </div>
            </div>
          )
        })}

        {filtered.length === 0 && !loading && (
          <div style={{ padding: '24px 16px', fontSize: 12, color: 'var(--text-secondary)', textAlign: 'center' }}>
            {tab === 'study'
              ? 'No study configs found. Put a YAML with top-level "study:" + "groups:" in experiments/study/ or $FMRIFLOW_HOME/configs/study/.'
              : tab === 'group'
              ? 'No group configs found. Put a YAML with top-level "group:" + "subjects:" in experiments/group/ or $FMRIFLOW_HOME/configs/group/.'
              : 'No subject configs found.'}
          </div>
        )}
      </div>

      <button style={rescanBtn} onClick={onRescan} disabled={loading}>
        {loading ? 'Scanning...' : 'Rescan'}
      </button>
    </div>
  )
}
