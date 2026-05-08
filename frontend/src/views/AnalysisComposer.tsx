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
import { ParamForm } from '../components/composer/ParamForm'
import { StageCard } from '../components/composer/StageCard'
import type { StageStatus } from '../components/composer/StageCard'
import { ModuleSlot } from '../components/composer/ModuleSlot'
import { ModuleStack } from '../components/composer/ModuleStack'
import { YamlEditor } from '../components/composer/YamlEditor'
import { StageStripPreview } from '../components/composer/StageStripPreview'
import type { PreviewStage } from '../components/composer/StageStripPreview'
import type {
  ModuleInfo,
  FeatureConfig,
  AnalyzerConfig,
  StepConfig,
} from '../api/types'
import type { FieldValues } from '../api/client'

// ── Constants ─────────────────────────────────────────────────────────

const STAGE_DEFS = [
  { num: 1, key: 'stimulus',    name: 'Stimuli',     color: '#00e5ff' },
  { num: 2, key: 'response',    name: 'Responses',   color: '#00e676' },
  { num: 3, key: 'features',    name: 'Features',    color: '#ffd600' },
  { num: 4, key: 'preparation', name: 'Preparation', color: '#ff9100' },
  { num: 5, key: 'model',       name: 'Model',       color: '#e040fb' },
  { num: 6, key: 'analysis',    name: 'Analyze',     color: '#448aff' },
  { num: 7, key: 'reporting',   name: 'Report',      color: '#69f0ae' },
] as const

const REPORTER_FORMATS = ['metrics', 'flatmap', 'flatmap_mapped', 'summary', 'weights', 'html']

// ── Styles ────────────────────────────────────────────────────────────

const pageStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 460px',
  gap: 24,
  alignItems: 'start',
  padding: '24px 28px',
  height: 'calc(100vh - 48px)',
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

const checkboxGroup: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 12,
}

const checkboxItem: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  fontSize: 13,
  color: 'var(--text-primary)',
  cursor: 'pointer',
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

