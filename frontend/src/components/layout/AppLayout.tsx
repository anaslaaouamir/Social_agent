import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuthStore, useAppStore, useNotifStore } from '../../store'
import { accountsApi, alertsApi } from '../../lib/api'
import { PlatformIcon } from '../ui'
import RagFloatingPanel from '../RagFloatingPanel'

const NAV = [
  { to: '/dashboard', icon: '◈', label: 'Dashboard' },
  { to: '/accounts', icon: '⊞', label: 'Comptes & Équipe' },
  { to: '/inbox', icon: '✉', label: 'Boîte de réception' },
  { to: '/posts', icon: '◧', label: 'Publications' },
  { to: '/calendar', icon: '▦', label: 'Calendrier' },
  { to: '/media', icon: '⊟', label: 'Médiathèque' },
  { to: '/hashtags', icon: '#', label: 'Hashtags' },
  { to: '/analytics', icon: '∿', label: 'Analytics' },
  { to: '/monitoring', icon: '⬡', label: 'Monitoring' },
  { to: '/alerts', icon: '⚠', label: 'Alertes' },
  { to: '/settings', icon: '⚙', label: 'Paramètres' },
]

// Mock team members for switcher
const TEAM = [
  { id: 'u1', name: 'Vous (Admin)', avatar: 'A', role: 'admin' },
  { id: 'u2', name: 'Sara Éditeur', avatar: 'S', role: 'editor' },
]

function platformEmoji(p: string) {
  return { instagram: '📸', facebook: '📘', twitter: '🐦', linkedin: '💼', tiktok: '🎵', threads: '@' }[p] || '🌐'
}

