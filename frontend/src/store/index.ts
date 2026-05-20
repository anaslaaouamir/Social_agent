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

interface ResourceCacheEntry<T = any> {
  data: T
  updatedAt: number
}

interface ResourceCacheStore {
  resources: Record<string, ResourceCacheEntry>
  getResource: <T = any>(key: string) => ResourceCacheEntry<T> | null
  setResource: <T = any>(key: string, data: T) => void
  clearResource: (key: string) => void
}

export const useResourceCache = create<ResourceCacheStore>((set, get) => ({
  resources: {},
  getResource: (key) => (get().resources[key] as ResourceCacheEntry | undefined) || null,
  setResource: (key, data) => set((state) => ({
    resources: {
      ...state.resources,
      [key]: { data, updatedAt: Date.now() },
    },
  })),
  clearResource: (key) => set((state) => {
    const next = { ...state.resources }
    delete next[key]
    return { resources: next }
  }),
}))
