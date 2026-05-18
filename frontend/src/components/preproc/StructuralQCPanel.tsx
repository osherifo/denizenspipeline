/** Structural-QC review panel: fmriprep report + niivue viewer + decision form. */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Niivue } from '@niivue/niivue'
import { MeshContourIndex, axCorSagToAxis } from './contourRenderer'
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
  // Multiple surfaces can be shown at once. Each renders in its own colour.
  const [surfaces, setSurfaces] = useState<Set<SurfaceKind>>(
    () => new Set<SurfaceKind>(['pial']),
  )
  // niivue sliceType: 0=axial 1=coronal 2=sagittal 3=multiplanar 4=render(3D)
  const [sliceType, setSliceType] = useState<number>(3)
  const [volumeVisible, setVolumeVisible] = useState<boolean>(true)
  // Freeview-style mesh-on-slice contours: niivue clips the 3D mesh
  // to a slab of this thickness (in mm, world space) around the
  // slice plane. 2mm reads as a thin band; in 3D mode we force
  // Infinity so the full mesh shows.
  const [contourMm, setContourMm] = useState<number>(2.0)
  // 'slab' = niivue's setMeshThicknessOn2D (3D mesh clipped to a
  // band around the slice plane — fast, but tangential crossings
  // become wide blobs); 'real' = true plane-triangle intersection
  // computed in JS and drawn as 1-px polylines on an overlay canvas
  // (Freeview-style; the right shape).
  // Implementation in ./contourRenderer.ts; design in
  // devdocs/proposals/frontend/true-contour-renderer.md.
  const [contourMode, setContourMode] = useState<'slab' | 'real'>('real')
  // Current voxel index per axis [X, Y, Z] for the scrubber UI.
  // Synced with niivue's crosshair via onLocationChange so clicking
  // in the canvas also moves the sliders.
  const [voxXYZ, setVoxXYZ] = useState<[number, number, number] | null>(null)
  const [dimsXYZ, setDimsXYZ] = useState<[number, number, number] | null>(null)
  // 2D zoom factor written into pan2Dxyzmm[3]. Default 1 = fit. Niivue's
  // built-in wheel-zoom only fires in dragMode=pan and is clamped to
  // [0.1, 10] in 0.1 steps; the explicit slider here bypasses both so
  // reviewers can crank in arbitrarily far to check contour quality.
  const [zoom2D, setZoom2D] = useState<number>(1.0)
  // 3D zoom factor written into scene.volScaleMultiplier. Niivue's
  // built-in 3D keyboard zoom clamps to [0.5, 2]; we bypass via the
  // slider to allow the same 0.25–20× range as 2D.
  const [zoom3D, setZoom3D] = useState<number>(1.0)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const overlayRef = useRef<HTMLCanvasElement | null>(null)
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

    // World-space slices (mm) are required for meshThicknessOn2D to
    // clip the mesh correctly. Voxel-space mode disables mesh
    // visibility entirely per the niivue API note.
    try {
      (nv as unknown as { setSliceMM?: (b: boolean) => void }).setSliceMM?.(true)
    } catch { /* niivue versions differ — best-effort */ }

    // Drag-pan when zoomed in — click still moves the crosshair (that's
    // a separate `mouseClick` path), but click+drag now translates the
    // view instead of adjusting contrast. As a side-effect this also
    // enables niivue's cursor-anchored wheel-zoom (per `sliceScroll2D`
    // which only zooms when dragMode === pan). Slice scrolling moves to
    // the scrubbers and click-to-navigate.
    try {
      const inst = nv as unknown as { opts?: { dragMode?: number } }
      if (inst.opts) inst.opts.dragMode = 3 /* DRAG_MODE.pan */
    } catch { /* */ }

    // Sync the slice scrubbers when the user clicks/scrolls inside
    // the canvas. Payload shape from niivue: `{ vox: [x, y, z], ... }`
    // in RAS voxel coordinates.
    ;(nv as unknown as { onLocationChange?: (loc: unknown) => void }).onLocationChange =
      (loc: unknown) => {
        const v = (loc as { vox?: number[] }).vox
        if (v && v.length >= 3) {
          setVoxXYZ([Math.round(v[0]), Math.round(v[1]), Math.round(v[2])])
        }
      }

    // niivue derives the file format from `name` (preferring it over `url`),
    // so the name MUST keep its extension or `getFileExt` blows up with
    // "Cannot read properties of undefined (reading 'toUpperCase')".
    nv.loadVolumes([{ url: fsFileUrl(subject, 'mri/T1.mgz'), name: 'T1.mgz' }])
      .then(() => {
        nv.setSliceType(sliceType)
        // Populate dim/voxel state so the scrubbers know their range
        // and starting position.
        const inst = nv as unknown as {
          volumes?: Array<{ dimsRAS?: number[] }>
          scene?: { crosshairPos?: Float32Array }
          frac2vox?: (f: Float32Array, idx?: number) => number[]
        }
        const d = inst.volumes?.[0]?.dimsRAS
        if (d && d.length >= 4) {
          setDimsXYZ([d[1], d[2], d[3]])
        }
        try {
          const f = inst.scene?.crosshairPos
          if (f && inst.frac2vox) {
            const v = inst.frac2vox(f)
            setVoxXYZ([Math.round(v[0]), Math.round(v[1]), Math.round(v[2])])
          }
        } catch { /* niivue versions differ — best-effort */ }
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

  // Drive 2D zoom from the slider. Anchors on the crosshair (same
  // formula niivue uses for its scroll-wheel zoom: shift pan by
  // delta-zoom × crosshair-mm) so zooming in keeps the point of
  // interest centred. No-op in 3D render mode.
  useEffect(() => {
    const nv = nvRef.current as unknown as {
      scene?: { crosshairPos?: Float32Array; pan2Dxyzmm?: Float32Array | number[] }
      frac2mm?: (f: Float32Array, idx?: number, force?: boolean) => number[]
      drawScene?: () => void
    } | null
    if (!nv?.scene?.pan2Dxyzmm || sliceType === 4) return
    try {
      const pan = nv.scene.pan2Dxyzmm
      const cur = pan[3]
      const zoomChange = cur - zoom2D
      const cross = nv.scene.crosshairPos
      if (cross && nv.frac2mm) {
        const mm = nv.frac2mm(cross)
        pan[0] += zoomChange * mm[0]
        pan[1] += zoomChange * mm[1]
        pan[2] += zoomChange * mm[2]
      }
      pan[3] = zoom2D
      nv.drawScene?.()
    } catch (e) {
      console.warn('niivue zoom failed', e)
    }
  }, [zoom2D, sliceType, showViewer])

  // Drive 3D zoom from the slider via volScaleMultiplier. Niivue
  // provides a `setScale()` helper which is just a setter for
  // scene.volScaleMultiplier — using it triggers a redraw without
  // the built-in [0.5, 2] clamp from the keyboard handler.
  useEffect(() => {
    const nv = nvRef.current as unknown as {
      setScale?: (s: number) => void
      scene?: { volScaleMultiplier?: number }
      drawScene?: () => void
    } | null
    if (!nv || sliceType !== 4) return
    try {
      if (nv.setScale) {
        nv.setScale(zoom3D)
      } else if (nv.scene) {
        nv.scene.volScaleMultiplier = zoom3D
        nv.drawScene?.()
      }
    } catch (e) {
      console.warn('niivue setScale failed', e)
    }
  }, [zoom3D, sliceType, showViewer])

  // Clip meshes to a slab around the slice plane so they read as
  // Freeview-style pial/white contours on 2D slices. In pure 3D
  // render mode (sliceType 4) we show the full mesh (Infinity).
  // When contourMode === 'real' AND we're in any 2D mode, we hide
  // niivue's slab (thickness 0) so only the true polyline overlay
  // shows; the contour-thickness slider therefore only applies to
  // slab mode.
  useEffect(() => {
    const nv = nvRef.current as unknown as {
      setMeshThicknessOn2D?: (n: number) => void
    } | null
    if (!nv?.setMeshThicknessOn2D) return
    const realActive = contourMode === 'real' && sliceType !== 4
    const thickness =
      sliceType === 4 ? Infinity : realActive ? 0 : contourMm
    try {
      nv.setMeshThicknessOn2D(thickness)
    } catch (e) {
      console.warn('niivue setMeshThicknessOn2D failed', e)
    }
  }, [contourMm, contourMode, sliceType, surfaces, showViewer])

  // Per-mesh AABB index cache, keyed by mesh.pts identity. WeakMap so
  // unloaded meshes garbage-collect their index automatically.
  const contourIndexCache = useRef<WeakMap<Float32Array, MeshContourIndex>>(
    new WeakMap(),
  )
  // Ref to the latest draw closure — installed once into niivue's
  // drawScene monkey-patch (see init effect), but updated whenever any
  // dependency changes so the patch always calls the current version.
  const drawContoursRef = useRef<() => void>(() => {})

  const drawContours = useCallback(() => {
    const nv = nvRef.current as unknown as {
      meshes?: Array<{
        pts?: Float32Array
        tris?: Uint32Array
        rgba255?: Uint8Array
        visible?: boolean
      }>
      scene?: { crosshairPos?: Float32Array; pan2Dxyzmm?: Float32Array | number[] }
      frac2mm?: (f: Float32Array, idx?: number, force?: boolean) => number[]
      screenSlices?: Array<{
        leftTopWidthHeight: [number, number, number, number]
        axCorSag: number
        leftTopMM: [number, number]
        fovMM: [number, number]
      }>
    } | null
    const overlay = overlayRef.current
    const nvCanvas = canvasRef.current
    if (!overlay || !nvCanvas) return
    const ctx = overlay.getContext('2d')
    if (!ctx) return

    // Match overlay backing-store + CSS size to niivue's canvas every
    // pass so resizes don't desync.
    if (overlay.width !== nvCanvas.width) overlay.width = nvCanvas.width
    if (overlay.height !== nvCanvas.height) overlay.height = nvCanvas.height
    overlay.style.width = nvCanvas.style.width || `${nvCanvas.clientWidth}px`
    overlay.style.height = nvCanvas.style.height || `${nvCanvas.clientHeight}px`
    ctx.clearRect(0, 0, overlay.width, overlay.height)

    if (!showViewer || contourMode !== 'real' || sliceType === 4) return
    if (!nv?.screenSlices || !nv.meshes || !nv.scene?.crosshairPos || !nv.frac2mm) return

    const crossMM = nv.frac2mm(nv.scene.crosshairPos) // [x, y, z] in real RAS mm

    for (const tile of nv.screenSlices) {
      const axisIdx = axCorSagToAxis(tile.axCorSag)
      if (axisIdx === null) continue // skip the 3D render tile in multi mode
      const sliceMM = crossMM[axisIdx]
      const ltwh = tile.leftTopWidthHeight
      const lt = tile.leftTopMM
      const fov = tile.fovMM

      for (const mesh of nv.meshes) {
        if (mesh.visible === false) continue
        const pts = mesh.pts
        const tris = mesh.tris
        const rgba = mesh.rgba255
        if (!pts || !tris || !rgba) continue

        let index = contourIndexCache.current.get(pts)
        if (!index) {
          index = new MeshContourIndex(pts, tris)
          contourIndexCache.current.set(pts, index)
        }
        const segs = index.intersect(axisIdx, sliceMM)
        if (segs.length === 0) continue

        ctx.strokeStyle = `rgb(${rgba[0]}, ${rgba[1]}, ${rgba[2]})`
        ctx.lineWidth = 1
        ctx.beginPath()
        // Project each real-RAS-mm endpoint to canvas pixels using
        // the same linear-interp niivue uses internally (see
        // sliceMM2px in index.js:129629). Pan + zoom are already
        // baked into leftTopMM and fovMM by niivue's draw2DMain
        // (it modifies screen2.mnMM/mxMM by `(mm - pan) / zoom`
        // before passing them to calculateMvpMatrix2D, and the
        // resulting projection is what the slice texture is rendered
        // through). So we plug in real mm directly — no extra
        // transform on our end. Y is flipped because canvas y grows
        // downward while the in-plane v axis grows upward.
        const lt0 = lt[0], lt1 = lt[1], fov0 = fov[0], fov1 = fov[1]
        const ltwh0 = ltwh[0], ltwh1 = ltwh[1], ltwh2 = ltwh[2], ltwh3 = ltwh[3]
        for (let i = 0; i < segs.length; i += 4) {
          const x1 = ltwh0 + ((segs[i] - lt0) / fov0) * ltwh2
          const y1 = ltwh1 + ltwh3 - ((segs[i + 1] - lt1) / fov1) * ltwh3
          const x2 = ltwh0 + ((segs[i + 2] - lt0) / fov0) * ltwh2
          const y2 = ltwh1 + ltwh3 - ((segs[i + 3] - lt1) / fov1) * ltwh3
          ctx.moveTo(x1, y1)
          ctx.lineTo(x2, y2)
        }
        ctx.stroke()
      }
    }
  }, [contourMode, sliceType, surfaces, voxXYZ, showViewer, zoom2D])

  // Keep the ref pointed at the latest closure, so the monkey-patch
  // below always calls the current version.
  useEffect(() => {
    drawContoursRef.current = drawContours
    drawContours()
  }, [drawContours])

  // Monkey-patch nv.drawScene so the overlay redraws after every
  // niivue draw — this is how we stay aligned during mouse drag-pan,
  // window resize, contrast tweaks, etc. that don't go through our
  // React state. Installed once per viewer-open, restored on unmount.
  useEffect(() => {
    const nv = nvRef.current as unknown as {
      drawScene?: () => void
    } | null
    if (!nv?.drawScene) return
    const original = nv.drawScene.bind(nv)
    nv.drawScene = () => {
      original()
      drawContoursRef.current()
    }
    return () => {
      if (nvRef.current) {
        (nvRef.current as unknown as { drawScene?: () => void }).drawScene = original
      }
    }
  }, [showViewer])

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

  // sliceType → which voxel axes the visible plane(s) move through.
  // niivue: 0=axial→Z, 1=coronal→Y, 2=sagittal→X, 3=multi=all, 4=3D none.
  function axesForSliceType(st: number): Array<0 | 1 | 2> {
    if (st === 3) return [0, 1, 2]
    if (st === 0) return [2]
    if (st === 1) return [1]
    if (st === 2) return [0]
    return []
  }

  const ZOOM_MIN = 0.25
  const ZOOM_MAX = 20

  // 2D and 3D zooms are different niivue knobs (pan2Dxyzmm[3] vs
  // volScaleMultiplier); the toolbar exposes one set of controls
  // that dispatches based on the active slice type.
  const activeZoom = sliceType === 4 ? zoom3D : zoom2D
  const setActiveZoom = sliceType === 4 ? setZoom3D : setZoom2D

  function bumpZoom(factor: number) {
    setActiveZoom((z) => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z * factor)))
  }

  function resetZoom() {
    // Clears 2D pan + 2D zoom + 3D zoom in one shot so a single
    // "reset" is enough no matter which view you're in.
    const nv = nvRef.current as unknown as {
      scene?: { pan2Dxyzmm?: Float32Array | number[]; volScaleMultiplier?: number }
      drawScene?: () => void
    } | null
    if (nv?.scene) {
      const p = nv.scene.pan2Dxyzmm
      if (p) { p[0] = 0; p[1] = 0; p[2] = 0; p[3] = 1 }
      nv.scene.volScaleMultiplier = 1
      try { nv.drawScene?.() } catch { /* */ }
    }
    setZoom2D(1.0)
    setZoom3D(1.0)
  }

  function setSlice(axisIdx: 0 | 1 | 2, vox: number) {
    const nv = nvRef.current as unknown as {
      scene?: { crosshairPos?: Float32Array }
      drawScene?: () => void
    } | null
    const dims = dimsXYZ
    if (!nv?.scene?.crosshairPos || !dims) return
    const clamped = Math.max(0, Math.min(dims[axisIdx] - 1, Math.round(vox)))
    // crosshairPos is in fractional [0,1] coords per axis; convert
    // voxel index → voxel-center fraction.
    nv.scene.crosshairPos[axisIdx] = (clamped + 0.5) / dims[axisIdx]
    setVoxXYZ((prev) => {
      const next: [number, number, number] = prev ? [prev[0], prev[1], prev[2]] : [0, 0, 0]
      next[axisIdx] = clamped
      return next
    })
    try { nv.drawScene?.() } catch { /* */ }
  }

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
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 1000,
              background: '#000',
              padding: 12,
              display: 'flex',
              flexDirection: 'column',
            }}
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
              {sliceType !== 4 && (
                <span
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginLeft: 6 }}
                  title="Contour rendering: 'real' = true plane-triangle intersection drawn on an overlay canvas (Freeview-style, the correct shape); 'slab' = niivue's setMeshThicknessOn2D (3D mesh clipped to a band, fast but wide at tangential crossings)."
                >
                  <span style={{ color: 'var(--text-secondary)' }}>Mode</span>
                  {(['real', 'slab'] as const).map((m) => (
                    <button
                      key={m}
                      style={{
                        ...btn,
                        padding: '2px 8px',
                        fontSize: 11,
                        background: contourMode === m ? 'var(--accent-cyan)' : btn.background,
                        color: contourMode === m ? '#000' : 'var(--text-primary)',
                        borderColor: contourMode === m ? 'var(--accent-cyan)' : 'var(--border)',
                      }}
                      onClick={() => setContourMode(m)}
                      title={m === 'real' ? 'True plane-triangle contour' : 'Niivue slab clip'}
                    >
                      {m}
                    </button>
                  ))}
                </span>
              )}
              {sliceType !== 4 && contourMode === 'slab' && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    marginLeft: 6,
                  }}
                  title="Mesh contour thickness on 2D slices (mm). Lower = thinner Freeview-style contour, higher = wider slab."
                >
                  <span style={{ color: 'var(--text-secondary)' }}>Contour</span>
                  <input
                    type="range"
                    min={0}
                    max={10}
                    step={0.5}
                    value={contourMm}
                    onChange={(e) => setContourMm(parseFloat(e.target.value))}
                    style={{ width: 90 }}
                  />
                  <span
                    style={{
                      fontVariantNumeric: 'tabular-nums',
                      color: 'var(--text-secondary)',
                      minWidth: 36,
                    }}
                  >
                    {contourMm.toFixed(1)}mm
                  </span>
                </span>
              )}
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  marginLeft: 6,
                }}
                title={
                  sliceType === 4
                    ? '3D zoom (volScaleMultiplier) — bypasses niivue\'s built-in [0.5, 2] clamp. Reset clears 2D + 3D.'
                    : '2D zoom — anchors on the crosshair. Buttons step ÷/× 1.5; slider is freeform. Reset re-centres.'
                }
              >
                <span style={{ color: 'var(--text-secondary)' }}>
                  Zoom {sliceType === 4 ? '(3D)' : '(2D)'}
                </span>
                <button
                  style={{ ...btn, padding: '2px 6px', fontSize: 11 }}
                  onClick={() => bumpZoom(1 / 1.5)}
                  title="Zoom out (÷1.5)"
                >
                  −
                </button>
                <input
                  type="range"
                  min={ZOOM_MIN}
                  max={ZOOM_MAX}
                  step={0.1}
                  value={activeZoom}
                  onChange={(e) => setActiveZoom(parseFloat(e.target.value))}
                  style={{ width: 110 }}
                />
                <button
                  style={{ ...btn, padding: '2px 6px', fontSize: 11 }}
                  onClick={() => bumpZoom(1.5)}
                  title="Zoom in (×1.5)"
                >
                  +
                </button>
                <span
                  style={{
                    fontVariantNumeric: 'tabular-nums',
                    color: 'var(--text-secondary)',
                    minWidth: 40,
                    textAlign: 'right',
                  }}
                >
                  {activeZoom.toFixed(2)}×
                </span>
                <button
                  style={{ ...btn, padding: '2px 6px', fontSize: 11 }}
                  onClick={resetZoom}
                  title="Reset zoom + pan"
                >
                  reset
                </button>
              </span>
              <span style={{ flex: 1 }} />
              <button
                style={{ ...btn, padding: '2px 8px', fontSize: 11 }}
                onClick={() => setShowViewer(false)}
                title="Close 3D viewer"
              >
                ✕ Close
              </button>
            </div>
            <div
              style={{
                position: 'relative',
                border: '1px solid var(--border)',
                borderTop: 'none',
                borderBottomLeftRadius: sliceType === 4 ? 4 : 0,
                borderBottomRightRadius: sliceType === 4 ? 4 : 0,
                background: '#000',
                overflow: 'hidden',
                flex: 1,
                minHeight: 0,
              }}
            >
              <canvas
                ref={canvasRef}
                style={{
                  width: '100%',
                  height: '100%',
                  display: 'block',
                }}
              />
              <canvas
                ref={overlayRef}
                style={{
                  position: 'absolute',
                  inset: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                  display:
                    contourMode === 'real' && sliceType !== 4 ? 'block' : 'none',
                }}
              />
            </div>
            {sliceType !== 4 && dimsXYZ && voxXYZ && (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  padding: '6px 10px',
                  border: '1px solid var(--border)',
                  borderTop: 'none',
                  borderBottomLeftRadius: 4,
                  borderBottomRightRadius: 4,
                  background: 'var(--bg-secondary)',
                  fontSize: 11,
                }}
              >
                {axesForSliceType(sliceType).map((axisIdx) => {
                  const label = (['Sagittal (X)', 'Coronal (Y)', 'Axial (Z)'] as const)[axisIdx]
                  return (
                    <div
                      key={axisIdx}
                      style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                    >
                      <span
                        style={{
                          color: 'var(--text-secondary)',
                          width: 92,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {label}
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={dimsXYZ[axisIdx] - 1}
                        step={1}
                        value={voxXYZ[axisIdx]}
                        onChange={(e) => setSlice(axisIdx, parseInt(e.target.value, 10))}
                        style={{ flex: 1 }}
                      />
                      <span
                        style={{
                          color: 'var(--text-secondary)',
                          fontVariantNumeric: 'tabular-nums',
                          minWidth: 64,
                          textAlign: 'right',
                        }}
                      >
                        {voxXYZ[axisIdx]} / {dimsXYZ[axisIdx] - 1}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
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
