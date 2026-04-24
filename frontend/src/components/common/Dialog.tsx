/** Custom fmriflow-branded dialogs to replace browser-native
 *  window.alert / window.confirm / window.prompt — those prepend
 *  "localhost says:" (or whatever the origin is), which we can't
 *  change from JS.
 *
 *  Usage:
 *    const dlg = useDialog()
 *    if (await dlg.confirm('Delete run?')) ...
 *    const name = await dlg.prompt('New filename:', { defaultValue: 'copy.yaml' })
 *    await dlg.alert('Save failed: permission denied')
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

type DialogKind = 'alert' | 'confirm' | 'prompt'

interface BaseOptions {
  title?: string
  message: string
}
interface PromptOptions extends BaseOptions {
  defaultValue?: string
  placeholder?: string
}
interface ConfirmOptions extends BaseOptions {
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'default' | 'danger'
}

interface DialogState {
  kind: DialogKind
  opts: BaseOptions & Partial<PromptOptions> & Partial<ConfirmOptions>
  resolve: (value: any) => void
}

interface DialogApi {
  alert: (message: string, title?: string) => Promise<void>
  confirm: (message: string, opts?: Omit<ConfirmOptions, 'message'>) => Promise<boolean>
  prompt: (message: string, opts?: Omit<PromptOptions, 'message'>) => Promise<string | null>
}

const DialogContext = createContext<DialogApi | null>(null)

export function useDialog(): DialogApi {
  const ctx = useContext(DialogContext)
  if (!ctx) {
    throw new Error('useDialog must be called inside <DialogProvider>')
  }
  return ctx
}

const DIALOG_TITLE = 'fMRIflow'

// ── Styles ──────────────────────────────────────────────────────────────

const overlay: CSSProperties = {
  position: 'fixed', inset: 0, zIndex: 10000,
  backgroundColor: 'rgba(0, 0, 0, 0.55)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  padding: 16,
}
const card: CSSProperties = {
  backgroundColor: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  minWidth: 360,
  maxWidth: 520,
  boxShadow: '0 20px 40px rgba(0, 0, 0, 0.4)',
  overflow: 'hidden',
}
const header: CSSProperties = {
  padding: '12px 18px',
  borderBottom: '1px solid var(--border)',
  fontSize: 11,
  fontWeight: 700,
  color: 'var(--accent-cyan)',
  letterSpacing: 1.5,
  textTransform: 'uppercase',
  backgroundColor: 'var(--bg-secondary)',
}
const titleStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: 'var(--text-primary)',
  marginBottom: 8,
}
const body: CSSProperties = {
  padding: '16px 18px',
  fontSize: 12,
  lineHeight: 1.55,
  color: 'var(--text-primary)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}
const input: CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  marginTop: 12,
  fontSize: 12,
  fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--accent-cyan)',
  borderRadius: 5,
  color: 'var(--text-primary)',
  outline: 'none',
  boxSizing: 'border-box',
}
const footer: CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 8,
  padding: '12px 18px',
  borderTop: '1px solid var(--border)',
  backgroundColor: 'var(--bg-secondary)',
}
const btn = (variant: 'primary' | 'default' | 'danger'): CSSProperties => ({
  padding: '6px 18px',
  fontSize: 11,
  fontWeight: 700,
  fontFamily: 'inherit',
  borderRadius: 6,
  cursor: 'pointer',
  border:
    variant === 'primary'
      ? '1px solid var(--accent-cyan)'
      : variant === 'danger'
        ? '1px solid var(--accent-red)'
        : '1px solid var(--border)',
  backgroundColor:
    variant === 'primary'
      ? 'rgba(0, 229, 255, 0.12)'
      : variant === 'danger'
        ? 'rgba(255, 23, 68, 0.12)'
        : 'var(--bg-input)',
  color:
    variant === 'primary'
      ? 'var(--accent-cyan)'
      : variant === 'danger'
        ? 'var(--accent-red)'
        : 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.5,
})

// ── Provider ────────────────────────────────────────────────────────────

export function DialogProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DialogState | null>(null)
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)

  const open = useCallback((kind: DialogKind, opts: DialogState['opts']) => {
    return new Promise<any>((resolve) => {
      setDraft(opts.defaultValue ?? '')
      setState({ kind, opts, resolve })
    })
  }, [])

  const api: DialogApi = {
    alert: (message, title) => open('alert', { message, title }),
    confirm: (message, opts) => open('confirm', { message, ...(opts ?? {}) }),
    prompt: (message, opts) => open('prompt', { message, ...(opts ?? {}) }),
  }

  // Focus the prompt input or the primary button when a dialog opens.
  useEffect(() => {
    if (!state) return
    const t = setTimeout(() => {
      if (state.kind === 'prompt' && inputRef.current) {
        inputRef.current.focus()
        inputRef.current.select()
      }
    }, 0)
    return () => clearTimeout(t)
  }, [state])

  const dismiss = (value: any) => {
    if (!state) return
    state.resolve(value)
    setState(null)
  }

  const onConfirm = () => {
    if (!state) return
    if (state.kind === 'alert') dismiss(undefined)
    else if (state.kind === 'confirm') dismiss(true)
    else if (state.kind === 'prompt') dismiss(draft)
  }

  const onCancel = () => {
    if (!state) return
    if (state.kind === 'alert') dismiss(undefined)
    else if (state.kind === 'confirm') dismiss(false)
    else if (state.kind === 'prompt') dismiss(null)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!state) return
    if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    } else if (e.key === 'Enter' && state.kind !== 'prompt') {
      // For prompt, Enter inside the input submits (handled on the input itself).
      e.preventDefault()
      onConfirm()
    }
  }

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      onConfirm()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onCancel()
    }
  }

  return (
    <DialogContext.Provider value={api}>
      {children}
      {state && (
        <div
          style={overlay}
          role="dialog"
          aria-modal="true"
          tabIndex={-1}
          onKeyDown={onKeyDown}
          onClick={(e) => {
            if (e.target === e.currentTarget) onCancel()
          }}
        >
          <div style={card}>
            <div style={header}>{DIALOG_TITLE}</div>
            <div style={body}>
              {state.opts.title && <div style={titleStyle}>{state.opts.title}</div>}
              <div>{state.opts.message}</div>
              {state.kind === 'prompt' && (
                <input
                  ref={inputRef}
                  style={input}
                  value={draft}
                  placeholder={state.opts.placeholder}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={onInputKeyDown}
                />
              )}
            </div>
            <div style={footer}>
              {state.kind !== 'alert' && (
                <button style={btn('default')} onClick={onCancel}>
                  {state.opts.cancelLabel ?? 'Cancel'}
                </button>
              )}
              <button
                style={btn(
                  state.opts.variant === 'danger'
                    ? 'danger'
                    : state.kind === 'alert'
                      ? 'default'
                      : 'primary',
                )}
                onClick={onConfirm}
                autoFocus={state.kind !== 'prompt'}
              >
                {state.kind === 'alert'
                  ? 'OK'
                  : state.opts.confirmLabel ?? (state.kind === 'prompt' ? 'OK' : 'Confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </DialogContext.Provider>
  )
}
