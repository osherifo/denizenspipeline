import { useState, useEffect, useCallback, useMemo } from 'react'
import { usePluginStore } from '../stores/plugin-store'
import { useConfigStore } from '../stores/config-store'
import { ParamForm } from '../components/composer/ParamForm'
import type { PluginInfo, FeatureConfig, StepConfig, AnalyzerConfig, ParamSchema } from '../api/types'

// ── Styles ──

const composerLayout: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 420px',
  gap: 32,
  alignItems: 'start',
}

const headerStyle: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 24,
}

const sectionStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px 24px',
  marginBottom: 20,
}

const stageHeaderStyle = (color?: string): React.CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  marginBottom: 16,
})

const stageNumberStyle = (color: string): React.CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 28,
  height: 28,
  borderRadius: '50%',
  backgroundColor: color,
  color: '#0a0a1a',
  fontSize: 13,
  fontWeight: 800,
  flexShrink: 0,
})

const stageNameStyle = (color: string): React.CSSProperties => ({
  fontSize: 15,
  fontWeight: 700,
  color,
  textTransform: 'uppercase',
  letterSpacing: 1,
})

const selectStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  cursor: 'pointer',
  outline: 'none',
  marginBottom: 12,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  outline: 'none',
  marginBottom: 12,
}

const miniCardStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: '12px 14px',
  marginBottom: 8,
}

const miniCardHeader: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 8,
}

const miniCardName: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
}

const removeBtn: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--accent-red)',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 700,
  padding: '2px 6px',
}

const addBtnStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '8px 16px',
  fontSize: 12,
  fontWeight: 600,
  backgroundColor: 'rgba(0, 229, 255, 0.08)',
  border: '1px solid rgba(0, 229, 255, 0.25)',
  borderRadius: 6,
  color: 'var(--accent-cyan)',
  cursor: 'pointer',
  marginTop: 8,
}

const checkboxGroupStyle: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 12,
}

const checkboxItemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  fontSize: 13,
  color: 'var(--text-primary)',
  cursor: 'pointer',
}

const yamlPanelStyle: React.CSSProperties = {
  position: 'sticky',
  top: 80,
}

const yamlLabelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginBottom: 8,
}

const yamlTextareaStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 500,
  padding: '12px 14px',
  fontSize: 12,
  lineHeight: 1.6,
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text-primary)',
  resize: 'vertical',
  outline: 'none',
}

const actionBarStyle: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  marginTop: 24,
  marginBottom: 32,
}

const primaryBtn: React.CSSProperties = {
  padding: '10px 24px',
  fontSize: 13,
  fontWeight: 700,
  backgroundColor: 'var(--accent-cyan)',
  color: '#0a0a1a',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  letterSpacing: 0.5,
}

const secondaryBtn: React.CSSProperties = {
  padding: '10px 24px',
  fontSize: 13,
  fontWeight: 700,
  backgroundColor: 'transparent',
  color: 'var(--accent-cyan)',
  border: '1px solid var(--accent-cyan)',
  borderRadius: 6,
  cursor: 'pointer',
  letterSpacing: 0.5,
}

const errorListStyle: React.CSSProperties = {
  backgroundColor: 'rgba(255, 23, 68, 0.08)',
  border: '1px solid rgba(255, 23, 68, 0.3)',
  borderRadius: 6,
  padding: '12px 16px',
  marginTop: 12,
}

const errorItemStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--accent-red)',
  marginBottom: 4,
}

const labelSmall: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 4,
}

// ── Stage Definitions ──

const STAGE_DEFS = [
  { num: 1, key: 'stimulus', name: 'Stimuli', color: '#00e5ff', categories: ['stimulus_loaders'] },
  { num: 2, key: 'response', name: 'Responses', color: '#00e676', categories: ['response_loaders', 'response_readers'] },
  { num: 3, key: 'features', name: 'Features', color: '#ffd600', categories: ['feature_extractors', 'feature_sources'] },
  { num: 4, key: 'preprocessing', name: 'Preprocessing', color: '#ff9100', categories: ['preprocessing_steps', 'preprocessors'] },
  { num: 5, key: 'model', name: 'Model', color: '#e040fb', categories: ['models'] },
  { num: 6, key: 'analysis', name: 'Analysis', color: '#448aff', categories: ['analyzers'] },
  { num: 7, key: 'reporting', name: 'Report', color: '#69f0ae', categories: ['reporters'] },
]

