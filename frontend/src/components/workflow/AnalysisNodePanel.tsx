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

import { useThemeStore } from '../../stores/theme-store'
import {
  fetchLogTail,
  fetchNodeOutputs,
  fetchNodeSource,
  fetchQaArtifacts,
  isConfigPreview,
  isLiveTarget,
  nodeFileUrl,
  qaFileUrl,
  QA_STAGES,
  regenerateQa,
  targetSupportsLog,
  targetSupportsQa,
  type GraphTarget,
  type LogTailResponse,
  type NodeOutputFile,
  type NodeOutputsResponse,
  type NodeSourceResponse,
  type QaArtifactsResponse,
  type QaFile,
  type RunGraphNode,
} from '../../api/run-graph'


const NIFTI_SUFFIXES = new Set(['.nii', '.gz', '.mgz'])
const TEXTY_SUFFIXES = new Set(['.json', '.tsv', '.csv', '.txt', '.log'])
const IMAGE_SUFFIXES = new Set(['.svg', '.png', '.jpg', '.jpeg', '.gif'])
const HTML_SUFFIXES = new Set(['.html', '.htm'])


type Tab = 'source' | 'outputs' | 'params' | 'log' | 'qa'


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

// Source tab when the node has no source file on this system — still
// clickable (so the reason is reachable) but visibly "unavailable".
const unavailableTabBtn: CSSProperties = {
  color: 'var(--accent-yellow, #ffb86c)',
  opacity: 0.85,
}

const noSourceNotice: CSSProperties = {
  margin: 10,
  padding: '10px 12px',
  fontSize: 11,
  lineHeight: 1.5,
  color: 'var(--accent-yellow, #ffb86c)',
  background: 'rgba(255, 184, 108, 0.10)',
  border: '1px solid var(--accent-yellow, #ffb86c)',
  borderRadius: 6,
}

const linkStyle: CSSProperties = { color: 'inherit', textDecoration: 'underline' }

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
  /** Merged onto the drawer's root style — used by the parent to drive a
   *  drag-resizable width that overrides the default percentage. */
  style?: CSSProperties
}


