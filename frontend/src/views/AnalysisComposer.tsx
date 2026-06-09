/** AnalysisComposer — Linear Stage Strip + ghost graph + Monaco YAML.
 *
 * Replaces both PipelineComposer (form-driven) and PipelineGraph
 * (free DAG editor). The analysis pipeline is a fixed sequence
 * of seven stages with module slots; the UI mirrors that
 * directly. See devdocs/proposals/frontend/analysis-composer-redesign.md.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useConfigStore } from '../stores/config-store'
import { useModuleStore } from '../stores/module-store'
import { StageCard } from '../components/composer/StageCard'
import type { StageStatus } from '../components/composer/StageCard'
import { ModuleSlot } from '../components/composer/ModuleSlot'
import { ModuleStack } from '../components/composer/ModuleStack'
import { SingleModuleSlot } from '../components/composer/SingleModuleSlot'
import { FeatureKindSlot } from '../components/composer/FeatureKindSlot'
import { YamlEditor } from '../components/composer/YamlEditor'
import { StageStripPreview } from '../components/composer/StageStripPreview'
import type { PreviewStage } from '../components/composer/StageStripPreview'
import { GroupComposer } from './GroupComposer'
import { StudyComposer } from './StudyComposer'
import {
  SubjectStagesProvider, useSubjectStages,
} from '../components/composer/SubjectStagesContext'
import type { SubjectStagesAPI } from '../components/composer/SubjectStagesContext'
import type {
  ModuleInfo,
  FeatureConfig,
  AnalyzerConfig,
  StepConfig,
} from '../api/types'
import type { FieldValues } from '../api/client'

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

// ── Constants ─────────────────────────────────────────────────────────

export const STAGE_DEFS = [
  { num: 1, key: 'stimulus',    name: 'Stimuli',     color: '#00e5ff' },
  { num: 2, key: 'response',    name: 'Responses',   color: '#00e676' },
  { num: 3, key: 'features',    name: 'Features',    color: '#ffd600' },
  { num: 4, key: 'preparation', name: 'Preparation', color: '#ff9100' },
  { num: 5, key: 'model',       name: 'Model',       color: '#e040fb' },
  { num: 6, key: 'analysis',    name: 'Analyze',     color: '#448aff' },
  { num: 7, key: 'reporting',   name: 'Report',      color: '#69f0ae' },
] as const

export type StageKey = typeof STAGE_DEFS[number]['key']

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

// ── Helpers ───────────────────────────────────────────────────────────

function modulesIn(modules: Record<string, ModuleInfo[]>, categories: string[]): ModuleInfo[] {
  const out: ModuleInfo[] = []
  for (const c of categories) out.push(...(modules[c] || []))
  return out
}

function suggestionsForPrefix(fv: FieldValues, prefix: string): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  const dot = prefix + '.'
  for (const [k, vs] of Object.entries(fv)) {
    if (k.startsWith(dot)) {
      const f = k.slice(dot.length)
      if (!f.includes('.')) out[f] = vs
    }
  }
  return out
}

export function summaryFor(stage: typeof STAGE_DEFS[number]['key'], config: any): { summary: string; status: StageStatus; badge?: string } {
  switch (stage) {
    case 'stimulus': {
      const loader = config.stimulus?.loader
      return {
        summary: loader ? loader : 'Pick a stimulus loader',
        status: loader ? 'filled' : 'empty',
      }
    }
    case 'response': {
      const loader = config.response?.loader
      const reader = config.response?.reader
      const parts = [loader, reader && reader !== 'auto' ? `+ ${reader}` : null].filter(Boolean)
      return {
        summary: parts.length ? parts.join(' ') : 'Pick a response loader',
        status: loader ? 'filled' : 'empty',
      }
    }
    case 'features': {
      const features = config.features || []
      return {
        summary: features.length
          ? features.map((f: FeatureConfig) => f.name).slice(0, 4).join(', ') +
            (features.length > 4 ? ` +${features.length - 4}` : '')
          : 'Add at least one feature',
        status: features.length ? 'filled' : 'empty',
        badge: features.length ? `(${features.length})` : undefined,
      }
    }
    case 'preparation': {
      const prep = config.preparation || {}
      const type = prep.type
      const stepCount = (prep.steps || []).length
      return {
        summary: !type
          ? 'Pick a preparer'
          : type === 'pipeline'
            ? `pipeline (${stepCount} steps)`
            : type,
        status: type ? 'filled' : 'empty',
      }
    }
    case 'model': {
      const type = config.model?.type
      return {
        summary: type ? type : 'Pick a model',
        status: type ? 'filled' : 'empty',
      }
    }
    case 'analysis': {
      const a = config.analysis || []
      return {
        summary: a.length
          ? a.map((x: AnalyzerConfig) => x.name).slice(0, 3).join(', ') +
            (a.length > 3 ? ` +${a.length - 3}` : '')
          : 'No analyzers (optional)',
        status: a.length ? 'filled' : 'empty',
        badge: a.length ? `(${a.length})` : undefined,
      }
    }
    case 'reporting': {
      const formats = config.reporting?.formats || []
      return {
        summary: formats.length ? formats.join(' + ') : 'No reporters',
        status: formats.length ? 'filled' : 'empty',
        badge: formats.length ? `(${formats.length})` : undefined,
      }
    }
  }
  return { summary: '', status: 'empty' }
}

// Find the validation-error message that mentions the given stage
// keyword. The backend doesn't tag errors, so we string-match.
export function errorFor(stage: string, errors: string[]): string | undefined {
  const needles: Record<string, string[]> = {
    stimulus: ['stimulus'],
    response: ['response'],
    features: ['feature'],
    preparation: ['preparation', 'preparer', 'step'],
    model: ['model'],
    analysis: ['analyz'],
    reporting: ['report'],
  }
  const tokens = needles[stage] || [stage]
  return errors.find((e) => tokens.some((t) => e.toLowerCase().includes(t)))
}

// ── Section Components ────────────────────────────────────────────────

export function StimulusBody() {
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const { config, setField } = useSubjectStages()

  const available = modulesIn(modules, ['stimulus_loaders'])
  const hints = useMemo(() => suggestionsForPrefix(fieldValues, 'stimulus'), [fieldValues])

  return (
    <SingleModuleSlot
      available={available}
      value={config.stimulus || {}}
      selectorKey="loader"
      onChange={(next) => setField('stimulus', next)}
      addLabel="Add stimulus loader"
      suggestions={hints}
    />
  )
}

export function ResponseBody() {
  // Single-pick "Loader" slot. Same "+ Add" affordance as every
  // other stage. The reader is loader-specific (only meaningful for
  // `local`) and lives inside the loader's params via the schema, so
  // we don't surface it as a separate slot here — that would imply
  // the reader is always relevant. If a loader exposes a `reader`
  // field, ParamForm renders it normally.
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const { config, setField } = useSubjectStages()

  const loaders = modulesIn(modules, ['response_loaders'])
  const hints = useMemo(() => suggestionsForPrefix(fieldValues, 'response'), [fieldValues])

  return (
    <SingleModuleSlot
      available={loaders}
      value={config.response || {}}
      selectorKey="loader"
      onChange={(next) => setField('response', next)}
      addLabel="Add response loader"
      suggestions={hints}
    />
  )
}

export function FeaturesBody() {
  const { config, addFeature, removeFeature, updateFeature, reorderFeatures } = useSubjectStages()
  const features = config.features || []

  return (
    <ModuleStack
      items={features}
      onAdd={() => addFeature({ name: '' })}
      onRemove={removeFeature}
      onMove={reorderFeatures}
      addLabel="Add feature"
      emptyMessage="No features yet — add at least one."
      renderSummary={(f) => (
        <span>
          <strong>{f.name || '<unnamed>'}</strong>
          <span style={{ color: 'var(--text-secondary)', marginLeft: 8 }}>
            {f.source || 'compute'}
            {f.extractor && f.extractor !== f.name ? ` · ${f.extractor}` : ''}
          </span>
        </span>
      )}
      renderEditor={(f, i) => (
        <FeatureKindSlot value={f} onChange={(next) => updateFeature(i, next)} />
      )}
    />
  )
}

export function PreparationBody() {
  // SingleModuleSlot picks the preparer (default, pipeline, …) with
  // the same "+ Add" affordance as the other single-pick stages.
  // The pipeline preparer's `steps` is a list-of-dicts ParamForm
  // can't sensibly render; we hide it and surface an inline
  // ModuleStack of preparation_step modules below when type=pipeline.
  const modules = useModuleStore((s) => s.modules)
  const {
    config, setField,
    addStep, removeStep, updateStep, reorderSteps,
  } = useSubjectStages()

  const prep = config.preparation || {}
  const prepType = (prep.type as string) || ''
  const steps: StepConfig[] = (prep.steps as StepConfig[]) || []
  const preparers = modulesIn(modules, ['preparers'])
  const stepModules = modulesIn(modules, ['preparation_steps'])

  return (
    <div>
      <SingleModuleSlot
        available={preparers}
        value={prep as Record<string, unknown>}
        selectorKey="type"
        onChange={(next) => {
          if (!next || !('type' in next)) {
            setField('preparation', {})
            return
          }
          const newType = next.type as string
          // Reset list-of-dict fields when swapping preparers.
          if (newType === 'pipeline') {
            setField('preparation', {
              ...next,
              steps: (next.steps as StepConfig[]) || [],
            })
          } else {
            const { steps: _drop, ...rest } = next as Record<string, unknown>
            setField('preparation', rest)
          }
        }}
        addLabel="Add preparer"
        hiddenFields={['steps']}
      />
      {prepType === 'pipeline' && (
        <div style={{ marginTop: 12 }}>
          <span style={{ ...labelSmall, marginBottom: 8 }}>Steps</span>
          <ModuleStack<StepConfig>
            items={steps}
            onAdd={() => addStep({ type: '', params: {} } as unknown as StepConfig)}
            onRemove={removeStep}
            onMove={reorderSteps}
            addLabel="Add preparation step"
            emptyMessage="No steps yet — add the first."
            renderSummary={(step) => (
              <span>
                <strong>{(step as any).type || '<pick step>'}</strong>
              </span>
            )}
            renderEditor={(step, i) => (
              <ModuleSlot
                available={stepModules}
                selectedName={(step as any).type || ''}
                values={(step as any).params || {}}
                onSelect={(v) =>
                  updateStep(i, { type: v, params: {} } as unknown as StepConfig)
                }
                onParamChange={(k, v) =>
                  updateStep(i, {
                    ...(step as object),
                    params: { ...((step as any).params || {}), [k]: v },
                  } as unknown as StepConfig)
                }
                placeholder="-- select step --"
              />
            )}
          />
        </div>
      )}
    </div>
  )
}

export function ModelBody() {
  // Model is `{type, params}` on disk. The SingleModuleSlot wrapper
  // wants a flat object with the selector key at the top level, so
  // we pass `{type, ...params}` as the slot's value and re-split
  // when writing back.
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const { config, setField } = useSubjectStages()

  const available = modulesIn(modules, ['models'])
  const hints = useMemo(() => suggestionsForPrefix(fieldValues, 'model.params'), [fieldValues])

  // Build the SingleModuleSlot's value: empty {} when no model is
  // picked (so we get the "+ Add" affordance), or {type, ...params}
  // when one is.
  const m = config.model || {}
  const slotValue: Record<string, unknown> = m.type
    ? { type: m.type, ...(m.params || {}) }
    : {}

  return (
    <SingleModuleSlot
      available={available}
      value={slotValue}
      selectorKey="type"
      onChange={(next) => {
        // Empty object → clear the model.
        if (!next || !('type' in next)) {
          setField('model', { type: '', params: {} })
          return
        }
        const { type, ...params } = next
        setField('model', { type: type as string, params })
      }}
      addLabel="Add model"
      suggestions={hints}
    />
  )
}

export function AnalysisBody() {
  const modules = useModuleStore((s) => s.modules)
  const { config, addAnalyzer, removeAnalyzer, updateAnalyzer } = useSubjectStages()

  const available = modulesIn(modules, ['analyzers'])
  const analyzers = (config.analysis as AnalyzerConfig[]) || []
  const reorder = useCallback(
    (from: number, to: number) => {
      // analyzer reorder isn't a store action; do it via update sequence.
      const next = [...analyzers]
      const [m] = next.splice(from, 1)
      next.splice(to, 0, m)
      // Replace using update calls so we don't bypass the store.
      next.forEach((a, idx) => updateAnalyzer(idx, a))
    },
    [analyzers, updateAnalyzer],
  )

  return (
    <ModuleStack<AnalyzerConfig>
      items={analyzers}
      onAdd={() => addAnalyzer({ name: '', params: {} })}
      onRemove={removeAnalyzer}
      onMove={reorder}
      addLabel="Add analyzer"
      emptyMessage="No analyzers (optional). Add one to compute follow-up stats."
      renderSummary={(a) => <strong>{a.name || '<pick analyzer>'}</strong>}
      renderEditor={(a, i) => (
        <ModuleSlot
          available={available}
          selectedName={a.name}
          values={a.params || {}}
          onSelect={(v) => updateAnalyzer(i, { name: v, params: {} })}
          onParamChange={(k, v) =>
            updateAnalyzer(i, { ...a, params: { ...(a.params || {}), [k]: v } })
          }
          placeholder="-- select analyzer --"
        />
      )}
    />
  )
}

export function ReportingBody() {
  // ModuleStack of reporter modules, mirroring the analyze stage.
  // Each entry is { name } (no params surfaced — most reporters
  // don't take any). The entry list is round-tripped to/from
  // `reporting.formats` as a flat list of strings, which is the
  // shape every existing analysis YAML uses.
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const { config, setField } = useSubjectStages()

  const reporters = modulesIn(modules, ['reporters'])
  const formats = (config.reporting?.formats || []) as string[]
  const outputDir = config.reporting?.output_dir || './results'
  const outputDirHints = fieldValues['reporting.output_dir'] || []

  const setFormats = (next: string[]) => setField('reporting.formats', next)

  return (
    <div>
      <ModuleStack<{ name: string }>
        items={formats.map((name) => ({ name }))}
        onAdd={() => setFormats([...formats, ''])}
        onRemove={(i) => setFormats(formats.filter((_, idx) => idx !== i))}
        onMove={(from, to) => {
          const next = [...formats]
          const [m] = next.splice(from, 1)
          next.splice(to, 0, m)
          setFormats(next)
        }}
        addLabel="Add reporter"
        emptyMessage="No reporters yet — add at least one."
        renderSummary={(r) => <strong>{r.name || '<pick reporter>'}</strong>}
        renderEditor={(r, i) => (
          <ModuleSlot
            available={reporters}
            selectedName={r.name}
            values={{}}
            onSelect={(v) => setFormats(formats.map((f, idx) => (idx === i ? v : f)))}
            onParamChange={() => {
              /* reporters don't expose params today */
            }}
            placeholder="-- select reporter --"
          />
        )}
      />
      <div style={{ marginTop: 14 }}>
        <label style={labelSmall}>Output directory</label>
        <input
          type="text"
          value={outputDir}
          onChange={(e) => setField('reporting.output_dir', e.target.value)}
          style={{ ...inputStyle, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}
          list="dl-reporting-output-dir"
        />
        {outputDirHints.length > 0 && (
          <datalist id="dl-reporting-output-dir">
            {outputDirHints.map((v) => <option key={v} value={v} />)}
          </datalist>
        )}
      </div>
    </div>
  )
}

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
        color: s.color,
        status: errorMsg ? 'error' : status,
        badge,
        anchorId: `stage-${s.key}`,
      }
    })
  }, [config, validationErrors])

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
              color={s.color}
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
