/** GroupComposer — author group-scope analysis configs.
 *
 * Layout mirrors :file:`AnalysisComposer.tsx`: a left form column with
 * scope-specific structured fields (group name, subject list,
 * group-scope plugin stacks) and a right column with a Monaco YAML
 * editor that is the source of truth for nested
 * ``subject_template`` / ``subject_overrides`` blocks.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useGroupConfigStore } from '../stores/group-config-store'
import { useModuleStore } from '../stores/module-store'
import { configFromYaml, configToYaml } from '../api/client'
import { ModuleStack } from '../components/composer/ModuleStack'
import { ModuleSlot } from '../components/composer/ModuleSlot'
import { YamlEditor } from '../components/composer/YamlEditor'
import { StageCard } from '../components/composer/StageCard'
import {
  SubjectStagesProvider,
} from '../components/composer/SubjectStagesContext'
import type {
  SubjectStagesAPI,
} from '../components/composer/SubjectStagesContext'
import {
  STAGE_DEFS, summaryFor,
  StimulusBody, ResponseBody, FeaturesBody, PreparationBody,
  ModelBody, AnalysisBody, ReportingBody,
} from '../components/composer/subject-stages'
import type {
  ModuleInfo, GroupPluginConfig,
  PipelineConfig, FeatureConfig, StepConfig, AnalyzerConfig,
} from '../api/types'


const pageStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 460px',
  gap: 24,
  alignItems: 'start',
  padding: '24px 28px',
  height: 'calc(100vh - 48px - 48px)',
  boxSizing: 'border-box',
}

const leftColStyle: CSSProperties = {
  overflowY: 'auto',
  paddingRight: 4,
  paddingBottom: 24,
  height: '100%',
}

const rightColStyle: CSSProperties = {
  position: 'sticky',
  top: 0,
  height: 'calc(100vh - 48px - 48px)',
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
}

const subtitleStyle: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginBottom: 18,
}

const cardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '16px 18px',
  marginBottom: 18,
}

const sectionTitle: CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: 'var(--text-primary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginBottom: 12,
}

const labelSmall: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4,
  display: 'block',
}

const inputStyle: CSSProperties = {
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

const actionBarStyle: CSSProperties = {
  display: 'flex',
  gap: 10,
  marginBottom: 18,
}

const primaryBtn: CSSProperties = {
  padding: '8px 18px',
  fontSize: 13,
  fontWeight: 600,
  border: '1px solid var(--accent-cyan)',
  borderRadius: 6,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
  cursor: 'pointer',
}

const secondaryBtn: CSSProperties = {
  ...primaryBtn,
  borderColor: 'var(--border)',
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
}

const yamlHeaderStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
}

const yamlEditorWrap: CSSProperties = {
  flex: 1,
  border: '1px solid var(--border)',
  borderRadius: 8,
  overflow: 'hidden',
  minHeight: 0,
}

const yamlErrorBlock: CSSProperties = {
  padding: '8px 10px',
  fontSize: 11,
  color: 'var(--accent-red, #ef5350)',
  backgroundColor: 'rgba(239, 83, 80, 0.08)',
  border: '1px solid var(--accent-red, #ef5350)',
  borderRadius: 6,
}

const errorListStyle: CSSProperties = {
  marginTop: 8,
  padding: '8px 12px',
  fontSize: 11,
  color: 'var(--accent-red, #ef5350)',
  backgroundColor: 'rgba(239, 83, 80, 0.08)',
  border: '1px solid var(--accent-red, #ef5350)',
  borderRadius: 6,
}


function modulesIn(modules: Record<string, ModuleInfo[]>, categories: string[]): ModuleInfo[] {
  const out: ModuleInfo[] = []
  for (const c of categories) out.push(...(modules[c] || []))
  return out
}


const overrideEditorWrap: CSSProperties = {
  border: '1px solid var(--border)',
  borderRadius: 6,
  overflow: 'hidden',
  height: 160,
}

const overrideHeaderRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 6,
}

const overrideErrorBlock: CSSProperties = {
  marginTop: 4,
  padding: '4px 8px',
  fontSize: 10,
  color: 'var(--accent-red, #ef5350)',
  backgroundColor: 'rgba(239, 83, 80, 0.08)',
  border: '1px solid var(--accent-red, #ef5350)',
  borderRadius: 4,
}


/** One per-subject override slot — Monaco YAML editor wired to a
 *  ``subject_overrides[<subject>]`` slice of the group config.
 *  Parses on a 600ms debounce; bad YAML leaves the store value
 *  untouched and surfaces a small error band. */
