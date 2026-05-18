/** MeshContourIndex unit tests: plane-triangle intersection math. */

import { describe, it, expect } from 'vitest'
import { MeshContourIndex, axCorSagToAxis } from '../contourRenderer'

describe('axCorSagToAxis', () => {
  it('maps niivue axCorSag to pts-axis indices', () => {
    expect(axCorSagToAxis(0)).toBe(2) // axial → z
    expect(axCorSagToAxis(1)).toBe(1) // coronal → y
    expect(axCorSagToAxis(2)).toBe(0) // sagittal → x
    expect(axCorSagToAxis(3)).toBeNull()
    expect(axCorSagToAxis(4)).toBeNull() // 3D render tile
  })
})

describe('MeshContourIndex', () => {
  // Single triangle in the z=0..1 strip; an axial slice at z=0.5
  // should cut it on edges (0→2) and (1→2) only — edge (0→1) is
  // both below the plane.
  //   v0 = (0, 0, 0)
  //   v1 = (2, 0, 0)
  //   v2 = (1, 2, 1)
  it('returns the two crossings of a single triangle for an axial slice', () => {
    const pts = new Float32Array([0, 0, 0, 2, 0, 0, 1, 2, 1])
    const tris = new Uint32Array([0, 1, 2])
    const index = new MeshContourIndex(pts, tris)

    const segs = index.intersect(2, 0.5)
    expect(segs.length).toBe(4) // exactly one segment, 4 floats

    // Linearly interp at z=0.5 (halfway up v2's z):
    //   v0→v2 at t=0.5 → (0.5, 1, 0.5)        → in-plane (x=0.5, y=1)
    //   v1→v2 at t=0.5 → (1.5, 1, 0.5)        → in-plane (x=1.5, y=1)
    const xs = [segs[0], segs[2]].sort((a, b) => a - b)
    const ys = [segs[1], segs[3]]
    expect(xs[0]).toBeCloseTo(0.5)
    expect(xs[1]).toBeCloseTo(1.5)
    expect(ys[0]).toBeCloseTo(1)
    expect(ys[1]).toBeCloseTo(1)
  })

  it('returns no crossings when the plane misses the triangle', () => {
    const pts = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0])
    const tris = new Uint32Array([0, 1, 2])
    const index = new MeshContourIndex(pts, tris)
    // Triangle lives at z=0; slice at z=5 doesn't intersect.
    expect(index.intersect(2, 5).length).toBe(0)
  })

  it('works for coronal (y) and sagittal (x) axes — in-plane axes flip', () => {
    // A unit tetrahedron-ish triangle from (0,0,0) to (1,1,1)-ish.
    //   v0 = (0, 0, 0)
    //   v1 = (1, 0, 0)
    //   v2 = (0, 1, 1)
    const pts = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 1])
    const tris = new Uint32Array([0, 1, 2])
    const index = new MeshContourIndex(pts, tris)

    // Coronal slice at y=0.5: edges v0→v2 (y 0→1) and v1→v2 (y 0→1)
    // straddle. In-plane axes for coronal are (x, z).
    const cor = index.intersect(1, 0.5)
    expect(cor.length).toBe(4)
    // v0→v2 at t=0.5 → (0, 0.5, 0.5) → (u=x=0, v=z=0.5)
    // v1→v2 at t=0.5 → (0.5, 0.5, 0.5) → (u=x=0.5, v=z=0.5)
    const corXs = [cor[0], cor[2]].sort((a, b) => a - b)
    expect(corXs[0]).toBeCloseTo(0)
    expect(corXs[1]).toBeCloseTo(0.5)
    expect(cor[1]).toBeCloseTo(0.5)
    expect(cor[3]).toBeCloseTo(0.5)

    // Sagittal slice at x=0.5: edges v0→v1 (x 0→1) and v1→v2 (x 1→0)
    // straddle. In-plane axes for sagittal are (y, z).
    const sag = index.intersect(0, 0.5)
    expect(sag.length).toBe(4)
    // v0→v1 at t=0.5 → (0.5, 0, 0) → (u=y=0, v=z=0)
    // v1→v2 at t=0.5 → (0.5, 0.5, 0.5) → (u=y=0.5, v=z=0.5)
    const sagPairs = [
      [sag[0], sag[1]],
      [sag[2], sag[3]],
    ].sort((a, b) => a[0] - b[0])
    expect(sagPairs[0][0]).toBeCloseTo(0)
    expect(sagPairs[0][1]).toBeCloseTo(0)
    expect(sagPairs[1][0]).toBeCloseTo(0.5)
    expect(sagPairs[1][1]).toBeCloseTo(0.5)
  })

  it('skips degenerate edge-on intersections', () => {
    // Triangle lying flat in the slice plane.
    const pts = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0])
    const tris = new Uint32Array([0, 1, 2])
    const index = new MeshContourIndex(pts, tris)
    // Slice exactly at z=0: every edge has both endpoints AT the
    // plane, so da*db=0 (not <0) — no crossings counted.
    expect(index.intersect(2, 0).length).toBe(0)
  })
})
