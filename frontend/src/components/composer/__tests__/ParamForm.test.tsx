import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { renderWithProviders, screen, fireEvent } from '../../../test/render'
import { ParamForm } from '../ParamForm'
import type { ParamSchema } from '../../../api/types'

function Stateful({ schema, initial }: { schema: ParamSchema; initial: Record<string, unknown> }) {
  const [values, setValues] = useState(initial)
  return (
    <ParamForm
      schema={schema}
      values={values}
      onChange={(k, v) => setValues((s) => ({ ...s, [k]: v }))}
    />
  )
}

describe('<ParamForm />', () => {
  it('renders empty-state for empty schema', () => {
    renderWithProviders(<ParamForm schema={{}} values={{}} onChange={vi.fn()} />)
    expect(screen.getByText('No configurable parameters')).toBeInTheDocument()
  })

  it('renders boolean as checkbox', () => {
    const schema: ParamSchema = { use_zscore: { type: 'bool', default: true } }
    renderWithProviders(
      <ParamForm schema={schema} values={{ use_zscore: true }} onChange={vi.fn()} />,
    )
    const cb = screen.getByRole('checkbox') as HTMLInputElement
    expect(cb.checked).toBe(true)
  })

  it('boolean checkbox propagates changes', async () => {
    const onChange = vi.fn()
    const schema: ParamSchema = { use_zscore: { type: 'bool', default: false } }
    const { user } = renderWithProviders(
      <ParamForm schema={schema} values={{ use_zscore: false }} onChange={onChange} />,
    )
    await user.click(screen.getByRole('checkbox'))
    expect(onChange).toHaveBeenCalledWith('use_zscore', true)
  })

  it('renders enum as select with placeholder', () => {
    const schema: ParamSchema = { mode: { type: 'string', enum: ['fast', 'slow'] } }
    renderWithProviders(<ParamForm schema={schema} values={{}} onChange={vi.fn()} />)
    expect(screen.getByRole('option', { name: 'fast' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'slow' })).toBeInTheDocument()
  })

  it('renders required indicator', () => {
    const schema: ParamSchema = { x: { type: 'string', required: true } }
    renderWithProviders(<ParamForm schema={schema} values={{}} onChange={vi.fn()} />)
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('renders numeric input with range hints', () => {
    const schema: ParamSchema = { delay: { type: 'int', min: 0, max: 5 } }
    renderWithProviders(<ParamForm schema={schema} values={{ delay: 2 }} onChange={vi.fn()} />)
    expect(screen.getByText(/Range: 0 to 5/)).toBeInTheDocument()
  })

  it('numeric input parses to number', async () => {
    const onChange = vi.fn()
    const schema: ParamSchema = { delay: { type: 'int' } }
    const { user } = renderWithProviders(
      <ParamForm schema={schema} values={{ delay: 0 }} onChange={onChange} />,
    )
    const input = screen.getByRole('spinbutton') as HTMLInputElement
    await user.clear(input)
    await user.type(input, '7')
    expect(onChange).toHaveBeenLastCalledWith('delay', 7)
  })

  it('list input renders comma-separated', () => {
    const schema: ParamSchema = { delays: { type: 'list[int]' } }
    renderWithProviders(
      <ParamForm schema={schema} values={{ delays: [1, 2, 3] }} onChange={vi.fn()} />,
    )
    const input = screen.getByDisplayValue('1, 2, 3')
    expect(input).toBeInTheDocument()
  })

  it('list input parses comma-separated values into number arrays', () => {
    const onChange = vi.fn()
    const schema: ParamSchema = { delays: { type: 'list[int]' } }
    renderWithProviders(<ParamForm schema={schema} values={{ delays: [] }} onChange={onChange} />)
    const input = screen.getByPlaceholderText('comma-separated values') as HTMLInputElement
    fireEvent.change(input, { target: { value: '1, 2, 3' } })
    const last = onChange.mock.calls[onChange.mock.calls.length - 1]
    expect(last[0]).toBe('delays')
    expect(last[1]).toEqual([1, 2, 3])
  })

  it('description is rendered when provided', () => {
    const schema: ParamSchema = { delay: { type: 'int', description: 'TR delays in seconds' } }
    renderWithProviders(<ParamForm schema={schema} values={{}} onChange={vi.fn()} />)
    expect(screen.getByText('TR delays in seconds')).toBeInTheDocument()
  })

  it('default value is shown when value is missing', () => {
    const schema: ParamSchema = { delay: { type: 'int', default: 4 } }
    renderWithProviders(<ParamForm schema={schema} values={{}} onChange={vi.fn()} />)
    const input = screen.getByDisplayValue('4')
    expect(input).toBeInTheDocument()
  })
})
