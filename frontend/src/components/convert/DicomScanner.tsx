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
  whiteSpace: 'nowrap',
  letterSpacing: 0.5,
}

const tdStyle: CSSProperties = {
  padding: '8px 10px',
  whiteSpace: 'nowrap',
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

      {/* Series table */}
      {scanResult && scanResult.series.length > 0 && (
        <>
          <div style={sectionLabel}>DICOM Series ({scanResult.series.length})</div>
          <div style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 6, overflowX: 'auto' }}>
            <table style={{ ...tableStyle, width: 'max-content', minWidth: '100%' }}>
              <thead>
                <tr>
                  <th style={thStyle}>SeriesNumber</th>
                  <th style={thStyle}>SeriesDescription</th>
                  <th style={thStyle}>Files</th>
                  <th style={thStyle}>Modality</th>
                  <th style={thStyle}>ImageType</th>
                  <th style={thStyle}>Manufacturer</th>
                  <th style={thStyle}>ManufacturerModelName</th>
                  <th style={thStyle}>MagneticFieldStrength</th>
                  <th style={thStyle}>SoftwareVersions</th>
                  <th style={thStyle}>StationName</th>
                  <th style={thStyle}>InstitutionName</th>
                  <th style={thStyle}>StudyDate</th>
                  <th style={thStyle}>ProtocolName</th>
                </tr>
              </thead>
              <tbody>
                {scanResult.series.map((s) => (
                  <tr key={s.number}>
                    <td style={tdStyle}>{cell(s.number)}</td>
                    <td style={tdStyle}>{cell(s.description)}</td>
                    <td style={tdStyle}>{cell(s.n_images)}</td>
                    <td style={tdStyle}>{cell(s.modality)}</td>
                    <td style={tdStyle}>{cell(s.image_type)}</td>
                    <td style={tdStyle}>{cell(s.manufacturer)}</td>
                    <td style={tdStyle}>{cell(s.model)}</td>
                    <td style={tdStyle}>{cell(s.field_strength)}</td>
                    <td style={tdStyle}>{cell(s.software_version)}</td>
                    <td style={tdStyle}>{cell(s.station_name)}</td>
                    <td style={tdStyle}>{cell(s.institution)}</td>
                    <td style={tdStyle}>{cell(s.study_date)}</td>
                    <td style={tdStyle}>{cell(s.protocol_name)}</td>
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

/** Header values verbatim; only absence is decorated. */
function cell(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  return String(v)
}
