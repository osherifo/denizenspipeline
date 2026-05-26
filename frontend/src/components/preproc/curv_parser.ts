/**
 * Parse a FreeSurfer "new" curvature binary file (.curv / .curv.pial)
 * into a raw signed Float32Array — no normalisation, no inversion.
 *
 * Format:
 *   3 bytes   magic  0xFF 0xFF 0xFF
 *   int32 BE  nVertices
 *   int32 BE  nFaces
 *   int32 BE  valsPerVertex  (always 1 for .curv)
 *   nVertices × float32 BE   raw signed curvature
 */
export function parseFreeSurferCurv(buf: ArrayBuffer): Float32Array {
  const view = new DataView(buf)
  const b0 = view.getUint8(0)
  const b1 = view.getUint8(1)
  const b2 = view.getUint8(2)
  if (b0 !== 0xff || b1 !== 0xff || b2 !== 0xff) {
    throw new Error('Not a FreeSurfer new-format curvature file')
  }
  const nVertices = view.getInt32(3, false)
  // bytes 7–10: nFaces (unused), 11–14: valsPerVertex (unused)
  const headerBytes = 3 + 4 + 4 + 4 // 15
  const out = new Float32Array(nVertices)
  for (let i = 0; i < nVertices; i++) {
    out[i] = view.getFloat32(headerBytes + i * 4, false)
  }
  return out
}
