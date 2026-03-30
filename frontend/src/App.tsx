import { useEffect, useState } from 'react'
import { NavBar } from './components/layout/NavBar'
import { PluginBrowser } from './views/PluginBrowser'
import { PipelineComposer } from './views/PipelineComposer'
import { RunManager } from './views/RunManager'
import { PluginEditor } from './views/PluginEditor'
import { ExperimentDashboard } from './views/ExperimentDashboard'
import { PreprocManager } from './views/PreprocManager'
import { DicomBidsConverter } from './views/DicomBidsConverter'
import { ErrorBrowser } from './views/ErrorBrowser'
import { usePluginStore } from './stores/plugin-store'

type Route = 'plugins' | 'composer' | 'runs' | 'editor' | 'dashboard' | 'preproc' | 'convert' | 'errors'

function getRoute(): Route {
  const hash = window.location.hash.replace('#', '').replace('/', '')
  if (hash === 'composer') return 'composer'
  if (hash === 'runs') return 'runs'
  if (hash === 'editor') return 'editor'
  if (hash === 'dashboard') return 'dashboard'
  if (hash === 'preproc') return 'preproc'
  if (hash === 'convert') return 'convert'
  if (hash === 'errors') return 'errors'
  return 'plugins'
}

const rootStyle: React.CSSProperties = {
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

const contentStyle: React.CSSProperties = {
  padding: '24px 32px',
  maxWidth: 1400,
  margin: '0 auto',
}

export function App() {
  const [route, setRoute] = useState<Route>(getRoute)
  const load = usePluginStore((s) => s.load)

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
        {route === 'plugins' && <PluginBrowser />}
        {route === 'composer' && <PipelineComposer />}
        {route === 'runs' && <RunManager />}
        {route === 'editor' && <PluginEditor />}
        {route === 'dashboard' && <ExperimentDashboard />}
        {route === 'preproc' && <PreprocManager />}
        {route === 'convert' && <DicomBidsConverter />}
        {route === 'errors' && <ErrorBrowser />}
      </div>
    </div>
  )
}
