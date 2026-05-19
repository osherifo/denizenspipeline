/**
 * Bootstrap card — Stage 0 of the preprocessing stack.
 *
 * The user picks a *kind* (fmriprep / nipype / custom / bids_app /
 * passthrough). When kind=nipype, a second dropdown picks the
 * registered workflow. Params are edited as JSON for v1 — a
 * schema-driven form is Phase 6b polish.
 *
 * A "preflight" badge surfaces the workflow's REQUIRED_PYTHON /
 * REQUIRED_TOOLS / REQUIRED_ENV status before launch, so the user
 * sees "ready" / "missing FSL" without clicking Run.
 */

import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { usePreprocStackStore } from '../../stores/preproc-stack-store'
import type { BootstrapKind, WorkflowInfo } from '../../api/types'


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


function preflightBadge(
  ok: boolean | null,
  errCount: number,
): CSSProperties {
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
  if (ok) {
    return {
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 12,
      fontSize: 11,
      color: 'var(--accent-green)',
      background: 'transparent',
      border: '1px solid var(--accent-green)',
    }
  }
  // errCount tells the call site how many errors there are; the
  // badge text already encodes it, so we don't repeat it in a
  // title attribute (and CSSProperties doesn't accept one).
  void errCount
  return {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 12,
    fontSize: 11,
    color: 'var(--accent-red)',
    background: 'transparent',
    border: '1px solid var(--accent-red)',
  }
}


export function BootstrapCard() {
  const bootstrap = usePreprocStackStore((s) => s.bootstrap)
  const workflows = usePreprocStackStore((s) => s.workflows)
  const preflight = usePreprocStackStore((s) => s.bootstrapPreflight)
  const setBootstrap = usePreprocStackStore((s) => s.setBootstrap)
  const checkPreflight = usePreprocStackStore((s) => s.checkBootstrapPreflight)

  const [paramsText, setParamsText] = useState(
    JSON.stringify(bootstrap.params ?? {}, null, 2),
  )
  const [paramsError, setParamsError] = useState<string | null>(null)

  // Re-preflight when kind or workflow changes.
  useEffect(() => {
    void checkPreflight()
  }, [bootstrap.kind, bootstrap.workflow, checkPreflight])

  const isNipype = bootstrap.kind === 'nipype'
  const nipypeWorkflows: WorkflowInfo[] = workflows.filter(
    (w) => !['fmriprep', 'custom', 'bids_app', 'passthrough'].includes(w.name),
  )

  function applyParams() {
    try {
      const parsed = JSON.parse(paramsText)
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setParamsError('Params must be a JSON object.')
        return
      }
      setParamsError(null)
      setBootstrap({ params: parsed })
    } catch (e) {
      setParamsError((e as Error).message)
    }
  }

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
          <span style={preflightBadge(okBadge, errCount)}>
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

      <label style={labelStyle}>Params (JSON)</label>
      <textarea
        style={{
          ...inputStyle,
          minHeight: 100,
          fontFamily:
            "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        }}
        value={paramsText}
        onChange={(e) => setParamsText(e.target.value)}
        onBlur={applyParams}
        spellCheck={false}
      />
      {paramsError && (
        <div
          style={{
            color: 'var(--accent-red)',
            fontSize: 11,
            marginTop: 4,
          }}
        >
          {paramsError}
        </div>
      )}

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
            <div key={i} style={{ marginBottom: 4 }}>
              · {err}
            </div>
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
            <div key={i} style={{ marginBottom: 4 }}>
              · {w}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
