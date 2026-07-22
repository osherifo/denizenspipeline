/** Monaco-based Python code editor. */
import Editor from '@monaco-editor/react'
import { useThemeStore } from '../../stores/theme-store'

interface CodeEditorProps {
  code: string
  onChange: (value: string) => void
}

export function CodeEditor({ code, onChange }: CodeEditorProps) {
  // Monaco ships its own themes; follow the app theme.
  const monacoTheme = useThemeStore((s) => s.mode) === 'light' ? 'light' : 'vs-dark'
  return (
    <Editor
      height="100%"
      language="python"
      theme={monacoTheme}
      value={code}
      onChange={(v) => onChange(v ?? '')}
      options={{
        minimap: { enabled: false },
        fontSize: 14,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 4,
        insertSpaces: true,
        renderLineHighlight: 'line',
        cursorBlinking: 'smooth',
        padding: { top: 12 },
      }}
    />
  )
}
