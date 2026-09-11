/** A mapping or list edited as YAML text. It parses on blur and shows parse errors instead of applying them. */
import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { dump, load } from 'js-yaml'

interface Props {
  value: unknown
  onChange: (value: Record<string, unknown> | unknown[]) => void
  expect?: 'mapping' | 'list'
  rows?: number
  placeholder?: string
}

const area: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)',
  background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'monospace', resize: 'vertical',
}

function toText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object' && Object.keys(value as object).length === 0) return ''
  return dump(value, { noRefs: true, lineWidth: 100 }).trimEnd()
}

export function YamlField({ value, onChange, expect = 'mapping', rows = 4, placeholder }: Props) {
  const serialized = JSON.stringify(value ?? null)
  const [text, setText] = useState(() => toText(value))
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { setText(toText(value)); setError(null) }, [serialized])  // eslint-disable-line react-hooks/exhaustive-deps

  const apply = () => {
    if (!text.trim()) {
      setError(null)
      onChange(expect === 'list' ? [] : {})
      return
    }
    try {
      const parsed = load(text)
      if (expect === 'mapping' && (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed))) {
        throw new Error('expected a mapping (key: value lines)')
      }
      if (expect === 'list' && !Array.isArray(parsed)) throw new Error('expected a list')
      setError(null)
      onChange(parsed as Record<string, unknown> | unknown[])
    } catch (e) {
      setError((e as Error).message.split('\n')[0])
    }
  }

  return (
    <div>
      <textarea style={area} rows={rows} spellCheck={false} placeholder={placeholder} value={text}
        onChange={(e) => setText(e.target.value)} onBlur={apply} />
      {error && <div style={{ color: 'var(--accent-red)', fontSize: 11 }}>{error}</div>}
    </div>
  )
}
