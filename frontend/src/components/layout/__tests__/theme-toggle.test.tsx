import { describe, it, expect } from 'vitest'
import { renderWithProviders, screen, fireEvent } from '../../../test/render'
import { NavBar } from '../NavBar'
import { useThemeStore } from '../../../stores/theme-store'

describe('light mode end-to-end', () => {
  it('toggle flips the document theme and label', () => {
    useThemeStore.setState({ mode: 'dark' })
    renderWithProviders(<NavBar currentRoute="dashboard" />)
    const btn = screen.getByRole('button', { name: /Switch to light mode/i })
    fireEvent.click(btn)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(screen.getByRole('button', { name: /Switch to dark mode/i })).toBeInTheDocument()
  })
})
