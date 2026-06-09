/** Subject-stage primitives shared across composer views.
 *
 * The subject pipeline form (7 collapsible StageCards each holding a
 * module-slot body) is rendered in two places:
 *
 *   - the Subject tab of :file:`AnalysisComposer.tsx`, against
 *     ``useConfigStore`` directly;
 *   - the Subject Template card of :file:`GroupComposer.tsx`, against
 *     an adapter rooted at ``groupConfig.subject_template``.
 *
 * Both callers wrap the body components in a
 * :class:`SubjectStagesProvider` whose ``api`` they own. Living in
 * ``components/composer/`` (instead of one of the composer view
 * files) keeps the import graph acyclic — GroupComposer used to
 * import from AnalysisComposer which in turn imports GroupComposer,
 * and that round-trip was fragile under bundler reordering.
 */

import { useCallback, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useModuleStore } from '../../stores/module-store'
import { ModuleSlot } from './ModuleSlot'
import { ModuleStack } from './ModuleStack'
import { SingleModuleSlot } from './SingleModuleSlot'
import { FeatureKindSlot } from './FeatureKindSlot'
import { useSubjectStages } from './SubjectStagesContext'
import type { StageStatus } from './StageCard'
import type {
  ModuleInfo,
  FeatureConfig,
  AnalyzerConfig,
  StepConfig,
} from '../../api/types'
import type { FieldValues } from '../../api/client'


// ── Stage definitions ─────────────────────────────────────────────────

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

export function summaryFor(stage: StageKey, config: any): { summary: string; status: StageStatus; badge?: string } {
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

/** Find the validation-error message that mentions the given stage
 *  keyword. The backend doesn't tag errors, so we string-match. */
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


// ── Local styles used by PreparationBody / ReportingBody ──────────────

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


// ── Stage body components ─────────────────────────────────────────────

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
