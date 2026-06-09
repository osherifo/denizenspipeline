/** GroupComposer — author group-scope analysis configs.
 *
 * Layout mirrors :file:`AnalysisComposer.tsx`: a left form column with
 * scope-specific structured fields (group name, subject list,
 * group-scope plugin stacks) and a right column with a Monaco YAML
 * editor that is the source of truth for nested
 * ``subject_template`` / ``subject_overrides`` blocks.
 */
import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'
import { useGroupConfigStore } from '../stores/group-config-store'
import { useModuleStore } from '../stores/module-store'
import { ModuleStack } from '../components/composer/ModuleStack'
import { ModuleSlot } from '../components/composer/ModuleSlot'
import { YamlEditor } from '../components/composer/YamlEditor'
import type { ModuleInfo, GroupPluginConfig } from '../api/types'


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
          Author a cross-subject group config. The right pane's YAML is the
          source of truth for <code>subject_template</code> and{' '}
          <code>subject_overrides</code> — edit the shared subject pipeline
          there until the full subject embed lands.
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
