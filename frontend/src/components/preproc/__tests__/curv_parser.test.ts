import { describe, it, expect } from 'vitest'
import { parseFreeSurferCurv } from '../curv_parser'

function buildCurvBuffer(values: number[]): ArrayBuffer {
  const headerSize = 3 + 4 + 4 + 4 // magic + nVert + nFace + valsPerVert
  const buf = new ArrayBuffer(headerSize + values.length * 4)
  const view = new DataView(buf)
  // Magic bytes
  view.setUint8(0, 0xff)
  view.setUint8(1, 0xff)
  view.setUint8(2, 0xff)
  // nVertices (big-endian)
  view.setInt32(3, values.length, false)
  // nFaces (unused, set to 0)
  view.setInt32(7, 0, false)
  // valsPerVertex (always 1)
  view.setInt32(11, 1, false)
  // Per-vertex float32 values (big-endian)
  for (let i = 0; i < values.length; i++) {
    view.setFloat32(headerSize + i * 4, values[i], false)
  }
  return buf
}

describe('parseFreeSurferCurv', () => {
  it('parses a minimal .curv buffer with known values', () => {
    const expected = [0.25, -0.5, 0.0, 1.0, -1.0]
    const buf = buildCurvBuffer(expected)
    const result = parseFreeSurferCurv(buf)
    expect(result).toBeInstanceOf(Float32Array)
    expect(result.length).toBe(expected.length)
    for (let i = 0; i < expected.length; i++) {
      expect(result[i]).toBeCloseTo(expected[i], 5)
    }
  })

  it('preserves signed values (no normalisation or inversion)', () => {
    const vals = [-0.3, 0.7, -0.001, 0.999]
    const result = parseFreeSurferCurv(buildCurvBuffer(vals))
    expect(result[0]).toBeCloseTo(-0.3, 5)
    expect(result[1]).toBeCloseTo(0.7, 5)
    expect(result[2]).toBeCloseTo(-0.001, 5)
    expect(result[3]).toBeCloseTo(0.999, 5)
  })

  it('handles an empty vertex array', () => {
    const result = parseFreeSurferCurv(buildCurvBuffer([]))
    expect(result.length).toBe(0)
  })

  it('rejects buffers without the magic bytes', () => {
    const buf = new ArrayBuffer(15)
    const view = new DataView(buf)
    view.setUint8(0, 0x00)
    view.setUint8(1, 0x00)
    view.setUint8(2, 0x00)
    expect(() => parseFreeSurferCurv(buf)).toThrow('Not a FreeSurfer')
  })
})