const REPORTER_FORMATS = ['metrics', 'flatmap', 'flatmap_mapped', 'summary', 'weights', 'html']

// ── Helper to find plugin by name across categories ──

function findPlugin(plugins: Record<string, PluginInfo[]>, categories: string[], name: string): PluginInfo | undefined {
  for (const cat of categories) {
    const list = plugins[cat] || []
    const found = list.find((p) => p.name === name)
    if (found) return found
  }
  return undefined
}

function getPluginsForCategories(plugins: Record<string, PluginInfo[]>, categories: string[]): PluginInfo[] {
  const result: PluginInfo[] = []
  for (const cat of categories) {
    result.push(...(plugins[cat] || []))
  }
  return result
}

// ── Section Components ──

function StimulusSection() {
  const plugins = usePluginStore((s) => s.plugins)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)

  const available = getPluginsForCategories(plugins, ['stimulus_loaders'])
  const selected = config.stimulus?.loader || ''
  const plugin = findPlugin(plugins, ['stimulus_loaders'], selected)

  return (
    <div>
      <select
        style={selectStyle}
        value={selected}
        onChange={(e) => setField('stimulus.loader', e.target.value)}
      >
        <option value="">-- select loader --</option>
        {available.map((p) => (
          <option key={p.name} value={p.name}>{p.name}</option>
        ))}
      </select>
      {plugin && (
        <ParamForm
          schema={plugin.params}
          values={config.stimulus || {}}
          onChange={(key, val) => setField(`stimulus.${key}`, val)}
        />
      )}
    </div>
  )
}

function ResponseSection() {
  const plugins = usePluginStore((s) => s.plugins)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)

  const available = getPluginsForCategories(plugins, ['response_loaders', 'response_readers'])
  const selected = config.response?.loader || ''
  const plugin = findPlugin(plugins, ['response_loaders', 'response_readers'], selected)

  return (
    <div>
      <select
        style={selectStyle}
        value={selected}
        onChange={(e) => setField('response.loader', e.target.value)}
      >
        <option value="">-- select loader --</option>
        {available.map((p) => (
          <option key={p.name} value={p.name}>{p.name}</option>
        ))}
      </select>
      {plugin && (
        <ParamForm
          schema={plugin.params}
          values={config.response || {}}
          onChange={(key, val) => setField(`response.${key}`, val)}
        />
      )}
    </div>
  )
}

function FeatureSection() {
  const plugins = usePluginStore((s) => s.plugins)
  const config = useConfigStore((s) => s.config)
  const { addFeature, removeFeature, updateFeature } = useConfigStore()

  const extractors = getPluginsForCategories(plugins, ['feature_extractors'])
  const sources = getPluginsForCategories(plugins, ['feature_sources'])
  const allFeaturePlugins = [...extractors, ...sources]

  const features = config.features || []
  const [adding, setAdding] = useState(false)

  const handleAdd = (name: string) => {
    addFeature({ name, params: {} })
    setAdding(false)
  }

  return (
    <div>
      {features.map((feat, i) => {
        const plugin = findPlugin(plugins, ['feature_extractors', 'feature_sources'], feat.extractor || feat.source || feat.name)
        return (
          <div key={i} style={miniCardStyle}>
            <div style={miniCardHeader}>
              <span style={miniCardName}>{feat.name}</span>
              <button style={removeBtn} onClick={() => removeFeature(i)}>x</button>
            </div>
            {feat.extractor && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
                extractor: {feat.extractor}
              </div>
            )}
            {feat.source && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
                source: {feat.source}
              </div>
            )}
            {plugin && (
              <ParamForm
                schema={plugin.params}
                values={feat.params || {}}
                onChange={(key, val) => {
                  const updated = { ...feat, params: { ...(feat.params || {}), [key]: val } }
                  updateFeature(i, updated)
                }}
              />
            )}
          </div>
        )
      })}
      {adding ? (
        <div style={{ marginTop: 8 }}>
          <select
            style={selectStyle}
            value=""
            onChange={(e) => {
              if (e.target.value) handleAdd(e.target.value)
            }}
          >
            <option value="">-- select feature --</option>
            {allFeaturePlugins.map((p) => (
              <option key={`${p.category}-${p.name}`} value={p.name}>
                {p.name} ({p.category})
                {p.n_dims != null ? ` [${p.n_dims}d]` : ''}
              </option>
            ))}
          </select>
          <button style={{ ...removeBtn, color: 'var(--text-secondary)' }} onClick={() => setAdding(false)}>
            cancel
          </button>
        </div>
      ) : (
        <button style={addBtnStyle} onClick={() => setAdding(true)}>+ Add Feature</button>
      )}
    </div>
  )
}

