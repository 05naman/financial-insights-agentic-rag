import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { AuthProvider } from './context/AuthContext'
import AskPage from './pages/AskPage'
import LibraryPage from './pages/LibraryPage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import { ThemeProvider } from './theme/ThemeContext'
import ErrorBoundary from './ui/ErrorBoundary'
import { ToastProvider } from './ui/Toast'

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route element={<Layout />}>
                  <Route path="/library" element={<LibraryPage />} />
                  <Route path="/:sessionId?" element={<AskPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
