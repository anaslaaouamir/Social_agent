import { useState, useEffect } from 'react'
import { analyticsApi } from '../lib/api'
import { useAppStore } from '../store'
import { PageHeader, Card, StatCard, Loading, PlatformIcon } from '../components/ui'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, RadarChart, Radar, PolarGrid, PolarAngleAxis } from 'recharts'

export default function AnalyticsPage() {
  const { accounts, selectedAccount, setSelectedAccount } = useAppStore()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [days, setDays] = useState(30)

  const acc = selectedAccount || accounts[0]

  useEffect(() => {
    if (!acc?.id) return
    setLoading(true)
    analyticsApi.overview(acc.id, days)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [acc?.id, days])

  const trendData = data?.trends || []
  const engagementTrendData = trendData.map((item: any) => ({
    ...item,
    engagement: Math.round((item.engagement_rate || 0) * 1000) / 10,
  }))

  const followersBase = Math.max(acc?.followers_count || data?.account?.followers || 1, 1)
  const platformData = [
    { platform: 'Portee', score: Math.min(100, Math.round(((trendData[trendData.length - 1]?.reach || 0) / followersBase) * 100)) },
    { platform: 'Engagement', score: Math.min(100, Math.round((data?.insights?.avg_engagement_rate || 0) * 1000)) },
    { platform: 'Croissance', score: Math.min(100, Math.round(((data?.forecast?.expected_new_followers || 0) / followersBase) * 1000)) },
    { platform: 'Contenu', score: Math.min(100, (data?.content_performance?.length || 0) * 20) },
    { platform: 'Timing', score: data?.insights?.optimal_frequency ? Math.min(100, Math.round(data.insights.optimal_frequency * 12)) : 0 },
  ]

  return (
    <div style={{ padding: '28px 32px' }}>
      <PageHeader
        title="Analytics"
        subtitle="Performance de vos reseaux sociaux"
        actions={
          <div style={{ display: 'flex', gap: 6 }}>
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => setDays(d)} style={{
                padding: '5px 12px', borderRadius: 7, fontSize: 12, fontWeight: 500, cursor: 'pointer',
                background: days === d ? 'rgba(108,99,255,0.15)' : 'transparent',
                border: `1px solid ${days === d ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
                color: days === d ? 'var(--accent-2)' : 'var(--text-2)',
              }}>{d}j</button>
            ))}
          </div>
        }
      />

      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {accounts.map((a: any) => (
          <button key={a.id} onClick={() => setSelectedAccount(a)} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
            borderRadius: 8, border: '1px solid', fontSize: 13, fontWeight: 500, cursor: 'pointer',
            borderColor: acc?.id === a.id ? 'rgba(108,99,255,0.4)' : 'var(--border)',
            background: acc?.id === a.id ? 'rgba(108,99,255,0.1)' : 'transparent',
            color: acc?.id === a.id ? 'var(--accent-2)' : 'var(--text-2)',
          }}>
            <PlatformIcon platform={a.platform} size={14} />
            {a.account_name}
          </button>
        ))}
      </div>

      {!acc ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-3)' }}>
          Connectez un compte pour voir les analytics
        </div>
      ) : loading ? <Loading /> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
            <StatCard label="Abonnes" value={data?.account?.followers?.toLocaleString() || acc.followers_count?.toLocaleString() || '-'} color="var(--accent-2)" />
            <StatCard label="Engagement moyen" value={data?.insights?.avg_engagement_rate ? `${(data.insights.avg_engagement_rate * 100).toFixed(1)}%` : '-'} color="var(--green)" />
            <StatCard label="Posts totaux" value={data?.total_posts ?? '-'} color="var(--accent-3)" />
            <StatCard label="Meilleur contenu" value={data?.insights?.best_content_type || '-'} color="var(--yellow)" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12, marginBottom: 20 }}>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Evolution des abonnes et de la portee</div>
              {trendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={trendData}>
                    <XAxis dataKey="label" tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} />
                    <Line type="monotone" dataKey="followers" stroke="var(--accent)" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="reach" stroke="var(--accent-3)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', fontSize: 12 }}>
                  Pas encore d'historique reel disponible.
                </div>
              )}
            </Card>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Score de performance</div>
              <ResponsiveContainer width="100%" height={200}>
                <RadarChart data={platformData}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis dataKey="platform" tick={{ fill: 'var(--text-3)', fontSize: 10 }} />
                  <Radar name="Score" dataKey="score" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.15} strokeWidth={2} />
                </RadarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Taux d'engagement par point d'historique</div>
              {engagementTrendData.length > 0 ? (
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={engagementTrendData}>
                    <XAxis dataKey="label" tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="engagement" fill="var(--green)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', fontSize: 12 }}>
                  Aucun engagement journalier reel pour le moment.
                </div>
              )}
            </Card>
            <Card>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Insights IA</div>
              {data?.insights ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[
                    { label: 'Meilleur type de contenu', value: data.insights.best_content_type || '-' },
                    { label: 'Frequence optimale', value: data.insights.optimal_frequency ? `${data.insights.optimal_frequency}x/semaine` : '-' },
                    { label: 'Tendance engagement', value: data.insights.engagement_trend || '-' },
                  ].map(item => (
                    <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'var(--bg-2)', borderRadius: 8 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{item.label}</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-2)' }}>{item.value}</span>
                    </div>
                  ))}
                  {data.forecast && (
                    <div style={{ padding: '10px 12px', background: 'rgba(34,197,94,0.08)', borderRadius: 8, border: '1px solid rgba(34,197,94,0.15)' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>Prevision {days}j</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--green)', fontFamily: 'var(--font-display)' }}>
                        +{data.forecast.expected_new_followers || 0}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-3)' }}>nouveaux abonnes estimes</div>
                    </div>
                  )}
                </div>
              ) : (
                <p style={{ color: 'var(--text-3)', fontSize: 13 }}>Publiez des posts pour obtenir des insights IA.</p>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
