/** Batch DICOM-to-BIDS conversion — form for shared settings + jobs table. */
import { useEffect, useRef } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { useConvertStore } from '../../stores/convert-store'

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
  width: 110,
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
  maxWidth: 400,
}

const selectStyle: CSSProperties = {
  ...inputStyle,
  appearance: 'auto' as const,
  maxWidth: 250,
}

const smallInput: CSSProperties = {
  ...inputStyle,
  maxWidth: 80,
}

const sectionTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginTop: 16,
  marginBottom: 10,
}

const checkRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  marginBottom: 8,
  gap: 8,
  marginLeft: 122,
}

const checkLabel: CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  userSelect: 'none',
}

const checkboxStyle: CSSProperties = {
  width: 14,
  height: 14,
  cursor: 'pointer',
  accentColor: 'var(--accent-cyan)',
}

const btnStyle: CSSProperties = {
  padding: '8px 24px',
  fontSize: 12,
  fontWeight: 600,
  fontFamily: 'inherit',
  borderRadius: 6,
  cursor: 'pointer',
}

const primaryBtn: CSSProperties = {
  ...btnStyle,
  border: 'none',
  backgroundColor: 'var(--accent-cyan)',
  color: '#000',
}

const secondaryBtn: CSSProperties = {
  ...btnStyle,
  border: '1px solid var(--border)',
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-secondary)',
}

const thStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  padding: '6px 8px',
  textAlign: 'left',
  borderBottom: '1px solid var(--border)',
}

const tdStyle: CSSProperties = {
  padding: '4px 4px',
  verticalAlign: 'middle',
}

const cellInput: CSSProperties = {
  padding: '6px 8px',
  fontSize: 12,
  fontFamily: 'inherit',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  width: '100%',
  boxSizing: 'border-box',
}

const removeBtn: CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontSize: 16,
  padding: '2px 6px',
  lineHeight: 1,
}

