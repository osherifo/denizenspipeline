/** Experiment Dashboard — browse configs, launch runs, watch live progress. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { useDashboardStore } from '../stores/dashboard-store'
import { ConfigBrowser } from '../components/dashboard/ConfigBrowser'
import { ConfigDetail } from '../components/dashboard/ConfigDetail'
import { RunHistory } from '../components/dashboard/RunHistory'
import { GroupRunHistory } from '../components/dashboard/GroupRunHistory'
import { StudyRunHistory } from '../components/dashboard/StudyRunHistory'
import { LiveProgress } from '../components/dashboard/LiveProgress'
import { GroupLiveProgress } from '../components/dashboard/GroupLiveProgress'
import { StudyLiveProgress } from '../components/dashboard/StudyLiveProgress'
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

// Right-side in-flight drawer: collapses to a thin spine, expands to a
// configurable width so the user can pin it open while a run is going.
const drawerBase: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  borderLeft: '1px solid var(--border)',
  backgroundColor: 'var(--bg-card)',
  transition: 'width 120ms ease',
  overflow: 'hidden',
}

const drawerHeader: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '10px 12px',
  borderBottom: '1px solid var(--border)',
  backgroundColor: 'var(--bg-secondary)',
}

const drawerTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 1,
  flex: 1,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
}

const drawerBtn: CSSProperties = {
  padding: '2px 6px',
  fontSize: 11,
  border: '1px solid var(--border)',
  borderRadius: 3,
  background: 'transparent',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

const drawerBody: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
}

const collapsedSpineLabel: CSSProperties = {
  writingMode: 'vertical-rl',
  transform: 'rotate(180deg)',
  padding: '12px 6px',
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 2,
  cursor: 'pointer',
  userSelect: 'none',
  whiteSpace: 'nowrap',
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

type DrawerMode = 'collapsed' | 'normal' | 'wide'

export function ExperimentDashboard() {
  const store = useDashboardStore()
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('normal')

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
    if (store.selectedFilename) {
      store.selectConfig(store.selectedFilename)
    }
    store.rescan()
  }

  const handleCopied = async (newFilename: string) => {
    await store.rescan()
    store.selectConfig(newFilename)
  }

  // Pick the LiveProgress component based on (1) the selected config's
  // kind, falling back to (2) what the event stream says — the latter
  // matters when the user has attached to an in-flight run without
  // selecting its config (CLI-launched group/study run).
  const cfg = store.selectedConfig?.config as Record<string, any> | undefined
  const cfgIsStudy = !!cfg
    && typeof cfg.study === 'string'
    && Array.isArray(cfg.groups)
  const cfgIsGroup = !!cfg && !cfgIsStudy
    && typeof cfg.group === 'string'
    && Array.isArray(cfg.subjects)
  // Infer run kind from the event stream when there's no matching
  // selected config (attach-from-CLI case). Two signals to check:
  //   - the 'started' wrapper event carries is_group / is_study flags
  //     stamped by RunManager._execute
  //   - the orchestrator's own 'group_started' / 'study_started' event
  //     fires after the wrapper, somewhere in the middle of the stream
  // Either presence is enough. The first event is NOT 'group_started'
  // for a group run — it's 'started' — so the original `liveEvents[0]`
  // check missed it, downgrading attached group runs to the subject
  // LiveProgress component.
  let eventIsStudy = false
  let eventIsGroup = false
  for (const e of store.liveEvents) {
    const a = e as any
    if (e.event === 'started') {
      if (a.is_study) eventIsStudy = true
      else if (a.is_group) eventIsGroup = true
    } else if (e.event === 'study_started') {
      eventIsStudy = true
    } else if (e.event === 'group_started') {
      eventIsGroup = true
    }
    if (eventIsStudy) break  // study trumps group; can stop early
  }
  const isStudy = cfgIsStudy || eventIsStudy
  const isGroup = (cfgIsGroup || eventIsGroup) && !isStudy

  const hasLive = store.liveRunId || store.liveEvents.length > 0
  const rid = store.liveRunId || store.lastRunId || 'completed'
  const onDismiss = () => useDashboardStore.setState({
    liveEvents: [], completedRun: null, stageStatuses: {},
    lastRunId: null,
  })

  const drawerWidth =
    drawerMode === 'collapsed' ? 36 :
    drawerMode === 'wide' ? 560 : 320

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
        {hasLive && (
          isStudy ? (
            <StudyLiveProgress
              runId={rid} events={store.liveEvents}
              startTime={store.liveStartTime} onDismiss={onDismiss}
            />
          ) : isGroup ? (
            <GroupLiveProgress
              runId={rid} events={store.liveEvents}
              startTime={store.liveStartTime} onDismiss={onDismiss}
            />
          ) : (
            <LiveProgress
              runId={rid} events={store.liveEvents}
              stageStatuses={store.stageStatuses}
              startTime={store.liveStartTime}
              completedRun={store.completedRun}
              onDismiss={onDismiss}
            />
          )
        )}

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

            {isStudy ? (
              <StudyRunHistory
                runs={store.studyConfigRuns}
                loading={store.runsLoading}
              />
            ) : isGroup ? (
              <GroupRunHistory
                runs={store.groupConfigRuns}
                loading={store.runsLoading}
              />
            ) : (
              <RunHistory
                runs={store.configRuns}
                selectedRun={store.selectedRun}
                loading={store.runsLoading}
                onSelectRun={(runId) => store.selectRun(runId)}
                onClearRun={() => store.clearRunSelection()}
              />
            )}
          </>
        ) : !hasLive ? (
          <div style={emptyState}>
            <div style={{ fontSize: 32, marginBottom: 8, color: 'var(--text-secondary)' }}>
              {'☰'}
            </div>
            <div>Select an experiment config to get started</div>
            <div style={{ fontSize: 12 }}>
              {store.configs.length} config{store.configs.length !== 1 ? 's' : ''} found
            </div>
          </div>
        ) : null}
      </div>

      {/* In-flight drawer — collapsible, scrollable internally. */}
      <div style={{ ...drawerBase, width: drawerWidth }}>
        {drawerMode === 'collapsed' ? (
          <div
            style={collapsedSpineLabel}
            onClick={() => setDrawerMode('normal')}
            title="Expand in-flight runs"
          >
            In-flight ◂
          </div>
        ) : (
          <>
            <div style={drawerHeader}>
              <span style={drawerTitle}>In-flight runs</span>
              <button
                style={drawerBtn}
                onClick={() => setDrawerMode(drawerMode === 'wide' ? 'normal' : 'wide')}
                title={drawerMode === 'wide' ? 'Shrink' : 'Expand'}
              >
                {drawerMode === 'wide' ? '▸' : '◂'}
              </button>
              <button
                style={drawerBtn}
                onClick={() => setDrawerMode('collapsed')}
                title="Collapse"
              >
                ✕
              </button>
            </div>
            <div style={drawerBody}>
              <AnalysisInFlightRuns
                onAttach={(runId) => store.attachToInFlightRun(runId)}
              />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