export default function AppLayout() {
  const { user, logout } = useAuthStore()
  const { accounts, setAccounts, sidebarCollapsed, setSidebarCollapsed } = useAppStore()
  const { unreadAlerts, setUnreadAlerts } = useNotifStore()
  const navigate = useNavigate()
  const [profileOpen, setProfileOpen] = useState(false)
  const [userSwitcherOpen, setUserSwitcherOpen] = useState(false)
  const [activeUser, setActiveUser] = useState(TEAM[0])

  const userInitial = user?.full_name?.charAt(0)?.toUpperCase() || 'U'
  const userName = user?.full_name || 'Utilisateur'
  const userEmail = user?.email || ''

  useEffect(() => {
    accountsApi.list().then(r => setAccounts(r.data)).catch(() => {})
    const refreshUnreadAlerts = () => {
      alertsApi.list({ acknowledged: false, limit: 500 }).then(r => setUnreadAlerts(r.data.length)).catch(() => {})
    }
    refreshUnreadAlerts()
    const interval = window.setInterval(refreshUnreadAlerts, 30000)
    window.addEventListener('alerts:changed', refreshUnreadAlerts)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('alerts:changed', refreshUnreadAlerts)
    }
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const W = sidebarCollapsed ? 64 : 224

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{
        width: W, minWidth: W, height: '100vh',
        background: 'var(--bg-1)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
        position: 'relative', zIndex: 10,
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 14px 14px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center',
          justifyContent: sidebarCollapsed ? 'center' : 'space-between',
        }}>
          {!sidebarCollapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 30, height: 30, borderRadius: 8,
                background: 'linear-gradient(135deg, var(--accent), var(--accent-3))',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
              }}>⚡</div>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15 }}>SocialAgent</span>
            </div>
          )}
          {sidebarCollapsed && (
            <div style={{
              width: 30, height: 30, borderRadius: 8,
              background: 'linear-gradient(135deg, var(--accent), var(--accent-3))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>⚡</div>
          )}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            style={{
              background: 'none', border: 'none', color: 'var(--text-3)',
              fontSize: 14, padding: 4, borderRadius: 4, cursor: 'pointer',
              display: sidebarCollapsed ? 'none' : 'block',
            }}
          >›‹</button>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '12px 8px', overflowY: 'auto' }}>
          {NAV.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 10px', borderRadius: 8, marginBottom: 2,
                textDecoration: 'none', fontSize: 13, fontWeight: 500,
                justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                background: isActive ? 'rgba(108,99,255,0.15)' : 'transparent',
                color: isActive ? 'var(--accent-2)' : 'var(--text-2)',
                border: isActive ? '1px solid rgba(108,99,255,0.2)' : '1px solid transparent',
              })}
            >
              <span style={{ fontSize: 15, minWidth: 18, textAlign: 'center' }}>{item.icon}</span>
              {!sidebarCollapsed && <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label}</span>}
              {item.to === '/alerts' && unreadAlerts > 0 && (
                <span style={{
                  marginLeft: 'auto', background: 'var(--red)', color: '#fff',
                  borderRadius: 999, fontSize: 10, padding: '1px 6px', fontWeight: 700,
                }}>{unreadAlerts}</span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Bottom section */}
        {!sidebarCollapsed && (
          <div style={{ padding: '8px', borderTop: '1px solid var(--border)' }}>
            {/* Connected accounts summary */}
            {accounts.length > 0 && (
              <div style={{ padding: '8px 10px', marginBottom: 6, background: 'var(--bg-2)', borderRadius: 8 }}>
                <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>
                  Comptes connectés
                </div>
                {accounts.slice(0, 3).map((acc: any) => (
                  <div key={acc.id} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <PlatformIcon platform={acc.platform} size={14} />
                    <span style={{ fontSize: 12, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {acc.account_name}
                    </span>
                  </div>
                ))}
                {accounts.length > 3 && (
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>+{accounts.length - 3} autres</div>
                )}
              </div>
            )}

            {/* User switcher */}
            <div
              onClick={() => setUserSwitcherOpen(!userSwitcherOpen)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 10px', borderRadius: 8, cursor: 'pointer',
                background: userSwitcherOpen ? 'var(--bg-2)' : 'transparent',
                marginBottom: 2,
              }}
            >
              <div style={{
                width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                background: 'linear-gradient(135deg, var(--accent-3), #0284c7)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, color: '#fff',
              }}>{activeUser.avatar}</div>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{ fontSize: 11, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {activeUser.name}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-3)' }}>Changer d'utilisateur</div>
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-3)' }}>⌄</span>
            </div>

            {userSwitcherOpen && (
              <div style={{ background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--border)', marginBottom: 6, overflow: 'hidden' }}>
                {TEAM.map(u => (
                  <div
                    key={u.id}
                    onClick={() => { setActiveUser(u); setUserSwitcherOpen(false); toast_msg(`Connecté en tant que ${u.name}`) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '7px 10px', cursor: 'pointer',
                      background: activeUser.id === u.id ? 'rgba(108,99,255,0.1)' : 'transparent',
                    }}
                  >
                    <div style={{
                      width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                      background: u.role === 'admin' ? 'linear-gradient(135deg, var(--accent), var(--accent-3))' : 'var(--bg-3)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, fontWeight: 700, color: '#fff',
                    }}>{u.avatar}</div>
                    <div style={{ flex: 1, overflow: 'hidden' }}>
                      <div style={{ fontSize: 11, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.name}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{u.role}</div>
                    </div>
                    {activeUser.id === u.id && <span style={{ fontSize: 10, color: 'var(--green)' }}>✓</span>}
                  </div>
                ))}
              </div>
            )}

            {/* User pill + logout */}
            <div
              onClick={() => setProfileOpen(!profileOpen)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                background: profileOpen ? 'var(--bg-2)' : 'transparent',
              }}
            >
              <div style={{
                width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                background: 'linear-gradient(135deg, var(--accent), var(--accent-3))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700, color: '#fff',
              }}>{userInitial}</div>
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <div style={{ fontSize: 12, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{userName}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{userEmail}</div>
              </div>
            </div>
            {profileOpen && (
              <div style={{ padding: '4px 8px' }}>
                <button
                  onClick={handleLogout}
                  style={{
                    width: '100%', padding: '7px 10px',
                    background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.2)',
                    color: 'var(--red)', borderRadius: 6, fontSize: 12, fontWeight: 500, cursor: 'pointer',
                  }}
                >Se déconnecter</button>
              </div>
            )}
          </div>
        )}
      </aside>

      {/* Main content */}
      <main style={{ flex: 1, overflow: 'auto', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </main>
      <RagFloatingPanel />
    </div>
  )
}

function toast_msg(msg: string) {
  // Simple toast without import
  const t = document.createElement('div')
  t.textContent = msg
  t.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#18181f;color:#f0f0f5;border:1px solid rgba(255,255,255,0.07);padding:8px 16px;border-radius:8px;font-size:13px;z-index:9999;'
  document.body.appendChild(t)
  setTimeout(() => t.remove(), 2000)
}
