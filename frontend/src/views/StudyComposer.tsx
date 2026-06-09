/** StudyComposer — author study-scope analysis configs.
 *
 * A study YAML wires together saved group configs and adds
 * study-scope analyzers/reporters that reduce across them. This
 * composer surfaces:
 *
 *   - study name + output_dir
 *   - groups: a list of (label, config-path) pairs picking saved group YAMLs
 *   - study_analyze: ModuleStack of study_analyzers
 *   - study_report:  ModuleStack of study_reporters
 *
 * The right-pane YAML editor is the source of truth for any nested
 * detail (per-group subjects overrides, intermediates / qa blocks, …).
 */
import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'
import { useStudyConfigStore } from '../stores/study-config-store'
import { useModuleStore } from '../stores/module-store'
import { useDashboardStore } from '../stores/dashboard-store'
import { ModuleStack } from '../components/composer/ModuleStack'
import { ModuleSlot } from '../components/composer/ModuleSlot'
import { YamlEditor } from '../components/composer/YamlEditor'
import type {
  ModuleInfo, StudyGroupRef, StudyPluginConfig,
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

const groupRefRow: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1.5fr auto',
  gap: 8,
  marginBottom: 8,
  alignItems: 'center',
}

const removeBtn: CSSProperties = {
  padding: '6px 12px',
  fontSize: 11,
  fontWeight: 600,
  border: '1px solid var(--border)',
  borderRadius: 6,
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
}

