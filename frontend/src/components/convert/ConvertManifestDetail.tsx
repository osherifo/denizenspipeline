/** Convert manifest detail panel — metadata, runs table, BIDS validation, scanner info. */
import { useState, useEffect } from 'react'
import { DirTree } from '../common/DirTree'
import type { CSSProperties } from 'react'
import type { ConvertManifestDetail, ConvertRunRecord } from '../../api/types'
import { useConvertStore } from '../../stores/convert-store'
import { ConvertDecisionTable } from './ConvertDecisionTable'

interface Props {
  manifest: ConvertManifestDetail
}

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
  gap: 10,
  marginBottom: 20,
}

const fieldCard: CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '8px 12px',
}

const fieldLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 2,
}

const fieldValue: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const sectionLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 16,
  marginBottom: 8,
}

const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 12,
}

const thStyle: CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  fontWeight: 700,
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}

const bidsThStyle: CSSProperties = { ...thStyle, textTransform: 'none', whiteSpace: 'nowrap' }

const tdStyle: CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

const btnStyle: CSSProperties = {
  padding: '6px 16px',
  fontSize: 11,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 5,
  cursor: 'pointer',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

const primaryBtn: CSSProperties = {
  ...btnStyle,
  backgroundColor: 'var(--accent-cyan)',
  color: 'var(--on-accent)',
  border: 'none',
}

const tagStyle: CSSProperties = {
  display: 'inline-block',
  padding: '2px 6px',
  borderRadius: 3,
  fontSize: 10,
  fontWeight: 600,
  marginRight: 4,
  marginBottom: 2,
}

export function ConvertManifestDetailPanel({ manifest }: Props) {
  const { validationErrors, validating, validateSelected } = useConvertStore()
  const [showJson, setShowJson] = useState(false)

  useEffect(() => { validateSelected() }, [manifest.subject])

  return (
    <div>
      {/* Header */}
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
        sub-{manifest.subject}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16 }}>
        {manifest.dataset} &middot; heudiconv {manifest.heudiconv_version}
        {manifest.heuristic && <> &middot; {manifest.heuristic.name}</>}
      </div>

      {/* Metadata grid */}
      <div style={gridStyle}>
        <div style={fieldCard}>
          <div style={fieldLabel}>Dataset</div>
          <div style={fieldValue}>{manifest.dataset}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>HeuDiConv</div>
          <div style={fieldValue}>{manifest.heudiconv_version}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Sessions</div>
          <div style={fieldValue}>
            {manifest.sessions.length > 0 ? manifest.sessions.join(', ') : 'none'}
          </div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Runs</div>
          <div style={fieldValue}>{manifest.runs.length}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>BIDS Valid</div>
          <div style={fieldValue}>
            {manifest.bids_valid === null
              ? <span style={{ color: 'var(--text-secondary)' }}>Not validated</span>
              : manifest.bids_valid
                ? <span style={{ color: 'var(--accent-green)' }}>{'\u2713'} Valid</span>
                : <span style={{ color: 'var(--accent-red)' }}>{'\u2717'} Invalid</span>
            }
          </div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Created</div>
          <div style={{ ...fieldValue, fontSize: 11 }}>{formatDate(manifest.created)}</div>
        </div>
      </div>

      {/* Heuristic info */}
      {manifest.heuristic && (
        <>
          <div style={sectionLabel}>Heuristic</div>
          <div style={{ ...gridStyle, gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
            <div style={fieldCard}>
              <div style={fieldLabel}>Name</div>
              <div style={{ ...fieldValue, color: 'var(--accent-cyan)' }}>{manifest.heuristic.name}</div>
            </div>
            {manifest.heuristic.scanner_pattern && (
              <div style={fieldCard}>
                <div style={fieldLabel}>Scanner Pattern</div>
                <div style={{ ...fieldValue, fontFamily: 'monospace', fontSize: 11 }}>{manifest.heuristic.scanner_pattern}</div>
              </div>
            )}
            {manifest.heuristic.description && (
              <div style={{ ...fieldCard, gridColumn: 'span 2' }}>
                <div style={fieldLabel}>Description</div>
                <div style={{ ...fieldValue, fontSize: 11 }}>{manifest.heuristic.description}</div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Scanner info */}
      {manifest.scanner && (
        <>
          <div style={sectionLabel}>Scanner</div>
          <div style={gridStyle}>
            {manifest.scanner.manufacturer && (
              <div style={fieldCard}>
                <div style={fieldLabel}>Manufacturer</div>
                <div style={fieldValue}>{manifest.scanner.manufacturer}</div>
              </div>
            )}
            {manifest.scanner.model && (
              <div style={fieldCard}>
                <div style={fieldLabel}>Model</div>
                <div style={fieldValue}>{manifest.scanner.model}</div>
              </div>
            )}
            {manifest.scanner.field_strength != null && (
              <div style={fieldCard}>
                <div style={fieldLabel}>Field Strength</div>
                <div style={fieldValue}>{manifest.scanner.field_strength}T</div>
              </div>
            )}
            {manifest.scanner.institution && (
              <div style={fieldCard}>
                <div style={fieldLabel}>Institution</div>
                <div style={fieldValue}>{manifest.scanner.institution}</div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Runs table — BIDS parts of each output file, verbatim: the parent
          datatype dir, every key-value entity found in any file (in BIDS
          order), the suffix, then what the sidecar and the image say. */}
      <div style={sectionLabel}>Runs ({manifest.runs.length})</div>
      {(() => {
        const keys = entityColumns(manifest.runs)
        return (
          <div style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 6, overflowX: 'auto', marginBottom: 16 }}>
            <table style={{ ...tableStyle, width: 'max-content', minWidth: '100%' }}>
              <thead>
                <tr>
                  <th style={bidsThStyle}>datatype</th>
                  {keys.map((k) => <th key={k} style={bidsThStyle}>{k}</th>)}
                  <th style={bidsThStyle}>suffix</th>
                  <th style={bidsThStyle}>shape</th>
                  <th style={bidsThStyle}>RepetitionTime</th>
                  <th style={bidsThStyle}>file</th>
                </tr>
              </thead>
              <tbody>
                {manifest.runs.map((run) => (
                  <tr key={run.output_file}>
                    <td style={tdStyle}>{run.datatype || '\u2014'}</td>
                    {keys.map((k) => <td key={k} style={tdStyle}>{run.entities?.[k] ?? '\u2014'}</td>)}
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{run.suffix || '\u2014'}</td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                      {run.shape.length ? `[${run.shape.join(', ')}]` : '\u2014'}
                    </td>
                    <td style={tdStyle}>{run.tr != null ? run.tr : '\u2014'}</td>
                    <td style={{ ...tdStyle, fontSize: 10, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                      {run.output_file}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })()}

      {/* BIDS Validation */}
      <div style={sectionLabel}>BIDS Validation</div>
      <div style={{ marginBottom: 16 }}>
        {validating && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Validating...</div>
        )}
        {!validating && validationErrors && (
          <div>
            {validationErrors.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--accent-green)', fontWeight: 600 }}>
                {'\u2713'} All checks passed
              </div>
            ) : (
              validationErrors.map((e, i) => (
                <div key={i} style={{
                  fontSize: 12, marginBottom: 4,
                  color: e.startsWith('Warning:') ? 'var(--accent-yellow)' : 'var(--accent-red)',
                }}>
                  {e.startsWith('Warning:') ? '!' : '\u2717'} {e}
                </div>
              ))
            )}
          </div>
        )}

        {/* BIDS errors from manifest */}
        {manifest.bids_errors.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent-red)', marginBottom: 4, textTransform: 'uppercase' }}>
              BIDS Errors
            </div>
            {manifest.bids_errors.map((e, i) => (
              <div key={i} style={{ fontSize: 11, color: 'var(--accent-red)', marginBottom: 2 }}>
                {'\u2717'} {e}
              </div>
            ))}
          </div>
        )}

        {/* BIDS warnings from manifest */}
        {manifest.bids_warnings.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent-yellow)', marginBottom: 4, textTransform: 'uppercase' }}>
              BIDS Warnings
            </div>
            {manifest.bids_warnings.map((w, i) => (
              <div key={i} style={{ fontSize: 11, color: 'var(--accent-yellow)', marginBottom: 2 }}>
                ! {w}
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 12 }}>
          <button style={primaryBtn} onClick={() => validateSelected()} disabled={validating}>
            {validating ? 'Validating...' : 'Re-validate'}
          </button>
        </div>
      </div>

      {/* Source & BIDS dirs */}
      <div style={sectionLabel}>Paths</div>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 2 }}>Source Dir</div>
        <div style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-primary)', marginBottom: 8, wordBreak: 'break-all' }}>
          {manifest.source_dir}
        </div>
        <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 2 }}>BIDS Dir</div>
        <div style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
          {manifest.bids_dir}
        </div>
      </div>

      <ConvertDecisionTable
        bidsDir={manifest.bids_dir}
        subject={manifest.subject}
      />

      {/* Output structure (read-only) */}
      <div style={sectionLabel}>Output structure</div>
      <DirTree path={manifest.bids_dir} title="BIDS directory" />

      {/* Raw JSON */}
      <div style={sectionLabel}>
        <span
          style={{ cursor: 'pointer' }}
          onClick={() => setShowJson(!showJson)}
        >
          Raw JSON {showJson ? '\u25BC' : '\u25B6'}
        </span>
      </div>
      {showJson && (
        <pre style={{
          backgroundColor: 'var(--bg-secondary)',
          padding: '12px',
          borderRadius: 6,
          fontSize: 10,
          lineHeight: 1.5,
          color: 'var(--text-secondary)',
          overflow: 'auto',
          maxHeight: 300,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}>
          {JSON.stringify(manifest, null, 2)}
        </pre>
      )}
    </div>
  )
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

/** Entity keys present in any run, BIDS-specified order first, then the rest alphabetically. */
const BIDS_ENTITY_ORDER = ['sub', 'ses', 'sample', 'task', 'tracksys', 'acq', 'nuc', 'voi', 'ce', 'trc', 'stain', 'rec', 'dir', 'run', 'mod', 'echo', 'flip', 'inv', 'mt', 'part', 'proc', 'hemi', 'space', 'split', 'recording', 'chunk', 'seg', 'res', 'den', 'label', 'desc']
function entityColumns(runs: ConvertRunRecord[]): string[] {
  const present = new Set<string>()
  for (const r of runs) for (const k of Object.keys(r.entities ?? {})) present.add(k)
  const ordered = BIDS_ENTITY_ORDER.filter((k) => present.has(k))
  const rest = [...present].filter((k) => !BIDS_ENTITY_ORDER.includes(k)).sort()
  return [...ordered, ...rest]
}
