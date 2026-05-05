import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from './store'
import { authApi } from './lib/api'
import AuthLayout from './components/layout/AuthLayout'
import AppLayout from './components/layout/AppLayout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import AccountsPage from './pages/AccountsPage'
import InboxPage from './pages/InboxPage'
import PostsPage from './pages/PostsPage'
import CreatePostPage from './pages/CreatePostPage'
import MediaLibraryPage from './pages/MediaLibraryPage'
import HashtagLibraryPage from './pages/HashtagLibraryPage'
import CalendarPage from './pages/CalendarPage'
import AnalyticsPage from './pages/AnalyticsPage'
import AlertsPage from './pages/AlertsPage'
import ChatbotPage from './pages/ChatbotPage'
import MonitoringPage from './pages/MonitoringPage'
import SettingsPage from './pages/SettingsPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore(s => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function RequireGuest({ children }: { children: React.ReactNode }) {
  const token = useAuthStore(s => s.token)
  if (token) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export default function App() {
  const token = useAuthStore(s => s.token)
  const user = useAuthStore(s => s.user)
  const setUser = useAuthStore(s => s.setUser)

  useEffect(() => {
    if (!token || user) return
    authApi.me().then(r => setUser(r.data)).catch(() => setUser(null))
  }, [token, user, setUser])

  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#18181f',
            color: '#f0f0f5',
            border: '1px solid rgba(255,255,255,0.07)',
            fontFamily: 'DM Sans, sans-serif',
            fontSize: '13px',
          },
          success: { iconTheme: { primary: '#22c55e', secondary: '#0a0a0f' } },
          error: { iconTheme: { primary: '#f43f5e', secondary: '#0a0a0f' } },
        }}
      />
      <Routes>
        {/* Auth */}
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<RequireGuest><LoginPage /></RequireGuest>} />
          <Route path="/register" element={<RequireGuest><RegisterPage /></RequireGuest>} />
        </Route>

        {/* App */}
        <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/posts" element={<PostsPage />} />
          <Route path="/posts/new" element={<CreatePostPage />} />
          <Route path="/media" element={<MediaLibraryPage />} />
          <Route path="/hashtags" element={<HashtagLibraryPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/chatbot" element={<ChatbotPage />} />
          <Route path="/monitoring" element={<MonitoringPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
