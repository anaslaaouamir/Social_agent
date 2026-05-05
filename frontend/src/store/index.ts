import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '../lib/api'

interface AuthStore {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string, refreshToken: string) => void
  setUser: (user: User | null) => void
  logout: () => void
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setAuth: (user, token, refreshToken) => {
        localStorage.setItem('access_token', token)
        localStorage.setItem('refresh_token', refreshToken)
        set({ user, token })
      },
      setUser: (user) => set({ user }),
      logout: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ user: null, token: null })
      },
    }),
    { name: 'auth-store', partialize: (s) => ({ user: s.user, token: s.token }) }
  )
)

interface AppStore {
  accounts: any[]
  selectedAccount: any | null
  sidebarCollapsed: boolean
  setAccounts: (accounts: any[]) => void
  setSelectedAccount: (account: any | null) => void
  setSidebarCollapsed: (v: boolean) => void
}

export const useAppStore = create<AppStore>((set) => ({
  accounts: [],
  selectedAccount: null,
  sidebarCollapsed: false,
  setAccounts: (accounts) => set({ accounts }),
  setSelectedAccount: (account) => set({ selectedAccount: account }),
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
}))

interface NotifStore {
  unreadAlerts: number
  setUnreadAlerts: (n: number) => void
}

export const useNotifStore = create<NotifStore>((set) => ({
  unreadAlerts: 0,
  setUnreadAlerts: (n) => set({ unreadAlerts: n }),
}))