function PreprocessingSection() {
  const plugins = usePluginStore((s) => s.plugins)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)
  const { addStep, removeStep, updateStep } = useConfigStore()

  const prep = config.preprocessing || {}
  const prepType = (prep.type as string) || 'default'
  const steps = prep.steps || []
  const stepPlugins = getPluginsForCategories(plugins, ['preprocessing_steps'])
  const preprocessorPlugins = getPluginsForCategories(plugins, ['preprocessors'])

  const [adding, setAdding] = useState(false)

  if (prepType === 'pipeline') {
    return (
      <div>
        <div style={{ marginBottom: 12 }}>
          <label style={labelSmall}>Type</label>
          <select
            style={selectStyle}
            value={prepType}
            onChange={(e) => setField('preprocessing.type', e.target.value)}
          >
            <option value="default">default</option>
            <option value="pipeline">pipeline (stackable steps)</option>
          </select>
        </div>
        {steps.map((step: StepConfig, i: number) => {
          const plugin = findPlugin(plugins, ['preprocessing_steps'], step.name)
          return (
            <div key={i} style={miniCardStyle}>
              <div style={miniCardHeader}>
                <span style={miniCardName}>{i + 1}. {step.name}</span>
                <button style={removeBtn} onClick={() => removeStep(i)}>x</button>
              </div>
              {plugin && (
                <ParamForm
                  schema={plugin.params}
                  values={step.params || {}}
                  onChange={(key, val) => {
                    const updated = { ...step, params: { ...(step.params || {}), [key]: val } }
                    updateStep(i, updated)
                  }}
                />
              )}
            </div>
          )
        })}
        {adding ? (
          <div style={{ marginTop: 8 }}>
            <select
              style={selectStyle}
              value=""
              onChange={(e) => {
                if (e.target.value) {
                  addStep({ name: e.target.value, params: {} })
                  setAdding(false)
                }
              }}
            >
              <option value="">-- select step --</option>
              {stepPlugins.map((p) => (
                <option key={p.name} value={p.name}>{p.name}</option>
              ))}
            </select>
            <button style={{ ...removeBtn, color: 'var(--text-secondary)' }} onClick={() => setAdding(false)}>
              cancel
            </button>
          </div>
        ) : (
          <button style={addBtnStyle} onClick={() => setAdding(true)}>+ Add Step</button>
        )}
      </div>
    )
  }

  // Default preprocessing mode
  const selectedPreprocessor = preprocessorPlugins.length > 0 ? preprocessorPlugins[0] : null

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <label style={labelSmall}>Type</label>
        <select
          style={selectStyle}
          value={prepType}
          onChange={(e) => setField('preprocessing.type', e.target.value)}
        >
          <option value="default">default</option>
          <option value="pipeline">pipeline (stackable steps)</option>
        </select>
      </div>
      {selectedPreprocessor && (
        <ParamForm
          schema={selectedPreprocessor.params}
          values={prep}
          onChange={(key, val) => setField(`preprocessing.${key}`, val)}
        />
      )}
    </div>
  )
}

