/**
 * Bootstrap card — Stage 0 of the preprocessing stack.
 *
 * The user picks a *kind* (fmriprep / nipype / custom / bids_app /
 * passthrough). When kind=nipype, a second dropdown picks the
 * registered workflow.
 *
 * Params render via the shared `ParamForm` when the chosen
 * workflow declares a non-empty `params_schema`. For workflows
 * that don't (the wrapped fmriprep / custom / bids_app backends,
 * which validate via their own dataclasses) we fall back to a
 * JSON textarea so power users can still configure them.
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import type {
  BootstrapKind,
  StackEvent,
  StackResultPayload,
  WorkflowInfo,
} from '../../api/types'
import { ParamForm } from '../composer/ParamForm'


type StageStatus =
  | 'pending'
  | 'running'
  | 'done'
  | 'cached'
  | 'failed'


function bootstrapStatusFromEvents(events: StackEvent[]): StageStatus {
  let status: StageStatus = 'pending'
  for (const ev of events) {
    if (ev.stage_index !== 0) continue
    if (ev.event === 'stage_start') status = 'running'
    else if (ev.event === 'stage_done') status = ev.cache_hit ? 'cached' : 'done'
    else if (ev.event === 'stage_failed') status = 'failed'
  }
  return status
}


function bootstrapStatusFromHistorical(
  result: StackResultPayload,
): StageStatus {
  if (result.stage_cache_hits.length === 0) {
    return result.status === 'failed' ? 'failed' : 'pending'
  }
  const isOnlyStage = result.stage_cache_hits.length === 1
  if (result.status === 'failed' && isOnlyStage) return 'failed'
  return result.stage_cache_hits[0] ? 'cached' : 'done'
}


const STATUS_COLOR: Record<StageStatus, string> = {
  pending: 'var(--text-secondary)',
  running: 'var(--accent-yellow)',
  done: 'var(--accent-green)',
  cached: 'var(--accent-cyan)',
  failed: 'var(--accent-red)',
}


const BOOTSTRAP_KINDS: { value: BootstrapKind; label: string }[] = [
  { value: 'fmriprep', label: 'fMRIPrep' },
  { value: 'nipype', label: 'Nipype workflow' },
  { value: 'custom', label: 'Custom shell' },
  { value: 'bids_app', label: 'BIDS-App' },
  { value: 'passthrough', label: 'Passthrough (already preprocessed)' },
]


const cardStyle: CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--accent-cyan)',
  borderRadius: 8,
  padding: 16,
  marginBottom: 16,
}

const labelStyle: CSSProperties = {
  display: 'block',
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: 1,
  color: 'var(--text-secondary)',
  marginBottom: 6,
  marginTop: 10,
}

const inputStyle: CSSProperties = {
  width: '100%',
  background: 'var(--bg-input)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  padding: '8px 10px',
  fontSize: 13,
  fontFamily: 'inherit',
  borderRadius: 4,
}

const stageTagStyle: CSSProperties = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 12,
  fontSize: 10,
  letterSpacing: 1,
  background: 'var(--accent-cyan)',
  color: 'var(--bg-primary)',
  fontWeight: 700,
}


function preflightBadgeStyle(ok: boolean | null): CSSProperties {
  if (ok === null) {
    return {
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 12,
      fontSize: 11,
      color: 'var(--text-secondary)',
      background: 'transparent',
      border: '1px solid var(--border)',
    }
  }
  const accent = ok ? 'var(--accent-green)' : 'var(--accent-red)'
  return {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 12,
    fontSize: 11,
    color: accent,
    background: 'transparent',
    border: `1px solid ${accent}`,
  }
}


export function BootstrapCard() {
  const bootstrap = usePreprocStackStore((s) => s.bootstrap)
  const workflows = usePreprocStackStore((s) => s.workflows)
  const preflight = usePreprocStackStore((s) => s.bootstrapPreflight)
  const setBootstrap = usePreprocStackStore((s) => s.setBootstrap)
  const checkPreflight = usePreprocStackStore((s) => s.checkBootstrapPreflight)
  const events = usePreprocStackStore((s) => s.activeEvents)
  const result = usePreprocStackStore((s) => s.activeResult)

  const stageStatus: StageStatus =
    events.length > 0
      ? bootstrapStatusFromEvents(events)
      : result
      ? bootstrapStatusFromHistorical(result)
      : 'pending'

  // Re-preflight when kind or workflow changes.
  useEffect(() => {
    void checkPreflight()
  }, [bootstrap.kind, bootstrap.workflow, checkPreflight])

  const isNipype = bootstrap.kind === 'nipype'
  const nipypeWorkflows: WorkflowInfo[] = workflows.filter(
    (w) => !['fmriprep', 'custom', 'bids_app', 'passthrough'].includes(w.name),
  )

  // Resolve the chosen workflow info so we can render its schema.
  const resolvedName = isNipype ? bootstrap.workflow ?? null : bootstrap.kind
  const resolvedInfo = useMemo(
    () => workflows.find((w) => w.name === resolvedName) ?? null,
    [workflows, resolvedName],
  )
  const schema = resolvedInfo?.params_schema ?? {}
  const hasSchema = Object.keys(schema).length > 0
  const params = (bootstrap.params ?? {}) as Record<string, unknown>

  const okBadge = preflight === null ? null : preflight.ok
  const errCount = preflight?.errors.length ?? 0

  return (
    <div style={cardStyle}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 6,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={stageTagStyle}>STAGE 0 · BOOTSTRAP</span>
          {stageStatus !== 'pending' && (
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                border: `1px solid ${STATUS_COLOR[stageStatus]}`,
                borderRadius: 12,
                color: STATUS_COLOR[stageStatus],
              }}
            >
              {stageStatus}
            </span>
          )}
          <span style={preflightBadgeStyle(okBadge)}>
            {okBadge === null
              ? 'unchecked'
              : okBadge
              ? 'ready'
              : `${errCount} preflight error${errCount === 1 ? '' : 's'}`}
          </span>
        </div>
      </div>

      <label style={labelStyle}>Backend</label>
      <select
        style={inputStyle}
        value={bootstrap.kind}
        onChange={(e) =>
          setBootstrap({ kind: e.target.value as BootstrapKind })
        }
      >
        {BOOTSTRAP_KINDS.map((k) => (
          <option key={k.value} value={k.value}>{k.label}</option>
        ))}
      </select>

      {isNipype && (
        <>
          <label style={labelStyle}>Workflow</label>
          <select
            style={inputStyle}
            value={bootstrap.workflow ?? ''}
            onChange={(e) => setBootstrap({ workflow: e.target.value })}
          >
            {nipypeWorkflows.length === 0 && (
              <option value="">(no nipype workflows registered)</option>
            )}
            {nipypeWorkflows.map((w) => (
              <option key={w.name} value={w.name}>
                {w.name} · {w.version} · {w.source}
              </option>
            ))}
          </select>
        </>
      )}

      {resolvedInfo?.description && (
        <div
          style={{
            marginTop: 10,
            fontSize: 12,
            color: 'var(--text-secondary)',
            fontStyle: 'italic',
          }}
        >
          {resolvedInfo.description}
        </div>
      )}

      <div style={{ marginTop: 14 }}>
        {hasSchema ? (
          <ParamForm
            schema={schema}
            values={params}
            onChange={(key, value) =>
              setBootstrap({ params: { ...params, [key]: value } })
            }
          />
        ) : (
          <BootstrapJsonFallback
            value={params}
            onChange={(next) => setBootstrap({ params: next })}
          />
        )}
      </div>

      {preflight && !preflight.ok && (
        <div
          style={{
            marginTop: 10,
            padding: 8,
            background: 'var(--bg-input)',
            border: '1px solid var(--accent-red)',
            borderRadius: 4,
            fontSize: 12,
          }}
        >
          {preflight.errors.map((err, i) => (
            <div key={i} style={{ marginBottom: 4 }}>· {err}</div>
          ))}
        </div>
      )}

      {preflight && preflight.warnings.length > 0 && (
        <div
          style={{
            marginTop: 8,
            padding: 8,
            background: 'var(--bg-input)',
            border: '1px solid var(--accent-yellow)',
            borderRadius: 4,
            fontSize: 12,
          }}
        >
          {preflight.warnings.map((w, i) => (
            <div key={i} style={{ marginBottom: 4 }}>· {w}</div>
          ))}
        </div>
      )}
    </div>
  )
}


function BootstrapJsonFallback({
  value,
  onChange,
}: {
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const [text, setText] = useState(JSON.stringify(value ?? {}, null, 2))
  const [error, setError] = useState<string | null>(null)

  // Reset textarea when the parent's params change (e.g. on workflow switch).
  useEffect(() => {
    setText(JSON.stringify(value ?? {}, null, 2))
    setError(null)
  }, [value])

  function applyParams() {
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
          fontSize: 11,
          textTransform: 'uppercase',
          letterSpacing: 1,
          color: 'var(--text-secondary)',
          marginBottom: 6,
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
          padding: '8px 10px',
          fontSize: 13,
          minHeight: 100,
          fontFamily:
            "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
          borderRadius: 4,
        }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={applyParams}
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
