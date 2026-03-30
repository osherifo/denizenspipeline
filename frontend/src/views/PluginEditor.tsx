/** Plugin Editor view — write, validate, and register plugins in the browser. */
import { useEffect, useCallback, useRef } from 'react'
import { useEditorStore } from '../stores/editor-store'
import { CodeEditor } from '../components/editor/CodeEditor'
import { PluginSidebar } from '../components/editor/PluginSidebar'
import { StatusPanel } from '../components/editor/StatusPanel'

const containerStyle: React.CSSProperties = {
  display: 'flex',
  height: 'calc(100vh - 48px)',
  margin: '0 -32px',
  backgroundColor: 'var(--bg-primary)',
}

const mainStyle: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '8px 16px',
  backgroundColor: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  fontSize: 13,
}

const inputStyle: React.CSSProperties = {
  padding: '4px 8px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  fontFamily: 'inherit',
}

const editorWrapper: React.CSSProperties = {
  flex: 1,
  overflow: 'hidden',
}

const emptyState: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--text-secondary)',
  fontSize: 14,
  gap: 8,
}

export function PluginEditor() {
  const store = useEditorStore()
  const validateTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load user plugins and template categories on mount
  useEffect(() => {
    store.loadUserPlugins()
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
      <PluginSidebar
        userPlugins={store.userPlugins}
        templateCategories={store.templateCategories}
        currentName={store.currentName}
        onOpen={(name) => store.openPlugin(name)}
        onDelete={(name) => {
          if (confirm(`Delete plugin "${name}"?`)) {
            store.deletePlugin(name)
          }
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
                placeholder="plugin_name"
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
              onDelete={() => {
                if (store.currentName && confirm(`Delete plugin "${store.currentName}"?`)) {
                  store.deletePlugin(store.currentName)
                }
              }}
              hasPlugin={store.userPlugins.some((p) => p.name === store.currentName)}
            />
          </>
        ) : (
          <div style={emptyState}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>{'</>'}</div>
            <div>Select a plugin or create one from a template</div>
            <div style={{ fontSize: 12 }}>
              Use the sidebar to get started
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