export function BatchForm() {
  const {
    batchJobs, batchShared, batchError,
    heuristics, heuristicsLoading, loadHeuristics,
    addBatchJob, removeBatchJob, updateBatchJob, updateBatchShared,
    startBatch, loadBatchYaml,
    batchRunning,
  } = useConvertStore()

  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { loadHeuristics() }, [])

  const validJobs = batchJobs.filter((j) => j.subject.trim() && j.source_dir.trim())
  const canRun = batchShared.heuristic && batchShared.bidsDir && validJobs.length > 0 && !batchRunning

  const handleLoadYaml = () => {
    fileRef.current?.click()
  }

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const text = await file.text()
    await loadBatchYaml(text)
    e.target.value = ''
  }

  const handleExportYaml = () => {
    const config = {
      convert_batch: {
        heuristic: batchShared.heuristic,
        bids_dir: batchShared.bidsDir,
        ...(batchShared.sourceRoot ? { source_root: batchShared.sourceRoot } : {}),
        max_workers: batchShared.maxWorkers,
        ...(batchShared.datasetName ? { dataset_name: batchShared.datasetName } : {}),
        validate_bids: batchShared.validateBids,
        jobs: batchJobs.filter((j) => j.subject.trim()).map((j) => ({
          subject: j.subject,
          source_dir: j.source_dir,
          ...(j.session ? { session: j.session } : {}),
        })),
      },
    }

    // Simple YAML serialization
    let yaml = 'convert_batch:\n'
    yaml += `  heuristic: ${config.convert_batch.heuristic}\n`
    yaml += `  bids_dir: ${config.convert_batch.bids_dir}\n`
    if (batchShared.sourceRoot) yaml += `  source_root: ${batchShared.sourceRoot}\n`
    yaml += `  max_workers: ${config.convert_batch.max_workers}\n`
    if (batchShared.datasetName) yaml += `  dataset_name: ${batchShared.datasetName}\n`
    yaml += `  validate_bids: ${config.convert_batch.validate_bids}\n`
    yaml += '\n  jobs:\n'
    for (const j of config.convert_batch.jobs) {
      yaml += `    - subject: ${j.subject}\n`
      yaml += `      source_dir: ${j.source_dir}\n`
      if (j.session) yaml += `      session: "${j.session}"\n`
    }

    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'batch_convert.yaml'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={containerStyle}>
      <div style={titleStyle}>Batch DICOM-to-BIDS Conversion</div>

      {/* Shared Settings */}
      <div style={sectionTitle}>Shared Settings</div>

      <div style={fieldRow}>
        <span style={labelStyle}>Heuristic</span>
        <select
          style={selectStyle}
          value={batchShared.heuristic}
          onChange={(e) => updateBatchShared({ heuristic: e.target.value })}
        >
          <option value="">Select heuristic...</option>
          {heuristics.map((h) => (
            <option key={h.name} value={h.name}>
              {h.name}{h.scanner_pattern ? ` (${h.scanner_pattern})` : ''}
            </option>
          ))}
        </select>
        {heuristicsLoading && (
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>loading...</span>
        )}
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>BIDS Dir</span>
        <input
          style={inputStyle}
          value={batchShared.bidsDir}
          onChange={(e) => updateBatchShared({ bidsDir: e.target.value })}
          placeholder="/data/bids/study/"
        />
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>Source Root</span>
        <input
          style={inputStyle}
          value={batchShared.sourceRoot}
          onChange={(e) => updateBatchShared({ sourceRoot: e.target.value })}
          placeholder="/data/dicoms/ (optional, for relative source dirs)"
        />
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>Max Workers</span>
        <input
          type="number"
          style={smallInput}
          value={batchShared.maxWorkers}
          min={1}
          max={16}
          onChange={(e) => updateBatchShared({ maxWorkers: Number(e.target.value) || 1 })}
        />
      </div>

      <div style={fieldRow}>
        <span style={labelStyle}>Dataset Name</span>
        <input
          style={inputStyle}
          value={batchShared.datasetName}
          onChange={(e) => updateBatchShared({ datasetName: e.target.value })}
          placeholder="(optional)"
        />
      </div>

      {/* Checkboxes */}
      <div style={checkRow}>
        <input
          type="checkbox"
          id="batch-minmeta"
          checked={batchShared.minmeta}
          onChange={(e) => updateBatchShared({ minmeta: e.target.checked })}
          style={checkboxStyle}
        />
        <label htmlFor="batch-minmeta" style={checkLabel}>Minimal metadata</label>
      </div>
      <div style={checkRow}>
        <input
          type="checkbox"
          id="batch-overwrite"
          checked={batchShared.overwrite}
          onChange={(e) => updateBatchShared({ overwrite: e.target.checked })}
          style={checkboxStyle}
        />
        <label htmlFor="batch-overwrite" style={checkLabel}>Overwrite existing</label>
      </div>
      <div style={checkRow}>
        <input
          type="checkbox"
          id="batch-validate"
          checked={batchShared.validateBids}
          onChange={(e) => updateBatchShared({ validateBids: e.target.checked })}
          style={checkboxStyle}
        />
        <label htmlFor="batch-validate" style={checkLabel}>Validate BIDS</label>
      </div>

      {/* Jobs Table */}
      <div style={sectionTitle}>Jobs ({batchJobs.length})</div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, width: 36 }}>#</th>
              <th style={thStyle}>Subject</th>
              <th style={thStyle}>Session</th>
              <th style={thStyle}>Source Dir</th>
              <th style={{ ...thStyle, width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {batchJobs.map((job, i) => (
              <tr key={i}>
                <td style={{ ...tdStyle, fontSize: 11, color: 'var(--text-secondary)', textAlign: 'center' }}>{i + 1}</td>
                <td style={tdStyle}>
                  <input
                    style={cellInput}
                    value={job.subject}
                    onChange={(e) => updateBatchJob(i, { subject: e.target.value })}
                    placeholder="sub01"
                  />
                </td>
                <td style={tdStyle}>
                  <input
                    style={cellInput}
                    value={job.session}
                    onChange={(e) => updateBatchJob(i, { session: e.target.value })}
                    placeholder="01"
                  />
                </td>
                <td style={tdStyle}>
                  <input
                    style={cellInput}
                    value={job.source_dir}
                    onChange={(e) => updateBatchJob(i, { source_dir: e.target.value })}
                    placeholder="session01/"
                  />
                </td>
                <td style={tdStyle}>
                  {batchJobs.length > 1 && (
                    <button style={removeBtn} onClick={() => removeBatchJob(i)} title="Remove job">
                      {'\u00D7'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        style={{ ...secondaryBtn, marginTop: 8, fontSize: 11, padding: '4px 16px' }}
        onClick={addBatchJob}
      >
        + Add Job
      </button>

      {/* Actions */}
      <div style={{ marginTop: 20, display: 'flex', gap: 12, alignItems: 'center' }}>
        <button style={primaryBtn} onClick={startBatch} disabled={!canRun}>
          {batchRunning ? 'Running...' : `Run Batch (${validJobs.length} jobs)`}
        </button>
        <button style={secondaryBtn} onClick={handleLoadYaml}>
          Load YAML
        </button>
        <button style={secondaryBtn} onClick={handleExportYaml}>
          Export YAML
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".yaml,.yml"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
      </div>

      {batchError && !batchRunning && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--accent-red)' }}>
          {batchError}
        </div>
      )}
    </div>
  )
}
