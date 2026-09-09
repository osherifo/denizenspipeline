import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { NavBar } from './components/layout/NavBar'
import { ModuleBrowser } from './views/ModuleBrowser'
import { AnalysisComposer } from './views/AnalysisComposer'
import { RunManager } from './views/RunManager'
import { ModuleEditor } from './views/ModuleEditor'
import { ExperimentDashboard } from './views/ExperimentDashboard'
import { PreprocView } from './views/PreprocView'
import { DicomBidsConverter } from './views/DicomBidsConverter'
import { ErrorBrowser } from './views/ErrorBrowser'
import { AutoflattenManager } from './views/AutoflattenManager'
import { WorkflowsView } from './views/WorkflowsView'
import { QCReviews } from './views/QCReviews'
import { Settings } from './views/Settings'
import { GroupRunsView } from './views/GroupRunsView'
import { StudyRunsView } from './views/StudyRunsView'
import { HubView } from './views/HubView'
import { useModuleStore } from './stores/module-store'

type Route =
  | 'modules' | 'analysis' | 'runs' | 'editor' | 'dashboard'
  | 'preproc' | 'convert' | 'autoflatten' | 'errors' | 'workflows'
  | 'qc-reviews' | 'settings' | 'group-runs' | 'study-runs' | 'hub'

function getRoute(): Route {
  const hash = window.location.hash.replace('#', '').replace('/', '')
  if (hash === 'modules') return 'modules'
  // Legacy aliases — both `composer` and `graph` now point at the
  // unified analysis composer.
  if (hash === 'analysis' || hash === 'composer' || hash === 'graph') return 'analysis'
  if (hash === 'runs') return 'runs'
  if (hash === 'editor') return 'editor'
  if (hash === 'dashboard') return 'dashboard'
  // #preproc and #preproc/<tab> (build | runs | library | outputs)
  if (hash === 'preproc' || hash.startsWith('preproc/')) return 'preproc'
  // Retired tabs fold into the unified Preprocessing page.
  if (hash === 'preproc-stack' || hash === 'post-preproc') return 'preproc'
  if (hash === 'convert') return 'convert'
  if (hash === 'autoflatten') return 'autoflatten'
  if (hash === 'errors') return 'errors'
  if (hash === 'workflows') return 'workflows'
  if (hash === 'qc-reviews') return 'qc-reviews'
  if (hash === 'settings') return 'settings'
  if (hash === 'group-runs') return 'group-runs'
  if (hash === 'study-runs') return 'study-runs'
  if (hash === 'hub') return 'hub'
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
/* Dark is the default theme; the light palette below overrides it when
   <html data-theme="light"> is set (see stores/theme-store.ts). Because the
   whole UI is styled through these variables, a theme is just this block. */
:root, :root[data-theme="dark"] {
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
  /* Contrast colour for text/icons sitting ON an accent-filled surface.
     In dark mode accents are bright, so near-black reads best. */
  --on-accent: #0a0a1a;
  /* Raised chrome sitting ON a --bg-secondary surface (e.g. an expanded
     sidebar group header) — must read as distinct from --bg-secondary. */
  --bg-elevated: #1e1e3a;
}

:root[data-theme="light"] {
  /* Tonal separation matters more in light mode: the page is a soft grey so
     white cards/panels actually lift off it, and the border is dark enough to
     read as a real edge (a near-white border is invisible on white). */
  --bg-primary: #e8ebf2;
  --bg-secondary: #f4f6fa;
  --bg-card: #ffffff;
  --bg-input: #ffffff;
  --text-primary: #1c2030;
  --text-secondary: #545d70;
  /* Accents are darkened from the dark-mode set so they keep >=4.5:1
     contrast against the light surfaces (the neon originals fail badly). */
  --accent-cyan: #026d99;
  --accent-green: #0b7a40;
  --accent-yellow: #8f5a00;
  --accent-red: #c62233;
  /* >=3:1 against BOTH the page and card surfaces, so every box actually
     reads as having an edge (a lighter border disappears on white). */
  --border: #74829d;
  --on-accent: #ffffff;
  --bg-elevated: #dfe4ee;
}

/* Pulse for a node that is actively running. Each node sets its own --pulse to
   its status colour, so one keyframes block serves every graph and both themes
   (see utils/status-colors.ts runningNodeStyle). */
@keyframes fmriflow-running-pulse {
  0%, 100% { box-shadow: 0 0 0 2px color-mix(in srgb, var(--pulse) 18%, transparent),
                         0 0 8px color-mix(in srgb, var(--pulse) 35%, transparent); }
  50%      { box-shadow: 0 0 0 5px color-mix(in srgb, var(--pulse) 30%, transparent),
                         0 0 20px color-mix(in srgb, var(--pulse) 60%, transparent); }
}

@media (prefers-reduced-motion: reduce) {
  /* Keep the emphasis, drop the movement. */
  @keyframes fmriflow-running-pulse {
    0%, 100% { box-shadow: 0 0 0 3px color-mix(in srgb, var(--pulse) 24%, transparent),
                           0 0 14px color-mix(in srgb, var(--pulse) 45%, transparent); }
  }
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
        {route === 'preproc' && <PreprocView />}
        {route === 'convert' && <DicomBidsConverter />}
        {route === 'autoflatten' && <AutoflattenManager />}
        {route === 'errors' && <ErrorBrowser />}
        {route === 'workflows' && <WorkflowsView />}
        {route === 'qc-reviews' && <QCReviews />}
        {route === 'settings' && <Settings />}
        {route === 'group-runs' && <GroupRunsView />}
        {route === 'study-runs' && <StudyRunsView />}
        {route === 'hub' && <HubView />}
      </div>
    </div>
  )
}
