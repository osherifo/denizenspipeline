/** Structural-QC review panel: fmriprep report + niivue viewer + decision form. */

import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Niivue } from '@niivue/niivue'
import {
  fetchReview,
  saveReview,
  fetchFreeviewCommand,
  reportUrl,
  fsFileUrl,
} from '../../api/structural-qc'
import type { StructuralQCReview, StructuralQCStatus } from '../../api/types'

interface Props {
  subject: string
}

const STATUSES: { value: StructuralQCStatus; label: string; color: string }[] = [
  { value: 'pending', label: 'Pending', color: 'var(--text-secondary)' },
  { value: 'approved', label: 'Approve', color: 'var(--accent-green)' },
  { value: 'needs_edits', label: 'Needs edits', color: 'var(--accent-yellow)' },
  { value: 'rejected', label: 'Rejected', color: 'var(--accent-red)' },
]

const sectionLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 16,
  marginBottom: 8,
}

const btn: CSSProperties = {
  padding: '6px 12px',
  fontSize: 12,
  fontWeight: 600,
  borderRadius: 4,
  border: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
}

const primaryBtn: CSSProperties = {
  ...btn,
  background: 'var(--accent-cyan)',
  color: '#000',
  border: 'none',
}

export function StructuralQCPanel({ subject }: Props) {
  const [review, setReview] = useState<StructuralQCReview | null>(null)
  const [status, setStatus] = useState<StructuralQCStatus>('pending')
  const [reviewer, setReviewer] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [freeviewCmd, setFreeviewCmd] = useState<string | null>(null)
  const [freeviewErr, setFreeviewErr] = useState<string | null>(null)
  const [showReport, setShowReport] = useState(false)
  const [showViewer, setShowViewer] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const nvRef = useRef<Niivue | null>(null)

  // Load existing review
  useEffect(() => {
    let cancelled = false
    fetchReview(subject)
      .then((r) => {
        if (cancelled) return
        setReview(r)
        setStatus(r.status)
        setReviewer(r.reviewer)
        setNotes(r.notes)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [subject])

  // Initialize niivue when viewer is opened
  useEffect(() => {
    if (!showViewer || !canvasRef.current) return
    const nv = new Niivue({ show3Dcrosshair: true, backColor: [0, 0, 0, 1] })
    nvRef.current = nv
    nv.attachToCanvas(canvasRef.current)

    // niivue derives the file format from `name` (preferring it over `url`),
    // so the name MUST keep its extension or `getFileExt` blows up with
    // "Cannot read properties of undefined (reading 'toUpperCase')".
    nv.loadVolumes([{ url: fsFileUrl(subject, 'mri/T1.mgz'), name: 'T1.mgz' }])
      .then(() => {
        return nv.loadMeshes([
          {
            url: fsFileUrl(subject, 'surf/lh.pial'),
            name: 'lh.pial',
            rgba255: [255, 0, 0, 255],
          },
          {
            url: fsFileUrl(subject, 'surf/rh.pial'),
            name: 'rh.pial',
            rgba255: [255, 0, 0, 255],
          },
        ])
      })
      .catch((e) => console.warn('niivue load failed', e))

    return () => {
      nvRef.current = null
    }
  }, [showViewer, subject])

  async function handleSave() {
    setSaving(true)
    try {
      const result = await saveReview(subject, {
        status,
        reviewer,
        notes,
        freeview_command_used: freeviewCmd,
      })
      setReview(result.review)
      setSavedAt(new Date().toLocaleTimeString())
    } catch (e) {
      console.error('Save failed', e)
      alert(`Save failed: ${e}`)
    } finally {
      setSaving(false)
    }
  }

  async function handleCopyFreeview() {
    setFreeviewErr(null)
    try {
      const { command } = await fetchFreeviewCommand(subject)
      await navigator.clipboard.writeText(command)
      setFreeviewCmd(command)
    } catch (e) {
      setFreeviewErr(String(e))
    }
  }

  const currentStatus = STATUSES.find((s) => s.value === status) ?? STATUSES[0]

  return (
    <div>
      <div style={sectionLabel}>
        Structural QC{' '}
        <span style={{ marginLeft: 6, color: currentStatus.color }}>
          ● {currentStatus.label}
        </span>
        {review?.timestamp && (
          <span
            style={{
              marginLeft: 8,
              fontSize: 10,
              color: 'var(--text-secondary)',
              fontWeight: 400,
              textTransform: 'none',
              letterSpacing: 0,
            }}
          >
            last saved {new Date(review.timestamp).toLocaleString()}
          </span>
        )}
      </div>

      {/* Report toggle + iframe */}
      <div style={{ marginBottom: 12 }}>
        <button style={btn} onClick={() => setShowReport((v) => !v)}>
          {showReport ? 'Hide' : 'Show'} fmriprep report
        </button>
        {showReport && (
          <iframe
            src={reportUrl(subject)}
            title="fmriprep report"
            style={{
              width: '100%',
              height: 600,
              marginTop: 8,
              border: '1px solid var(--border)',
              borderRadius: 4,
            }}
          />
        )}
      </div>

      {/* Niivue toggle + canvas */}
      <div style={{ marginBottom: 12 }}>
        <button style={btn} onClick={() => setShowViewer((v) => !v)}>
          {showViewer ? 'Hide' : 'Show'} 3D viewer (T1 + pial)
        </button>
        {showViewer && (
          <div
            style={{
              marginTop: 8,
              border: '1px solid var(--border)',
              borderRadius: 4,
              background: '#000',
              overflow: 'hidden',
            }}
          >
            <canvas
              ref={canvasRef}
              style={{ width: '100%', height: 500, display: 'block' }}
            />
          </div>
        )}
      </div>

      {/* Decision panel */}
      <div
        style={{
          padding: 12,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 6,
        }}
      >
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {STATUSES.map((s) => (
            <button
              key={s.value}
              onClick={() => setStatus(s.value)}
              style={{
                ...btn,
                borderColor: status === s.value ? s.color : 'var(--border)',
                background:
                  status === s.value ? s.color : 'var(--bg-secondary)',
                color: status === s.value ? '#000' : 'var(--text-primary)',
              }}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input
            placeholder="reviewer (e.g. omar)"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
            style={{
              flex: 1,
              padding: '6px 8px',
              fontSize: 12,
              border: '1px solid var(--border)',
              borderRadius: 4,
              background: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
        <textarea
          placeholder="notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          style={{
            width: '100%',
            padding: 8,
            fontSize: 12,
            border: '1px solid var(--border)',
            borderRadius: 4,
            background: 'var(--bg-secondary)',
            color: 'var(--text-primary)',
            resize: 'vertical',
            marginBottom: 8,
            boxSizing: 'border-box',
          }}
        />

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button style={primaryBtn} onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save review'}
          </button>
          {status === 'needs_edits' && (
            <button style={btn} onClick={handleCopyFreeview}>
              Copy freeview command
            </button>
          )}
          {savedAt && (
            <span style={{ fontSize: 11, color: 'var(--accent-green)' }}>
              ✓ saved {savedAt}
            </span>
          )}
          {freeviewCmd && (
            <span style={{ fontSize: 11, color: 'var(--accent-cyan)' }}>
              ✓ freeview command copied
            </span>
          )}
          {freeviewErr && (
            <span style={{ fontSize: 11, color: 'var(--accent-red)' }}>
              {freeviewErr}
            </span>
          )}
        </div>

        {freeviewCmd && (
          <pre
            style={{
              marginTop: 8,
              padding: 8,
              fontSize: 11,
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}
          >
            {freeviewCmd}
          </pre>
        )}
      </div>
    </div>
  )
}
