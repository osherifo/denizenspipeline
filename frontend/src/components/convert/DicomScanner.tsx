/** Tab 3: DICOM Scanner — input source dir path, scan for DICOM series info. */
import { useState } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import { useConvertStore } from '../../stores/convert-store'
import { PathField } from '../common/PathPicker'

const containerStyle: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px 24px',
}

const titleStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 16,
}

const fieldRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 12,
  gap: 12,
}

const labelStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  width: 100,
  textAlign: 'right',
  flexShrink: 0,
}

const inputStyle: CSSProperties = {
  padding: '8px 12px',
  fontSize: 12,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 5,
  color: 'var(--text-primary)',
  flex: 1,
  maxWidth: 500,
}

const primaryBtn: CSSProperties = {
  padding: '8px 24px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  backgroundColor: 'var(--accent-cyan)',
  color: 'var(--on-accent)',
}

const secondaryBtn: CSSProperties = {
  padding: '8px 24px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: '1px solid var(--border)',
  borderRadius: 6,
  cursor: 'pointer',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

const sectionLabel: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 20,
  marginBottom: 10,
  borderTop: '1px solid var(--border)',
  paddingTop: 16,
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

const fieldCardLabel: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 2,
}

const fieldCardValue: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
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

export function DicomScanner() {
  const { scanResult, scanning, scanError, scanDicom, clearScan, cancelScan, scanProgress } = useConvertStore()
  const [sourceDir, setSourceDir] = useState('')

  const handleScan = () => {
    if (sourceDir.trim()) {
      scanDicom(sourceDir.trim())
    }
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && sourceDir.trim() && !scanning) {
      handleScan()
    }
  }

  return (
    <div style={containerStyle}>
      <div style={titleStyle}>Scan DICOM Directory</div>

      <div style={fieldRow}>
        <span style={labelStyle}>Source Dir</span>
        <PathField
          style={inputStyle}
          value={sourceDir}
          onChange={setSourceDir}
          onKeyDown={handleKeyDown}
          placeholder="/data/dicom/sub-01/"
        />
      </div>

      <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
        <button style={primaryBtn} onClick={handleScan} disabled={!sourceDir.trim() || scanning}>
          {scanning ? 'Scanning...' : 'Scan'}
        </button>
        {scanning && (
          <button style={secondaryBtn} onClick={() => void cancelScan()}>Cancel</button>
        )}
        {scanning && scanProgress && (
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', alignSelf: 'center' }}>
            {scanProgress.files_seen} files · {scanProgress.dicoms_seen} DICOMs · {scanProgress.series_found} series
            {scanProgress.current_dir ? ` · ${scanProgress.current_dir.split('/').slice(-2).join('/')}` : ''}
          </span>
        )}
        {scanResult && (
          <button style={secondaryBtn} onClick={clearScan}>
            Clear
          </button>
        )}
      </div>

      {/* Error */}
      {scanError && (
        <div style={{ marginTop: 16, fontSize: 12, color: 'var(--accent-red)' }}>
          {scanError}
        </div>
      )}

      {/* Scanner summary (per-series detail is in the table) */}
      {scanResult && scanResult.series.length > 0 && (() => {
        const names = new Map<string, number>()
        for (const sr of scanResult.series) {
          const k = [sr.manufacturer, sr.model, sr.field_strength ? `${sr.field_strength}T` : null].filter(Boolean).join(' ') || 'unknown scanner'
          names.set(k, (names.get(k) ?? 0) + 1)
        }
        return (
          <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
            {names.size > 1 ? `${names.size} different scanners in this directory: ` : 'Scanner: '}
            {[...names.entries()].map(([k, n]) => `${k} (${n} series)`).join(' · ')}
          </div>
        )
      })()}
      {/* Series table */}
      {scanResult && scanResult.series.length > 0 && (
        <>
          <div style={sectionLabel}>DICOM Series ({scanResult.series.length})</div>
          <div style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 6, overflow: 'hidden' }}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={thStyle}>#</th>
                  <th style={thStyle}>Description</th>
                  <th style={thStyle}>Images</th>
                  <th style={thStyle}>Modality</th>
                  <th style={thStyle}>Scanner</th>
                  <th style={thStyle}>Station</th>
                  <th style={thStyle}>Date</th>
                </tr>
              </thead>
              <tbody>
                {scanResult.series.map((s) => (
                  <tr key={s.number}>
                    <td style={{ ...tdStyle, fontWeight: 600, width: 50 }}>{s.number}</td>
                    <td style={{ ...tdStyle, fontWeight: 600 }}>{s.description}</td>
                    <td style={tdStyle}>{s.n_images}</td>
                    <td style={tdStyle}>
                      <span style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: 3,
                        fontSize: 10,
                        fontWeight: 600,
                        backgroundColor: modalityColor(s.modality_guess).bg,
                        color: modalityColor(s.modality_guess).text,
                      }}>
                        {s.modality_guess}
                      </span>
                    </td>
                    <td style={tdStyle} title={[s.software_version, s.institution, s.protocol_name].filter(Boolean).join(' · ')}>
                      {[s.manufacturer, s.model].filter(Boolean).join(' ') || '—'}{s.field_strength ? ` · ${s.field_strength}T` : ''}
                    </td>
                    <td style={tdStyle}>{s.station_name || '—'}</td>
                    <td style={tdStyle}>{s.study_date ? `${s.study_date.slice(0, 4)}-${s.study_date.slice(4, 6)}-${s.study_date.slice(6, 8)}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {scanResult && scanResult.series.length === 0 && (
        <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
          No DICOM series found in the specified directory.
        </div>
      )}
    </div>
  )
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
