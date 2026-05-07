/** Displays KB matches for a failed run's triage record, plus a
 *  "Save to KB" CTA that opens a pre-filled draft form.
 *
 *  Usage: <TriageMatches runId={run.run_id} /> — the component
 *  fetches its own data and renders nothing while loading or if the
 *  run has no triage record (still running / succeeded / too-early).
 */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import type { TriageRecord, TriageCandidateMatch } from '../../api/types'
import { fetchTriage, saveNewErrorFromCapture } from '../../api/client'
import { useDialog } from '../common/Dialog'

interface Props {
  runId: string
  /** If true, the component refetches every few seconds until a
   *  record appears (useful when a run JUST failed and the triage
   *  thread hasn't finished writing triage.json yet). */
  poll?: boolean
}

// ── Styles ──────────────────────────────────────────────────────────────

const panel: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '12px 14px',
  marginBottom: 12,
  fontSize: 12,
}

const header: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginBottom: 8,
  gap: 12,
}

const title: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
  letterSpacing: 1,
  textTransform: 'uppercase',
}

const matchRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '6px 0',
  borderBottom: '1px solid var(--border)',
}

const matchId: CSSProperties = {
  fontFamily: 'monospace',
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  width: 40,
  flexShrink: 0,
}

const matchTitle: CSSProperties = {
  flex: 1,
  fontSize: 12,
  color: 'var(--text-primary)',
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}

const confBarOuter: CSSProperties = {
  width: 80,
  height: 6,
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 3,
  overflow: 'hidden',
  flexShrink: 0,
}

const emptyMsg: CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  fontStyle: 'italic',
}

const btn: CSSProperties = {
  padding: '4px 10px',
  fontSize: 10,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 4,
  cursor: 'pointer',
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const primaryBtn: CSSProperties = {
  ...btn,
  border: '1px solid var(--accent-cyan)',
  backgroundColor: 'rgba(0, 229, 255, 0.12)',
  color: 'var(--accent-cyan)',
}

// ── Component ───────────────────────────────────────────────────────────

function confidenceColor(c: number): string {
  if (c >= 0.85) return 'var(--accent-green)'
  if (c >= 0.5) return 'var(--accent-cyan)'
  return 'var(--text-secondary)'
}

export function TriageMatches({ runId, poll = false }: Props) {
  const [record, setRecord] = useState<TriageRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const dlg = useDialog()

  useEffect(() => {
    let cancelled = false
    let timer: number | null = null

    async function load() {
      try {
        const r = await fetchTriage(runId)
        if (cancelled) return
        setRecord(r)
        setLoading(false)
        // Keep polling while there's no record AND caller asked for it.
        if (poll && r === null) {
          timer = window.setTimeout(load, 3000)
        }
      } catch {
        if (!cancelled) setLoading(false)
      }
    }
    load()

    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [runId, poll])

  async function handleSave() {
    if (!record) return
    const titleInput = await dlg.prompt(
      'Short title for this KB entry:',
      { defaultValue: record.symptom || '' },
    )
    if (!titleInput) return
    setSaving(true)
    try {
      const r = await saveNewErrorFromCapture({
        run_id: runId,
        title: titleInput,
        tags: record.tags,
      })
      await dlg.alert(
        `Saved draft #${r.id} → devdocs/errors/_proposed/${r.filename}\n\n` +
        `Edit it to fill in root_cause / fix, then move it up to ` +
        `devdocs/errors/ to promote to a real KB entry.`,
      )
    } catch (e) {
      await dlg.alert(`Save failed: ${e}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return null
  if (record === null) return null

  const matches = record.candidate_matches || []

  return (
    <div style={panel}>
      <div style={header}>
        <span style={title}>
          {matches.length > 0
            ? `Matches in KB (${matches.length})`
            : 'Triage captured'}
        </span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button style={btn} onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save to KB'}
          </button>
        </div>
      </div>
      {matches.length === 0 && (
        <div style={emptyMsg}>
          No existing entries matched this failure — save a new one to start a
          pattern for next time.
        </div>
      )}
      {matches.map((m: TriageCandidateMatch) => (
        <div key={m.id} style={matchRow}>
          <div style={matchId}>#{m.id}</div>
          <div style={matchTitle} title={m.title}>{m.title}</div>
          <div
            style={confBarOuter}
            title={`${Math.round(m.confidence * 100)}% — ${m.match_on}`}
          >
            <div
              style={{
                width: `${Math.round(m.confidence * 100)}%`,
                height: '100%',
                backgroundColor: confidenceColor(m.confidence),
              }}
            />
          </div>
          <a
            href={`#/errors?id=${m.id}`}
            style={{ ...primaryBtn, textDecoration: 'none', display: 'inline-block' }}
          >
            View fix
          </a>
        </div>
      ))}
    </div>
  )
}
