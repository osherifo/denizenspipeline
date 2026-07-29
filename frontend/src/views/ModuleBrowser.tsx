import { useEffect, useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useModuleStore } from '../stores/module-store'
import { ModuleCard } from '../components/modules/ModuleCard'
import { ModuleSourceEditor } from './ModuleSourceEditor'
import {
  fetchTemplate, fetchTemplateCategories, fetchQaStages,
} from '../api/client'
import type { ModuleInfo } from '../api/types'

const headerStyle: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 8,
}

const subtitleStyle: CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  marginBottom: 24,
}

const searchWrapperStyle: CSSProperties = {
  marginBottom: 24,
}

const searchInputStyle: CSSProperties = {
  width: '100%',
  maxWidth: 480,
  padding: '10px 16px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  outline: 'none',
}

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
  gap: 24,
  alignItems: 'start',
}

const stageColumnStyle: CSSProperties = {
  minWidth: 0,
}

const stageTitleStyle = (color?: string): CSSProperties => ({
  fontSize: 14,
  fontWeight: 700,
  color: color || 'var(--accent-cyan)',
  marginBottom: 4,
  textTransform: 'uppercase',
  letterSpacing: 1.5,
})

const stageDescStyle: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginBottom: 12,
}

const countBadge: CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 8px',
  borderRadius: 10,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  marginLeft: 8,
}

const loadingStyle: CSSProperties = {
  color: 'var(--text-secondary)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

const errorStyle: CSSProperties = {
  color: 'var(--accent-red)',
  fontSize: 14,
  padding: '60px 0',
  textAlign: 'center',
}

type Scope = 'subject' | 'group' | 'study' | 'qa'

const SCOPE_ORDER: Scope[] = ['subject', 'group', 'study', 'qa']
const SCOPE_LABELS: Record<Scope, string> = {
  subject: 'Subject',
  group: 'Group',
  study: 'Study',
  qa: 'QA',
}

// Plugin categories that belong to each scope. ``qa_reporters`` registers
// against subject pipeline stages but is shown in its own tab so the
// regular subject columns don't conflate "pipeline plugins" with
// "stage-level QA reporters".
const CATEGORIES_BY_SCOPE: Record<Scope, ReadonlySet<string>> = {
  subject: new Set([
    'stimulus_loaders', 'response_loaders', 'response_readers',
    'feature_extractors', 'feature_sources',
    'preparers', 'preparation_steps',
    'analyzers', 'models', 'reporters', 'nipype_nodes',
  ]),
  group: new Set(['group_analyzers', 'group_reporters']),
  study: new Set(['study_analyzers', 'study_reporters']),
  qa: new Set(['qa_reporters']),
}

function scopeForCategory(category: string): Scope {
  for (const scope of SCOPE_ORDER) {
    if (CATEGORIES_BY_SCOPE[scope].has(category)) return scope
  }
  return 'subject'
}

const tabsRow: CSSProperties = {
  display: 'flex',
  gap: 4,
  borderBottom: '1px solid var(--border)',
  marginBottom: 18,
}

const tabBtn = (active: boolean): CSSProperties => ({
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 600,
  border: 'none',
  background: 'transparent',
  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  borderBottom: active ? '2px solid var(--accent-cyan)' : '2px solid transparent',
  cursor: 'pointer',
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  fontFamily: 'inherit',
  marginBottom: -1,
})

const scopeBadge: CSSProperties = {
  display: 'inline-block',
  fontSize: 10,
  fontWeight: 600,
  padding: '1px 6px',
  borderRadius: 10,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  marginLeft: 6,
}

const newModuleBtn: CSSProperties = {
  padding: '10px 16px',
  fontSize: 12,
  fontWeight: 700,
  border: '1px solid var(--accent-cyan)',
  borderRadius: 6,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  fontFamily: 'inherit',
}

const dialogBackdrop: CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.6)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
}

const dialogCard: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '20px 22px',
  width: 460,
  maxWidth: '90vw',
  display: 'flex',
  flexDirection: 'column',
  gap: 14,
}

const dialogLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4,
  display: 'block',
}

const dialogInput: CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  fontSize: 13,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  outline: 'none',
  boxSizing: 'border-box',
}

const dialogActions: CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 10,
}

const dialogErrorBlock: CSSProperties = {
  fontSize: 11,
  color: 'var(--accent-red, #ef5350)',
  backgroundColor: 'rgba(239, 83, 80, 0.08)',
  border: '1px solid var(--accent-red, #ef5350)',
  borderRadius: 6,
  padding: '8px 10px',
}

interface NewModuleSeed {
  category: string
  name: string
  stage?: string
  initialCode: string
}

