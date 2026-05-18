/**
 * True polyline contour computation: plane × triangle intersection.
 *
 * Drop-in replacement for niivue's `setMeshThicknessOn2D` slab clipping
 * when we want Freeview-style 1-pixel contours instead of a 3D-mesh slab
 * projected onto the slice. The shape is "for each triangle that the
 * slice plane cuts, compute the two edge-crossings and connect them" —
 * the union is the contour.
 *
 * Coordinate convention (matches niivue with `setSliceMM(true)`, i.e.
 * RAS world space):
 *   axisIdx = 0 → sagittal (slice plane x = const, in-plane = (y, z))
 *   axisIdx = 1 → coronal  (slice plane y = const, in-plane = (x, z))
 *   axisIdx = 2 → axial    (slice plane z = const, in-plane = (x, y))
 *
 * The bin index buckets triangles by the slice-axis range they span, so
 * each query touches only the triangles whose bounding box straddles the
 * plane — ~100x speedup over brute force on a ~150k-triangle hemisphere
 * mesh in practice. Built once per mesh (Float32Array `pts`,
 * Uint32Array `tris`), queried per slice change.
 */

export type SliceAxis = 0 | 1 | 2

const BIN_WIDTH_MM = 2

interface AxisIndex {
  axisMin: number
  bins: Uint32Array[]
}

export class MeshContourIndex {
  private indexes: AxisIndex[] = []

  constructor(
    public readonly pts: Float32Array,
    public readonly tris: Uint32Array,
  ) {
    for (let axis = 0 as SliceAxis; axis < 3; axis = (axis + 1) as SliceAxis) {
      this.indexes[axis] = this.buildAxis(axis)
    }
  }

  private buildAxis(axis: SliceAxis): AxisIndex {
    const { pts, tris } = this
    const nTris = tris.length / 3
    let axisMin = Infinity
    let axisMax = -Infinity
    for (let t = 0; t < nTris; t++) {
      const a = tris[t * 3] * 3
      const b = tris[t * 3 + 1] * 3
      const c = tris[t * 3 + 2] * 3
      const va = pts[a + axis], vb = pts[b + axis], vc = pts[c + axis]
      const lo = va < vb ? (va < vc ? va : vc) : (vb < vc ? vb : vc)
      const hi = va > vb ? (va > vc ? va : vc) : (vb > vc ? vb : vc)
      if (lo < axisMin) axisMin = lo
      if (hi > axisMax) axisMax = hi
    }
    const nBins = Math.max(1, Math.ceil((axisMax - axisMin) / BIN_WIDTH_MM) + 1)
    // Two-pass bin fill so each bin array is exactly sized (no resizes).
    const counts = new Uint32Array(nBins)
    for (let t = 0; t < nTris; t++) {
      const a = tris[t * 3] * 3
      const b = tris[t * 3 + 1] * 3
      const c = tris[t * 3 + 2] * 3
      const va = pts[a + axis], vb = pts[b + axis], vc = pts[c + axis]
      const lo = va < vb ? (va < vc ? va : vc) : (vb < vc ? vb : vc)
      const hi = va > vb ? (va > vc ? va : vc) : (vb > vc ? vb : vc)
      const binLo = Math.max(0, Math.floor((lo - axisMin) / BIN_WIDTH_MM))
      const binHi = Math.min(nBins - 1, Math.floor((hi - axisMin) / BIN_WIDTH_MM))
      for (let i = binLo; i <= binHi; i++) counts[i]++
    }
    const bins: Uint32Array[] = []
    for (let i = 0; i < nBins; i++) bins.push(new Uint32Array(counts[i]))
    const cursors = new Uint32Array(nBins)
    for (let t = 0; t < nTris; t++) {
      const a = tris[t * 3] * 3
      const b = tris[t * 3 + 1] * 3
      const c = tris[t * 3 + 2] * 3
      const va = pts[a + axis], vb = pts[b + axis], vc = pts[c + axis]
      const lo = va < vb ? (va < vc ? va : vc) : (vb < vc ? vb : vc)
      const hi = va > vb ? (va > vc ? va : vc) : (vb > vc ? vb : vc)
      const binLo = Math.max(0, Math.floor((lo - axisMin) / BIN_WIDTH_MM))
      const binHi = Math.min(nBins - 1, Math.floor((hi - axisMin) / BIN_WIDTH_MM))
      for (let i = binLo; i <= binHi; i++) {
        bins[i][cursors[i]++] = t
      }
    }
    return { axisMin, bins }
  }

