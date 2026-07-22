/** Settings — view + edit working-directory paths and other env-shaped knobs.
 *
 * Saves write to ~/.config/fmriflow/settings.json on the host. Env vars
 * still take precedence; if you have $FMRIFLOW_HOME exported in your
 * shell, that wins over the value entered here. The "Source" tag on
 * each row tells you which tier the running server is using.
 *
 * Saved values do NOT apply live — services cache resolved paths at
 * startup. After saving, restart fmriflow.
 */

import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import {
  fetchSettings, saveSettings,
  fetchResultRoots, addResultRoot, removeResultRoot,
} from '../api/client'
import type {
  SettingsKey, SettingsSnapshot, SettingsUpdate, ResultRoot,
} from '../api/types'

const SETTINGS_FIELDS: Array<{
  key: SettingsKey
  label: string
  description: string
  placeholder: string
}> = [
  {
    key: 'FMRIFLOW_HOME',
    label: 'Working directory ($FMRIFLOW_HOME)',
    description:
      'Holds your addons, configs, runs, stores, secrets, and (by default) data. ' +
      'Default: ~/projects/fmriflow.',
    placeholder: '/home/you/projects/fmriflow',
  },
  {
    key: 'FMRIFLOW_DATA',
    label: 'Big-data directory ($FMRIFLOW_DATA)',
    description:
      'Optional override for the data subtree (BIDS / derivatives / work / results). ' +
      'Default: $FMRIFLOW_HOME/data.',
    placeholder: '/mnt/raid/fmriflow-data',
  },
  {
    key: 'FS_LICENSE',
    label: 'FreeSurfer license file ($FS_LICENSE)',
    description:
      'Default: $FMRIFLOW_HOME/secrets/freesurfer-license.txt. Drop the license at ' +
      'the default location and leave this blank, or point it elsewhere.',
    placeholder: '/path/to/freesurfer/license.txt',
  },
  {
    key: 'FMRIFLOW_SINGULARITY_BIN',
    label: 'Apptainer / Singularity binary ($FMRIFLOW_SINGULARITY_BIN)',
    description:
      'Path to apptainer or singularity, used when preproc YAMLs ask for ' +
      'container_type: apptainer. Auto-detected if left blank.',
    placeholder: '/usr/bin/apptainer',
  },
]

const containerStyle: CSSProperties = {
  maxWidth: 920,
  padding: '24px 32px',
}

const headerStyle: CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 4,
}

const subtitleStyle: CSSProperties = {
  fontSize: 13,
  color: 'var(--text-secondary)',
  marginBottom: 24,
}

const sectionHeader: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginTop: 28,
  marginBottom: 12,
}

const fieldRow: CSSProperties = {
  marginBottom: 16,
  padding: '14px 16px',
  border: '1px solid var(--border)',
  borderRadius: 8,
  backgroundColor: 'var(--bg-card)',
}

const fieldHeaderRow: CSSProperties = {
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: 12,
  marginBottom: 6,
}

const labelStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const descStyle: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginBottom: 10,
  lineHeight: 1.5,
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

function sourceBadge(source: 'env' | 'persisted' | 'default'): CSSProperties {
  const colors = {
    env: { color: 'var(--accent-cyan)', bg: 'rgba(0, 229, 255, 0.1)' },
    persisted: { color: 'var(--accent-green, #4caf50)', bg: 'rgba(76, 175, 80, 0.1)' },
    default: { color: 'var(--text-secondary)', bg: 'transparent' },
  }
  const c = colors[source]
  return {
    fontSize: 10,
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: 12,
    color: c.color,
    backgroundColor: c.bg,
    border: `1px solid ${c.color}`,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  }
}

const footerRow: CSSProperties = {
  marginTop: 28,
  display: 'flex',
  alignItems: 'center',
  gap: 12,
}

const saveBtn: CSSProperties = {
  padding: '8px 18px',
  fontSize: 13,
  fontWeight: 600,
  border: '1px solid var(--accent-cyan)',
  borderRadius: 6,
  backgroundColor: 'rgba(0, 229, 255, 0.1)',
  color: 'var(--accent-cyan)',
  cursor: 'pointer',
}

