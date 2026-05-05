import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore, useAuthStore } from '../store'
import { analyticsApi, alertsApi, postsApi } from '../lib/api'
import { PageHeader, Card, StatCard, Loading, Btn, PlatformIcon, Badge } from '../components/ui'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'

const PLATFORMS = [
  { id: 'instagram', label: 'Instagram', color: '#e1306c' },
  { id: 'facebook', label: 'Facebook', color: '#1877f2' },
  { id: 'twitter', label: 'Twitter', color: '#1da1f2' },
  { id: 'linkedin', label: 'LinkedIn', color: '#0a66c2' },
  { id: 'tiktok', label: 'TikTok', color: '#ff0050' },
  { id: 'threads', label: 'Threads', color: '#111111' },
  { id: 'youtube', label: 'YouTube', color: '#ff0000' },
  { id: 'pinterest', label: 'Pinterest', color: '#bd081c' },
]

export default function DashboardPage() {
  const { user } = useAuthStore()
  const { accounts, selectedAccount, setSelectedAccount } = useAppStore()
  const [analytics, setAnalytics] = useState<any>(null)
  const [recentPosts, setRecentPosts] = useState<any[]>([])
  const [alerts, setAlerts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const acc = selectedAccount || accounts[0]
  const firstName = user?.full_name?.split(' ')?.[0] || 'Utilisateur'

  useEffect(() => {
    if (acc?.id) {
      setLoading(true)
      Promise.all([
        analyticsApi.overview(acc.id, 30).then(r => setAnalytics(r.data)),
        postsApi.liveList({ account_id: acc.id, limit: 5 }).then(r => setRecentPosts(r.data.items || [])),
        alertsApi.list({ acknowledged: false, limit: 5 }).then(r => setAlerts(r.data)),
      ]).finally(() => setLoading(false))
    }
  }, [acc?.id])

  const trendData = (analytics?.trends || []).slice(-14).map((item: any) => ({
    day: item.label || new Date(item.date || item.timestamp * 1000).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' }),
    reach: item.reach || 0,
    engagement: Math.round((item.engagement_rate || 0) * 1000) / 10,
  }))

  const contentTypeData = (analytics?.content_performance || []).map((item: any) => ({
    type: item.type,
    count: item.count,
    engagement: Math.round((item.avg_engagement_rate || 0) * 1000) / 10,
  }))

  if (accounts.length === 0) {
    return (
      <div style={{ padding: '40px 32px' }}>
        <PageHeader title={`Bonjour, ${firstName}`} />
        <div className="glass" style={{ borderRadius: 16, padding: 48, textAlign: 'center', marginTop: 20 }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>+</div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 22, marginBottom: 8 }}>
            Connectez vos reseaux sociaux
          </h2>
          <p style={{ color: 'var(--text-3)', marginBottom: 24, maxWidth: 400, margin: '0 auto 24px' }}>
            Commencez par connecter au moins un compte pour acceder au tableau de bord complet.
          </p>
          <Btn onClick={() => navigate('/accounts')}>Connecter un compte</Btn>
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200 }}>
      <PageHeader
        title={`Bonjour, ${firstName}`}
        subtitle="Voici l'etat de vos reseaux sociaux aujourd'hui"
        actions={<Btn onClick={() => navigate('/posts/new')}>+ Nouvelle publication</Btn>}
      />

      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {accounts.map((a: any) => (
          <button
            key={a.id}
            onClick={() => setSelectedAccount(a)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
              borderRadius: 8, border: '1px solid',
              borderColor: acc?.id === a.id ? 'rgba(108,99,255,0.4)' : 'var(--border)',
              background: acc?.id === a.id ? 'rgba(108,99,255,0.1)' : 'transparent',
              color: acc?.id === a.id ? 'var(--accent-2)' : 'var(--text-2)',
              fontSize: 13, fontWeight: 500, cursor: 'pointer',
            }}
          >
            <PlatformIcon platform={a.platform} size={16} />
            {a.account_name}
          </button>
        ))}
      </div>

      {loading ? <Loading /> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
            <StatCard
              label="Abonnes"
              value={analytics?.account?.followers?.toLocaleString() ?? acc?.followers_count?.toLocaleString() ?? '-'}
              color="var(--accent-2)"
            />
            <StatCard
              label="Taux d'engagement"
              value={analytics?.insights?.avg_engagement_rate
                ? `${(analytics.insights.avg_engagement_rate * 100).toFixed(1)}%`
                : '-'}
              color="var(--green)"
            />
            <StatCard
              label="Posts publies"
              value={analytics?.published_posts ?? '-'}
              color="var(--accent-3)"
            />
            <StatCard
              label="Alertes actives"
              value={alerts.length}
              color={alerts.length > 0 ? 'var(--red)' : 'var(--text-3)'}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginBottom: 24 }}>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Portee et engagement (14 jours)</div>
              {trendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={180}>
                  <AreaChart data={trendData}>
                    <defs>
                      <linearGradient id="gReach" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="day" tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} />
                    <Area type="monotone" dataKey="reach" stroke="var(--accent)" fill="url(#gReach)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', fontSize: 12 }}>
                  Pas encore de points de tendance reels.
                </div>
              )}
            </Card>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Engagement par type</div>
              {contentTypeData.length > 0 ? (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={contentTypeData} layout="vertical">
                    <XAxis type="number" tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="type" tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} width={64} />
                    <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="engagement" fill="var(--accent)" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', fontSize: 12 }}>
                  Aucun type de contenu reel a comparer.
                </div>
              )}
            </Card>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Card>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Publications recentes</span>
                <Btn size="sm" variant="ghost" onClick={() => navigate('/posts')}>Voir tout</Btn>
              </div>
              {recentPosts.length === 0 ? (
                <p style={{ color: 'var(--text-3)', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
                  Aucune publication
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {recentPosts.map((p: any) => (
                    <div key={p.id} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                      background: 'var(--bg-2)', borderRadius: 8,
                    }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: 6,
                        background: 'var(--bg-3)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 14, flexShrink: 0,
                      }}>
                        {p.content_type === 'video' ? 'V' : p.content_type === 'story' ? 'S' : 'P'}
                      </div>
                      <div style={{ flex: 1, overflow: 'hidden' }}>
                        <div style={{ fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {(p.caption || p.text || '')?.slice(0, 50) || '(sans legende)'}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                          {(p.content_type || p.media_type || 'post')} - {(p.likes_count ?? p.likes ?? 0)} likes - {(p.comments_count ?? 0)} commentaires
                        </div>
                      </div>
                      <Badge label={p.status || 'live'} type={p.status === 'published' ? 'positive' : p.status === 'failed' ? 'negative' : 'neutral'} />
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Alertes recentes</span>
                <Btn size="sm" variant="ghost" onClick={() => navigate('/alerts')}>Voir tout</Btn>
              </div>
              {alerts.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  <div style={{ fontSize: 24, marginBottom: 8 }}>OK</div>
                  <p style={{ color: 'var(--text-3)', fontSize: 13 }}>Aucune alerte active</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {alerts.map((a: any) => (
                    <div key={a.id} style={{
                      padding: '10px 12px', background: 'var(--bg-2)', borderRadius: 8,
                      borderLeft: `3px solid ${a.severity === 'critical' ? 'var(--red)' : a.severity === 'high' ? 'var(--orange)' : 'var(--yellow)'}`,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{a.title}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{a.description?.slice(0, 80)}...</div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div style={{ marginTop: 24 }}>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
              Connecter d'autres plateformes
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {PLATFORMS.filter(p => !accounts.some((a: any) => a.platform === p.id)).map(p => (
                <button
                  key={p.id}
                  onClick={() => navigate('/accounts')}
                  style={{
                    padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 500,
                    background: 'var(--bg-2)', border: '1px solid var(--border)',
                    color: 'var(--text-2)', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <PlatformIcon platform={p.id} size={14} />
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
