import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../lib/api'
import { useAuthStore } from '../store'
import toast from 'react-hot-toast'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !password) return
    setLoading(true)
    try {
      const tokenRes = await authApi.login(email, password)
      const { access_token, refresh_token } = tokenRes.data
      localStorage.setItem('access_token', access_token)
      const meRes = await authApi.me()
      setAuth(meRes.data, access_token, refresh_token)
      navigate('/dashboard')
      toast.success(`Bienvenue, ${meRes.data.full_name} !`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Identifiants incorrects')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="animate-fade">
      <div className="glass" style={{ borderRadius: 16, padding: '32px', marginBottom: 16 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, marginBottom: 6 }}>
          Connexion
        </h1>
        <p style={{ color: 'var(--text-3)', fontSize: 13, marginBottom: 28 }}>
          Accédez à votre tableau de bord
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>
              Email
            </label>
            <input
              type="email" value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="vous@exemple.com"
              required
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>
              Mot de passe
            </label>
            <input
              type="password" value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: 8, padding: '11px',
              background: loading ? 'var(--bg-3)' : 'linear-gradient(135deg, var(--accent), #8b5cf6)',
              border: 'none', borderRadius: 8, color: '#fff',
              fontWeight: 600, fontSize: 14,
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Connexion...' : 'Se connecter'}
          </button>
        </form>
      </div>

      <p style={{ textAlign: 'center', fontSize: 13, color: 'var(--text-3)' }}>
        Pas encore de compte ?{' '}
        <Link to="/register" style={{ color: 'var(--accent-2)', textDecoration: 'none' }}>
          S'inscrire
        </Link>
      </p>
    </div>
  )
}