function findModule(
  modules: Record<string, ModuleInfo[]>,
  categories: string[],
  name: string,
): ModuleInfo | undefined {
  for (const c of categories) {
    const found = (modules[c] || []).find((m) => m.name === name)
    if (found) return found
  }
  return undefined
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

function summaryFor(stage: typeof STAGE_DEFS[number]['key'], config: any): { summary: string; status: StageStatus; badge?: string } {
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
      const type = prep.type || 'default'
      const stepCount = (prep.steps || []).length
      return {
        summary: type === 'pipeline' ? `pipeline (${stepCount} steps)` : 'default',
        status: 'filled', // preparation always has a default
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
function errorFor(stage: string, errors: string[]): string | undefined {
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

function StimulusBody() {
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)

  const available = modulesIn(modules, ['stimulus_loaders'])
  const selected = config.stimulus?.loader || ''
  const hints = useMemo(() => suggestionsForPrefix(fieldValues, 'stimulus'), [fieldValues])

  return (
    <ModuleSlot
      label="Loader"
      available={available}
      selectedName={selected}
      values={config.stimulus || {}}
      onSelect={(v) => setField('stimulus.loader', v)}
      onParamChange={(k, v) => setField(`stimulus.${k}`, v)}
      suggestions={hints}
      placeholder="-- select loader --"
    />
  )
}

function ResponseBody() {
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)

  const loaders = modulesIn(modules, ['response_loaders'])
  const readers = modulesIn(modules, ['response_readers'])
  const loaderName = config.response?.loader || ''
  const readerName = (config.response?.reader as string) || ''
  const showReader = readerName && readerName !== 'auto'
  const hints = useMemo(() => suggestionsForPrefix(fieldValues, 'response'), [fieldValues])

  return (
    <div>
      <ModuleSlot
        label="Loader"
        available={loaders}
        selectedName={loaderName}
        values={config.response || {}}
        onSelect={(v) => setField('response.loader', v)}
        onParamChange={(k, v) => setField(`response.${k}`, v)}
        suggestions={hints}
        placeholder="-- select loader --"
      />
      {showReader && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          <ModuleSlot
            label={`${readerName} reader params`}
            available={readers}
            selectedName={readerName}
            values={config.response || {}}
            onSelect={(v) => setField('response.reader', v)}
            onParamChange={(k, v) => setField(`response.${k}`, v)}
            suggestions={hints}
            placeholder="-- select reader --"
          />
        </div>
      )}
    </div>
  )
}

function FeaturesBody() {
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const config = useConfigStore((s) => s.config)
  const { addFeature, removeFeature, updateFeature, reorderFeatures } = useConfigStore()

  const sources = modulesIn(modules, ['feature_sources'])
  const extractors = modulesIn(modules, ['feature_extractors'])
  const features = config.features || []
  const featureHints = useMemo(() => suggestionsForPrefix(fieldValues, 'features'), [fieldValues])

  return (
    <ModuleStack
      items={features}
      onAdd={() => addFeature({ name: '', source: 'compute' })}
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
      renderEditor={(f, i) => {
        const source = f.source || 'compute'
        const isCompute = source === 'compute'
        const extractorName = f.extractor || (isCompute ? f.name : '')
        const sourceModule = findModule(modules, ['feature_sources'], source)
        const extractorModule = isCompute
          ? findModule(modules, ['feature_extractors'], extractorName)
          : null

        return (
          <div>
            {/* Name */}
            <div style={{ marginBottom: 10 }}>
              <label style={labelSmall}>Name</label>
              <input
                type="text"
                value={f.name}
                style={inputStyle}
                onChange={(e) => updateFeature(i, { ...f, name: e.target.value })}
                placeholder="e.g. english1000"
              />
            </div>
            {/* Source */}
            <div style={{ marginBottom: 10 }}>
              <label style={labelSmall}>Source</label>
              <select
                style={selectStyle}
                value={source}
                onChange={(e) => {
                  const newSource = e.target.value
                  const updated: FeatureConfig = { name: f.name, source: newSource }
                  if (newSource === 'compute') {
                    updated.extractor = f.name
                    updated.params = {}
                  }
                  updateFeature(i, updated)
                }}
              >
                {sources.map((s) => (
                  <option key={s.name} value={s.name}>{s.name}</option>
                ))}
              </select>
            </div>
            {/* Compute → extractor selector + params */}
            {isCompute && (
              <ModuleSlot
                label="Extractor"
                available={extractors}
                selectedName={extractorName}
                values={f.params || {}}
                onSelect={(v) => {
                  const updated = { ...f, source: 'compute', extractor: v }
                  // Auto-name when the user hasn't customised it.
                  if (f.name === '' || f.name === f.extractor) updated.name = v
                  updateFeature(i, updated)
                }}
                onParamChange={(k, v) =>
                  updateFeature(i, { ...f, params: { ...(f.params || {}), [k]: v } })
                }
                placeholder="-- select extractor --"
              />
            )}
            {/* Non-compute source params */}
            {!isCompute && sourceModule && Object.keys(sourceModule.params).length > 0 && (
              <ParamForm
                schema={sourceModule.params}
                values={f as unknown as Record<string, unknown>}
                onChange={(k, v) => updateFeature(i, { ...f, [k]: v })}
                suggestions={featureHints}
              />
            )}
          </div>
        )
      }}
    />
  )
}

function PreparationBody() {
  const modules = useModuleStore((s) => s.modules)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)
  const { addStep, removeStep, updateStep, reorderSteps } = useConfigStore()

  const prep = config.preparation || {}
  const prepType = (prep.type as string) || 'default'
  const steps: StepConfig[] = (prep.steps as StepConfig[]) || []
  const preparers = modulesIn(modules, ['preparers'])
  const stepModules = modulesIn(modules, ['preparation_steps'])

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <label style={checkboxItem}>
          <input
            type="checkbox"
            checked={prepType === 'pipeline'}
            onChange={(e) => {
              if (e.target.checked) {
                setField('preparation.type', 'pipeline')
                if (!prep.steps) setField('preparation.steps', [])
              } else {
                setField('preparation.type', 'default')
              }
            }}
          />
          Use pipeline of preparation steps instead of a single preparer
        </label>
      </div>

      {prepType === 'default' ? (
        <ModuleSlot
          label="Preparer"
          available={preparers}
          selectedName={(prep.preparer as string) || 'default'}
          values={prep}
          onSelect={(v) => setField('preparation.preparer', v)}
          onParamChange={(k, v) => setField(`preparation.${k}`, v)}
          placeholder="default"
        />
      ) : (
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
      )}
    </div>
  )
}

function ModelBody() {
  const modules = useModuleStore((s) => s.modules)
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)

  const available = modulesIn(modules, ['models'])
  const selected = config.model?.type || ''
  const hints = useMemo(() => suggestionsForPrefix(fieldValues, 'model.params'), [fieldValues])

  return (
    <ModuleSlot
      label="Model"
      available={available}
      selectedName={selected}
      values={config.model?.params || {}}
      onSelect={(v) => setField('model.type', v)}
      onParamChange={(k, v) => setField(`model.params.${k}`, v)}
      suggestions={hints}
      placeholder="-- select model --"
    />
  )
}

function AnalysisBody() {
  const modules = useModuleStore((s) => s.modules)
  const config = useConfigStore((s) => s.config)
  const { addAnalyzer, removeAnalyzer, updateAnalyzer } = useConfigStore()

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

function ReportingBody() {
  const fieldValues = useModuleStore((s) => s.fieldValues)
  const config = useConfigStore((s) => s.config)
  const toggleReporter = useConfigStore((s) => s.toggleReporter)
  const setField = useConfigStore((s) => s.setField)

  const formats = config.reporting?.formats || []
  const outputDir = config.reporting?.output_dir || './results'
  const outputDirHints = fieldValues['reporting.output_dir'] || []

  return (
    <div>
      <label style={labelSmall}>Formats</label>
      <div style={checkboxGroup}>
        {REPORTER_FORMATS.map((fmt) => (
          <label key={fmt} style={checkboxItem}>
            <input
              type="checkbox"
              checked={formats.includes(fmt)}
              onChange={() => toggleReporter(fmt)}
              style={{ accentColor: 'var(--accent-cyan)', cursor: 'pointer' }}
            />
            {fmt}
          </label>
        ))}
      </div>
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

export function AnalysisComposer() {
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
  const fieldValues = useModuleStore((s) => s.fieldValues)
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
  )
}
