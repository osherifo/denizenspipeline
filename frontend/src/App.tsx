import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { NavBar } from './components/layout/NavBar'
import { ModuleBrowser } from './views/ModuleBrowser'
import { AnalysisComposer } from './views/AnalysisComposer'
import { RunManager } from './views/RunManager'
import { ModuleEditor } from './views/ModuleEditor'
import { ExperimentDashboard } from './views/ExperimentDashboard'
import { PreprocManager } from './views/PreprocManager'
import { DicomBidsConverter } from './views/DicomBidsConverter'
import { ErrorBrowser } from './views/ErrorBrowser'
import { AutoflattenManager } from './views/AutoflattenManager'
import { WorkflowsView } from './views/WorkflowsView'
import { PostPreprocBuilder } from './views/PostPreprocBuilder'
import { QCReviews } from './views/QCReviews'
import { Settings } from './views/Settings'
import { GroupRunsView } from './views/GroupRunsView'
import { useModuleStore } from './stores/module-store'

type Route =
  | 'modules' | 'analysis' | 'runs' | 'editor' | 'dashboard'
  | 'preproc' | 'convert' | 'autoflatten' | 'errors' | 'workflows'
  | 'post-preproc' | 'qc-reviews' | 'settings' | 'group-runs'

function getRoute(): Route {
  const hash = window.location.hash.replace('#', '').replace('/', '')
  if (hash === 'modules') return 'modules'
  // Legacy aliases — both `composer` and `graph` now point at the
  // unified analysis composer.
  if (hash === 'analysis' || hash === 'composer' || hash === 'graph') return 'analysis'
  if (hash === 'runs') return 'runs'
  if (hash === 'editor') return 'editor'
  if (hash === 'dashboard') return 'dashboard'
  if (hash === 'preproc') return 'preproc'
  if (hash === 'convert') return 'convert'
  if (hash === 'autoflatten') return 'autoflatten'
  if (hash === 'errors') return 'errors'
  if (hash === 'workflows') return 'workflows'
  if (hash === 'post-preproc') return 'post-preproc'
  if (hash === 'qc-reviews') return 'qc-reviews'
  if (hash === 'settings') return 'settings'
  if (hash === 'group-runs') return 'group-runs'
  return 'dashboard'
}

const rootStyle: CSSProperties = {
  display: 'flex',
  minHeight: '100vh',
  margin: 0,
  padding: 0,
  fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
  backgroundColor: 'var(--bg-primary)',
  color: 'var(--text-primary)',
}

const cssVars = `
:root {
  --bg-primary: #0a0a1a;
  --bg-secondary: #111128;
  --bg-card: #1a1a2e;
  --bg-input: #16213e;
  --text-primary: #e0e0e0;
  --text-secondary: #8888aa;
  --accent-cyan: #00e5ff;
  --accent-green: #00e676;
  --accent-yellow: #ffd600;
  --accent-red: #ff1744;
  --border: #2a2a4a;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-secondary);
}

::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}

input, select, textarea, button {
  font-family: inherit;
}
`

const contentStyle: CSSProperties = {
  flex: 1,
  padding: '24px 32px',
  maxWidth: 1400,
  overflowY: 'auto',
}

export function App() {
  const [route, setRoute] = useState<Route>(getRoute)
  const load = useModuleStore((s) => s.load)

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const onHashChange = () => setRoute(getRoute())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return (
    <div style={rootStyle}>
      <style>{cssVars}</style>
      <NavBar currentRoute={route} />
      <div style={contentStyle}>
        {route === 'modules' && <ModuleBrowser />}
        {route === 'analysis' && <AnalysisComposer />}
        {route === 'runs' && <RunManager />}
        {route === 'editor' && <ModuleEditor />}
        {route === 'dashboard' && <ExperimentDashboard />}
        {route === 'preproc' && <PreprocManager />}
        {route === 'convert' && <DicomBidsConverter />}
        {route === 'autoflatten' && <AutoflattenManager />}
        {route === 'errors' && <ErrorBrowser />}
        {route === 'workflows' && <WorkflowsView />}
        {route === 'post-preproc' && <PostPreprocBuilder />}
        {route === 'qc-reviews' && <QCReviews />}
        {route === 'settings' && <Settings />}
        {route === 'group-runs' && <GroupRunsView />}
      </div>
    </div>
  )
}
