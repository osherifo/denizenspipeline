/** FeatureKindSlot — one feature entry as "pick a kind → ParamForm".
 *
 * The features stage takes a list of modules just like the analyze
 * stage. The complication is that fmriflow's underlying schema
 * supports two shapes:
 *
 *   - source: compute, extractor: <X>, params: {...}    (run an extractor)
 *   - source: <grouped_hdf | filesystem | cloud>, ...   (load precomputed)
 *
 * To keep the UI symmetric with the analyze stage ("pick module →
 * params"), we synthesise a flat dropdown:
 *
 *   - one entry per registered feature_extractor (under "compute"),
 *   - one entry per non-compute feature_source.
 *
 * Each picked entry maps to a single ParamForm with its own flat
 * schema. The component owns the round-trip back to the on-disk
 * FeatureConfig shape so the YAML emitted by the existing
 * `configToYaml` endpoint is identical to today.
 */

import { useMemo } from 'react'
import { ParamForm } from './ParamForm'
import { useModuleStore } from '../../stores/module-store'
import type { FeatureConfig, ModuleInfo, ParamSchema } from '../../api/types'
import type { CSSProperties } from 'react'

interface FeatureKindSlotProps {
  value: FeatureConfig
  onChange: (next: FeatureConfig) => void
}

interface FeatureKind {
  key: string
  display: string
  group: 'compute' | 'load'
  schema: ParamSchema
  docstring?: string
  matches: (f: FeatureConfig) => boolean
  toConfig: (values: Record<string, unknown>) => FeatureConfig
  fromConfig: (f: FeatureConfig) => Record<string, unknown>
}

/** Pull all (extractor + non-compute source) entries into one list. */
function buildKinds(
  extractors: ModuleInfo[],
  sources: ModuleInfo[],
): FeatureKind[] {
  const kinds: FeatureKind[] = []

  // 1. Compute group — one entry per registered feature_extractor.
  // The form surfaces the extractor's own params plus a `name`
  // field (which defaults to the extractor name; users can rename
  // to disambiguate same-extractor-different-params entries).
  const nameField = {
    type: 'string',
    description: 'Name written to the YAML for this feature entry.',
  }
  for (const ext of extractors) {
    const schema: ParamSchema = { name: nameField, ...ext.params }
    kinds.push({
      key: `compute:${ext.name}`,
      display: ext.name,
      group: 'compute',
      schema,
      docstring: ext.docstring,
      matches: (f) => {
        const isCompute = !f.source || f.source === 'compute'
        if (!isCompute) return false
        if (f.extractor) return f.extractor === ext.name
        // Legacy shape: no `extractor` key — assume name == extractor.
        return f.name === ext.name
      },
      fromConfig: (f) => ({
        name: f.name || ext.name,
        ...(f.params || {}),
      }),
      toConfig: (values) => {
        const { name, ...rest } = values
        return {
          source: 'compute',
          extractor: ext.name,
          name: (name as string) || ext.name,
          params: rest,
        }
      },
    })
  }

  // 2. Load group — one entry per non-compute source.
  // The source's PARAM_SCHEMA is rendered directly. The `name`
  // field is part of that schema for sources that need it
  // (grouped_hdf, filesystem, cloud all declare it).
  for (const src of sources) {
    if (src.name === 'compute') continue
    kinds.push({
      key: src.name,
      display: src.name,
      group: 'load',
      schema: src.params,
      docstring: src.docstring,
      matches: (f) => f.source === src.name,
      fromConfig: (f) => {
        // Drop the `source` key — the kind dropdown owns it.
        const { source: _src, ...rest } = f as Record<string, unknown>
        return rest
      },
      toConfig: (values) => ({
        source: src.name,
        // Cast: values may not satisfy the structural FeatureConfig
        // type (it has known optional keys), but we know the schema
        // came from the source's PARAM_SCHEMA so it's valid YAML.
        ...(values as unknown as FeatureConfig),
      }),
    })
  }

  return kinds
}

const labelStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 6,
  display: 'block',
}

const selectStyle: CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  fontSize: 13,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  outline: 'none',
  marginBottom: 12,
}

const docstringStyle: CSSProperties = {
  margin: '0 0 12px 0',
  padding: '10px 12px',
  fontSize: 12,
  color: 'var(--text-secondary)',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  lineHeight: 1.5,
  fontStyle: 'italic',
}

export function FeatureKindSlot({ value, onChange }: FeatureKindSlotProps) {
  const modules = useModuleStore((s) => s.modules)

  const kinds = useMemo(
    () =>
      buildKinds(
        modules.feature_extractors || [],
        modules.feature_sources || [],
      ),
    [modules],
  )

  const selected = useMemo(
    () => kinds.find((k) => k.matches(value)),
    [kinds, value],
  )

  const formValues = useMemo(
    () => (selected ? selected.fromConfig(value) : {}),
    [selected, value],
  )

  const handleSelect = (key: string) => {
    const kind = kinds.find((k) => k.key === key)
    if (!kind) return
    // Reset to the new kind's defaults (extracted from its schema).
    const defaults: Record<string, unknown> = {}
    for (const [field, spec] of Object.entries(kind.schema)) {
      if (spec.default !== undefined) defaults[field] = spec.default
    }
    onChange(kind.toConfig(defaults))
  }

  const handleParamChange = (key: string, val: unknown) => {
    if (!selected) return
    onChange(selected.toConfig({ ...formValues, [key]: val }))
  }

  return (
    <div>
      <label style={labelStyle}>Feature</label>
      <select
        style={selectStyle}
        value={selected?.key ?? ''}
        onChange={(e) => handleSelect(e.target.value)}
      >
        <option value="">-- pick feature --</option>
        <optgroup label="Compute (run an extractor)">
          {kinds
            .filter((k) => k.group === 'compute')
            .map((k) => (
              <option key={k.key} value={k.key}>{k.display}</option>
            ))}
        </optgroup>
        <optgroup label="Load precomputed">
          {kinds
            .filter((k) => k.group === 'load')
            .map((k) => (
              <option key={k.key} value={k.key}>{k.display}</option>
            ))}
        </optgroup>
      </select>
      {selected?.docstring && (
        <div style={docstringStyle}>{selected.docstring}</div>
      )}
      {selected && (
        <ParamForm
          schema={selected.schema}
          values={formValues}
          onChange={handleParamChange}
        />
      )}
    </div>
  )
}