const bannerStyle = (kind: 'info' | 'warning' | 'success'): CSSProperties => {
  const palette = {
    info: { color: 'var(--accent-cyan)', bg: 'rgba(0, 229, 255, 0.08)' },
    warning: { color: 'var(--accent-yellow)', bg: 'rgba(255, 184, 108, 0.10)' },
    success: { color: 'var(--accent-green, #4caf50)', bg: 'rgba(76, 175, 80, 0.10)' },
  }[kind]
  return {
    padding: '10px 14px',
    borderRadius: 6,
    fontSize: 12,
    color: palette.color,
    backgroundColor: palette.bg,
    border: `1px solid ${palette.color}`,
    marginBottom: 16,
  }
}

const resolvedTable: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 12,
}

const resolvedTd: CSSProperties = {
  padding: '6px 12px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
}

const resolvedKey: CSSProperties = {
  ...resolvedTd,
  color: 'var(--text-secondary)',
  width: 180,
  fontWeight: 600,
}

export function Settings() {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null)
  const [edits, setEdits] = useState<SettingsUpdate>({})
  const [createMissing, setCreateMissing] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [createdDirs, setCreatedDirs] = useState<string[]>([])

  const reload = () => {
    setLoading(true)
    fetchSettings()
      .then((s) => {
        setSnapshot(s)
        setEdits({})
        setLoading(false)
      })
      .catch((e) => {
        setError(String(e))
        setLoading(false)
      })
  }

  useEffect(reload, [])

  if (loading) {
    return <div style={containerStyle}>Loading…</div>
  }
  if (error || !snapshot) {
    return (
      <div style={containerStyle}>
        <div style={bannerStyle('warning')}>Failed to load settings: {error}</div>
      </div>
    )
  }

  const onChange = (key: SettingsKey, value: string) => {
    setEdits((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const onSave = async () => {
    setSaving(true)
    setError(null)
    try {
      // Submit only fields that were touched. Empty string clears
      // the persisted value (the snapshot then falls back to env or
      // default).
      const payload: SettingsUpdate = { create_missing: createMissing }
      for (const f of SETTINGS_FIELDS) {
        if (Object.prototype.hasOwnProperty.call(edits, f.key)) {
          payload[f.key] = edits[f.key] ?? ''
        }
      }
      const next = await saveSettings(payload)
      setSnapshot(next)
      setEdits({})
      setSaved(true)
      setCreatedDirs(next.created ?? [])
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const fieldValue = (key: SettingsKey): string => {
    if (Object.prototype.hasOwnProperty.call(edits, key)) {
      return edits[key] ?? ''
    }
    return snapshot.values[key].persisted ?? ''
  }

  const dirty = Object.keys(edits).length > 0

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>Settings</div>
      <div style={subtitleStyle}>
        Persisted in <code>{snapshot.runtime_config_path}</code>. Shell-exported env
        vars (e.g. <code>$FMRIFLOW_HOME</code>) still take precedence.
      </div>

      {saved && (
        <div style={bannerStyle('success')}>
          Saved. <strong>Restart fmriflow</strong> for the new paths to apply —
          services cache the resolved layout at startup.
          {createdDirs.length > 0 && (
            <div style={{ marginTop: 6 }}>
              Created on disk: {createdDirs.map((d) => <code key={d}>{d}</code>)}
            </div>
          )}
        </div>
      )}

      <div style={sectionHeader}>Paths</div>

      {SETTINGS_FIELDS.map((field) => {
        const v = snapshot.values[field.key]
        return (
          <div key={field.key} style={fieldRow}>
            <div style={fieldHeaderRow}>
              <div style={labelStyle}>{field.label}</div>
              <span style={sourceBadge(v.source)}>{v.source}</span>
            </div>
            <div style={descStyle}>
              {field.description}
              {v.source !== 'default' && (
                <>
                  <br />
                  <span style={{ color: 'var(--text-secondary)' }}>
                    Effective: <code>{v.effective}</code>
                    {v.source === 'env' && ' (from environment, overrides this form)'}
                  </span>
                </>
              )}
            </div>
            <input
              type="text"
              style={inputStyle}
              placeholder={field.placeholder}
              value={fieldValue(field.key)}
              onChange={(e) => onChange(field.key, e.target.value)}
              disabled={v.source === 'env'}
            />
            {v.source === 'env' && (
              <div
                style={{
                  fontSize: 11,
                  color: 'var(--text-secondary)',
                  marginTop: 6,
                  fontStyle: 'italic',
                }}
              >
                Locked: an environment variable is currently set. Unset it in your shell
                to edit the persisted value here.
              </div>
            )}
          </div>
        )
      })}

      <div style={footerRow}>
        <button
          style={saveBtn}
          onClick={onSave}
          disabled={!dirty || saving}
          aria-disabled={!dirty || saving}
        >
          {saving ? 'Saving…' : 'Save settings'}
        </button>
        <label
          style={{
            fontSize: 12,
            color: 'var(--text-secondary)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            cursor: 'pointer',
          }}
        >
          <input
            type="checkbox"
            checked={createMissing}
            onChange={(e) => setCreateMissing(e.target.checked)}
          />
          Create directories if they don't exist
        </label>
        {dirty && (
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Unsaved changes
          </span>
        )}
      </div>

      <div style={sectionHeader}>Resolved layout</div>
      <table style={resolvedTable}>
        <tbody>
          {Object.entries(snapshot.resolved).map(([k, v]) => (
            <tr key={k}>
              <td style={resolvedKey}>{k}</td>
              <td style={resolvedTd}>{v}</td>
            </tr>
          ))}
          <tr>
            <td style={resolvedKey}>license_file_exists</td>
            <td style={resolvedTd}>{snapshot.license_file_exists ? 'yes' : 'no'}</td>
          </tr>
          <tr>
            <td style={resolvedKey}>subjects_db</td>
            <td style={resolvedTd}>
              {snapshot.subjects_db_exists
                ? `present (${snapshot.subjects_db_count ?? '?'} subjects)`
                : 'not present'}
            </td>
          </tr>
        </tbody>
      </table>

      <ResultRootsSection />
    </div>
  )
}


function ResultRootsSection() {
  const [roots, setRoots] = useState<ResultRoot[]>([])
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [envOverride, setEnvOverride] = useState(false)

  const load = () => {
    fetchResultRoots()
      .then((s) => { setRoots(s.roots); setEnvOverride(!!s.env_override) })
      .catch((e) => setErr(String(e)))
  }
  useEffect(load, [])

  const add = () => {
    if (!path.trim()) return
    setBusy(true); setErr(null)
    addResultRoot(path.trim())
      .then((s) => { setRoots(s.roots); setPath('') })
      .catch((e) => setErr(String(e)))
      .finally(() => setBusy(false))
  }
  const remove = (p: string) => {
    setBusy(true); setErr(null)
    removeResultRoot(p)
      .then((s) => setRoots(s.roots))
      .catch((e) => setErr(String(e)))
      .finally(() => setBusy(false))
  }

  return (
    <>
      <div style={sectionHeader}>Result locations</div>
      <div style={descStyle}>
        Extra <strong>read-only</strong> directories the dashboard also scans for
        results and runs. Each should be an <code>$FMRIFLOW_HOME</code>-shaped tree
        (with <code>data/results/</code>, <code>study_runs/</code>,{' '}
        <code>group_runs/</code>, <code>runs/</code>). New runs are never written
        here. Applies on the next refresh — no restart needed.
      </div>

      {err && <div style={bannerStyle('warning')}>{err}</div>}

      {envOverride && (
        <div style={bannerStyle('info')}>
          <code>$FMRIFLOW_RESULT_ROOTS</code> is set in the environment and
          overrides this list — unset it in your shell to manage roots here.
        </div>
      )}

      <table style={resolvedTable}>
        <tbody>
          {roots.map((r) => (
            <tr key={r.root_id}>
              <td style={resolvedTd}>
                <code>{r.path}</code>{' '}
                {r.is_primary
                  ? <span style={sourceBadge('env')}>primary</span>
                  : <span style={sourceBadge('default')}>read-only</span>}
                {!r.reachable && (
                  <span style={{ ...sourceBadge('default'), color: 'var(--accent-red, #cc6677)' }}>
                    unreachable
                  </span>
                )}
              </td>
              <td style={{ ...resolvedTd, textAlign: 'right', width: 90 }}>
                {!r.is_primary && (
                  <button
                    style={{ fontSize: 11, padding: '2px 8px', cursor: 'pointer' }}
                    disabled={busy || envOverride}
                    onClick={() => remove(r.path)}
                  >
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <input
          type="text"
          style={{ ...inputStyle, flex: 1 }}
          placeholder="/path/to/another/fmriflow"
          value={path}
          disabled={envOverride}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') add() }}
        />
        <button
          style={{ padding: '6px 14px', cursor: 'pointer' }}
          disabled={busy || envOverride || !path.trim()}
          onClick={add}
        >
          Add location
        </button>
      </div>
    </>
  )
}
