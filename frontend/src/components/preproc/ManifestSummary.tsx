/** The friendly, read-only summary of a preprocessing manifest: what was produced, in which
 *  space, per run with QC badges. Used by the manifest browser and the app node popup. */
import type { CSSProperties } from 'react'
import type { ManifestDetail as ManifestDetailType } from '../../api/types'
import { QcBadge } from './QcBadge'

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

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

export function ManifestSummary({ manifest }: { manifest: ManifestDetailType }) {
  return (
    <>
      {/* Metadata grid */}
      <div style={gridStyle}>
        <div style={fieldCard}>
          <div style={fieldLabel}>Dataset</div>
          <div style={fieldValue}>{manifest.dataset}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Space</div>
          <div style={fieldValue}>{manifest.space} ({manifest.resolution || 'native'})</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Backend</div>
          <div style={fieldValue}>{manifest.backend} {manifest.backend_version}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Format</div>
          <div style={fieldValue}>{manifest.output_format}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Runs</div>
          <div style={fieldValue}>{manifest.runs.length}</div>
        </div>
        <div style={fieldCard}>
          <div style={fieldLabel}>Created</div>
          <div style={{ ...fieldValue, fontSize: 11 }}>{formatDate(manifest.created)}</div>
        </div>
        {manifest.confounds_applied.length > 0 && (
          <div style={{ ...fieldCard, gridColumn: 'span 2' }}>
            <div style={fieldLabel}>Confounds Applied</div>
            <div style={{ ...fieldValue, fontSize: 11 }}>{manifest.confounds_applied.join(', ')}</div>
          </div>
        )}
      </div>

      {/* Runs table */}
      <div style={sectionLabel}>Runs ({manifest.runs.length})</div>
      <div style={{ backgroundColor: 'var(--bg-secondary)', borderRadius: 6, overflow: 'hidden', marginBottom: 16 }}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Run</th>
              <th style={thStyle}>TRs</th>
              <th style={thStyle}>Shape</th>
              <th style={thStyle}>QC</th>
            </tr>
          </thead>
          <tbody>
            {manifest.runs.map((run) => (
              <tr key={run.run_name}>
                <td style={{ ...tdStyle, fontWeight: 600 }}>{run.run_name}</td>
                <td style={tdStyle}>{run.n_trs}</td>
                <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 10 }}>
                  [{run.shape.join(', ')}]
                </td>
                <td style={tdStyle}>
                  <QcBadge label="FD" value={run.qc?.mean_fd ?? null} thresholds={[0.3, 0.5]} suffix="mm" />
                  <QcBadge label="tSNR" value={run.qc?.tsnr_median ?? null} decimals={1} />
                  {run.qc?.n_high_motion_trs != null && run.qc.n_high_motion_trs > 0 && (
                    <span style={{
                      display: 'inline-block', padding: '2px 6px', borderRadius: 3,
                      fontSize: 10, fontWeight: 600,
                      backgroundColor: 'rgba(255, 214, 0, 0.12)', color: 'var(--accent-yellow)',
                    }}>
                      {run.qc.n_high_motion_trs} hi-motion TRs
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </>
  )
}
