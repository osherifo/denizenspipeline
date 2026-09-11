/** The subject fan-out node: which subjects, which subject graph runs for each of them,
 *  and the input values it gets (for every subject, or per subject). */
import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { fetchAnalysisGraph, fetchAnalysisTemplate, saveAnalysisGraph } from '../../api/analysis'
import type { AnalysisGraphInputSpec, AnalysisGraphNodeDoc } from '../../api/types'
import { formatInputValue, parseInputValue, useAnalysisGraphStore } from '../../stores/analysis-graph-store'
import { useDialog } from '../common/Dialog'
import { YamlField } from './YamlField'

/** Params this section edits; the generic form shows the rest. */
export const MAP_SUBJECTS_PARAMS = ['subjects', 'body', 'inputs', 'subject_inputs', 'subject_template', 'subject_overrides']

const h: CSSProperties = { fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--text-secondary)', margin: '4px 0' }
const small: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)' }
const input: CSSProperties = {
  width: '100%', minWidth: 0, boxSizing: 'border-box', padding: '4px 6px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'inherit',
}
const btn: CSSProperties = { ...input, width: 'auto', cursor: 'pointer' }
const STATUS_COLOR: Record<string, string> = { running: 'var(--accent-cyan)', ok: 'var(--accent-green)', failed: 'var(--accent-red)' }

const isBinding = (v: unknown) => typeof v === 'string' && v.startsWith('$inputs.')

