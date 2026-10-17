import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import Layout from './components/Layout'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './theme/ThemeContext'
import { ToastProvider } from './ui/Toast'

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

async function visit(path: string) {
  const el = document.createElement('div')
  document.body.append(el)
  const root = createRoot(el)
  await act(async () => {
    root.render(
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <MemoryRouter initialEntries={[path]}>
              <Routes>
                <Route path="/login" element={<Where />} />
                <Route element={<Layout />}>
                  <Route path="*" element={<Where />} />
                </Route>
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>,
    )
  })
  const shown = el.querySelector('[data-testid="where"]')?.textContent
  await act(async () => root.unmount())
  el.remove()
  return shown
}

beforeAll(() => {
  // jsdom has no matchMedia; the theme provider asks for it
  window.matchMedia ??= ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as never
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})
afterEach(() => localStorage.clear())

describe('pages need a login', () => {
  it.each(['/', '/library', '/7', '/anything/else'])('%s sends a visitor without a token to /login', async (path) => {
    expect(await visit(path)).toBe('/login')
  })
})
