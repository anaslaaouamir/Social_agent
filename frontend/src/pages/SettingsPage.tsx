import { useState } from 'react'
import { api } from '../lib/api'
import { useAuthStore } from '../store'
import { PageHeader, Card, Btn, Spinner } from '../components/ui'
import toast from 'react-hot-toast'

export default function SettingsPage() {
  const { user, setAuth, token } = useAuthStore()
  const [form, setForm] = useState({ full_name: user?.full_name || '', preferred_language: user?.preferred_language || 'fr' })
  const [pwForm, setPwForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [saving, setSaving] = useState(false)
  const [savingPw, setSavingPw] = useState(false)

  const handleProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const res = await api.patch('/api/profile/', form)
      if (user && token) {
        setAuth({ ...user, ...res.data }, token, localStorage.getItem('refresh_token') || '')
      }
      toast.success('Profil mis à jour !')
    } catch {
      toast.error('Erreur de mise à jour')
    } finally {
      setSaving(false)
    }
  }

  const handlePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (pwForm.new_password !== pwForm.confirm) { toast.error('Les mots de passe ne correspondent pas'); return }
    if (pwForm.new_password.length < 8) { toast.error('Minimum 8 caractères'); return }
    setSavingPw(true)
    try {
      await api.post('/api/profile/change-password', {
        current_password: pwForm.current_password,
        new_password: pwForm.new_password,
      })
      toast.success('Mot de passe modifié !')
      setPwForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Erreur')
    } finally {
      setSavingPw(false)
    }
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 600 }}>
      <PageHeader title="Paramètres" subtitle="Gérez votre profil et vos préférences" />

      {/* Profile */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Profil utilisateur</div>
        <form onSubmit={handleProfile} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Email</label>
            <input value={user?.email || ''} disabled style={{ opacity: 0.5 }} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Nom complet</label>
            <input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} placeholder="Votre nom" required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Langue préférée</label>
            <select value={form.preferred_language} onChange={e => setForm(f => ({ ...f, preferred_language: e.target.value }))}>
              <option value="fr">Français</option>
              <option value="ar">Arabe</option>
              <option value="en">Anglais</option>
            </select>
          </div>
          <Btn type="submit" disabled={saving} style={{ alignSelf: 'flex-start' }}>
            {saving ? <Spinner /> : 'Enregistrer'}
          </Btn>
        </form>
      </Card>

      {/* Password */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Changer le mot de passe</div>
        <form onSubmit={handlePassword} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Mot de passe actuel</label>
            <input type="password" value={pwForm.current_password} onChange={e => setPwForm(f => ({ ...f, current_password: e.target.value }))} required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Nouveau mot de passe</label>
            <input type="password" value={pwForm.new_password} onChange={e => setPwForm(f => ({ ...f, new_password: e.target.value }))} required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Confirmer</label>
            <input type="password" value={pwForm.confirm} onChange={e => setPwForm(f => ({ ...f, confirm: e.target.value }))} required />
          </div>
          <Btn type="submit" disabled={savingPw} style={{ alignSelf: 'flex-start' }}>
            {savingPw ? <Spinner /> : 'Changer le mot de passe'}
          </Btn>
        </form>
      </Card>

      {/* Danger zone */}
      <Card style={{ border: '1px solid rgba(244,63,94,0.2)', background: 'rgba(244,63,94,0.03)' }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--red)' }}>Zone dangereuse</div>
        <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>
          La suppression de votre compte est irréversible. Toutes vos données seront effacées.
        </p>
        <Btn variant="danger" onClick={() => toast.error('Cette fonctionnalité n\'est pas encore disponible')}>
          Supprimer mon compte
        </Btn>
      </Card>
    </div>
  )
}