  /**
   * Returns line segments where the plane `axis == sliceMM` cuts the
   * mesh, packed as `[u1, v1, u2, v2, ...]` Float32Array in the
   * **in-plane mm** coordinate system. The caller projects to pixels.
   */
  intersect(axis: SliceAxis, sliceMM: number): Float32Array {
    const idx = this.indexes[axis]
    const bin = Math.floor((sliceMM - idx.axisMin) / BIN_WIDTH_MM)
    if (bin < 0 || bin >= idx.bins.length) return new Float32Array(0)
    const candidates = idx.bins[bin]
    const { pts, tris } = this
    const out = new Float32Array(candidates.length * 4)
    // In-plane (u, v) axes — the two pts dimensions other than `axis`.
    const uIdx: SliceAxis = axis === 0 ? 1 : 0
    const vIdx: SliceAxis = axis === 2 ? 1 : 2
    let nOut = 0
    for (let ci = 0; ci < candidates.length; ci++) {
      const t = candidates[ci]
      const a = tris[t * 3] * 3
      const b = tris[t * 3 + 1] * 3
      const c = tris[t * 3 + 2] * 3
      const da = pts[a + axis] - sliceMM
      const db = pts[b + axis] - sliceMM
      const dc = pts[c + axis] - sliceMM
      let n = 0
      let u1 = 0, v1 = 0, u2 = 0, v2 = 0
      // For each edge that straddles the plane, linearly interpolate
      // the crossing point. A triangle crossed by a plane yields
      // exactly two crossings in the generic case (zero or one are
      // edge-on degenerate; we skip those).
      if (da * db < 0) {
        const f = da / (da - db)
        u1 = pts[a + uIdx] + f * (pts[b + uIdx] - pts[a + uIdx])
        v1 = pts[a + vIdx] + f * (pts[b + vIdx] - pts[a + vIdx])
        n++
      }
      if (db * dc < 0) {
        const f = db / (db - dc)
        const u = pts[b + uIdx] + f * (pts[c + uIdx] - pts[b + uIdx])
        const v = pts[b + vIdx] + f * (pts[c + vIdx] - pts[b + vIdx])
        if (n === 0) { u1 = u; v1 = v } else { u2 = u; v2 = v }
        n++
      }
      if (n < 2 && dc * da < 0) {
        const f = dc / (dc - da)
        const u = pts[c + uIdx] + f * (pts[a + uIdx] - pts[c + uIdx])
        const v = pts[c + vIdx] + f * (pts[a + vIdx] - pts[c + vIdx])
        if (n === 0) { u1 = u; v1 = v } else { u2 = u; v2 = v }
        n++
      }
      if (n === 2) {
        out[nOut++] = u1
        out[nOut++] = v1
        out[nOut++] = u2
        out[nOut++] = v2
      }
    }
    return out.subarray(0, nOut)
  }
}

/**
 * Map niivue's `axCorSag` (0=axial, 1=coronal, 2=sagittal) to the
 * pts-axis convention used by `MeshContourIndex` (0=x, 1=y, 2=z).
 *   axCorSag 0 (axial)    → slice axis z = 2
 *   axCorSag 1 (coronal)  → slice axis y = 1
 *   axCorSag 2 (sagittal) → slice axis x = 0
 */
export function axCorSagToAxis(axCorSag: number): SliceAxis | null {
  if (axCorSag === 0) return 2
  if (axCorSag === 1) return 1
  if (axCorSag === 2) return 0
  return null
}