function ModelSection() {
  const plugins = usePluginStore((s) => s.plugins)
  const config = useConfigStore((s) => s.config)
  const setField = useConfigStore((s) => s.setField)

  const available = getPluginsForCategories(plugins, ['models'])
  const selected = config.model?.type || ''
  const plugin = findPlugin(plugins, ['models'], selected)

  return (
    <div>
      <select
        style={selectStyle}
        value={selected}
        onChange={(e) => setField('model.type', e.target.value)}
      >
        <option value="">-- select model --</option>
        {available.map((p) => (
          <option key={p.name} value={p.name}>{p.name}</option>
        ))}
      </select>
      {plugin && (
        <ParamForm
          schema={plugin.params}
          values={config.model?.params || {}}
          onChange={(key, val) => setField(`model.params.${key}`, val)}
        />
      )}
    </div>
  )
}

function AnalysisSection() {
  const plugins = usePluginStore((s) => s.plugins)
  const config = useConfigStore((s) => s.config)
  const { addAnalyzer, removeAnalyzer, updateAnalyzer } = useConfigStore()

  const available = getPluginsForCategories(plugins, ['analyzers'])
  const analyzers = config.analysis || []
  const [adding, setAdding] = useState(false)

  return (
    <div>
      {analyzers.map((a: AnalyzerConfig, i: number) => {
        const plugin = findPlugin(plugins, ['analyzers'], a.name)
        return (
          <div key={i} style={miniCardStyle}>
            <div style={miniCardHeader}>
              <span style={miniCardName}>{a.name}</span>
              <button style={removeBtn} onClick={() => removeAnalyzer(i)}>x</button>
            </div>
            {plugin && (
              <ParamForm
                schema={plugin.params}
                values={a.params || {}}
                onChange={(key, val) => {
                  const updated = { ...a, params: { ...(a.params || {}), [key]: val } }
                  updateAnalyzer(i, updated)
                }}
              />
            )}
          </div>
        )
      })}
      {adding ? (
        <div style={{ marginTop: 8 }}>
          <select
            style={selectStyle}
            value=""
            onChange={(e) => {
              if (e.target.value) {
                addAnalyzer({ name: e.target.value, params: {} })
                setAdding(false)
              }
            }}
          >
            <option value="">-- select analyzer --</option>
            {available.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
          <button style={{ ...removeBtn, color: 'var(--text-secondary)' }} onClick={() => setAdding(false)}>
            cancel
          </button>
        </div>
      ) : (
        <button style={addBtnStyle} onClick={() => setAdding(true)}>+ Add Analyzer</button>
      )}
    </div>
  )
}

function ReportingSection() {
  const config = useConfigStore((s) => s.config)
  const toggleReporter = useConfigStore((s) => s.toggleReporter)
  const setField = useConfigStore((s) => s.setField)

  const formats = config.reporting?.formats || []
  const outputDir = config.reporting?.output_dir || './results'

  return (
    <div>
      <label style={labelSmall}>Formats</label>
      <div style={checkboxGroupStyle}>
        {REPORTER_FORMATS.map((fmt) => (
          <label key={fmt} style={checkboxItemStyle}>
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
      <div style={{ marginTop: 16 }}>
        <label style={labelSmall}>Output directory</label>
        <input
          type="text"
          value={outputDir}
          onChange={(e) => setField('reporting.output_dir', e.target.value)}
          style={{ ...inputStyle, fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}
        />
      </div>
    </div>
  )
}

// ── Stage Section Mapping ──

function getStageContent(stageKey: string) {
  switch (stageKey) {
    case 'stimulus': return <StimulusSection />
    case 'response': return <ResponseSection />
    case 'features': return <FeatureSection />
    case 'preprocessing': return <PreprocessingSection />
    case 'model': return <ModelSection />
    case 'analysis': return <AnalysisSection />
    case 'reporting': return <ReportingSection />
    default: return null
  }
}

// ── Main Composer ──

export function PipelineComposer() {
  const config = useConfigStore((s) => s.config)
  const yamlString = useConfigStore((s) => s.yamlString)
  const validationErrors = useConfigStore((s) => s.validationErrors)
  const isDirty = useConfigStore((s) => s.isDirty)
  const setField = useConfigStore((s) => s.setField)
  const validate = useConfigStore((s) => s.validate)
  const exportYaml = useConfigStore((s) => s.exportYaml)
  const syncYaml = useConfigStore((s) => s.syncYaml)
  const reset = useConfigStore((s) => s.reset)
  const loaded = usePluginStore((s) => s.loaded)

  // Sync YAML preview when config changes
  useEffect(() => {
    if (isDirty) {
      const timer = setTimeout(() => syncYaml(), 500)
      return () => clearTimeout(timer)
    }
  }, [config, isDirty, syncYaml])

  const handleValidate = useCallback(async () => {
    await validate()
  }, [validate])

  const handleExport = useCallback(async () => {
    const yaml = await exportYaml()
    // Copy to clipboard
    try {
      await navigator.clipboard.writeText(yaml)
    } catch {
      // fallback: user can copy from textarea
    }
  }, [exportYaml])

  if (!loaded) {
    return (
      <div style={{ color: 'var(--text-secondary)', fontSize: 14, padding: '60px 0', textAlign: 'center' }}>
        Loading plugin metadata...
      </div>
    )
  }

  return (
    <div>
      <div style={headerStyle}>Pipeline Composer</div>
      <div style={composerLayout}>
        {/* Left: Form */}
        <div>
          {/* Experiment & Subject */}
          <div style={sectionStyle}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <label style={labelSmall}>Experiment</label>
                <input
                  type="text"
                  value={config.experiment || ''}
                  onChange={(e) => setField('experiment', e.target.value)}
                  style={inputStyle}
                  placeholder="e.g. reading_task"
                />
              </div>
              <div>
                <label style={labelSmall}>Subject</label>
                <input
                  type="text"
                  value={config.subject || ''}
                  onChange={(e) => setField('subject', e.target.value)}
                  style={inputStyle}
                  placeholder="e.g. sub-01"
                />
              </div>
            </div>
          </div>

          {/* Pipeline Stages */}
          {STAGE_DEFS.map((stage) => (
            <div key={stage.key} style={sectionStyle}>
              <div style={stageHeaderStyle(stage.color)}>
                <div style={stageNumberStyle(stage.color)}>{stage.num}</div>
                <div style={stageNameStyle(stage.color)}>{stage.name}</div>
              </div>
              {getStageContent(stage.key)}
            </div>
          ))}

          {/* Split config */}
          <div style={sectionStyle}>
            <div style={{ ...stageNameStyle('var(--text-primary)'), marginBottom: 12 }}>
              Train / Test Split
            </div>
            <label style={labelSmall}>Test runs (comma-separated)</label>
            <input
              type="text"
              value={(config.split?.test_runs || []).join(', ')}
              onChange={(e) =>
                setField(
                  'split.test_runs',
                  e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter((s) => s)
                )
              }
              style={inputStyle}
              placeholder="e.g. run-05, run-06"
            />
          </div>

          {/* Actions */}
          <div style={actionBarStyle}>
            <button style={primaryBtn} onClick={handleValidate}>
              Validate
            </button>
            <button style={secondaryBtn} onClick={handleExport}>
              Export YAML
            </button>
            <button
              style={{ ...secondaryBtn, color: 'var(--text-secondary)', borderColor: 'var(--border)' }}
              onClick={reset}
            >
              Reset
            </button>
          </div>

          {/* Validation errors */}
          {validationErrors.length > 0 && (
            <div style={errorListStyle}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-red)', marginBottom: 8 }}>
                Validation Errors ({validationErrors.length})
              </div>
              {validationErrors.map((err, i) => (
                <div key={i} style={errorItemStyle}>- {err}</div>
              ))}
            </div>
          )}
        </div>

        {/* Right: YAML preview */}
        <div style={yamlPanelStyle}>
          <div style={yamlLabelStyle}>YAML Preview</div>
          <textarea
            style={yamlTextareaStyle}
            value={yamlString}
            readOnly
            placeholder="Configure your pipeline to see the YAML output here..."
          />
        </div>
      </div>
    </div>
  )
}