const addBtn: CSSProperties = {
  padding: '8px 14px',
  fontSize: 12,
  fontWeight: 600,
  border: '1px dashed var(--border)',
  borderRadius: 6,
  backgroundColor: 'transparent',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  width: '100%',
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


export function StudyComposer() {
  const config = useStudyConfigStore((s) => s.config)
  const yamlString = useStudyConfigStore((s) => s.yamlString)
  const validationErrors = useStudyConfigStore((s) => s.validationErrors)
  const yamlErrors = useStudyConfigStore((s) => s.yamlErrors)
  const isDirty = useStudyConfigStore((s) => s.isDirty)
  const yamlEditing = useStudyConfigStore((s) => s.yamlEditing)
  const setField = useStudyConfigStore((s) => s.setField)
  const validate = useStudyConfigStore((s) => s.validate)
  const exportYaml = useStudyConfigStore((s) => s.exportYaml)
  const syncYaml = useStudyConfigStore((s) => s.syncYaml)
  const setYamlDirect = useStudyConfigStore((s) => s.setYamlDirect)
  const applyYaml = useStudyConfigStore((s) => s.applyYaml)
  const reset = useStudyConfigStore((s) => s.reset)
  const addGroupRef = useStudyConfigStore((s) => s.addGroupRef)
  const removeGroupRef = useStudyConfigStore((s) => s.removeGroupRef)
  const updateGroupRef = useStudyConfigStore((s) => s.updateGroupRef)
  const addStudyAnalyzer = useStudyConfigStore((s) => s.addStudyAnalyzer)
  const removeStudyAnalyzer = useStudyConfigStore((s) => s.removeStudyAnalyzer)
  const updateStudyAnalyzer = useStudyConfigStore((s) => s.updateStudyAnalyzer)
  const addStudyReporter = useStudyConfigStore((s) => s.addStudyReporter)
  const removeStudyReporter = useStudyConfigStore((s) => s.removeStudyReporter)
  const updateStudyReporter = useStudyConfigStore((s) => s.updateStudyReporter)

  const modules = useModuleStore((s) => s.modules)
  const moduleStoreLoaded = useModuleStore((s) => s.loaded)
  const configs = useDashboardStore((s) => s.configs)
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

  const studyAnalyzers = useMemo(
    () => modulesIn(modules, ['study_analyzers']),
    [modules],
  )
  const studyReporters = useMemo(
    () => modulesIn(modules, ['study_reporters']),
    [modules],
  )

  // Surface saved group configs in the picker datalist so users can
  // pick by filename instead of typing the path from memory.
  const groupConfigSuggestions = useMemo(
    () => configs.filter((c) => c.group).map((c) => c.filename),
    [configs],
  )

  const groups = (config.groups || []) as StudyGroupRef[]
  const studyAnalyze = (config.study_analyze || []) as StudyPluginConfig[]
  const studyReport = (config.study_report || []) as StudyPluginConfig[]

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
          Author a cross-group study config. Pick saved group YAMLs to
          combine, then layer on study-scope analyzers / reporters.
        </div>

        <div style={actionBarStyle}>
          <button style={primaryBtn} onClick={() => validate()}>Validate</button>
          <button style={secondaryBtn} onClick={handleExport}>Copy YAML</button>
          <button style={secondaryBtn} onClick={reset}>Reset</button>
        </div>

        {/* Top — study + output_dir */}
        <div style={cardStyle}>
          <div style={{ marginBottom: 12 }}>
            <label style={labelSmall}>Study name</label>
            <input
              type="text"
              value={config.study || ''}
              onChange={(e) => setField('study', e.target.value)}
              style={inputStyle}
              placeholder="e.g. modality_compare"
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

        {/* Groups */}
        <div style={cardStyle}>
          <div style={sectionTitle}>Groups</div>
          {groups.map((g, i) => (
            <div key={i} style={groupRefRow}>
              <input
                type="text"
                value={g.name}
                onChange={(e) =>
                  updateGroupRef(i, { ...g, name: e.target.value })
                }
                style={inputStyle}
                placeholder="name (e.g. reading)"
              />
              <input
                type="text"
                value={g.config}
                onChange={(e) =>
                  updateGroupRef(i, { ...g, config: e.target.value })
                }
                style={{
                  ...inputStyle,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 12,
                }}
                placeholder="path/to/group.yaml"
                list={`dl-group-config-${i}`}
              />
              <datalist id={`dl-group-config-${i}`}>
                {groupConfigSuggestions.map((f) => (
                  <option key={f} value={f} />
                ))}
              </datalist>
              <button
                type="button"
                style={removeBtn}
                onClick={() => removeGroupRef(i)}
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            style={addBtn}
            onClick={() => addGroupRef({ name: '', config: '' })}
          >
            + Add group
          </button>
          {groups.length === 0 && (
            <div style={{
              marginTop: 8, fontSize: 11, fontStyle: 'italic',
              color: 'var(--text-secondary)',
            }}>
              No groups yet — a study needs at least one.
            </div>
          )}
        </div>

        {/* Study analyze */}
        <div style={cardStyle}>
          <div style={sectionTitle}>Study analyze</div>
          <ModuleStack<StudyPluginConfig>
            items={studyAnalyze}
            onAdd={() => addStudyAnalyzer({ name: '', params: {} })}
            onRemove={removeStudyAnalyzer}
            onMove={(from, to) => {
              const next = [...studyAnalyze]
              const [m] = next.splice(from, 1)
              next.splice(to, 0, m)
              next.forEach((a, idx) => updateStudyAnalyzer(idx, a))
            }}
            addLabel="Add study analyzer"
            emptyMessage="No study analyzers yet. Add one to reduce across groups."
            renderSummary={(p) => <strong>{p.name || '<pick analyzer>'}</strong>}
            renderEditor={(p, i) => (
              <ModuleSlot
                available={studyAnalyzers}
                selectedName={p.name}
                values={p.params || {}}
                onSelect={(v) => updateStudyAnalyzer(i, { name: v, params: {} })}
                onParamChange={(k, v) =>
                  updateStudyAnalyzer(i, {
                    ...p,
                    params: { ...(p.params || {}), [k]: v },
                  })
                }
                placeholder="-- select study analyzer --"
              />
            )}
          />
        </div>

        {/* Study report */}
        <div style={cardStyle}>
          <div style={sectionTitle}>Study report</div>
          <ModuleStack<StudyPluginConfig>
            items={studyReport}
            onAdd={() => addStudyReporter({ name: '', params: {} })}
            onRemove={removeStudyReporter}
            onMove={(from, to) => {
              const next = [...studyReport]
              const [m] = next.splice(from, 1)
              next.splice(to, 0, m)
              next.forEach((a, idx) => updateStudyReporter(idx, a))
            }}
            addLabel="Add study reporter"
            emptyMessage="No study reporters yet."
            renderSummary={(p) => <strong>{p.name || '<pick reporter>'}</strong>}
            renderEditor={(p, i) => (
              <ModuleSlot
                available={studyReporters}
                selectedName={p.name}
                values={p.params || {}}
                onSelect={(v) => updateStudyReporter(i, { name: v, params: {} })}
                onParamChange={(k, v) =>
                  updateStudyReporter(i, {
                    ...p,
                    params: { ...(p.params || {}), [k]: v },
                  })
                }
                placeholder="-- select study reporter --"
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
