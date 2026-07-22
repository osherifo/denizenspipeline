/** Monaco-backed YAML editor for the composer's right panel.
 *
 * Replaces the textarea-based YAML viewer that PipelineComposer
 * and PipelineGraph each had. The editor is dumb: parent owns
 * the string and decides when to apply it. Apply / debounce
 * logic lives in the composer view + config-store.
 */

import Editor from '@monaco-editor/react'
import { useThemeStore } from '../../stores/theme-store'

interface YamlEditorProps {
  value: string
  onChange: (value: string) => void
  /** Hide the read-only border-flash when the parent knows the
   * editor is actively being typed in. Defaults to false. */
  readOnly?: boolean
  height?: string | number
}

export function YamlEditor({
  value,
  onChange,
  readOnly = false,
  height = '100%',
}: YamlEditorProps) {
  // Monaco ships its own themes; follow the app theme.
  const monacoTheme = useThemeStore((s) => s.mode) === 'light' ? 'light' : 'vs-dark'
  return (
    <Editor
      height={height}
      language="yaml"
      theme={monacoTheme}
      value={value}
      onChange={(v) => onChange(v ?? '')}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 13,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 2,
        insertSpaces: true,
        wordWrap: 'on',
        renderLineHighlight: 'line',
        padding: { top: 12 },
      }}
    />
  )
}
