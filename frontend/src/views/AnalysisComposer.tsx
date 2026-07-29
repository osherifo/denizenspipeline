/** AnalysisComposer — Linear Stage Strip + ghost graph + Monaco YAML.
 *
 * Replaces both PipelineComposer (form-driven) and PipelineGraph
 * (free DAG editor). The analysis pipeline is a fixed sequence
 * of seven stages with module slots; the UI mirrors that
 * directly.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useThemeStore } from '../stores/theme-store'
import { identityColor } from '../utils/status-colors'
import { useConfigStore } from '../stores/config-store'
import { useModuleStore } from '../stores/module-store'
import { StageCard } from '../components/composer/StageCard'
import { YamlEditor } from '../components/composer/YamlEditor'
import { StageStripPreview } from '../components/composer/StageStripPreview'
import type { PreviewStage } from '../components/composer/StageStripPreview'
import { GroupComposer } from './GroupComposer'
import { StudyComposer } from './StudyComposer'
import {
  SubjectStagesProvider,
} from '../components/composer/SubjectStagesContext'
import type { SubjectStagesAPI } from '../components/composer/SubjectStagesContext'
import {
  STAGE_DEFS, summaryFor, errorFor,
  StimulusBody, ResponseBody, FeaturesBody, PreparationBody,
  ModelBody, AnalysisBody, ReportingBody,
} from '../components/composer/subject-stages'

type Scope = 'subject' | 'group' | 'study'
const SCOPE_ORDER: Scope[] = ['subject', 'group', 'study']
const SCOPE_LABELS: Record<Scope, string> = {
  subject: 'Subject',
  group: 'Group',
  study: 'Study',
}

const scopeTabsRow: CSSProperties = {
  display: 'flex',
  gap: 4,
  padding: '12px 28px 0 28px',
  borderBottom: '1px solid var(--border)',
}

const scopeTabBtn = (active: boolean): CSSProperties => ({
  padding: '8px 18px',
  fontSize: 12,
  fontWeight: 700,
  border: 'none',
  background: 'transparent',
  color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
  borderBottom: active ? '2px solid var(--accent-cyan)' : '2px solid transparent',
  cursor: 'pointer',
  letterSpacing: 0.8,
  textTransform: 'uppercase',
  fontFamily: 'inherit',
  marginBottom: -1,
})

// ── Styles ────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 460px',
  gap: 24,
  alignItems: 'start',
  padding: '24px 28px',
  // 48px navbar + 48px scope tab bar; matches GroupComposer / StudyComposer.
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

const headerStyle: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 4,
}

const subtitleStyle: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginBottom: 18,
}

const topCardStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '16px 18px',
  marginBottom: 18,
}

const inputRow: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 16,
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

const selectStyle: CSSProperties = {
  ...inputStyle,
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

const previewLabelStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginBottom: 8,
  marginTop: 8,
}

// ── (helpers + stage bodies moved to components/composer/subject-stages.tsx) ──


// ── Main view ─────────────────────────────────────────────────────────

/** AnalysisComposer top-level — scope tabs + delegated body per scope.
 *
 * Subject scope keeps the existing 7-stage form (rendered inline below
 * as :func:`SubjectComposerBody`). Group / study scopes hand off to
 * sibling composer views that have their own state stores and
 * scope-shaped YAML editors. */
export function AnalysisComposer() {
  const [scope, setScope] = useState<Scope>('subject')
  const pageHeight: CSSProperties = { height: 'calc(100vh - 48px)' }
  return (
    <div style={pageHeight}>
      <div style={scopeTabsRow}>
        {SCOPE_ORDER.map((s) => (
          <button
            key={s}
            style={scopeTabBtn(scope === s)}
            onClick={() => setScope(s)}
          >
            {SCOPE_LABELS[s]}
          </button>
        ))}
      </div>
      {scope === 'subject' && <SubjectComposerBody />}
      {scope === 'group' && <GroupComposer />}
      {scope === 'study' && <StudyComposer />}
    </div>
  )
}


