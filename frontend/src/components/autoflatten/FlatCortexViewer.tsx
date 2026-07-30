/**
 * Viewer for the flattened cortex — the poster panel's interaction model.
 *
 * Flattening leaves each hemisphere at an arbitrary orientation, so the two
 * are shown as separate images that can be turned, mirrored and brought
 * together until they read as a pair. Everything is a CSS transform on a
 * server-rendered PNG: no WebGL, no mesh in the browser.
 *
 * The images are the cortex alone, drawn from the run's own
 * `?h.autoflatten.flat.patch.3d` and shaded by a per-vertex scalar. That is
 * deliberately not the `.flat.patch.png` the CLI writes, which bundles the
 * patch outline, a distortion map and a histogram into one QA figure.
 */
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

import {
  autoflattenFlatRenderUrl,
  fetchAutoflattenFlatRenderInfo,
} from '../../api/client'

type Hemi = 'lh' | 'rh'

/** Per-hemisphere placement: rotation in degrees, and a mirror sign per axis. */
interface HemiOrient {
  rot: number
  fx: 1 | -1
  fy: 1 | -1
}

const FLAT: HemiOrient = { rot: 0, fx: 1, fy: 1 }

interface Props {
  subjectsDir: string
  subject: string
  /** Shown above the images. */
  caption?: string
}

export function FlatCortexViewer({ subjectsDir, subject, caption }: Props) {
  const [hemis, setHemis] = useState<Hemi[]>([])
  const [scalars, setScalars] = useState<string[]>([])
  const [scalar, setScalar] = useState('curv')
  const [orient, setOrient] = useState<Record<Hemi, HemiOrient>>({
    lh: { ...FLAT }, rh: { ...FLAT },
  })
  const [gap, setGap] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const surfaceRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    if (!subjectsDir || !subject) return
    fetchAutoflattenFlatRenderInfo(subjectsDir, subject)
      .then(r => {
        if (cancelled) return
        const found = Object.keys(r.hemispheres ?? {}) as Hemi[]
        setHemis(found)
        setScalars(found.length ? (r.hemispheres[found[0]]?.scalars ?? []) : [])
      })
      .catch(e => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [subjectsDir, subject])

  const patch = (h: Hemi, d: Partial<HemiOrient>) =>
    setOrient(o => ({ ...o, [h]: { ...o[h], ...d } }))
  const flip = (h: Hemi, axis: 'fx' | 'fy') =>
    patch(h, { [axis]: (orient[h][axis] * -1) as 1 | -1 })
  const reset = () => {
    setOrient({ lh: { ...FLAT }, rh: { ...FLAT } })
    setGap(0)
    setZoom(1)
  }

  // A rotated element keeps its original layout box, so its corners swing
  // outside it and an export clips them. Pad by the overhang, which grows as
  // |sin| of the larger rotation. Mirroring needs no padding — it keeps the
  // same bounding box.
  const maxRot = Math.max(...hemis.map(h => Math.abs(orient[h].rot)), 0)
  const rotPad = 2 + Math.round(Math.abs(Math.sin((maxRot * Math.PI) / 180)) * 22)

  /**
   * Export by re-drawing the source PNGs onto a canvas with the same
   * transforms, rather than screenshotting the DOM. That keeps the full
   * resolution of the rendered images instead of the on-screen size, and
   * avoids a dependency purely for one button.
   */
  const download = async () => {
    setBusy(true)
    try {
      const loaded = await Promise.all(hemis.map(h => loadImage(
        autoflattenFlatRenderUrl(subjectsDir, subject, h, scalar),
      )))

      // A rotated image needs a box big enough for its swung corners.
      const boxes = loaded.map((img, i) => rotatedSize(
        img.naturalWidth, img.naturalHeight, orient[hemis[i]].rot,
      ))
      const gapPx = gap * (loaded[0].naturalWidth / 400)  // gap is in screen-ish units
      const totalW = boxes.reduce((a, b) => a + b.w, 0) + gapPx * (loaded.length - 1)
      const totalH = Math.max(...boxes.map(b => b.h))

      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(totalW)
      canvas.height = Math.ceil(totalH)
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('could not get a 2D context')

      let x = 0
      loaded.forEach((img, i) => {
        const o = orient[hemis[i]]
        const box = boxes[i]
        ctx.save()
        ctx.translate(x + box.w / 2, totalH / 2)
        ctx.rotate((o.rot * Math.PI) / 180)
        ctx.scale(o.fx, o.fy)
        ctx.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2)
        ctx.restore()
        x += box.w + gapPx
      })

      const a = document.createElement('a')
      a.href = canvas.toDataURL('image/png')
      a.download = `${subject}-flattened-cortex.png`
      a.click()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (error && hemis.length === 0) {
    return <div style={hintStyle}>Could not load flatmaps: {error}</div>
  }
  if (hemis.length === 0) {
    return <div style={hintStyle}>No flat patches found for {subject}.</div>
  }

  return (
    <div style={boxStyle}>
      <div style={headerStyle} data-no-export="true">
        <span>{caption ?? 'Flattened cortex'}</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-secondary)' }}>
          rendered from ?h.autoflatten.flat.patch.3d
        </span>
      </div>

      <div style={controlRowStyle} data-no-export="true">
        <label style={labelStyle}>
          shading
          <select value={scalar} onChange={e => setScalar(e.target.value)} style={selectStyle}>
            {scalars.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>

        {hemis.map(h => (
          <span key={h} style={hemiGroupStyle}>
            <span style={ctrlLabelStyle}>{h}</span>
            <input
              type="range" min={-180} max={180} step={1}
              value={orient[h].rot}
              onChange={e => patch(h, { rot: Number(e.target.value) })}
              title={`Rotate ${h}`}
              style={rotSliderStyle}
            />
            {/* Fixed width so the row does not reflow as the number changes. */}
            <span style={rotValueStyle}>{orient[h].rot}°</span>
            <button style={toggleStyle(orient[h].fx === -1)} title="Flip horizontally"
                    onClick={() => flip(h, 'fx')}>⇋</button>
            <button style={toggleStyle(orient[h].fy === -1)} title="Flip vertically"
                    onClick={() => flip(h, 'fy')}>⇅</button>
          </span>
        ))}

        {hemis.length > 1 && (
          <label style={labelStyle}>
            gap
            <button style={ctrlBtnStyle} onClick={() => setGap(g => g - 5)}>−</button>
            <input
              type="number" step={5} value={gap}
              onChange={e => setGap(Number(e.target.value) || 0)}
              style={numStyle}
            />
            <button style={ctrlBtnStyle} onClick={() => setGap(g => g + 5)}>+</button>
          </label>
        )}

        <label style={labelStyle}>
          zoom
          <input type="range" min={0.4} max={3} step={0.1} value={zoom}
                 onChange={e => setZoom(Number(e.target.value))} />
        </label>

        <button style={btnStyle} onClick={reset}>reset</button>
        <button style={btnStyle} onClick={download} disabled={busy}>
          {busy ? 'exporting…' : '↓ download'}
        </button>
      </div>

      <div ref={surfaceRef} style={surfaceStyle}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: `${rotPad}% 2%`,
        }}>
          {hemis.map((h, i) => (
            <img
              key={`${h}-${scalar}`}
              src={autoflattenFlatRenderUrl(subjectsDir, subject, h, scalar)}
              alt={`${h} flattened cortex`}
              onError={() => setError(`could not render ${h}`)}
              style={{
                width: `${45 * zoom}%`,
                // Mirror nested inside rotate, so flips are about the
                // image's own axes rather than the screen's.
                transform: `rotate(${orient[h].rot}deg) scale(${orient[h].fx}, ${orient[h].fy})`,
                marginLeft: i > 0 ? gap : 0,
                transition: 'transform 80ms linear',
              }}
            />
          ))}
        </div>
      </div>

      {error && <div style={{ ...hintStyle, color: 'var(--accent-red, #f87171)' }}>{error}</div>}
    </div>
  )
}

