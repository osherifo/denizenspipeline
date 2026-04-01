/** Convert manifest detail panel — metadata, runs table, BIDS validation, scanner info. */
import { useState, useEffect } from 'react'
import type { CSSProperties } from 'react'
import type { ConvertManifestDetail } from '../../api/types'
import { useConvertStore } from '../../stores/convert-store'

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
  color: '#000',
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

      {/* Runs table */}
      <div style={sectionLabel}>Runs ({manifest.runs.length})</div>
      <div style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 6, overflow: 'hidden', marginBottom: 16 }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Modality</th>
              <th style={thStyle}>Task</th>
              <th style={thStyle}>Run</th>
              <th style={thStyle}>Session</th>
              <th style={thStyle}>Volumes</th>
              <th style={thStyle}>TR</th>
              <th style={thStyle}>Shape</th>
              <th style={thStyle}>Output</th>
            </tr>
          </thead>
          <tbody>
            {manifest.runs.map((run) => (
              <tr key={run.run_name}>
                <td style={tdStyle}>
                  <span style={{
                    ...tagStyle,
                    backgroundColor: modalityColor(run.modality).bg,
                    color: modalityColor(run.modality).text,
                  }}>
                    {run.modality}
                  </span>
                </td>
                <td style={{ ...tdStyle, fontWeight: 600 }}>{run.task || '\u2014'}</td>
                <td style={tdStyle}>{run.run_name}</td>
                <td style={tdStyle}>{run.session || '\u2014'}</td>
                <td style={tdStyle}>{run.n_volumes}</td>
                <td style={tdStyle}>{run.tr != null ? `${run.tr}s` : '\u2014'}</td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                  [{run.shape.join(', ')}]
                </td>
                <td style={{ ...tdStyle, fontSize: 10, fontFamily: 'monospace', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {run.output_file}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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

function modalityColor(modality: string): { bg: string; text: string } {
  switch (modality.toLowerCase()) {
    case 'bold':
    case 'func':
      return { bg: 'rgba(0, 229, 255, 0.12)', text: 'var(--accent-cyan)' }
    case 'anat':
    case 't1w':
    case 't2w':
      return { bg: 'rgba(0, 230, 118, 0.12)', text: 'var(--accent-green)' }
    case 'dwi':
    case 'dti':
      return { bg: 'rgba(255, 214, 0, 0.12)', text: 'var(--accent-yellow)' }
    case 'fmap':
    case 'fieldmap':
      return { bg: 'rgba(255, 23, 68, 0.12)', text: 'var(--accent-red)' }
    default:
      return { bg: 'rgba(136, 136, 170, 0.12)', text: 'var(--text-secondary)' }
  }
}
