/**
 * Transform card — Stage N of the preprocessing stack.
 *
 * Status badge + reorder/remove buttons + a schema-driven param
 * form (the shared `ParamForm`). Transforms without a declared
 * schema fall back to a JSON textarea.
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import type { StackEvent } from '../../api/types'
import { ParamForm } from '../composer/ParamForm'


type StageStatus =
  | 'pending'
  | 'running'
  | 'done'
  | 'cached'
  | 'failed'


function statusFromEvents(
  events: StackEvent[],
  stageIndex: number,
): StageStatus {
  let status: StageStatus = 'pending'
  for (const ev of events) {
    if (ev.stage_index !== stageIndex) continue
    if (ev.event === 'stage_start') status = 'running'
    else if (ev.event === 'stage_done') status = ev.cache_hit ? 'cached' : 'done'
    else if (ev.event === 'stage_failed') status = 'failed'
  }
  return status
}


const STATUS_COLOR: Record<StageStatus, string> = {
  pending: 'var(--text-secondary)',
  running: 'var(--accent-yellow)',
  done: 'var(--accent-green)',
  cached: 'var(--accent-cyan)',
  failed: 'var(--accent-red)',
}


const cardStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: 12,
  marginBottom: 8,
}

const buttonStyle: CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '2px 8px',
  fontSize: 11,
  cursor: 'pointer',
  borderRadius: 4,
}


export function TransformCard({
  index,
  name,
  params,
}: {
  index: number
  name: string
  params: Record<string, unknown>
}) {
  const setParams = usePreprocStackStore((s) => s.setTransformParams)
  const moveUp = usePreprocStackStore((s) => s.moveTransformUp)
  const moveDown = usePreprocStackStore((s) => s.moveTransformDown)
  const remove = usePreprocStackStore((s) => s.removeTransform)
  const total = usePreprocStackStore((s) => s.transformsStack.length)
  const events = usePreprocStackStore((s) => s.activeEvents)
  const transforms = usePreprocStackStore((s) => s.transforms)

  // stage_index in events is 1-based for transforms (0 = bootstrap),
  // so this transform's index in the stage list is index + 1.
  const status = statusFromEvents(events, index + 1)

  const info = useMemo(
    () => transforms.find((t) => t.name === name) ?? null,
    [transforms, name],
  )
  const schema = info?.params_schema ?? {}
  const hasSchema = Object.keys(schema).length > 0

  return (
    <div style={cardStyle}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              fontSize: 11,
              color: 'var(--text-secondary)',
              fontWeight: 700,
              letterSpacing: 1,
            }}
          >
            STAGE {index + 1}
          </span>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{name}</span>
          {info && (
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              {info.version} · {info.source}
            </span>
          )}
          <span
            style={{
              fontSize: 11,
              padding: '2px 8px',
              border: `1px solid ${STATUS_COLOR[status]}`,
              borderRadius: 12,
              color: STATUS_COLOR[status],
            }}
          >
            {status}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <button
            style={buttonStyle}
            onClick={() => moveUp(index)}
            disabled={index === 0}
            title="Move up"
          >
            ↑
          </button>
          <button
            style={buttonStyle}
            onClick={() => moveDown(index)}
            disabled={index === total - 1}
            title="Move down"
          >
            ↓
          </button>
          <button
            style={{ ...buttonStyle, color: 'var(--accent-red)' }}
            onClick={() => remove(index)}
            title="Remove stage"
          >
            ✕
          </button>
        </div>
      </div>

      {info?.description && (
        <div
          style={{
            fontSize: 11,
            color: 'var(--text-secondary)',
            fontStyle: 'italic',
            marginBottom: 8,
          }}
        >
          {info.description}
        </div>
      )}

      {hasSchema ? (
        <ParamForm
          schema={schema}
          values={params}
          onChange={(key, value) =>
            setParams(index, { ...params, [key]: value })
          }
        />
      ) : (
        <TransformJsonFallback
          value={params}
          onChange={(next) => setParams(index, next)}
        />
      )}
    </div>
  )
}


function TransformJsonFallback({
  value,
  onChange,
}: {
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const [text, setText] = useState(JSON.stringify(value ?? {}, null, 2))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setText(JSON.stringify(value ?? {}, null, 2))
    setError(null)
  }, [value])

  function apply() {
    try {
      const parsed = JSON.parse(text)
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setError('Params must be a JSON object.')
        return
      }
      setError(null)
      onChange(parsed)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div>
      <label
        style={{
          display: 'block',
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: 1,
          color: 'var(--text-secondary)',
          marginBottom: 4,
        }}
      >
        Params (raw JSON — no schema declared)
      </label>
      <textarea
        style={{
          width: '100%',
          background: 'var(--bg-input)',
          border: '1px solid var(--border)',
          color: 'var(--text-primary)',
          padding: '6px 8px',
          fontSize: 12,
          fontFamily:
            "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
          borderRadius: 4,
          minHeight: 60,
        }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={apply}
        spellCheck={false}
      />
      {error && (
        <div
          style={{
            color: 'var(--accent-red)',
            fontSize: 11,
            marginTop: 4,
          }}
        >
          {error}
        </div>
      )}
    </div>
  )
}
