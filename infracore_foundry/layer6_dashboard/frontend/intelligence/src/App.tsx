import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@shared/store/authStore'
import { Login } from './pages/Login'
import { Search } from './pages/Search'
import { EntityProfile } from './pages/EntityProfile'
import { NetworkExplorer } from './pages/NetworkExplorer'
import { AlertsDashboard } from './pages/AlertsDashboard'
import { ReportCenter } from './pages/ReportCenter'
import CsvImport from './pages/CsvImport'
import { FocusedIntelligence } from './pages/FocusedIntelligence'
import { Navigation } from './components/Navigation'
import { ErrorBoundary } from '@shared/components/ErrorBoundary'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuth = useAuthStore((s) => s.isAuthenticated())
  const hasHydrated = useAuthStore((s) => s._hasHydrated)
  const loc = useLocation()
  if (!hasHydrated) return null
  if (!isAuth) return <Navigate to="/login" state={{ from: loc }} replace />
  return <>{children}</>
}

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white flex flex-col">
      <Navigation />
      <main className="flex-1 pt-14">
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<ProtectedRoute><AppLayout><Search /></AppLayout></ProtectedRoute>} />
        <Route path="/entity/:entityType/:entityId" element={<ProtectedRoute><AppLayout><EntityProfile /></AppLayout></ProtectedRoute>} />
        <Route path="/network/:entityType/:entityId" element={<ProtectedRoute><AppLayout><NetworkExplorer /></AppLayout></ProtectedRoute>} />
        <Route path="/alerts" element={<ProtectedRoute><AppLayout><AlertsDashboard /></AppLayout></ProtectedRoute>} />
        <Route path="/reports" element={<ProtectedRoute><AppLayout><ReportCenter /></AppLayout></ProtectedRoute>} />
        <Route path="/sources" element={<Navigate to="/imports" replace />} />
        <Route path="/imports" element={<ProtectedRoute><AppLayout><CsvImport /></AppLayout></ProtectedRoute>} />
        <Route path="/intelligence" element={<ProtectedRoute><AppLayout><FocusedIntelligence /></AppLayout></ProtectedRoute>} />
        <Route path="/intelligence/:cin" element={<ProtectedRoute><AppLayout><FocusedIntelligence /></AppLayout></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
