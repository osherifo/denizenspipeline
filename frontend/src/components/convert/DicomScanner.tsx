/** Tab 3: DICOM Scanner — input source dir path, scan for DICOM series info. */
import { useState } from 'react'
import { useConvertStore } from '../../stores/convert-store'

const containerStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  padding: '20px 24px',
}

const titleStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 16,
}

const fieldRow: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 12,
  gap: 12,
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  width: 100,
  textAlign: 'right',
  flexShrink: 0,
}

const inputStyle: React.CSSProperties = {
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

const primaryBtn: React.CSSProperties = {
  padding: '8px 24px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  border: 'none',
  borderRadius: 6,
  cursor: 'pointer',
  backgroundColor: 'var(--accent-cyan)',
  color: '#000',
}

const secondaryBtn: React.CSSProperties = {
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

const sectionLabel: React.CSSProperties = {
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

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
  gap: 10,
  marginBottom: 20,
}

const fieldCard: React.CSSProperties = {
  backgroundColor: 'var(--bg-secondary)',
  borderRadius: 6,
  padding: '8px 12px',
}

const fieldCardLabel: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 2,
}

const fieldCardValue: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-primary)',
}

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 12,
}

const thStyle: React.CSSProperties = {
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

const tdStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-primary)',
}

export function DicomScanner() {
  const { scanResult, scanning, scanError, scanDicom, clearScan } = useConvertStore()
  const [sourceDir, setSourceDir] = useState('')

  const handleScan = () => {
    if (sourceDir.trim()) {
      scanDicom(sourceDir.trim())
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && sourceDir.trim() && !scanning) {
      handleScan()
    }
  }

  return (
    <div style={containerStyle}>
      <div style={titleStyle}>Scan DICOM Directory</div>

      <div style={fieldRow}>
        <span style={labelStyle}>Source Dir</span>
        <input
          style={inputStyle}
          value={sourceDir}
          onChange={(e) => setSourceDir(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="/data/dicom/sub-01/"
        />
      </div>

      <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
        <button style={primaryBtn} onClick={handleScan} disabled={!sourceDir.trim() || scanning}>
          {scanning ? 'Scanning...' : 'Scan'}
        </button>
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

      {/* Scanner info */}
      {scanResult && scanResult.scanner && (
        <>
          <div style={sectionLabel}>Scanner Info</div>
          <div style={gridStyle}>
            {scanResult.scanner.manufacturer && (
              <div style={fieldCard}>
                <div style={fieldCardLabel}>Manufacturer</div>
                <div style={fieldCardValue}>{scanResult.scanner.manufacturer}</div>
              </div>
            )}
            {scanResult.scanner.model && (
              <div style={fieldCard}>
                <div style={fieldCardLabel}>Model</div>
                <div style={fieldCardValue}>{scanResult.scanner.model}</div>
              </div>
            )}
            {scanResult.scanner.field_strength != null && (
              <div style={fieldCard}>
                <div style={fieldCardLabel}>Field Strength</div>
                <div style={fieldCardValue}>{scanResult.scanner.field_strength}T</div>
              </div>
            )}
            {scanResult.scanner.institution && (
              <div style={fieldCard}>
                <div style={fieldCardLabel}>Institution</div>
                <div style={fieldCardValue}>{scanResult.scanner.institution}</div>
              </div>
            )}
            {scanResult.scanner.station_name && (
              <div style={fieldCard}>
                <div style={fieldCardLabel}>Station</div>
                <div style={fieldCardValue}>{scanResult.scanner.station_name}</div>
              </div>
            )}
            {scanResult.scanner.software_version && (
              <div style={fieldCard}>
                <div style={fieldCardLabel}>Software</div>
                <div style={fieldCardValue}>{scanResult.scanner.software_version}</div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Matching heuristic */}
      {scanResult && scanResult.matching_heuristic && (
        <div style={{
          backgroundColor: 'rgba(0, 230, 118, 0.08)',
          border: '1px solid rgba(0, 230, 118, 0.3)',
          borderRadius: 6,
          padding: '10px 14px',
          marginBottom: 16,
          fontSize: 12,
        }}>
          <span style={{ fontWeight: 700, color: 'var(--accent-green)' }}>{'\u2713'} Matching heuristic: </span>
          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{scanResult.matching_heuristic}</span>
        </div>
      )}

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
