/** Drawer inside the DAG modal: shows files in a node's work_dir.
 *
 * Renders each file based on its kind:
 *   - `view`    inline  (NIfTI → niivue, JSON / TSV / text → <pre>)
 *   - `pickle`  decoded JSON via /pickle endpoint
 *   - `link`    "Copy path" + a tool hint
 *
 * Crash files are surfaced inline as `<pre>` snippets fetched from the
 * generic file endpoint (we whitelist .txt).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Niivue } from '@niivue/niivue'

import {
  fetchNodeOutputs,
  fetchNodePickle,
  nodeFileUrl,
} from '../../api/node-outputs'
import type {
  NodeOutputFile,
  NodeOutputsList,
  NodePickleResponse,
} from '../../api/types'

const NIFTI_SUFFIXES = new Set(['.nii', '.gz', '.mgz'])
const TEXTY_SUFFIXES = new Set([
  '.json', '.tsv', '.csv', '.txt', '.log', '.cfg', '.rst', '.dat',
])
const IMAGE_SUFFIXES = new Set(['.svg', '.png', '.jpg', '.jpeg', '.gif'])
const HTML_SUFFIXES = new Set(['.html', '.htm'])


// ── styles ──────────────────────────────────────────────────────────────


const drawer: CSSProperties = {
  width: '40%',
  minWidth: 360,
  maxWidth: 560,
  borderLeft: '1px solid var(--border)',
  background: 'var(--bg-card)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const drawerHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 10px',
  borderBottom: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
}

const closeBtn: CSSProperties = {
  marginLeft: 'auto',
  padding: '2px 8px',
  fontSize: 11,
  border: '1px solid var(--border)',
  borderRadius: 4,
  background: 'var(--bg-secondary)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
}

const filesList: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '8px 10px',
}

const fileCard: CSSProperties = {
  border: '1px solid var(--border)',
  borderRadius: 4,
  marginBottom: 8,
  overflow: 'hidden',
  background: 'var(--bg-secondary)',
}

const fileHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 10px',
  fontSize: 11,
  fontWeight: 600,
  cursor: 'pointer',
  userSelect: 'none',
}

const fileBody: CSSProperties = {
  padding: 8,
  borderTop: '1px solid var(--border)',
  background: 'var(--bg-card)',
  fontSize: 11,
  maxHeight: 480,
  overflow: 'auto',
}

const preStyle: CSSProperties = {
  margin: 0,
  fontFamily: '"JetBrains Mono", monospace',
  fontSize: 11,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}


// ── helpers ─────────────────────────────────────────────────────────────


function _humanSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`
}


function _isNifti(suffix: string, name: string): boolean {
  if (suffix === '.nii' || suffix === '.mgz') return true
  // .gz alone — only count as NIfTI if .nii.gz
  return suffix === '.gz' && name.toLowerCase().endsWith('.nii.gz')
}


// ── individual file renderers ───────────────────────────────────────────


function NiivueFile(
  { url, name }: { url: string; name: string },
) {
  const ref = useRef<HTMLCanvasElement | null>(null)
  useEffect(() => {
    if (!ref.current) return
    const nv = new Niivue({ backColor: [0, 0, 0, 1] })
    nv.attachToCanvas(ref.current)
    nv.loadVolumes([{ url, name }]).catch((e) =>
      console.warn('niivue load failed', e),
    )
  }, [url, name])
  return (
    <div style={{ height: 320, background: '#000' }}>
      <canvas ref={ref} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}


function TextyFile({ url, name }: { url: string; name: string }) {
  const [body, setBody] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then((r) => r.text())
      .then((t) => { if (!cancelled) setBody(t) })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [url])
  if (error) {
    return <div style={{ color: 'var(--accent-red)' }}>{error}</div>
  }
  // Pretty-print JSON.
  let display = body
  if (name.toLowerCase().endsWith('.json')) {
    try {
      display = JSON.stringify(JSON.parse(body), null, 2)
    } catch {
      /* leave raw */
    }
  }
  return <pre style={preStyle}>{display}</pre>
}


function PickleFile(
  { runId, node, rel }: { runId: string; node: string; rel: string },
) {
  const [data, setData] = useState<NodePickleResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    fetchNodePickle(runId, node, rel)
      .then((r) => { if (!cancelled) setData(r) })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [runId, node, rel])
  if (error) return <div style={{ color: 'var(--accent-red)' }}>{error}</div>
  if (!data) return <div style={{ color: 'var(--text-secondary)' }}>loading…</div>
  if (data.error) {
    return (
      <div>
        <div style={{ color: 'var(--accent-yellow)', marginBottom: 6 }}>
          Could not decode pickle: {data.error}
        </div>
        <div style={{ color: 'var(--text-secondary)', fontSize: 10 }}>
          fmriprep's `result_*.pklz` files often reference paths
          inside the singularity container that don't exist on the
          host — that's fine, the file is still on disk.
        </div>
      </div>
    )
  }
  return (
    <pre style={preStyle}>
      {JSON.stringify(data.value, null, 2)}
    </pre>
  )
}