function SubjectOverrideCard({
  subject, value, onChange, onRemove,
}: {
  subject: string
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  onRemove: () => void
}) {
  const [text, setText] = useState<string>('')
  const [parseError, setParseError] = useState<string | null>(null)
  const lastSyncedRef = useRef<string | null>(null)
  const applyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountedRef = useRef(false)

  // Hydrate / refresh editor text from the store value when the store
  // changes externally (initial load, YAML editor on right pane edits
  // the same key, …). Skip when the change came from this editor's
  // own debounced apply — lastSyncedRef tracks that.
  useEffect(() => {
    let cancelled = false
    configToYaml(value || {}).then((yaml) => {
      if (cancelled) return
      if (yaml.trim() === (lastSyncedRef.current || '').trim()) return
      setText(yaml)
      lastSyncedRef.current = yaml
      setParseError(null)
    }).catch(() => { /* leave text as-is */ })
    return () => { cancelled = true }
  }, [value])

  // Cancel the debounced YAML-apply timer + flag the card as
  // unmounted, so a setTimeout that fires after Remove can't write
  // to the store or call setState on a stale component.
  useEffect(() => {
    return () => {
      unmountedRef.current = true
      if (applyTimer.current) {
        clearTimeout(applyTimer.current)
        applyTimer.current = null
      }
    }
  }, [])

  const handleEditorChange = (next: string) => {
    setText(next)
    if (applyTimer.current) clearTimeout(applyTimer.current)
    applyTimer.current = setTimeout(async () => {
      try {
        const result = await configFromYaml(next || '{}')
        if (unmountedRef.current) return
        if (result.errors.length > 0) {
          setParseError(result.errors[0])
          return
        }
        setParseError(null)
        lastSyncedRef.current = next
        onChange((result.config as Record<string, unknown>) || {})
      } catch (e) {
        if (unmountedRef.current) return
        setParseError(String(e))
      }
    }, 600)
  }

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={overrideHeaderRow}>
        <span style={{
          fontSize: 12, fontWeight: 700, color: 'var(--text-primary)',
          fontFamily: "'JetBrains Mono', monospace",
        }}>{subject}</span>
        <button
          type="button"
          onClick={onRemove}
          style={{
            padding: '4px 10px', fontSize: 10, fontWeight: 600,
            border: '1px solid var(--border)', borderRadius: 4,
            backgroundColor: 'transparent', color: 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          Remove
        </button>
      </div>
      <div style={overrideEditorWrap}>
        <YamlEditor value={text} onChange={handleEditorChange} height="100%" />
      </div>
      {parseError && (
        <div style={overrideErrorBlock}>YAML: {parseError}</div>
      )}
    </div>
  )
}


/** Subject overrides card — list of per-subject sparse override dicts.
 *
 * Subjects with overrides come from ``config.subject_overrides``;
 * the "+ Add override" dropdown offers any subject in ``config.subjects``
 * that doesn't yet have one. Each card is a small YAML editor scoped
 * to ``subject_overrides[<subject>]``. */
function SubjectOverridesCard() {
  const config = useGroupConfigStore((s) => s.config)
  const setField = useGroupConfigStore((s) => s.setField)
  const [pickSubject, setPickSubject] = useState<string>('')

  const subjects = (config.subjects || []) as string[]
  const overrides = (config.subject_overrides || {}) as Record<string, Record<string, unknown>>
  const overrideKeys = useMemo(() => Object.keys(overrides), [overrides])

  // Subjects that don't yet have an override entry.
  const candidates = subjects.filter((s) => !(s in overrides))

  const handleAdd = () => {
    if (!pickSubject) return
    if (pickSubject in overrides) {
      setPickSubject('')
      return
    }
    setField('subject_overrides', { ...overrides, [pickSubject]: {} })
    setPickSubject('')
  }

  const handleRemove = (subject: string) => {
    const next = { ...overrides }
    delete next[subject]
    setField('subject_overrides', next)
  }

  const handleUpdate = (subject: string, next: Record<string, unknown>) => {
    setField('subject_overrides', { ...overrides, [subject]: next })
  }

  return (
    <div style={cardStyle}>
      <div style={sectionTitle}>Subject overrides</div>
      <div style={{
        fontSize: 11, color: 'var(--text-secondary)', marginBottom: 12,
      }}>
        Sparse per-subject deviations from the template above. Each entry
        is deep-merged on top of the template for that subject's run.
      </div>

      {overrideKeys.map((sub) => (
        <SubjectOverrideCard
          key={sub}
          subject={sub}
          value={overrides[sub] || {}}
          onChange={(next) => handleUpdate(sub, next)}
          onRemove={() => handleRemove(sub)}
        />
      ))}

      {overrideKeys.length === 0 && (
        <div style={{
          fontSize: 11, fontStyle: 'italic',
          color: 'var(--text-secondary)', marginBottom: 10,
        }}>
          No overrides yet — every subject uses the shared template.
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <select
          value={pickSubject}
          onChange={(e) => setPickSubject(e.target.value)}
          style={{ ...inputStyle, maxWidth: 220 }}
          disabled={candidates.length === 0}
        >
          <option value="">
            {candidates.length === 0
              ? subjects.length === 0
                ? 'No subjects defined yet'
                : 'Every subject already overridden'
              : 'Pick a subject…'}
          </option>
          {candidates.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={handleAdd}
          disabled={!pickSubject}
          style={{
            padding: '8px 14px', fontSize: 12, fontWeight: 600,
            border: '1px solid var(--accent-cyan)',
            borderRadius: 6,
            backgroundColor: 'rgba(0, 229, 255, 0.1)',
            color: 'var(--accent-cyan)',
            cursor: pickSubject ? 'pointer' : 'not-allowed',
            opacity: pickSubject ? 1 : 0.5,
          }}
        >
          + Add override
        </button>
      </div>
    </div>
  )
}


export function GroupComposer() {
  const config = useGroupConfigStore((s) => s.config)
  const yamlString = useGroupConfigStore((s) => s.yamlString)
  const validationErrors = useGroupConfigStore((s) => s.validationErrors)
  const yamlErrors = useGroupConfigStore((s) => s.yamlErrors)
  const isDirty = useGroupConfigStore((s) => s.isDirty)
  const yamlEditing = useGroupConfigStore((s) => s.yamlEditing)
  const setField = useGroupConfigStore((s) => s.setField)
  const validate = useGroupConfigStore((s) => s.validate)
  const exportYaml = useGroupConfigStore((s) => s.exportYaml)
  const syncYaml = useGroupConfigStore((s) => s.syncYaml)
  const setYamlDirect = useGroupConfigStore((s) => s.setYamlDirect)
  const applyYaml = useGroupConfigStore((s) => s.applyYaml)
  const reset = useGroupConfigStore((s) => s.reset)
  const addGroupAnalyzer = useGroupConfigStore((s) => s.addGroupAnalyzer)
  const removeGroupAnalyzer = useGroupConfigStore((s) => s.removeGroupAnalyzer)
  const updateGroupAnalyzer = useGroupConfigStore((s) => s.updateGroupAnalyzer)
  const addGroupReporter = useGroupConfigStore((s) => s.addGroupReporter)
  const removeGroupReporter = useGroupConfigStore((s) => s.removeGroupReporter)
  const updateGroupReporter = useGroupConfigStore((s) => s.updateGroupReporter)

  const modules = useModuleStore((s) => s.modules)
  const moduleStoreLoaded = useModuleStore((s) => s.loaded)
  const yamlApplyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // form → YAML sync
  useEffect(() => {
    if (isDirty && !yamlEditing) {
      const t = setTimeout(() => syncYaml(), 500)
      return () => clearTimeout(t)
    }
  }, [config, isDirty, yamlEditing, syncYaml])

  const handleYamlChange = useCallback(
    (value: string) => {
      setYamlDirect(value)
      if (yamlApplyTimer.current) clearTimeout(yamlApplyTimer.current)
      yamlApplyTimer.current = setTimeout(() => applyYaml(), 800)
    },
    [setYamlDirect, applyYaml],
  )

  const handleExport = useCallback(async () => {
    const yaml = await exportYaml()
    try {
      await navigator.clipboard.writeText(yaml)
    } catch {
      // clipboard rejected; user can copy from the editor
    }
  }, [exportYaml])

  // Adapter so the 7 stage bodies (StimulusBody / ResponseBody / …)
  // can edit ``subject_template`` without ever knowing they're inside
  // a group config. Every read / write is scoped to that nested slice.
  const subjectTemplate = useMemo<PipelineConfig>(() => {
    return (config.subject_template as PipelineConfig | undefined) || {}
  }, [config.subject_template])

  const stagesApi = useMemo<SubjectStagesAPI>(() => {
    const writeTemplate = (next: PipelineConfig) => {
      setField('subject_template', next)
    }
    return {
      config: subjectTemplate,
      setField: (path: string, value: unknown) => {
        // Same dot-path semantics the subject store uses, but rooted
        // at ``subject_template``.
        setField(`subject_template.${path}`, value)
      },
      addFeature: (f: FeatureConfig) => {
        writeTemplate({
          ...subjectTemplate,
          features: [...(subjectTemplate.features || []), f],
        })
      },
      removeFeature: (i: number) => {
        writeTemplate({
          ...subjectTemplate,
          features: (subjectTemplate.features || []).filter((_, idx) => idx !== i),
        })
      },
      updateFeature: (i: number, f: FeatureConfig) => {
        const arr = [...(subjectTemplate.features || [])]
        arr[i] = f
        writeTemplate({ ...subjectTemplate, features: arr })
      },
      reorderFeatures: (from: number, to: number) => {
        const arr = [...(subjectTemplate.features || [])]
        const [m] = arr.splice(from, 1)
        arr.splice(to, 0, m)
        writeTemplate({ ...subjectTemplate, features: arr })
      },
      addStep: (s: StepConfig) => {
        const prep = { ...(subjectTemplate.preparation || {}) }
        prep.steps = [...((prep.steps as StepConfig[]) || []), s]
        writeTemplate({ ...subjectTemplate, preparation: prep })
      },
      removeStep: (i: number) => {
        const prep = { ...(subjectTemplate.preparation || {}) }
        prep.steps = ((prep.steps as StepConfig[]) || []).filter((_, idx) => idx !== i)
        writeTemplate({ ...subjectTemplate, preparation: prep })
      },
      updateStep: (i: number, s: StepConfig) => {
        const prep = { ...(subjectTemplate.preparation || {}) }
        const arr = [...((prep.steps as StepConfig[]) || [])]
        arr[i] = s
        prep.steps = arr
        writeTemplate({ ...subjectTemplate, preparation: prep })
      },
      reorderSteps: (from: number, to: number) => {
        const prep = { ...(subjectTemplate.preparation || {}) }
        const arr = [...((prep.steps as StepConfig[]) || [])]
        const [m] = arr.splice(from, 1)
        arr.splice(to, 0, m)
        prep.steps = arr
        writeTemplate({ ...subjectTemplate, preparation: prep })
      },
      addAnalyzer: (a: AnalyzerConfig) => {
        writeTemplate({
          ...subjectTemplate,
          analysis: [...((subjectTemplate.analysis as AnalyzerConfig[]) || []), a],
        })
      },
      removeAnalyzer: (i: number) => {
        writeTemplate({
          ...subjectTemplate,
          analysis: ((subjectTemplate.analysis as AnalyzerConfig[]) || []).filter(
            (_, idx) => idx !== i,
          ),
        })
      },
      updateAnalyzer: (i: number, a: AnalyzerConfig) => {
        const arr = [...((subjectTemplate.analysis as AnalyzerConfig[]) || [])]
        arr[i] = a
        writeTemplate({ ...subjectTemplate, analysis: arr })
      },
    }
  }, [subjectTemplate, setField])

  const groupAnalyzers = useMemo(
    () => modulesIn(modules, ['group_analyzers']),
    [modules],
  )
  const groupReporters = useMemo(
    () => modulesIn(modules, ['group_reporters']),
    [modules],
  )

  const subjects = (config.subjects || []).join(', ')
  const groupAnalyze = (config.group_analyze || []) as GroupPluginConfig[]
  const groupReport = (config.group_report || []) as GroupPluginConfig[]

  if (!moduleStoreLoaded) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-secondary)' }}>
        Loading module metadata…
      </div>
    )
  }

  return (
    <div style={pageStyle}>
      {/* ── Left column ── */}
      <div style={leftColStyle}>
        <div style={subtitleStyle}>
          Author a cross-subject group config. The shared subject
          pipeline is editable in the <code>Subject template</code> card
          below — the same 7-stage form the Subject scope uses, rooted
          at <code>subject_template</code> instead of the top level.
          Per-subject deviations go under <code>Subject overrides</code>.
          The right pane's YAML mirrors every form edit and is also
          editable directly.
        </div>

        <div style={actionBarStyle}>
          <button style={primaryBtn} onClick={() => validate()}>Validate</button>
          <button style={secondaryBtn} onClick={handleExport}>Copy YAML</button>
          <button style={secondaryBtn} onClick={reset}>Reset</button>
        </div>

        {/* Top — group + subjects + output_dir */}
        <div style={cardStyle}>
          <div style={{ marginBottom: 12 }}>
            <label style={labelSmall}>Group name</label>
            <input
              type="text"
              value={config.group || ''}
              onChange={(e) => setField('group', e.target.value)}
              style={inputStyle}
              placeholder="e.g. reading_8subj"
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={labelSmall}>Subjects (comma-separated)</label>
            <input
              type="text"
              value={subjects}
              onChange={(e) =>
                setField(
                  'subjects',
                  e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                )
              }
              style={inputStyle}
              placeholder="e.g. S01, S02, S03"
            />
          </div>
          <div>
            <label style={labelSmall}>Output directory</label>
            <input
              type="text"
              value={config.output_dir || ''}
              onChange={(e) => setField('output_dir', e.target.value)}
              style={{ ...inputStyle, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}
              placeholder="./results"
            />
          </div>
        </div>

        {/* Subject template — full 7-stage subject pipeline editor.
            Renders the same StageCard / body components SubjectComposer
            uses, but rooted at config.subject_template via the
            SubjectStagesProvider adapter. */}
        <div style={cardStyle}>
          <div style={sectionTitle}>Subject template</div>
          <div style={{
            fontSize: 11, color: 'var(--text-secondary)', marginBottom: 12,
          }}>
            Shared subject pipeline applied to every subject in the group.
            Per-subject deviations go under <code>subject_overrides</code>.
          </div>
          <SubjectStagesProvider api={stagesApi}>
            {STAGE_DEFS.map((s) => {
              const { summary, status, badge } = summaryFor(s.key, subjectTemplate)
              return (
                <StageCard
                  key={s.key}
                  num={s.num}
                  name={s.name}
                  color={s.color}
                  status={status}
                  summary={summary}
                  badge={badge}
                  anchorId={`group-stage-${s.key}`}
                  initiallyCollapsed={true}
                >
                  {s.key === 'stimulus' && <StimulusBody />}
                  {s.key === 'response' && <ResponseBody />}
                  {s.key === 'features' && <FeaturesBody />}
                  {s.key === 'preparation' && <PreparationBody />}
                  {s.key === 'model' && <ModelBody />}
                  {s.key === 'analysis' && <AnalysisBody />}
                  {s.key === 'reporting' && <ReportingBody />}
                </StageCard>
              )
            })}
          </SubjectStagesProvider>
        </div>

        {/* Subject overrides — per-subject sparse override dicts. */}
        <SubjectOverridesCard />

        {/* Group analyze */}
        <div style={cardStyle}>
          <div style={sectionTitle}>Group analyze</div>
          <ModuleStack<GroupPluginConfig>
            items={groupAnalyze}
            onAdd={() => addGroupAnalyzer({ name: '', params: {} })}
            onRemove={removeGroupAnalyzer}
            onMove={(from, to) => {
              const next = [...groupAnalyze]
              const [m] = next.splice(from, 1)
              next.splice(to, 0, m)
              next.forEach((a, idx) => updateGroupAnalyzer(idx, a))
            }}
            addLabel="Add group analyzer"
            emptyMessage="No group analyzers yet. Add one to reduce across subjects."
            renderSummary={(p) => <strong>{p.name || '<pick analyzer>'}</strong>}
            renderEditor={(p, i) => (
              <ModuleSlot
                available={groupAnalyzers}
                selectedName={p.name}
                values={p.params || {}}
                onSelect={(v) => updateGroupAnalyzer(i, { name: v, params: {} })}
                onParamChange={(k, v) =>
                  updateGroupAnalyzer(i, {
                    ...p,
                    params: { ...(p.params || {}), [k]: v },
                  })
                }
                placeholder="-- select group analyzer --"
              />
            )}
          />
        </div>

        {/* Group report */}
        <div style={cardStyle}>
          <div style={sectionTitle}>Group report</div>
          <ModuleStack<GroupPluginConfig>
            items={groupReport}
            onAdd={() => addGroupReporter({ name: '', params: {} })}
            onRemove={removeGroupReporter}
            onMove={(from, to) => {
              const next = [...groupReport]
              const [m] = next.splice(from, 1)
              next.splice(to, 0, m)
              next.forEach((a, idx) => updateGroupReporter(idx, a))
            }}
            addLabel="Add group reporter"
            emptyMessage="No group reporters yet."
            renderSummary={(p) => <strong>{p.name || '<pick reporter>'}</strong>}
            renderEditor={(p, i) => (
              <ModuleSlot
                available={groupReporters}
                selectedName={p.name}
                values={p.params || {}}
                onSelect={(v) => updateGroupReporter(i, { name: v, params: {} })}
                onParamChange={(k, v) =>
                  updateGroupReporter(i, {
                    ...p,
                    params: { ...(p.params || {}), [k]: v },
                  })
                }
                placeholder="-- select group reporter --"
              />
            )}
          />
        </div>

        {validationErrors.length > 0 && (
          <div style={errorListStyle}>
            <strong>Validation errors</strong>
            <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
              {validationErrors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* ── Right column: YAML editor ── */}
      <div style={rightColStyle}>
        <div style={yamlHeaderStyle}>
          <span>YAML {yamlEditing ? '(editing)' : ''}</span>
          {yamlEditing && (
            <span style={{ fontSize: 10, color: 'var(--accent-cyan)' }}>
              applying after pause…
            </span>
          )}
        </div>
        <div style={yamlEditorWrap}>
          <YamlEditor value={yamlString} onChange={handleYamlChange} />
        </div>
        {yamlErrors.length > 0 && (
          <div style={yamlErrorBlock}>
            {yamlErrors.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
