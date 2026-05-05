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

type SurfaceKind = 'pial' | 'white' | 'inflated'

// Match FreeSurfer's freeview palette: pial = green, white = red.
const SURFACE_COLORS: Record<SurfaceKind, [number, number, number, number]> = {
  pial:     [ 60, 220,  90, 255],   // green
  white:    [255,  80,  80, 255],   // red
  inflated: [ 80, 160, 255, 255],   // blue
}

const ALL_SURFACES: SurfaceKind[] = ['pial', 'white', 'inflated']

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
  const [fullscreen, setFullscreen] = useState(false)
  // Multiple surfaces can be shown at once. Each renders in its own colour.
  const [surfaces, setSurfaces] = useState<Set<SurfaceKind>>(
    () => new Set<SurfaceKind>(['pial']),
  )
  // niivue sliceType: 0=axial 1=coronal 2=sagittal 3=multiplanar 4=render(3D)
  const [sliceType, setSliceType] = useState<number>(3)
  const [volumeVisible, setVolumeVisible] = useState<boolean>(true)
  // Per-mesh opacity (0..1). Default 0.55 so an inner surface peeks
  // through an outer one in 3D — same trick freeview uses.
  const [surfaceAlpha, setSurfaceAlpha] = useState<number>(0.55)
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

  // Initialize niivue when viewer is opened. Surface kind / slice type
  // changes go through their own effects so we don't reload the volume.
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
        nv.setSliceType(sliceType)
      })
      .catch((e) => console.warn('niivue load failed', e))

    return () => {
      nvRef.current = null
    }
    // We *don't* depend on sliceType / surfaceKind here — those are
    // applied incrementally below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showViewer, subject])

  // Apply slice-type changes without recreating the niivue instance.
  useEffect(() => {
    const nv = nvRef.current
    if (!nv) return
    try {
      nv.setSliceType(sliceType)
    } catch (e) {
      console.warn('niivue setSliceType failed', e)
    }
  }, [sliceType])

  // Apply mesh opacity live whenever the slider moves or meshes reload.
  useEffect(() => {
    const nv = nvRef.current as unknown as {
      meshes?: Array<{ id: string }>
      setMeshProperty?: (id: string, key: string, val: number) => void
      drawScene?: () => void
      updateGLVolume?: () => void
    } | null
    if (!nv || !nv.setMeshProperty) return
    const ms = nv.meshes ?? []
    if (ms.length === 0) return
    try {
      for (const m of ms) {
        nv.setMeshProperty(m.id, 'opacity', surfaceAlpha)
      }
      nv.drawScene?.()
    } catch (e) {
      console.warn('niivue setMeshProperty failed', e)
    }
  }, [surfaceAlpha, surfaces, showViewer])

  // Toggle volume opacity (0 = invisible, 1 = full). Lets the user
  // hide the T1 "skull" in 3D mode so the cortex meshes are unobstructed.
  useEffect(() => {
    const nv = nvRef.current as unknown as {
      volumes?: Array<unknown>
      setOpacity?: (idx: number, opacity: number) => void
      updateGLVolume?: () => void
    } | null
    if (!nv) return
    const vols = nv.volumes ?? []
    if (vols.length === 0 || !nv.setOpacity) return
    try {
      for (let i = 0; i < vols.length; i++) {
        nv.setOpacity(i, volumeVisible ? 1 : 0)
      }
      nv.updateGLVolume?.()
    } catch (e) {
      console.warn('niivue setOpacity failed', e)
    }
  }, [volumeVisible, surfaces, sliceType, showViewer])

  // Reload meshes when the surface set changes — supports multiple
  // surfaces simultaneously, colour-coded per kind.
  useEffect(() => {
    const nv = nvRef.current
    if (!nv || !showViewer) return
    const inst = nv
    let cancelled = false
    async function reload() {
      try {
        const meshes = (inst as unknown as { meshes?: Array<unknown> }).meshes ?? []
        for (const m of [...meshes]) {
          try {
            (inst as unknown as { removeMesh?: (m: unknown) => void }).removeMesh?.(m)
          } catch { /* niivue versions differ — best-effort */ }
        }
        if (cancelled || surfaces.size === 0) {
          inst.updateGLVolume()
          return
        }
        const specs = []
        for (const kind of surfaces) {
          const rgba = SURFACE_COLORS[kind]
          specs.push(
            { url: fsFileUrl(subject, `surf/lh.${kind}`), name: `lh.${kind}`, rgba255: rgba },
            { url: fsFileUrl(subject, `surf/rh.${kind}`), name: `rh.${kind}`, rgba255: rgba },
          )
        }
        await inst.loadMeshes(specs)
      } catch (e) {
        console.warn('niivue mesh reload failed', e)
      }
    }
    reload()
    return () => {
      cancelled = true
    }
  }, [surfaces, showViewer, subject])

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
          {showViewer ? 'Hide' : 'Show'} 3D viewer
        </button>
        {showViewer && (
          <div
            style={fullscreen ? {
              position: 'fixed',
              inset: 0,
              zIndex: 1000,
              background: '#000',
              padding: 12,
              display: 'flex',
              flexDirection: 'column',
            } : { marginTop: 8 }}
          >
            {/* Toolbar — view + surface pickers */}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 12,
                alignItems: 'center',
                padding: 8,
                border: '1px solid var(--border)',
                borderTopLeftRadius: 4,
                borderTopRightRadius: 4,
                background: 'var(--bg-secondary)',
                fontSize: 11,
              }}
            >
              <span style={{ color: 'var(--text-secondary)' }}>View:</span>
              {[
                { v: 3, label: 'Multi' },
                { v: 0, label: 'Axial' },
                { v: 1, label: 'Coronal' },
                { v: 2, label: 'Sagittal' },
                { v: 4, label: '3D' },
              ].map((opt) => (
                <button
                  key={opt.v}
                  style={{
                    ...btn,
                    padding: '2px 8px',
                    fontSize: 11,
                    background: sliceType === opt.v ? 'var(--accent-cyan)' : btn.background,
                    color: sliceType === opt.v ? '#000' : 'var(--text-primary)',
                    borderColor: sliceType === opt.v ? 'var(--accent-cyan)' : 'var(--border)',
                  }}
                  onClick={() => setSliceType(opt.v)}
                >
                  {opt.label}
                </button>
              ))}
              <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--border)' }} />
              <span style={{ color: 'var(--text-secondary)' }}>Volume:</span>
              <button
                style={{
                  ...btn,
                  padding: '2px 8px',
                  fontSize: 11,
                  background: volumeVisible ? 'var(--accent-cyan)' : btn.background,
                  color: volumeVisible ? '#000' : 'var(--text-primary)',
                  borderColor: volumeVisible ? 'var(--accent-cyan)' : 'var(--border)',
                }}
                onClick={() => setVolumeVisible((v) => !v)}
                title={volumeVisible
                  ? 'Hide the T1 — useful in 3D mode so the cortex meshes are unobstructed'
                  : 'Show the T1 volume'}
              >
                {volumeVisible ? 'on' : 'off'}
              </button>
              <span style={{ width: 1, alignSelf: 'stretch', background: 'var(--border)' }} />
              <span style={{ color: 'var(--text-secondary)' }}>Surfaces:</span>
              {ALL_SURFACES.map((k) => {
                const on = surfaces.has(k)
                const color = `rgb(${SURFACE_COLORS[k].slice(0, 3).join(',')})`
                return (
                  <button
                    key={k}
                    style={{
                      ...btn,
                      padding: '2px 8px',
                      fontSize: 11,
                      background: on ? color : btn.background,
                      color: on ? '#000' : 'var(--text-primary)',
                      borderColor: on ? color : 'var(--border)',
                    }}
                    onClick={() => {
                      setSurfaces((prev) => {
                        const next = new Set(prev)
                        if (next.has(k)) next.delete(k)
                        else next.add(k)
                        return next
                      })
                    }}
                  >
                    {k}
                  </button>
                )
              })}
              <button
                style={{ ...btn, padding: '2px 8px', fontSize: 11 }}
                onClick={() => setSurfaces(new Set())}
                title="Hide all surfaces"
              >
                clear
              </button>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  marginLeft: 6,
                }}
              >
                <span style={{ color: 'var(--text-secondary)' }}>α</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={surfaceAlpha}
                  onChange={(e) => setSurfaceAlpha(parseFloat(e.target.value))}
                  style={{ width: 90 }}
                  title="Surface opacity (lower = more transparent)"
                />
                <span
                  style={{
                    fontVariantNumeric: 'tabular-nums',
                    color: 'var(--text-secondary)',
                    minWidth: 28,
                  }}
                >
                  {surfaceAlpha.toFixed(2)}
                </span>
              </span>
              <span style={{ flex: 1 }} />
              <button
                style={{ ...btn, padding: '2px 8px', fontSize: 11 }}
                onClick={() => setFullscreen((v) => !v)}
                title="Pop out to fullscreen"
              >
                {fullscreen ? '⤢ Exit fullscreen' : '⤢ Fullscreen'}
              </button>
            </div>
            <div
              style={{
                border: '1px solid var(--border)',
                borderTop: 'none',
                borderBottomLeftRadius: 4,
                borderBottomRightRadius: 4,
                background: '#000',
                overflow: 'hidden',
                flex: fullscreen ? 1 : undefined,
                minHeight: 0,
              }}
            >
              <canvas
                ref={canvasRef}
                style={{
                  width: '100%',
                  height: fullscreen ? '100%' : '70vh',
                  display: 'block',
                }}
              />
            </div>
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
