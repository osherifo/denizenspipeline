/** Drawer inside AnalysisGraphModal — shows source code + outputs for
 *  the selected plugin node.
 *
 *  Tabs:
 *    - source   plugin .py file (read-only)
 *    - outputs  files attributable to this plugin in the run dir
 *    - params   the config block the plugin received (JSON pretty-printed)
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import Editor from '@monaco-editor/react'

import {
  fetchLogTail,
  fetchNodeOutputs,
  fetchNodeSource,
  isConfigPreview,
  isLiveTarget,
  nodeFileUrl,
  targetSupportsLog,
  type GraphTarget,
  type LogTailResponse,
  type NodeOutputFile,
  type NodeOutputsResponse,
  type NodeSourceResponse,
  type RunGraphNode,
} from '../../api/run-graph'


const NIFTI_SUFFIXES = new Set(['.nii', '.gz', '.mgz'])
const TEXTY_SUFFIXES = new Set(['.json', '.tsv', '.csv', '.txt', '.log'])
const IMAGE_SUFFIXES = new Set(['.svg', '.png', '.jpg', '.jpeg', '.gif'])
const HTML_SUFFIXES = new Set(['.html', '.htm'])


type Tab = 'source' | 'outputs' | 'params' | 'log'


const drawer: CSSProperties = {
  width: '45%',
  minWidth: 380,
  maxWidth: 720,
  borderLeft: '1px solid var(--border)',
  background: 'var(--bg-card)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const headerStyle: CSSProperties = {
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

const tabBar: CSSProperties = {
  display: 'flex',
  borderBottom: '1px solid var(--border)',
  background: 'var(--bg-secondary)',
}

function tabBtn(active: boolean): CSSProperties {
  return {
    flex: 1,
    padding: '6px 8px',
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    border: 'none',
    background: 'transparent',
    color: active ? 'var(--accent-cyan)' : 'var(--text-secondary)',
    borderBottom: active ? '2px solid var(--accent-cyan)' : '2px solid transparent',
    cursor: 'pointer',
    fontFamily: 'inherit',
  }
}

const body: CSSProperties = {
  flex: 1,
  overflow: 'auto',
}

const preStyle: CSSProperties = {
  margin: 0,
  padding: '10px 12px',
  fontFamily: '"JetBrains Mono", monospace',
  fontSize: 11,
  whiteSpace: 'pre',
  color: 'var(--text-primary)',
  background: 'var(--bg-card)',
}


function _human(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`
}


function _isNifti(suffix: string, name: string): boolean {
  if (suffix === '.nii' || suffix === '.mgz') return true
  return suffix === '.gz' && name.toLowerCase().endsWith('.nii.gz')
}


interface Props {
  target: GraphTarget
  node: RunGraphNode
  onClose: () => void
}


export function AnalysisNodePanel({ target, node, onClose }: Props) {
  // For a config preview, outputs don't exist; fall back to params
  // instead when no source is registered.
  const previewOnly = isConfigPreview(target)
  const live = isLiveTarget(target)
  const supportsLog = targetSupportsLog(target)
  const _defaultTab = (): Tab =>
    node.source_path ? 'source' : (previewOnly ? 'params' : 'outputs')
  const [tab, setTab] = useState<Tab>(_defaultTab)
  const [source, setSource] = useState<NodeSourceResponse | null>(null)
  const [outputs, setOutputs] = useState<NodeOutputsResponse | null>(null)
  const [log, setLog] = useState<LogTailResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openFile, setOpenFile] = useState<string | null>(null)

  // Reset state when switching nodes.
  useEffect(() => {
    setSource(null)
    setOutputs(null)
    setLog(null)
    setError(null)
    setOpenFile(null)
    setTab(_defaultTab())
  }, [node.id])

  useEffect(() => {
    let cancelled = false
    if (tab === 'source' && node.source_path && !source) {
      fetchNodeSource(target, node.id)
        .then((s) => { if (!cancelled) setSource(s) })
        .catch((e) => { if (!cancelled) setError(String(e)) })
    } else if (tab === 'outputs' && !outputs) {
      fetchNodeOutputs(target, node.id)
        .then((o) => { if (!cancelled) setOutputs(o) })
        .catch((e) => { if (!cancelled) setError(String(e)) })
    }
    return () => { cancelled = true }
  }, [tab, node.id])

  // Log tab — polls every 2s while the run is live.
  useEffect(() => {
    if (tab !== 'log' || !supportsLog) return
    let cancelled = false
    let timer: number | null = null
    async function load() {
      try {
        const r = await fetchLogTail(target)
        if (cancelled || r === null) return
        setLog(r)
        if (live) timer = window.setTimeout(load, 2000)
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    }
    load()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [tab, node.id, supportsLog, live])

  const paramsText = useMemo(
    () => JSON.stringify(node.params ?? {}, null, 2),
    [node],
  )

  return (
    <div style={drawer}>
      <div style={headerStyle}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700 }}>{node.label}</div>
          <div style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
            {node.kind.replace('_', ' ')} · {node.stage}
          </div>
        </div>
        <button style={closeBtn} onClick={onClose} aria-label="Close panel">→</button>
      </div>

      <div style={tabBar}>
        <button
          style={tabBtn(tab === 'source')}
          onClick={() => setTab('source')}
          disabled={!node.source_path}
          title={node.source_path ?? 'no source registered'}
        >
          Source
        </button>
        {!isConfigPreview(target) && (
          <button style={tabBtn(tab === 'outputs')} onClick={() => setTab('outputs')}>
            Outputs
          </button>
        )}
        <button style={tabBtn(tab === 'params')} onClick={() => setTab('params')}>
          Params
        </button>
        {supportsLog && (
          <button style={tabBtn(tab === 'log')} onClick={() => setTab('log')}>
            Log
          </button>
        )}
      </div>

      <div style={body}>
        {error && (
          <div style={{ padding: 12, color: 'var(--accent-red)', fontSize: 11 }}>
            {error}
          </div>
        )}

        {tab === 'source' && (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {!node.source_path && (
              <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
                No source file registered for this node.
              </div>
            )}
            {node.source_path && !source && !error && (
              <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
                Loading…
              </div>
            )}
            {source && (
              <>
                <div style={{
                  padding: '4px 10px', fontSize: 9, color: 'var(--text-secondary)',
                  background: 'var(--bg-secondary)', wordBreak: 'break-all',
                  flex: '0 0 auto',
                }}>
                  {source.path}
                </div>
                <div style={{ flex: 1, minHeight: 0 }}>
                  <Editor
                    height="100%"
                    language={source.language === 'python' ? 'python' : 'plaintext'}
                    theme="vs-dark"
                    value={source.text}
                    options={{
                      readOnly: true,
                      domReadOnly: true,
                      minimap: { enabled: false },
                      fontSize: 12,
                      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                      lineNumbers: 'on',
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      renderLineHighlight: 'none',
                      contextmenu: false,
                      padding: { top: 8 },
                    }}
                  />
                </div>
              </>
            )}
          </div>
        )}

        {tab === 'outputs' && (
          <>
            {!outputs && !error && (
              <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
                Loading…
              </div>
            )}
            {outputs && outputs.files.length === 0 && (
              <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
                No output files attributed to this node.
                <div style={{ fontSize: 9, marginTop: 6, opacity: 0.7 }}>
                  Plugins outside the report stage usually leave their
                  state in the pipeline context, not on disk. Open the
                  Source tab to see what this plugin does.
                </div>
              </div>
            )}
            {outputs && outputs.files.map((f) => (
              <FileRow
                key={f.rel}
                file={f}
                url={nodeFileUrl(target, node.id, f.rel)}
                open={openFile === f.rel}
                onToggle={() => setOpenFile(openFile === f.rel ? null : f.rel)}
              />
            ))}
            {outputs && (
              <div style={{ padding: 8, fontSize: 9, color: 'var(--text-secondary)' }}>
                <code style={{ wordBreak: 'break-all' }}>{outputs.output_dir}</code>
              </div>
            )}
          </>
        )}

        {tab === 'params' && (
          <pre style={preStyle}>{paramsText}</pre>
        )}

        {tab === 'log' && (
          <>
            {!log && !error && (
              <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
                Loading log…
              </div>
            )}
            {log && (
              <>
                <div style={{
                  padding: '4px 10px', fontSize: 9,
                  color: 'var(--text-secondary)',
                  background: 'var(--bg-secondary)',
                  wordBreak: 'break-all',
                  flex: '0 0 auto',
                }}>
                  {log.log_path || '(no log path)'}
                  {live && (
                    <span style={{
                      marginLeft: 8, color: 'var(--accent-cyan)', fontWeight: 700,
                    }}>
                      ● tailing
                    </span>
                  )}
                </div>
                <pre style={{
                  ...preStyle,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}>
                  {log.log_tail || '(log empty — the subprocess may not have written anything yet)'}
                </pre>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}


function FileRow({
  file, url, open, onToggle,
}: { file: NodeOutputFile; url: string; open: boolean; onToggle: () => void }) {
  return (
    <div style={{
      borderBottom: '1px solid var(--border)',
      background: open ? 'var(--bg-secondary)' : 'transparent',
    }}>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 12px', fontSize: 11, fontWeight: 600,
          cursor: 'pointer', userSelect: 'none',
        }}
      >
        <span>{open ? '▼' : '▶'}</span>
        <span style={{ flex: 1 }}>{file.name}</span>
        <span style={{ fontSize: 9, color: 'var(--text-secondary)', fontWeight: 400 }}>
          {file.suffix} · {_human(file.size)}
        </span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          style={{ fontSize: 10, color: 'var(--accent-cyan)', textDecoration: 'none', fontWeight: 600 }}
        >
          open
        </a>
      </div>
      {open && (
        <div style={{ padding: 10 }}>
          <FilePreview file={file} url={url} />
        </div>
      )}
    </div>
  )
}


function FilePreview({ file, url }: { file: NodeOutputFile; url: string }) {
  if (IMAGE_SUFFIXES.has(file.suffix)) {
    return <img src={url} alt={file.name} style={{ maxWidth: '100%', display: 'block' }} />
  }
  if (HTML_SUFFIXES.has(file.suffix)) {
    return (
      <iframe src={url} title={file.name}
              style={{ width: '100%', height: 400, border: '1px solid var(--border)', borderRadius: 4 }} />
    )
  }
  if (TEXTY_SUFFIXES.has(file.suffix)) {
    return <TextyPreview url={url} name={file.name} />
  }
  if (_isNifti(file.suffix, file.name)) {
    return (
      <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
        NIfTI volume — <a href={url} style={{ color: 'var(--accent-cyan)' }}>download</a>
      </div>
    )
  }
  return (
    <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
      Binary file —{' '}
      <a href={url} style={{ color: 'var(--accent-cyan)' }}>download</a>
    </div>
  )
}


function TextyPreview({ url, name }: { url: string; name: string }) {
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
  if (error) return <div style={{ color: 'var(--accent-red)', fontSize: 11 }}>{error}</div>
  let display = body
  if (name.toLowerCase().endsWith('.json')) {
    try { display = JSON.stringify(JSON.parse(body), null, 2) } catch { /* leave raw */ }
  }
  return (
    <pre style={{
      ...preStyle, padding: 0, maxHeight: 400, overflow: 'auto',
      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    }}>{display}</pre>
  )
}
