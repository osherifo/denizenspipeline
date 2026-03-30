/** Sidebar: user plugin list + template picker. */
import { useEffect, useState } from 'react'
import type { UserPlugin } from '../../api/types'

interface PluginSidebarProps {
  userPlugins: UserPlugin[]
  templateCategories: string[]
  currentName: string
  onOpen: (name: string) => void
  onDelete: (name: string) => void
  onNewFromTemplate: (category: string, name: string) => void
  onNew: () => void
}

const sidebarStyle: React.CSSProperties = {
  width: 240,
  minWidth: 240,
  backgroundColor: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const sectionTitle: React.CSSProperties = {
  padding: '12px 16px 8px',
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--text-secondary)',
  letterSpacing: 2,
  textTransform: 'uppercase',
}

const pluginItem = (active: boolean): React.CSSProperties => ({
  padding: '8px 16px',
  fontSize: 13,
  cursor: 'pointer',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  backgroundColor: active ? 'rgba(0, 229, 255, 0.08)' : 'transparent',
  borderLeft: active ? '3px solid var(--accent-cyan)' : '3px solid transparent',
  color: active ? 'var(--accent-cyan)' : 'var(--text-primary)',
})

const badgeStyle = (registered: boolean): React.CSSProperties => ({
  fontSize: 10,
  padding: '2px 6px',
  borderRadius: 4,
  backgroundColor: registered ? 'rgba(0, 230, 118, 0.15)' : 'rgba(255, 214, 0, 0.15)',
  color: registered ? 'var(--accent-green)' : 'var(--accent-yellow)',
})

const templateBtn: React.CSSProperties = {
  padding: '6px 16px',
  fontSize: 13,
  cursor: 'pointer',
  color: 'var(--text-secondary)',
  backgroundColor: 'transparent',
  border: 'none',
  textAlign: 'left',
  fontFamily: 'inherit',
  width: '100%',
}

const newBtnStyle: React.CSSProperties = {
  margin: '8px 16px',
  padding: '8px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  border: '1px dashed var(--border)',
  borderRadius: 6,
  color: 'var(--accent-cyan)',
  cursor: 'pointer',
  fontFamily: 'inherit',
  textAlign: 'center',
}

const CATEGORY_LABELS: Record<string, string> = {
  feature_extractors: 'Feature Extractor',
  preprocessing_steps: 'Preprocessing Step',
  reporters: 'Reporter',
  analyzers: 'Analyzer',
  stimulus_loaders: 'Stimulus Loader',
  response_loaders: 'Response Loader',
  models: 'Model',
}

export function PluginSidebar({
  userPlugins,
  templateCategories,
  currentName,
  onOpen,
  onDelete,
  onNewFromTemplate,
  onNew,
}: PluginSidebarProps) {
  const [showTemplates, setShowTemplates] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [nameError, setNameError] = useState(false)

  return (
    <div style={sidebarStyle}>
      <div style={sectionTitle}>My Plugins</div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {userPlugins.map((p) => (
          <div
            key={p.name}
            style={pluginItem(currentName === p.name)}
            onClick={() => onOpen(p.name)}
          >
            <div>
              <div>{p.name}</div>
              {p.category && (
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                  {CATEGORY_LABELS[p.category] ?? p.category}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={badgeStyle(p.registered)}>
                {p.registered ? 'active' : 'saved'}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(p.name) }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  fontSize: 14,
                  padding: '0 2px',
                  lineHeight: 1,
                  borderRadius: 4,
                  opacity: 0.5,
                }}
                onMouseOver={(e) => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.color = 'var(--accent-red, #ff1744)' }}
                onMouseOut={(e) => { e.currentTarget.style.opacity = '0.5'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                title={`Delete ${p.name}`}
              >
                &#x2715;
              </button>
            </div>
          </div>
        ))}
        {userPlugins.length === 0 && (
          <div style={{ padding: '12px 16px', fontSize: 12, color: 'var(--text-secondary)' }}>
            No user plugins yet
          </div>
        )}
      </div>

      <div style={{ borderTop: '1px solid var(--border)' }}>
        <div
          style={{ ...sectionTitle, cursor: showTemplates ? 'pointer' : 'default' }}
          onClick={() => { if (showTemplates) { setShowTemplates(false); setTemplateName(''); setNameError(false) } }}
        >
          New Plugin {showTemplates && <span style={{ fontSize: 10, fontWeight: 400 }}>&#x2715;</span>}
        </div>
        {!showTemplates ? (
          <button style={newBtnStyle} onClick={() => setShowTemplates(true)}>
            + From Template
          </button>
        ) : (
          <div style={{ padding: '4px 16px 12px' }}>
            <input
              type="text"
              placeholder="plugin_name"
              value={templateName}
              onChange={(e) => { setTemplateName(e.target.value); setNameError(false) }}
              style={{
                width: '100%',
                padding: '6px 8px',
                fontSize: 12,
                backgroundColor: 'var(--bg-input)',
                border: nameError ? '1px solid var(--accent-red, #ff1744)' : '1px solid var(--border)',
                borderRadius: 4,
                color: 'var(--text-primary)',
                fontFamily: 'inherit',
                marginBottom: nameError ? 2 : 6,
              }}
              autoFocus
            />
            {nameError && (
              <div style={{ fontSize: 11, color: 'var(--accent-red, #ff1744)', marginBottom: 4 }}>
                Enter a name first
              </div>
            )}
            {templateCategories.map((cat) => (
              <button
                key={cat}
                style={templateBtn}
                onClick={() => {
                  if (templateName.trim()) {
                    onNewFromTemplate(cat, templateName.trim())
                    setShowTemplates(false)
                    setTemplateName('')
                    setNameError(false)
                  } else {
                    setNameError(true)
                  }
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-card)'
                  e.currentTarget.style.color = 'var(--accent-cyan)'
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent'
                  e.currentTarget.style.color = 'var(--text-secondary)'
                }}
              >
                {CATEGORY_LABELS[cat] ?? cat}
              </button>
            ))}
            <button
              style={{ ...templateBtn, color: 'var(--text-secondary)', fontSize: 11, marginTop: 4 }}
              onClick={() => { setShowTemplates(false); setTemplateName('') }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