function LinkFile({ path }: { path: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <code style={{ fontSize: 10, flex: 1, wordBreak: 'break-all' }}>{path}</code>
      <button
        style={{
          ...closeBtn,
          marginLeft: 0,
        }}
        onClick={() => {
          navigator.clipboard.writeText(path)
            .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })
            .catch(() => { /* ignore */ })
        }}
      >
        {copied ? 'Copied!' : 'Copy path'}
      </button>
    </div>
  )
}


// ── main panel ──────────────────────────────────────────────────────────


function _bestRenderer(
  file: NodeOutputFile,
  url: string,
  fullPath: string,
  runId: string,
  node: string,
): React.ReactNode {
  if (_isNifti(file.suffix, file.name)) {
    return <NiivueFile url={url} name={file.name} />
  }
  if (TEXTY_SUFFIXES.has(file.suffix)) {
    return <TextyFile url={url} name={file.name} />
  }
  if (IMAGE_SUFFIXES.has(file.suffix)) {
    return (
      <img src={url} alt={file.name}
           style={{ maxWidth: '100%', display: 'block' }} />
    )
  }
  if (HTML_SUFFIXES.has(file.suffix)) {
    return (
      <iframe src={url} title={file.name}
              style={{ width: '100%', height: 360, border: 'none' }} />
    )
  }
  if (file.kind === 'pickle') {
    return <PickleFile runId={runId} node={node} rel={file.rel} />
  }
  return <LinkFile path={fullPath} />
}


interface Props {
  runId: string
  node: string | null
  leafDir?: string
  onClose: () => void
}


export function NodeOutputsPanel({ runId, node, onClose }: Props) {
  const [data, setData] = useState<NodeOutputsList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openFile, setOpenFile] = useState<string | null>(null)

  useEffect(() => {
    if (!node) return
    let cancelled = false
    setData(null)
    setError(null)
    setOpenFile(null)
    fetchNodeOutputs(runId, node)
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [runId, node])

  const files = useMemo(() => data?.files ?? [], [data])
  const crashes = useMemo(() => data?.crashes ?? [], [data])

  if (!node) return null

  return (
    <div style={drawer}>
      <div style={drawerHeader}>
        <div style={{ fontSize: 12, fontWeight: 700 }}>{node.split('.').pop()}</div>
        <code style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
          {node}
        </code>
        <button style={closeBtn} onClick={onClose}>Close</button>
      </div>

      {error && (
        <div style={{ padding: 10, color: 'var(--accent-red)', fontSize: 11 }}>
          {error}
        </div>
      )}

      {data && !data.exists && (
        <div style={{ padding: 10, color: 'var(--text-secondary)', fontSize: 11 }}>
          No work_dir on disk for this node ({data.leaf_dir}).
          fmriprep may have cached this step from a prior run, or
          the work tree was deleted.
        </div>
      )}

      {data && data.exists && files.length === 0 && crashes.length === 0 && (
        <div style={{ padding: 10, color: 'var(--text-secondary)', fontSize: 11 }}>
          The work_dir exists but no whitelisted files were found.
        </div>
      )}

      <div style={filesList}>
        {crashes.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div style={{
              fontSize: 10, color: 'var(--accent-red)', fontWeight: 700,
              textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6,
            }}>
              Crashes ({crashes.length})
            </div>
            {crashes.map((c) => (
              <div key={c.path} style={fileCard}>
                <div style={{ ...fileHeader, color: 'var(--accent-red)' }}>
                  {c.name}
                  <span style={{
                    flex: 1, color: 'var(--text-secondary)', fontWeight: 400,
                  }}>
                    {' '}{_humanSize(c.size)}
                  </span>
                </div>
                <div style={fileBody}>
                  <LinkFile path={c.path} />
                </div>
              </div>
            ))}
          </div>
        )}

        {files.map((f) => {
          const url = nodeFileUrl(runId, node, f.rel)
          const fullPath = `${data?.leaf_dir ?? ''}/${f.rel}`
          const isOpen = openFile === f.rel
          return (
            <div key={f.rel} style={fileCard}>
              <div
                style={fileHeader}
                onClick={() => setOpenFile(isOpen ? null : f.rel)}
              >
                <span>{isOpen ? '▼' : '▶'}</span>
                <span>{f.name}</span>
                <span style={{ flex: 1 }} />
                <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>
                  {f.suffix} · {_humanSize(f.size)} · {f.kind}
                </span>
              </div>
              {isOpen && (
                <div style={fileBody}>
                  {_bestRenderer(f, url, fullPath, runId, node)}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