// ── export helpers ──────────────────────────────────────────────────

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`could not load ${src}`))
    img.src = src
  })
}

/** Bounding box of a w×h rectangle rotated by `deg`. */
export function rotatedSize(w: number, h: number, deg: number): { w: number; h: number } {
  const r = (deg * Math.PI) / 180
  const c = Math.abs(Math.cos(r))
  const s = Math.abs(Math.sin(r))
  return { w: w * c + h * s, h: w * s + h * c }
}

// ── styles ──────────────────────────────────────────────────────────

const boxStyle: CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 6,
  overflow: 'hidden', marginTop: 12,
}
const headerStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '8px 12px', borderBottom: '1px solid var(--border)',
  fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
  letterSpacing: 0.5, color: 'var(--accent-cyan)',
}
const controlRowStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
  padding: '8px 12px', borderBottom: '1px solid var(--border)',
  fontSize: 11, color: 'var(--text-secondary)',
}
const hemiGroupStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 3,
}
const labelStyle: CSSProperties = { display: 'flex', alignItems: 'center', gap: 5 }
const ctrlLabelStyle: CSSProperties = {
  fontWeight: 700, textTransform: 'uppercase', marginRight: 2,
}
const selectStyle: CSSProperties = {
  background: 'var(--bg-card)', color: 'var(--text-primary)',
  border: '1px solid var(--border)', borderRadius: 3, padding: '2px 5px',
  fontSize: 11,
}
const rotSliderStyle: CSSProperties = { width: 110 }
const rotValueStyle: CSSProperties = {
  width: 38, textAlign: 'right', fontVariantNumeric: 'tabular-nums',
  color: 'var(--text-primary)',
}
const numStyle: CSSProperties = {
  width: 52, background: 'var(--bg-card)', color: 'var(--text-primary)',
  border: '1px solid var(--border)', borderRadius: 3, padding: '2px 4px',
  fontSize: 11, textAlign: 'center',
}
const ctrlBtnStyle: CSSProperties = {
  background: 'var(--bg-card)', color: 'var(--text-secondary)',
  border: '1px solid var(--border)', borderRadius: 3,
  padding: '1px 6px', cursor: 'pointer', fontSize: 12, lineHeight: 1.4,
}
const btnStyle: CSSProperties = { ...ctrlBtnStyle, padding: '3px 10px' }
const toggleStyle = (on: boolean): CSSProperties => ({
  ...ctrlBtnStyle,
  color: on ? 'var(--on-accent, #fff)' : 'var(--text-secondary)',
  background: on ? 'var(--accent-cyan, #0891b2)' : 'var(--bg-card)',
  borderColor: on ? 'var(--accent-cyan, #0891b2)' : 'var(--border)',
})
const surfaceStyle: CSSProperties = {
  background: 'var(--bg-card)', minHeight: 200,
}
const hintStyle: CSSProperties = {
  fontSize: 11, color: 'var(--text-secondary)', padding: '8px 12px',
}
