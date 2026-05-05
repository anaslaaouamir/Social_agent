import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../lib/api'
import { useAuthStore } from '../store'
import toast from 'react-hot-toast'

export default function RegisterPage() {
  const [form, setForm] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (form.password !== form.confirm) { toast.error('Les mots de passe ne correspondent pas'); return }
    if (form.password.length < 8) { toast.error('Mot de passe trop court (min 8 caractères)'); return }
    setLoading(true)
    try {
      await authApi.register({ email: form.email, password: form.password, full_name: form.full_name })
      const tokenRes = await authApi.login(form.email, form.password)
      const { access_token, refresh_token } = tokenRes.data
      localStorage.setItem('access_token', access_token)
      const meRes = await authApi.me()
      setAuth(meRes.data, access_token, refresh_token)
      navigate('/accounts')
      toast.success('Compte créé avec succès !')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Erreur lors de l\'inscription')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="animate-fade">
      <div className="glass" style={{ borderRadius: 16, padding: '32px', marginBottom: 16 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, marginBottom: 6 }}>
          Créer un compte
        </h1>
        <p style={{ color: 'var(--text-3)', fontSize: 13, marginBottom: 28 }}>
          Commencez à gérer vos réseaux sociaux
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Nom complet</label>
            <input value={form.full_name} onChange={set('full_name')} placeholder="Votre nom" required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Email</label>
            <input type="email" value={form.email} onChange={set('email')} placeholder="vous@exemple.com" required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Mot de passe</label>
            <input type="password" value={form.password} onChange={set('password')} placeholder="Min. 8 caractères" required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Confirmer</label>
            <input type="password" value={form.confirm} onChange={set('confirm')} placeholder="Répétez le mot de passe" required />
          </div>

          <button
            type="submit" disabled={loading}
            style={{
              marginTop: 8, padding: '11px',
              background: loading ? 'var(--bg-3)' : 'linear-gradient(135deg, var(--accent), #8b5cf6)',
              border: 'none', borderRadius: 8, color: '#fff',
              fontWeight: 600, fontSize: 14, opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Création...' : 'Créer mon compte'}
          </button>
        </form>
      </div>
      <p style={{ textAlign: 'center', fontSize: 13, color: 'var(--text-3)' }}>
        Déjà un compte ?{' '}
        <Link to="/login" style={{ color: 'var(--accent-2)', textDecoration: 'none' }}>Se connecter</Link>
      </p>
    </div>
  )
}