export function MapSubjectsSection({ node }: { node: AnalysisGraphNodeDoc }) {
  const params = node.data.params
  const updateNodeParams = useAnalysisGraphStore((s) => s.updateNodeParams)
  const templates = useAnalysisGraphStore((s) => s.templates)
  const graphs = useAnalysisGraphStore((s) => s.graphs)
  const openBody = useAnalysisGraphStore((s) => s.openBody)
  const loadGraphs = useAnalysisGraphStore((s) => s.loadGraphs)
  const subjectStatus = useAnalysisGraphStore((s) => s.subjectStatus)
  const dlg = useDialog()
  const set = (patch: Record<string, unknown>) => updateNodeParams(node.id, { ...params, ...patch })

  const subjects = Array.isArray(params.subjects) ? params.subjects.map(String) : []
  const [subjectsText, setSubjectsText] = useState(subjects.join('\n'))
  const useTemplate = Boolean(params.subject_template)
  const body = typeof params.body === 'string' ? params.body : ''

  const subjectTemplates = useMemo(() => templates.filter((t) => (t.scope ?? 'subject') === 'subject'), [templates])
  const subjectGraphs = useMemo(() => graphs.filter((g) => g.scope === 'subject'), [graphs])
  const isSaved = subjectGraphs.some((g) => g.name === body)
  const isTemplate = !isSaved && subjectTemplates.some((t) => t.name === body)

  // The body's inputs give the columns of the values table.
  const [bodyInputs, setBodyInputs] = useState<Record<string, AnalysisGraphInputSpec> | null>(null)
  useEffect(() => {
    let cancelled = false
    const fetchInputs = isSaved ? fetchAnalysisGraph(body).then((r) => r.graph.inputs)
      : isTemplate ? fetchAnalysisTemplate(body).then((r) => r.graph.inputs) : null
    if (!fetchInputs) { setBodyInputs(null); return }
    fetchInputs.then((inputs) => { if (!cancelled) setBodyInputs(inputs) }).catch(() => { if (!cancelled) setBodyInputs(null) })
    return () => { cancelled = true }
  }, [body, isSaved, isTemplate])

  const shared = (params.inputs && typeof params.inputs === 'object' ? params.inputs : {}) as Record<string, unknown>
  const perSubject = (params.subject_inputs && typeof params.subject_inputs === 'object' ? params.subject_inputs : {}) as Record<string, Record<string, unknown>>
  const columns = Object.keys(bodyInputs ?? {}).filter((k) => k !== 'subject')

  const setShared = (name: string, text: string) => {
    const next = { ...shared }
    if (text.trim() === '') delete next[name]
    else next[name] = parseInputValue(text)
    set({ inputs: next })
  }
  const setForSubject = (subject: string, name: string, text: string) => {
    const row = { ...(perSubject[subject] ?? {}) }
    if (text.trim() === '') delete row[name]
    else row[name] = parseInputValue(text)
    const next = { ...perSubject, [subject]: row }
    if (Object.keys(row).length === 0) delete next[subject]
    set({ subject_inputs: next })
  }

  async function copyTemplate() {
    const name = await dlg.prompt(`Copy template "${body}" to a saved graph named:`, { defaultValue: `${body}_copy`, placeholder: 'graph_name' })
    if (!name) return
    const { graph } = await fetchAnalysisTemplate(body)
    await saveAnalysisGraph(name, { ...graph, name })
    await loadGraphs()
    set({ body: name })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div>
        <div style={h}>Subjects</div>
        {isBinding(params.subjects) ? (
          <div style={small}>from the graph input <code>{String(params.subjects).slice('$inputs.'.length)}</code> <button style={btn} onClick={() => { setSubjectsText(''); set({ subjects: [] }) }}>list them here instead</button></div>
        ) : (
          <textarea style={{ ...input, fontFamily: 'monospace' }} rows={Math.min(Math.max(subjects.length, 2), 8)} placeholder="one subject id per line"
            value={subjectsText} onChange={(e) => setSubjectsText(e.target.value)}
            onBlur={() => set({ subjects: subjectsText.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean) })} />
        )}
        {Object.keys(subjectStatus).length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
            {Object.entries(subjectStatus).map(([sub, st]) => (
              <span key={sub} style={{ fontSize: 11, border: `1px solid ${STATUS_COLOR[st]}`, color: STATUS_COLOR[st], borderRadius: 4, padding: '0 5px' }}>{sub} {st}</span>
            ))}
          </div>
        )}
      </div>

      <div>
        <div style={h}>Run for each subject</div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 6, fontSize: 12 }}>
          <label><input type="radio" checked={!useTemplate} onChange={() => set({ subject_template: undefined, subject_overrides: undefined })} /> subject graph</label>
          <label><input type="radio" checked={useTemplate} onChange={() => set({ subject_template: { experiment: 'untitled' }, body: undefined })} /> stage config</label>
        </div>
        {!useTemplate ? (
          <>
            {isBinding(params.body) ? (
              <div style={small}>from the graph input <code>{String(params.body).slice('$inputs.'.length)}</code></div>
            ) : (
              <select style={input} value={body} onChange={(e) => set({ body: e.target.value || undefined })} aria-label="subject graph to run">
                <option value="">choose a subject graph…</option>
                {subjectGraphs.length > 0 && <optgroup label="saved graphs">{subjectGraphs.map((g) => <option key={g.name} value={g.name}>{g.name}</option>)}</optgroup>}
                <optgroup label="templates">{subjectTemplates.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}</optgroup>
                {body && !isSaved && !isTemplate && <option value={body}>{body}</option>}
              </select>
            )}
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              <button style={{ ...btn, opacity: isSaved || isTemplate ? 1 : 0.5 }} disabled={!(isSaved || isTemplate)} onClick={() => void openBody(body)}>Open subject graph</button>
              {isTemplate && <button style={btn} title="Keep your own copy to edit, instead of the shared template" onClick={() => void copyTemplate()}>Copy to a saved graph…</button>}
            </div>
          </>
        ) : (
          <>
            <div style={small}>Stage config shared by every subject (the group config's subject_template).</div>
            <YamlField value={params.subject_template} rows={6} onChange={(v) => set({ subject_template: v })} />
            <div style={{ ...small, marginTop: 6 }}>Per-subject overrides, deep-merged: <code>{'{subject: {key: value}}'}</code></div>
            <YamlField value={params.subject_overrides ?? {}} rows={3} onChange={(v) => set({ subject_overrides: v })} />
          </>
        )}
      </div>

      {!useTemplate && (
        <div>
          <div style={h}>Input values</div>
          {isBinding(params.inputs) ? (
            <div style={small}>from the graph input <code>{String(params.inputs).slice('$inputs.'.length)}</code></div>
          ) : columns.length === 0 ? (
            <div style={small}>{body ? 'the subject graph declares no inputs besides subject' : 'choose a subject graph to fill in its inputs'}</div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <div style={small}>A value in the first row applies to every subject; <code>{'{subject}'}</code> becomes the subject id. A value in a subject's row wins.</div>
              <table style={{ borderCollapse: 'collapse', fontSize: 11, marginTop: 4 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', padding: 3 }} />
                    {columns.map((c) => <th key={c} style={{ textAlign: 'left', padding: 3 }} title={bodyInputs?.[c]?.description}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ padding: 3, fontWeight: 700 }}>all</td>
                    {columns.map((c) => (
                      <td key={c} style={{ padding: 3 }}>
                        <input style={{ ...input, minWidth: 110 }} aria-label={`${c} for every subject`} placeholder={formatInputValue(bodyInputs?.[c]?.default)}
                          defaultValue={formatInputValue(shared[c])} onBlur={(e) => setShared(c, e.target.value)} />
                      </td>
                    ))}
                  </tr>
                  {subjects.map((sub) => (
                    <tr key={sub}>
                      <td style={{ padding: 3 }}>{sub}</td>
                      {columns.map((c) => (
                        <td key={c} style={{ padding: 3 }}>
                          <input style={{ ...input, minWidth: 110 }} aria-label={`${c} for ${sub}`}
                            defaultValue={formatInputValue(perSubject[sub]?.[c])} onBlur={(e) => setForSubject(sub, c, e.target.value)} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
