/** Experiment Dashboard — browse configs, launch runs, watch live progress. */
import { useEffect } from 'react'
import type { CSSProperties } from 'react'
import { useDashboardStore } from '../stores/dashboard-store'
import { ConfigBrowser } from '../components/dashboard/ConfigBrowser'
import { ConfigDetail } from '../components/dashboard/ConfigDetail'
import { RunHistory } from '../components/dashboard/RunHistory'
import { LiveProgress } from '../components/dashboard/LiveProgress'
import { AnalysisInFlightRuns } from '../components/dashboard/AnalysisInFlightRuns'

const containerStyle: CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 48px)',
  margin: '0 -32px',
  backgroundColor: 'var(--bg-primary)',
}

const mainPanel: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '20px 24px',
}

const emptyState: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--text-secondary)',
  fontSize: 14,
  gap: 8,
  height: '100%',
}

const pulseKeyframes = `
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
`

export function ExperimentDashboard() {
  const store = useDashboardStore()

  useEffect(() => {
    store.loadConfigs()
  }, [])

  const handleRun = () => {
    if (store.selectedConfig) {
      store.runConfig(store.selectedConfig.path)
    }
  }

  const handleValidate = () => {
    if (store.selectedFilename) {
      store.validateConfig(store.selectedFilename)
    }
  }

  const handleSaved = () => {
    // Re-fetch the selected config after a save so the parsed summary
    // and raw YAML reflect the new content.
    if (store.selectedFilename) {
      store.selectConfig(store.selectedFilename)
    }
    store.rescan()
  }

  const handleCopied = async (newFilename: string) => {
    // Refresh the list, then select the new config.
    await store.rescan()
    store.selectConfig(newFilename)
  }

  return (
    <div style={containerStyle}>
      <style>{pulseKeyframes}</style>

      <ConfigBrowser
        configs={store.configs}
        selectedFilename={store.selectedFilename}
        loading={store.configsLoading}
        onSelect={(filename) => store.selectConfig(filename)}
        onRescan={() => store.rescan()}
      />

      <div style={mainPanel}>
        <AnalysisInFlightRuns />
        {store.selectedConfig ? (
          <>
            <ConfigDetail
              config={store.selectedConfig}
              validationErrors={store.validationErrors}
              validating={store.validating}
              onRun={handleRun}
              onValidate={handleValidate}
              onSaved={handleSaved}
              onCopied={handleCopied}
              isRunning={store.liveRunId !== null}
            />

            {/* Live progress — shown when a run is active or just completed */}
            {(store.liveRunId || store.liveEvents.length > 0) && (
              <LiveProgress
                runId={store.liveRunId || 'completed'}
                events={store.liveEvents}
                stageStatuses={store.stageStatuses}
                startTime={store.liveStartTime}
                completedRun={store.completedRun}
                onDismiss={() => useDashboardStore.setState({ liveEvents: [], completedRun: null, stageStatuses: {} })}
              />
            )}

            <RunHistory
              runs={store.configRuns}
              selectedRun={store.selectedRun}
              loading={store.runsLoading}
              onSelectRun={(runId) => store.selectRun(runId)}
              onClearRun={() => store.clearRunSelection()}
            />
          </>
        ) : (
          <div style={emptyState}>
            <div style={{ fontSize: 32, marginBottom: 8, color: 'var(--text-secondary)' }}>
              {'\u2630'}
            </div>
            <div>Select an experiment config to get started</div>
            <div style={{ fontSize: 12 }}>
              {store.configs.length} config{store.configs.length !== 1 ? 's' : ''} found
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
