/** Manifest detail panel — metadata, runs table with QC, validation. */
import { useState, useEffect } from 'react'
import type { CSSProperties } from 'react'
import type { ManifestDetail as ManifestDetailType } from '../../api/types'
import { usePreprocStore } from '../../stores/preproc-store'
import { ManifestSummary } from './ManifestSummary'
import { StructuralQCPanel } from './StructuralQCPanel'

interface Props {
  manifest: ManifestDetailType
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
  color: 'var(--on-accent)',
  border: 'none',
}

export function ManifestDetail({ manifest }: Props) {
  const { validationErrors, validating, validateSelected, configs, loadConfigs } = usePreprocStore()
  const [showJson, setShowJson] = useState(false)
  const [selectedConfig, setSelectedConfig] = useState<string>('')

  useEffect(() => { loadConfigs() }, [])
  useEffect(() => { validateSelected() }, [manifest.subject])

  const handleValidateAgainst = () => {
    if (selectedConfig) {
      validateSelected(selectedConfig)
    }
  }

  return (
    <div>
      {/* Header */}
      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
        sub-{manifest.subject}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16 }}>
        {manifest.backend} {manifest.backend_version} &middot; {manifest.space} &middot; {manifest.output_format}
      </div>

      <ManifestSummary manifest={manifest} />

      {/* Structural QC */}
      <StructuralQCPanel subject={manifest.subject} />

      {/* Validation */}
      <div style={sectionLabel}>Validation</div>
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

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12 }}>
          <select
            style={{
              ...btnStyle,
              minWidth: 200,
              appearance: 'auto',
            }}
            value={selectedConfig}
            onChange={(e) => setSelectedConfig(e.target.value)}
          >
            <option value="">Validate against config...</option>
            {configs.map((c) => (
              <option key={c.filename} value={c.path}>{c.filename}</option>
            ))}
          </select>
          <button style={primaryBtn} onClick={handleValidateAgainst} disabled={!selectedConfig || validating}>
            Check
          </button>
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
