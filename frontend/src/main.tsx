import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { DialogProvider } from './components/common/Dialog'
import { AssistantPanel } from './components/agent/AssistantPanel'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DialogProvider>
      <App />
      <AssistantPanel />
    </DialogProvider>
  </StrictMode>,
)