export function ModuleBrowser() {
  const refreshModules = useModuleStore((s) => s.refresh)
  const { modules, stages, loaded, loading, error } = useModuleStore()
  const [search, setSearch] = useState('')
  const [scope, setScope] = useState<Scope>('subject')
  const [editing, setEditing] = useState<{ category: string; name: string } | null>(null)
  const [creating, setCreating] = useState<NewModuleSeed | null>(null)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [templateCategories, setTemplateCategories] = useState<string[] | null>(null)
  const [qaStages, setQaStages] = useState<Record<string, string> | null>(null)

  // Group modules by (scope, stage). Keying by scope alongside stage
  // keeps qa_reporters from leaking into the regular subject columns
  // — a qa_reporter with ``stage: prepare`` lives under the QA tab's
  // ``prepare`` column, not next to the subject ``preparers``.
  const filteredByScopeStage = useMemo(() => {
    const query = search.toLowerCase().trim()
    const result: Record<Scope, Record<string, ModuleInfo[]>> = {
      subject: {}, group: {}, study: {}, qa: {},
    }
    for (const [category, moduleList] of Object.entries(modules)) {
      const filtered = query
        ? moduleList.filter(
            (p) =>
              p.name.toLowerCase().includes(query) ||
              (p.docstring && p.docstring.toLowerCase().includes(query))
          )
        : moduleList
      if (filtered.length === 0) continue
      const scope = scopeForCategory(category)
      for (const m of filtered) {
        const stage = m.stage || category
        if (!result[scope][stage]) result[scope][stage] = []
        result[scope][stage].push(m)
      }
    }
    return result
  }, [modules, search])

  // Per-scope module counts for the tab badges.
  const scopeCounts = useMemo(() => {
    const counts: Record<Scope, number> = { subject: 0, group: 0, study: 0, qa: 0 }
    for (const scope of SCOPE_ORDER) {
      for (const list of Object.values(filteredByScopeStage[scope])) {
        counts[scope] += list.length
      }
    }
    return counts
  }, [filteredByScopeStage])

  if (editing) {
    return (
      <ModuleSourceEditor
        category={editing.category}
        name={editing.name}
        onBack={() => setEditing(null)}
      />
    )
  }

  if (creating) {
    return (
      <ModuleSourceEditor
        mode="create"
        category={creating.category}
        name={creating.name}
        stage={creating.stage}
        initialCode={creating.initialCode}
        onBack={() => {
          setCreating(null)
          // Pick up the newly saved (or newly cancelled) module so the
          // browser list reflects the live registry without a reload.
          refreshModules()
        }}
      />
    )
  }

  if (loading) {
    return <div style={loadingStyle}>Loading modules...</div>
  }

  if (error) {
    return <div style={errorStyle}>Error loading modules: {error}</div>
  }

  if (!loaded) {
    return <div style={loadingStyle}>Waiting for data...</div>
  }

  // Stages within the active scope, ordered by their per-scope index.
  // Stages with no ``scope`` field (older backend) default to subject.
  // The QA tab borrows the subject pipeline stages — qa_reporters
  // register against them but live in this dedicated tab so the
  // regular subject columns stay focused on pipeline plugins.
  const stagesForScope = scope === 'qa' ? 'subject' : scope
  const visibleStages = stages
    .filter((s) => (s.scope ?? 'subject') === stagesForScope)
    .sort((a, b) => a.index - b.index)
  const stageModulesAt = (stageName: string): ModuleInfo[] =>
    filteredByScopeStage[scope][stageName] || []
  const totalModules = Object.values(modules).reduce((sum, list) => sum + list.length, 0)

  return (
    <div>
      <div style={headerStyle}>Module Browser</div>
      <div style={subtitleStyle}>
        {totalModules} modules across {stages.length} stages
      </div>

      <div style={tabsRow}>
        {SCOPE_ORDER.map((s) => (
          <button
            key={s}
            style={tabBtn(scope === s)}
            onClick={() => setScope(s)}
          >
            {SCOPE_LABELS[s]}
            <span style={scopeBadge}>{scopeCounts[s] ?? 0}</span>
          </button>
        ))}
      </div>

      <div style={{
        ...searchWrapperStyle,
        display: 'flex', gap: 12, alignItems: 'center',
      }}>
        <input
          type="text"
          placeholder="Search modules by name or description..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={searchInputStyle}
        />
        <button
          type="button"
          onClick={() => {
            setShowCreateDialog(true)
          }}
          style={newModuleBtn}
        >
          + New module
        </button>
      </div>
      {visibleStages.length === 0 ? (
        <div style={{ ...loadingStyle, padding: '32px 0' }}>
          No {SCOPE_LABELS[scope].toLowerCase()}-scope stages registered.
        </div>
      ) : (
        <div style={gridStyle}>
          {visibleStages.map((stage) => {
            const stageModules = stageModulesAt(stage.name)
            if (search && stageModules.length === 0) return null
            return (
              <div key={stage.name} style={stageColumnStyle}>
                <div style={stageTitleStyle(stage.color)}>
                  {stage.index}. {stage.name}
                  <span style={countBadge}>{stageModules.length}</span>
                </div>
                <div style={stageDescStyle}>{stage.description}</div>
                {stageModules.length === 0 ? (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                    No modules
                  </div>
                ) : (
                  <div style={{
                    maxHeight: 330,
                    overflowY: stageModules.length > 3 ? 'auto' : 'visible',
                    paddingRight: stageModules.length > 3 ? 4 : 0,
                  }}>
                    {stageModules.map((p) => (
                      <ModuleCard
                        key={`${p.category}-${p.name}`}
                        module={p}
                        onEdit={(category, name) => setEditing({ category, name })}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showCreateDialog && (
        <NewModuleDialog
          scope={scope}
          templateCategories={templateCategories}
          qaStages={qaStages}
          onLoadTemplateCategories={async () => {
            const cats = await fetchTemplateCategories()
            setTemplateCategories(cats)
            return cats
          }}
          onLoadQaStages={async () => {
            const m = await fetchQaStages()
            setQaStages(m)
            return m
          }}
          onCancel={() => setShowCreateDialog(false)}
          onCreate={async (category, name, stage) => {
            const tmpl = await fetchTemplate(category, name, stage)
            setShowCreateDialog(false)
            setCreating({
              category, name, stage,
              initialCode: tmpl.code,
            })
          }}
        />
      )}
    </div>
  )
}


// ── + New module dialog ──────────────────────────────────────────────

interface NewModuleDialogProps {
  scope: Scope
  templateCategories: string[] | null
  qaStages: Record<string, string> | null
  onLoadTemplateCategories: () => Promise<string[]>
  onLoadQaStages: () => Promise<Record<string, string>>
  onCancel: () => void
  onCreate: (category: string, name: string, stage?: string) => Promise<void>
}

function NewModuleDialog({
  scope, templateCategories, qaStages,
  onLoadTemplateCategories, onLoadQaStages,
  onCancel, onCreate,
}: NewModuleDialogProps) {
  const [category, setCategory] = useState<string>('')
  const [name, setName] = useState<string>('')
  const [stage, setStage] = useState<string>('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch on open if we haven't cached yet.
  useEffect(() => {
    if (templateCategories == null) onLoadTemplateCategories().catch(() => {})
    if (qaStages == null) onLoadQaStages().catch(() => {})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Default the category to the first one belonging to the active
  // scope (when scope='qa' that's qa_reporters; for subject we pick
  // any subject-scope creatable category) — saves a click.
  useEffect(() => {
    if (category || !templateCategories) return
    const scopeCats = templateCategories.filter(
      (c) => CATEGORIES_BY_SCOPE[scope].has(c),
    )
    if (scopeCats.length > 0) setCategory(scopeCats[0])
  }, [templateCategories, scope, category])

  const isQa = category === 'qa_reporters'
  const availableStages = qaStages ? Object.keys(qaStages).sort() : []
  const validName = /^[a-z][a-z0-9_]*$/.test(name)

  const canSubmit =
    !!category && !!name && validName && (!isQa || !!stage) && !submitting

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      await onCreate(category, name, isQa ? stage : undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setSubmitting(false)
    }
  }

  return (
    <div style={dialogBackdrop} onClick={onCancel}>
      <div style={dialogCard} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
          New module
        </div>
        <div>
          <label style={dialogLabel}>Category</label>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value)
              setError(null)
            }}
            style={dialogInput}
          >
            <option value="">
              {templateCategories == null ? 'Loading…' : 'Pick a category…'}
            </option>
            {(templateCategories || [])
              .filter((c) => CATEGORIES_BY_SCOPE[scope].has(c))
              .map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
          </select>
        </div>

        {isQa && (
          <div>
            <label style={dialogLabel}>Stage</label>
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              style={dialogInput}
            >
              <option value="">
                {qaStages == null ? 'Loading…' : 'Pick a stage…'}
              </option>
              {availableStages.map((s) => (
                <option key={s} value={s}>
                  {s} ({qaStages?.[s]})
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label style={dialogLabel}>Name (snake_case)</label>
          <input
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              setError(null)
            }}
            style={dialogInput}
            placeholder="e.g. my_score_histogram"
            autoFocus
          />
          {name && !validName && (
            <div style={{ fontSize: 10, color: 'var(--accent-red)', marginTop: 4 }}>
              Use lowercase letters, digits, and underscores; must start with a letter.
            </div>
          )}
        </div>

        {error && <div style={dialogErrorBlock}>{error}</div>}

        <div style={dialogActions}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '8px 16px', fontSize: 12, fontWeight: 600,
              border: '1px solid var(--border)', borderRadius: 6,
              backgroundColor: 'transparent', color: 'var(--text-secondary)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              padding: '8px 18px', fontSize: 12, fontWeight: 700,
              border: '1px solid var(--accent-cyan)',
              borderRadius: 6,
              backgroundColor: canSubmit
                ? 'var(--accent-cyan)' : 'rgba(0, 229, 255, 0.1)',
              color: canSubmit ? 'var(--on-accent)' : 'var(--accent-cyan)',
              cursor: canSubmit ? 'pointer' : 'not-allowed',
              letterSpacing: 0.5, textTransform: 'uppercase',
              fontFamily: 'inherit',
            }}
          >
            {submitting ? 'Loading…' : 'Open editor'}
          </button>
        </div>
      </div>
    </div>
  )
}
