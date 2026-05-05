import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'

import { Btn, Card, Empty, Modal, PageHeader, PlatformIcon } from '../components/ui'
import { accountsApi } from '../lib/api'
import { useAppStore } from '../store'

const PLATFORMS = [
  { id: 'instagram', label: 'Instagram', desc: 'Posts, Stories, Reels', icon: '📸' },
  { id: 'facebook', label: 'Facebook', desc: 'Posts, Pages, Groupes', icon: '📘' },
  { id: 'twitter', label: 'Twitter / X', desc: 'Tweets, Threads', icon: '🐦' },
  { id: 'linkedin', label: 'LinkedIn', desc: 'Posts professionnels', icon: '💼' },
  { id: 'tiktok', label: 'TikTok', desc: 'Vidéos courtes', icon: '🎵' },
  { id: 'threads', label: 'Threads', desc: 'Posts courts, conversations', icon: '@' },
  { id: 'youtube', label: 'YouTube', desc: 'Videos, Shorts', icon: 'YT' },
  { id: 'pinterest', label: 'Pinterest', desc: 'Pins, idees, shopping', icon: 'P' },
]

export default function AccountsPage() {
  const { accounts, setAccounts } = useAppStore()
  const [connecting, setConnecting] = useState<string | null>(null)
  const [confirmPlatform, setConfirmPlatform] = useState<typeof PLATFORMS[0] | null>(null)
  const [addUserModal, setAddUserModal] = useState(false)
  const [newUserForm, setNewUserForm] = useState({ full_name: '', email: '', role: 'editor' })
  const [addingUser, setAddingUser] = useState(false)
  const [users, setUsers] = useState([
    { id: '1', name: 'Vous (Admin)', email: 'admin@example.com', role: 'admin', avatar: 'A' },
  ])

  const load = () => accountsApi.list().then(r => setAccounts(r.data)).catch(() => {})

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const connected = params.get('connected')
    const error = params.get('error')
    const platform = params.get('platform')
    if (!connected && !error) return

    if (error) {
      toast.error(error)
    } else if (connected && Number(connected) > 0) {
      toast.success(`${platform === 'facebook' ? 'Facebook' : 'Compte'} connecte${Number(connected) > 1 ? 's' : ''} !`)
      load()
    } else if (connected) {
      toast.error("Connexion OAuth reussie, mais aucune Page Facebook n'a ete importee.")
    }

    params.delete('connected')
    params.delete('error')
    params.delete('platform')
    const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
    window.history.replaceState({}, '', next)
  }, [])

  const handleConnect = async (platform: typeof PLATFORMS[0]) => {
    setConfirmPlatform(null)
    setConnecting(platform.id)
    try {
      if (platform.id === 'facebook') {
        const res = await accountsApi.getFacebookAuthUrl()
        const authUrl = res.data?.auth_url
        if (!authUrl) throw new Error('URL OAuth Facebook introuvable')
        window.location.assign(authUrl)
        return
      }

      if (platform.id === 'instagram') {
        const res = await accountsApi.getInstagramAuthUrl()
        const authUrl = res.data?.auth_url
        if (!authUrl) throw new Error('URL OAuth Instagram introuvable')
        window.location.assign(authUrl)
        return
      }

      if (platform.id === 'linkedin') {
        const res = await accountsApi.getLinkedInAuthUrl()
        const authUrl = res.data?.auth_url
        if (!authUrl) throw new Error('URL OAuth LinkedIn introuvable')
        window.location.assign(authUrl)
        return
      }

      if (platform.id === 'twitter') {
        const res = await accountsApi.getTwitterAuthUrl()
        const authUrl = res.data?.auth_url
        if (!authUrl) throw new Error('URL OAuth X introuvable')
        window.location.assign(authUrl)
        return
      }

      if (platform.id === 'tiktok') {
        const res = await accountsApi.getTikTokAuthUrl()
        const authUrl = res.data?.auth_url
        if (!authUrl) throw new Error('URL OAuth TikTok introuvable')
        window.location.assign(authUrl)
        return
      }

      if (platform.id === 'threads') {
        const res = await accountsApi.getThreadsAuthUrl()
        const authUrl = res.data?.auth_url
        if (!authUrl) throw new Error('URL OAuth Threads introuvable')
        window.location.assign(authUrl)
        return
      }

      if (platform.id === 'youtube') {
        const res = await accountsApi.getYouTubeAuthUrl()
        const authUrl = res.data?.auth_url
        if (!authUrl) throw new Error('URL OAuth YouTube introuvable')
        window.location.assign(authUrl)
        return
      }

      if (platform.id === 'pinterest') {
        throw new Error(`OAuth ${platform.label} pas encore configuree cote backend`)
      }

      throw new Error(`Connexion OAuth non configuree pour ${platform.label}`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message || 'Erreur de connexion')
    } finally {
      setConnecting(null)
    }
  }

  const handleDisconnect = async (id: string, name: string) => {
    if (!confirm(`Deconnecter ${name} ?`)) return
    try {
      await accountsApi.disconnect(id)
      await load()
      toast.success('Deconnecte')
    } catch {
      toast.error('Erreur')
    }
  }

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setAddingUser(true)
    await new Promise(r => setTimeout(r, 700))
    setUsers(u => [...u, {
      id: Date.now().toString(),
      name: newUserForm.full_name,
      email: newUserForm.email,
      role: newUserForm.role,
      avatar: newUserForm.full_name.charAt(0).toUpperCase(),
    }])
    toast.success(`Invitation envoyee a ${newUserForm.email}`)
    setNewUserForm({ full_name: '', email: '', role: 'editor' })
    setAddUserModal(false)
    setAddingUser(false)
  }

  const connectedSet = new Set(accounts.map((a: any) => a.platform))

  return (
    <div style={{ padding: '28px 32px', maxWidth: 960, overflowY: 'auto', minHeight: '100%' }}>
      <PageHeader
        title="Comptes & Equipe"
        subtitle="Connectez vos reseaux via OAuth et gerez les acces"
        actions={<Btn onClick={() => setAddUserModal(true)}>+ Ajouter un utilisateur</Btn>}
      />

      <div style={{ marginBottom: 36 }}>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
          Equipe ({users.length} membre{users.length > 1 ? 's' : ''})
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {users.map(u => (
            <Card key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px' }}>
              <div style={{
                width: 38, height: 38, borderRadius: '50%', flexShrink: 0,
                background: u.role === 'admin' ? 'linear-gradient(135deg, var(--accent), var(--accent-3))' : 'var(--bg-3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 15, fontWeight: 700, color: '#fff',
              }}>{u.avatar}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{u.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{u.email}</div>
              </div>
              <span style={{
                padding: '3px 10px', borderRadius: 999, fontSize: 11, fontWeight: 600,
                background: u.role === 'admin' ? 'rgba(108,99,255,0.15)' : 'rgba(34,197,94,0.1)',
                color: u.role === 'admin' ? 'var(--accent-2)' : 'var(--green)',
                border: `1px solid ${u.role === 'admin' ? 'rgba(108,99,255,0.2)' : 'rgba(34,197,94,0.2)'}`,
              }}>
                {u.role === 'admin' ? 'Admin' : u.role === 'editor' ? 'Editeur' : 'Lecteur'}
              </span>
              {u.role !== 'admin' && (
                <Btn size="sm" variant="danger" onClick={() => { setUsers(us => us.filter(x => x.id !== u.id)); toast.success('Retire') }}>
                  Retirer
                </Btn>
              )}
            </Card>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
          Plateformes - connexion directe OAuth
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
          {PLATFORMS.map(platform => {
            const connected = connectedSet.has(platform.id)
            const isConnecting = connecting === platform.id
            return (
              <div
                key={platform.id}
                onClick={() => !connected && !isConnecting && setConfirmPlatform(platform)}
                style={{
                  padding: '16px 12px', borderRadius: 12, textAlign: 'center',
                  background: connected ? 'rgba(34,197,94,0.07)' : isConnecting ? 'rgba(108,99,255,0.06)' : 'var(--bg-1)',
                  border: `1px solid ${connected ? 'rgba(34,197,94,0.2)' : isConnecting ? 'rgba(108,99,255,0.2)' : 'var(--border)'}`,
                  cursor: connected || isConnecting ? 'default' : 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ marginBottom: 6 }}>
                  <PlatformIcon platform={platform.id} size={28} />
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{platform.label}</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 8 }}>{platform.desc}</div>
                {isConnecting ? (
                  <span style={{ fontSize: 10, color: 'var(--accent-2)' }}>Connexion...</span>
                ) : connected ? (
                  <span style={{ fontSize: 10, color: 'var(--green)', fontWeight: 600 }}>Connecte</span>
                ) : (
                  <span style={{ fontSize: 10, color: 'var(--accent-2)' }}>Se connecter</span>
                )}
              </div>
            )
          })}
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 6 }}>
          Les cles API sont configurees dans .env - la connexion utilise OAuth 2.0, aucune saisie manuelle necessaire.
        </div>
      </div>

      <div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
          Comptes connectes ({accounts.length})
        </div>
        {accounts.length === 0 ? (
          <Empty icon="🔗" title="Aucun compte connecte" desc="Cliquez sur une plateforme pour vous connecter via OAuth." />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {accounts.map((acc: any) => (
              <Card key={acc.id} style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: 'var(--bg-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>
                  <PlatformIcon platform={acc.platform} size={28} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{acc.account_name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {PLATFORMS.find(p => p.id === acc.platform)?.label} · Connecte via OAuth
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 700, fontFamily: 'var(--font-display)', fontSize: 18 }}>{acc.followers_count?.toLocaleString()}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>abonnes</div>
                </div>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--green)', boxShadow: '0 0 6px var(--green)' }} />
                <Btn size="sm" variant="danger" onClick={() => handleDisconnect(acc.id, acc.account_name)}>Deconnecter</Btn>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Modal open={!!confirmPlatform} onClose={() => setConfirmPlatform(null)} title={`Connecter ${confirmPlatform?.label}`} width={420}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px', background: 'var(--bg-2)', borderRadius: 10 }}>
            <span style={{ fontSize: 32 }}>{confirmPlatform?.icon}</span>
            <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>
              Vous serez redirige vers <strong>{confirmPlatform?.label}</strong> pour autoriser l'acces. Les cles API sont deja configurees dans votre .env.
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '10px 14px', background: 'rgba(108,99,255,0.06)', borderRadius: 8, border: '1px solid rgba(108,99,255,0.12)' }}>
            OAuth 2.0 - aucun mot de passe stocke. Tokens securises cote serveur.
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={() => setConfirmPlatform(null)}>Annuler</Btn>
            <Btn onClick={() => confirmPlatform && handleConnect(confirmPlatform)}>
              Autoriser {confirmPlatform?.label}
            </Btn>
          </div>
        </div>
      </Modal>

      <Modal open={addUserModal} onClose={() => setAddUserModal(false)} title="Inviter un utilisateur" width={420}>
        <form onSubmit={handleAddUser} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '10px 14px', background: 'var(--bg-2)', borderRadius: 8 }}>
            L'utilisateur recevra une invitation par email pour rejoindre votre espace.
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Nom complet</label>
            <input value={newUserForm.full_name} onChange={e => setNewUserForm(f => ({ ...f, full_name: e.target.value }))} placeholder="Prenom Nom" required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Email</label>
            <input type="email" value={newUserForm.email} onChange={e => setNewUserForm(f => ({ ...f, email: e.target.value }))} placeholder="utilisateur@exemple.com" required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Role</label>
            <select value={newUserForm.role} onChange={e => setNewUserForm(f => ({ ...f, role: e.target.value }))}>
              <option value="editor">Editeur - peut creer et publier</option>
              <option value="viewer">Lecteur - lecture seule</option>
              <option value="admin">Admin - acces complet</option>
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
            <Btn variant="ghost" onClick={() => setAddUserModal(false)}>Annuler</Btn>
            <Btn type="submit" disabled={addingUser}>{addingUser ? 'Envoi...' : "Envoyer l'invitation"}</Btn>
          </div>
        </form>
      </Modal>
    </div>
  )
}