function SubjectComposerBody() {
  // Stage hues are identity markers; light mode darkens rather than replaces them.
  const themeMode = useThemeStore((s) => s.mode)
  const config = useConfigStore((s) => s.config)
  const yamlString = useConfigStore((s) => s.yamlString)
  const validationErrors = useConfigStore((s) => s.validationErrors)
  const yamlErrors = useConfigStore((s) => s.yamlErrors)
  const isDirty = useConfigStore((s) => s.isDirty)
  const yamlEditing = useConfigStore((s) => s.yamlEditing)
  const setField = useConfigStore((s) => s.setField)
  const validate = useConfigStore((s) => s.validate)
  const exportYaml = useConfigStore((s) => s.exportYaml)
  const syncYaml = useConfigStore((s) => s.syncYaml)
  const setYamlDirect = useConfigStore((s) => s.setYamlDirect)
  const applyYaml = useConfigStore((s) => s.applyYaml)
  const reset = useConfigStore((s) => s.reset)
  const addFeature = useConfigStore((s) => s.addFeature)
  const removeFeature = useConfigStore((s) => s.removeFeature)
  const updateFeature = useConfigStore((s) => s.updateFeature)
  const reorderFeatures = useConfigStore((s) => s.reorderFeatures)
  const addStep = useConfigStore((s) => s.addStep)
  const removeStep = useConfigStore((s) => s.removeStep)
  const updateStep = useConfigStore((s) => s.updateStep)
  const reorderSteps = useConfigStore((s) => s.reorderSteps)
  const addAnalyzer = useConfigStore((s) => s.addAnalyzer)
  const removeAnalyzer = useConfigStore((s) => s.removeAnalyzer)
  const updateAnalyzer = useConfigStore((s) => s.updateAnalyzer)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const moduleStoreLoaded = useModuleStore((s) => s.loaded)
  const yamlApplyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stagesApi = useMemo<SubjectStagesAPI>(() => ({
    config,
    setField,
    addFeature, removeFeature, updateFeature, reorderFeatures,
    addStep, removeStep, updateStep, reorderSteps,
    addAnalyzer, removeAnalyzer, updateAnalyzer,
  }), [
    config, setField,
    addFeature, removeFeature, updateFeature, reorderFeatures,
    addStep, removeStep, updateStep, reorderSteps,
    addAnalyzer, removeAnalyzer, updateAnalyzer,
  ])

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

  // Build the snapshot the ghost graph + StageCard headers need.
  const previewStages: PreviewStage[] = useMemo(() => {
    return STAGE_DEFS.map((s) => {
      const { status, badge } = summaryFor(s.key, config)
      const errorMsg = errorFor(s.key, validationErrors)
      return {
        key: s.key,
        label: s.name,
        num: s.num,
        color: identityColor(s.color, themeMode),
        status: errorMsg ? 'error' : status,
        badge,
        anchorId: `stage-${s.key}`,
      }
    })
  }, [config, validationErrors, themeMode])

  const handleStageClick = (key: string) => {
    document.getElementById(`stage-${key}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  }

  if (!moduleStoreLoaded) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-secondary)' }}>
        Loading module metadata…
      </div>
    )
  }

  return (
   <SubjectStagesProvider api={stagesApi}>
    <div style={pageStyle}>
      {/* ── Left column ── */}
      <div style={leftColStyle}>
        <div style={headerStyle}>Analysis Composer</div>
        <div style={subtitleStyle}>
          Build an encoding-model pipeline. Seven stages, plug a module into each.
        </div>

        <div style={actionBarStyle}>
          <button style={primaryBtn} onClick={() => validate()}>Validate</button>
          <button style={secondaryBtn} onClick={handleExport}>Copy YAML</button>
          <button style={secondaryBtn} onClick={reset}>Reset</button>
        </div>

        {/* Top — experiment + subject */}
        <div style={topCardStyle}>
          <div style={inputRow}>
            <div>
              <label style={labelSmall}>Experiment</label>
              <input
                type="text"
                value={config.experiment || ''}
                onChange={(e) => setField('experiment', e.target.value)}
                style={inputStyle}
                placeholder="e.g. reading_task"
                list="dl-experiment"
              />
              {fieldValues['experiment'] && (
                <datalist id="dl-experiment">
                  {fieldValues['experiment'].map((v) => <option key={v} value={v} />)}
                </datalist>
              )}
            </div>
            <div>
              <label style={labelSmall}>Subject</label>
              <input
                type="text"
                value={config.subject || ''}
                onChange={(e) => setField('subject', e.target.value)}
                style={inputStyle}
                placeholder="e.g. sub-01"
                list="dl-subject"
              />
              {fieldValues['subject'] && (
                <datalist id="dl-subject">
                  {fieldValues['subject'].map((v) => <option key={v} value={v} />)}
                </datalist>
              )}
            </div>
          </div>
        </div>

        {/* Stage cards */}
        {STAGE_DEFS.map((s) => {
          const preview = previewStages.find((p) => p.key === s.key)!
          const { summary } = summaryFor(s.key, config)
          const errorMsg = errorFor(s.key, validationErrors)
          return (
            <StageCard
              key={s.key}
              num={s.num}
              name={s.name}
              color={identityColor(s.color, themeMode)}
              status={preview.status}
              summary={summary}
              badge={preview.badge}
              errorMessage={errorMsg}
              anchorId={`stage-${s.key}`}
              initiallyCollapsed={s.key !== 'stimulus'}
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

        {/* Train/test split */}
        <div style={topCardStyle}>
          <label style={labelSmall}>Train / test split — test runs (comma-separated)</label>
          <input
            type="text"
            value={(config.split?.test_runs || []).join(', ')}
            onChange={(e) =>
              setField(
                'split.test_runs',
                e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
              )
            }
            style={inputStyle}
            placeholder="e.g. run-05, run-06"
            list="dl-test-runs"
          />
          {fieldValues['split.test_runs'] && (
            <datalist id="dl-test-runs">
              {fieldValues['split.test_runs'].map((v) => <option key={v} value={v} />)}
            </datalist>
          )}
        </div>

        {/* Ghost graph */}
        <div style={previewLabelStyle}>Pipeline preview</div>
        <StageStripPreview stages={previewStages} onNodeClick={handleStageClick} />
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
            <div style={{ fontWeight: 700, marginBottom: 4 }}>YAML Parse Error</div>
            {yamlErrors.map((e, i) => (
              <div key={i}>{e}</div>
            ))}
          </div>
        )}
      </div>
    </div>
   </SubjectStagesProvider>
  )
}