export function AnalysisNodePanel({ target, node, onClose, style }: Props) {
  // Monaco ships its own themes; follow the app theme.
  const monacoTheme = useThemeStore((s) => s.mode) === 'light' ? 'light' : 'vs-dark'
  // For a config preview, outputs don't exist; fall back to params
  // instead when no source is registered.
  const previewOnly = isConfigPreview(target)
  const live = isLiveTarget(target)
  const supportsLog = targetSupportsLog(target)
  const supportsQa = targetSupportsQa(target) && QA_STAGES.has(node.stage)
  const _defaultTab = (): Tab =>
    node.source_path ? 'source' : (previewOnly ? 'params' : 'outputs')
  const [tab, setTab] = useState<Tab>(_defaultTab)
  const [source, setSource] = useState<NodeSourceResponse | null>(null)
  const [outputs, setOutputs] = useState<NodeOutputsResponse | null>(null)
  const [log, setLog] = useState<LogTailResponse | null>(null)
  const [qa, setQa] = useState<QaArtifactsResponse | null>(null)
  const [qaBusy, setQaBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openFile, setOpenFile] = useState<string | null>(null)

  // A stable string key for the active target — drilldowns swap the
  // panel's target prop while node.id may stay the same (e.g. same
  // stage key in two scopes), so reset/refetch effects key off this
  // instead of the object identity.
  const targetKey = JSON.stringify(target)

  // Reset state when switching nodes or when the target changes.
  useEffect(() => {
    setSource(null)
    setOutputs(null)
    setLog(null)
    setQa(null)
    setError(null)
    setOpenFile(null)
    setTab(_defaultTab())
  }, [node.id, targetKey])

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
  }, [tab, node.id, targetKey])

  // QA tab — fetch once when activated, and re-poll every 3 s while
  // the target is live so newly-finished stages light up. Stop polling
  // immediately when we learn the stage has no registered plugins —
  // there's nothing for further polls to discover.
  useEffect(() => {
    if (tab !== 'qa' || !supportsQa) return
    let cancelled = false
    let timer: number | null = null
    async function load() {
      try {
        const r = await fetchQaArtifacts(target, node.stage)
        if (cancelled) return
        setQa(r)
        const noPlugins = (r.registered_plugins?.length ?? 0) === 0
        if (live && !noPlugins) timer = window.setTimeout(load, 3000)
      } catch (e) {
        if (cancelled) return
        setError(String(e))
      }
    }
    load()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [tab, node.id, node.stage, supportsQa, live, targetKey])

  const handleRegenerateQa = async () => {
    setQaBusy(true)
    setError(null)
    try {
      const r = await regenerateQa(target, node.stage)
      setQa(r)
    } catch (e) {
      setError(String(e))
    } finally {
      setQaBusy(false)
    }
  }

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
  }, [tab, node.id, supportsLog, live, targetKey])

  const paramsText = useMemo(
    () => JSON.stringify(node.params ?? {}, null, 2),
    [node],
  )

  return (
    <div style={{ ...drawer, ...style }}>
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
        {/* Not disabled when there's no source: a disabled tab makes the click
            do nothing with no explanation. Keep it selectable so the panel can
            say *why* there's nothing to show. */}
        <button
          style={{
            ...tabBtn(tab === 'source'),
            ...(node.source_path ? {} : unavailableTabBtn),
          }}
          onClick={() => setTab('source')}
          title={node.source_path ?? 'No source available — open for details'}
        >
          Source{node.source_path ? '' : ' ⚠'}
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
        {supportsQa && (
          <button style={tabBtn(tab === 'qa')} onClick={() => setTab('qa')}>
            QA
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
              <div style={noSourceNotice}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>
                  ⚠ No source available for “{node.label ?? node.id}”.
                </div>
                <div style={{ marginBottom: 6 }}>
                  This node has no source file registered on <em>this</em> system, so
                  there's nothing to display. Usually one of:
                </div>
                <ul style={{ margin: '0 0 8px 16px', padding: 0, lineHeight: 1.6 }}>
                  <li>
                    the plugin it names <strong>isn't installed here</strong> — install it
                    from the <a href="#hub" style={linkStyle}>Hub</a>, or author it in the{' '}
                    <a href="#editor" style={linkStyle}>module editor</a>;
                  </li>
                  <li>
                    it's a structural node (a stage/group container) that has no
                    implementation file of its own.
                  </li>
                </ul>
                <div style={{ color: 'var(--text-secondary)' }}>
                  The <strong>Params</strong> tab still shows how this node is configured.
                </div>
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
                    theme={monacoTheme}
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

        {tab === 'qa' && (
          <QaTab
            target={target}
            stage={node.stage}
            qa={qa}
            busy={qaBusy}
            onRegenerate={handleRegenerateQa}
          />
        )}
      </div>
    </div>
  )
}


function QaTab({
  target, stage, qa, busy, onRegenerate,
}: {
  target: GraphTarget
  stage: string
  qa: QaArtifactsResponse | null
  busy: boolean
  onRegenerate: () => void
}) {
  const [openFile, setOpenFile] = useState<string | null>(null)
  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border)',
        fontSize: 10, color: 'var(--text-secondary)',
      }}>
        <span>QA · stage <code>{stage}</code></span>
        <button
          onClick={onRegenerate}
          disabled={busy}
          style={{
            marginLeft: 'auto', padding: '3px 10px', fontSize: 10,
            fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5,
            border: '1px solid var(--border)', borderRadius: 4,
            background: busy ? 'transparent' : 'var(--accent-cyan)',
            color: busy ? 'var(--text-secondary)' : 'var(--on-accent)',
            cursor: busy ? 'wait' : 'pointer',
            fontFamily: 'inherit',
          }}
          title="Reload the stage intermediate and re-render every QA plugin"
        >
          {busy ? 'Regenerating…' : '↻ Regenerate'}
        </button>
      </div>
      {!qa && !busy && (
        <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
          Loading…
        </div>
      )}
      {qa && qa.registered_plugins.length === 0 && (
        <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
          No QA plugins are registered for the <code>{stage}</code> stage
          in this build. Built-ins ship for <code>prepare</code> and{' '}
          <code>model</code> today; the rest land in Phase 3.
        </div>
      )}
      {qa && qa.registered_plugins.length > 0 && qa.plugins.length === 0 && (
        <div style={{ padding: 12, color: 'var(--text-secondary)', fontSize: 11 }}>
          No QA artifacts on disk yet for <code>{stage}</code>. Either the
          stage hasn't finished, or the run didn't have{' '}
          <code>qa.enabled: true</code>. Click <strong>Regenerate</strong>{' '}
          if an <code>intermediates/{stage}.joblib*</code> exists.
          <div style={{ marginTop: 6, opacity: 0.8 }}>
            Expected plugins: {qa.registered_plugins.join(', ')}
          </div>
        </div>
      )}
      {qa && qa.plugins.map((plugin) => (
        <div key={plugin.name} style={{
          borderBottom: '1px solid var(--border)',
        }}>
          <div style={{
            padding: '6px 12px', fontSize: 11, fontWeight: 700,
            color: 'var(--accent-cyan)', letterSpacing: 0.3,
            background: 'var(--bg-secondary)',
          }}>
            {plugin.name}
          </div>
          {plugin.files.map((f) => (
            <QaFileRow
              key={f.rel}
              file={f}
              url={qaFileUrl(target, stage, f.rel)}
              open={openFile === f.rel}
              onToggle={() => setOpenFile(openFile === f.rel ? null : f.rel)}
            />
          ))}
        </div>
      ))}
      {qa && qa.plugins.length > 0 && (
        <div style={{ padding: 8, fontSize: 9, color: 'var(--text-secondary)' }}>
          <code style={{ wordBreak: 'break-all' }}>{qa.qa_dir}</code>
        </div>
      )}
    </div>
  )
}


function QaFileRow({
  file, url, open, onToggle,
}: { file: QaFile; url: string; open: boolean; onToggle: () => void }) {
  return (
    <div style={{ background: open ? 'var(--bg-secondary)' : 'transparent' }}>
      <div
        onClick={onToggle}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 16px', fontSize: 11,
          cursor: 'pointer', userSelect: 'none',
        }}
      >
        <span>{open ? '▼' : '▶'}</span>
        <span style={{ flex: 1 }}>{file.name}</span>
        <span style={{ fontSize: 9, color: 'var(--text-secondary)' }}>
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
          <FilePreview file={file as unknown as NodeOutputFile} url={url} />
        </div>
      )}
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
