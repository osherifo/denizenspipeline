import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

interface ProvidersProps {
  children: ReactNode
  route?: string
}

function Providers({ children, route = '/' }: ProvidersProps) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

export function renderWithProviders(
  ui: ReactElement,
  opts: { route?: string } & Omit<RenderOptions, 'wrapper'> = {},
) {
  const { route, ...rest } = opts
  return {
    user: userEvent.setup(),
    ...render(ui, {
      wrapper: ({ children }) => <Providers route={route}>{children}</Providers>,
      ...rest,
    }),
  }
}

export { screen, within, waitFor, fireEvent } from '@testing-library/react'
export { default as userEvent } from '@testing-library/user-event'
