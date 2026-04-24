/** Module Editor view — write, validate, and register modules in the browser. */
import { useEffect, useCallback, useRef } from 'react'
import type { CSSProperties } from 'react'
import { useEditorStore } from '../stores/editor-store'
import { CodeEditor } from '../components/editor/CodeEditor'
import { ModuleSidebar } from '../components/editor/ModuleSidebar'
import { StatusPanel } from '../components/editor/StatusPanel'
import { useDialog } from '../components/common/Dialog'

const containerStyle: CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 48px)',
  margin: '0 -32px',
  backgroundColor: 'var(--bg-primary)',
}

const mainStyle: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '8px 16px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  fontSize: 13,
}

const inputStyle: CSSProperties = {
  padding: '4px 8px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
}

const editorWrapper: CSSProperties = {
  flex: 1,
  overflow: 'hidden',
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
}

export function ModuleEditor() {
  const store = useEditorStore()
  const dlg = useDialog()
  const validateTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load user modules and template categories on mount
  useEffect(() => {
    store.loadUserModules()
    store.loadTemplateCategories()
  }, [])

  // Debounced validation on code change
  const handleCodeChange = useCallback((value: string) => {
    store.setCode(value)
    if (validateTimer.current) clearTimeout(validateTimer.current)
    validateTimer.current = setTimeout(() => {
      store.validate()
    }, 1000)
  }, [])

  const hasCode = store.code.length > 0

  return (
    <div style={containerStyle}>
      <ModuleSidebar
        userModules={store.userModules}
        templateCategories={store.templateCategories}
        currentName={store.currentName}
        onOpen={(name) => store.openModule(name)}
        onDelete={async (name) => {
          const ok = await dlg.confirm(
            `Delete module "${name}"?`,
            { variant: 'danger', confirmLabel: 'Delete' },
          )
          if (ok) store.deleteModule(name)
        }}
        onNewFromTemplate={(category, name) => store.newFromTemplate(category, name)}
        onNew={() => store.reset()}
      />

      <div style={mainStyle}>
        {hasCode ? (
          <>
            {/* Header bar with name/category */}
            <div style={headerStyle}>
              <label style={{ color: 'var(--text-secondary)' }}>Name:</label>
              <input
                type="text"
                value={store.currentName}
                onChange={(e) => store.setName(e.target.value)}
                style={{ ...inputStyle, width: 200 }}
                placeholder="module_name"
              />
              {store.currentCategory && (
                <span style={{
                  padding: '2px 8px',
                  fontSize: 11,
                  borderRadius: 4,
                  backgroundColor: 'rgba(0, 229, 255, 0.1)',
                  color: 'var(--accent-cyan)',
                }}>
                  {store.currentCategory}
                </span>
              )}
              {store.validation?.class_name && (
                <span style={{ color: 'var(--text-secondary)', fontSize: 12, marginLeft: 'auto' }}>
                  class {store.validation.class_name}
                </span>
              )}
              <button
                onClick={() => store.reset()}
                style={{
                  marginLeft: store.validation?.class_name ? 12 : 'auto',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: 16,
                  padding: '2px 6px',
                  lineHeight: 1,
                  borderRadius: 4,
                }}
                onMouseOver={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.backgroundColor = 'var(--bg-input)' }}
                onMouseOut={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.backgroundColor = 'transparent' }}
                title="Close editor"
              >
                &#x2715;
              </button>
            </div>

            {/* Code editor */}
            <div style={editorWrapper}>
              <CodeEditor code={store.code} onChange={handleCodeChange} />
            </div>

            {/* Status panel */}
            <StatusPanel
              validation={store.validation}
              validating={store.validating}
              saveError={store.saveError}
              saveSuccess={store.saveSuccess}
              isDirty={store.isDirty}
              onValidate={() => store.validate()}
              onSave={() => store.save()}
              onDelete={async () => {
                if (!store.currentName) return
                const ok = await dlg.confirm(
                  `Delete module "${store.currentName}"?`,
                  { variant: 'danger', confirmLabel: 'Delete' },
                )
                if (ok) store.deleteModule(store.currentName)
              }}
              hasModule={store.userModules.some((p) => p.name === store.currentName)}
            />
          </>
        ) : (
          <div style={emptyState}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>{'</>'}</div>
            <div>Select a module or create one from a template</div>
            <div style={{ fontSize: 12 }}>
              Use the sidebar to get started
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
