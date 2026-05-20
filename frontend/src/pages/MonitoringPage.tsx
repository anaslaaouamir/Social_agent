import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { Card, Loading, PageHeader, StatCard } from '../components/ui'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

interface PipelineService {
  status: string
  last_run?: number
  queue_size?: number
  last_scan?: number
  processed_today?: number
  last_update?: number
}

interface MonitoringData {
  accounts: number
  total_followers?: number
  platforms?: Array<{ platform: string; account_name: string; followers: number }>
  posts: Record<string, number>
  comments: Record<string, number>
  alerts: Record<string, number>
  pipeline: Record<string, PipelineService | { status: string }>
  timestamp: number
}

interface KPIs {
  total_accounts: number
  total_followers: number
  published_posts: number
  scheduled_posts: number
  avg_engagement_rate: number
  total_likes: number
  total_comments: number
  total_reach: number
  negative_comments: number
  critical_alerts: number
}

function timeAgo(ts?: number) {
  if (!ts) return '-'
  const diff = Math.round(Date.now() / 1000 - ts)
  if (diff < 60) return `il y a ${diff}s`
  if (diff < 3600) return `il y a ${Math.round(diff / 60)} min`
  return `il y a ${Math.round(diff / 3600)} h`
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'running' || status === 'healthy' ? 'var(--green)' : 'var(--red)'
  return <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}`, flexShrink: 0 }} />
}

export default function MonitoringPage() {
  const [data, setData] = useState<MonitoringData | null>(null)
  const [kpis, setKpis] = useState<KPIs | null>(null)
  const [kpiError, setKpiError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [history, setHistory] = useState<Array<{ t: string; followers: number; posts: number }>>([])
  const [lastRefresh, setLastRefresh] = useState(Date.now())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = async () => {
    try {
      const [ovRes, kpiRes] = await Promise.all([
        api.get('/api/monitoring/overview'),
        api.get('/api/monitoring/kpis'),
      ])
      setData(ovRes.data as MonitoringData)
      if (typeof kpiRes.data?.error === 'string') {
        setKpis(null)
        setKpiError(kpiRes.data.error)
      } else {
        setKpis(kpiRes.data as KPIs)
        setKpiError(null)
      }
      setLastRefresh(Date.now())
      setHistory(h => {
        const posts = Object.values((ovRes.data as MonitoringData).posts || {}).reduce((a, b) => a + b, 0)
        return [
          ...h.slice(-29),
          {
            t: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            followers: ovRes.data.total_followers || 0,
            posts,
          },
        ]
      })
    } catch {
      // keep UI stable even if one endpoint fails
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    intervalRef.current = setInterval(fetchData, 15000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const pipelineServices = data?.pipeline || {
    scheduler: { status: 'running' },
    publisher: { status: 'running', queue_size: 0 },
    comment_monitor: { status: 'running' },
    sentiment_worker: { status: 'running', processed_today: 0 },
    analytics_worker: { status: 'running' },
    elasticsearch: { status: 'healthy' },
    redis: { status: 'healthy' },
  }

  const serviceLabels: Record<string, string> = {
    scheduler: 'Scheduler',
    publisher: 'Publisher',
    comment_monitor: 'Comment Monitor',
    sentiment_worker: 'Sentiment Worker',
    analytics_worker: 'Analytics Worker',
    celery_monitor: 'Celery Monitor',
    elasticsearch: 'Elasticsearch',
    redis: 'Redis',
    database: 'Database',
  }

  const postStatuses = data?.posts || {}
  const commentSentiments = data?.comments || {}
  const alertSeverities = data?.alerts || {}
  const hasAccounts = (data?.accounts || 0) > 0

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200 }}>
      <PageHeader
        title="Monitoring Temps Reel"
        subtitle={`Mise a jour auto toutes les 15s · Derniere: ${new Date(lastRefresh).toLocaleTimeString('fr-FR')}`}
        actions={
          <button
            onClick={fetchData}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '7px 14px',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 600,
              background: 'rgba(108,99,255,0.12)',
              border: '1px solid rgba(108,99,255,0.25)',
              color: 'var(--accent-2)',
              cursor: 'pointer',
            }}
          >
            Rafraichir
          </button>
        }
      />

      {loading ? <Loading /> : (
        <>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '5px 12px',
            borderRadius: 999,
            marginBottom: 20,
            background: 'rgba(34,197,94,0.08)',
            border: '1px solid rgba(34,197,94,0.2)',
            fontSize: 12,
            color: 'var(--green)',
          }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--green)', boxShadow: '0 0 8px var(--green)', display: 'inline-block' }} />
            LIVE · Auto-refresh 15s
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 20 }}>
            <StatCard label="Comptes" value={kpis?.total_accounts ?? data?.accounts ?? '-'} color="var(--accent-2)" />
            <StatCard label="Total abonnes" value={(kpis?.total_followers ?? data?.total_followers ?? 0).toLocaleString()} color="var(--accent-3)" />
            <StatCard label="Posts publies" value={kpis?.published_posts ?? '-'} color="var(--green)" />
            <StatCard label="Taux d engagement" value={kpis ? `${kpis.avg_engagement_rate}%` : '-'} color="var(--yellow)" />
            <StatCard label="Alertes critiques" value={kpis?.critical_alerts ?? 0} color={(kpis?.critical_alerts ?? 0) > 0 ? 'var(--red)' : 'var(--text-3)'} />
          </div>

          {!hasAccounts && (
            <Card style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Aucun compte connecte</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                Le monitoring technique repond bien, mais il n y a pas encore de compte social connecte pour afficher les KPIs metier.
                {kpiError ? ` ${kpiError}.` : ''}
              </div>
            </Card>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 280px', gap: 14, marginBottom: 14 }}>
            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Abonnes en temps reel</div>
              <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 12 }}>
                Points toutes les 15 secondes · {history.length} mesures
              </div>
              {history.length > 1 ? (
                <ResponsiveContainer width="100%" height={140}>
                  <LineChart data={history}>
                    <XAxis dataKey="t" tick={{ fill: 'var(--text-3)', fontSize: 9 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: 'var(--text-3)', fontSize: 9 }} axisLine={false} tickLine={false} domain={['auto', 'auto']} />
                    <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} />
                    <Line type="monotone" dataKey="followers" stroke="var(--accent)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', fontSize: 12 }}>
                  En attente de donnees...
                </div>
              )}
            </Card>

            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 16 }}>Distribution des sentiments</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  { key: 'positive', label: 'Positifs', color: 'var(--green)' },
                  { key: 'negative', label: 'Negatifs', color: 'var(--red)' },
                  { key: 'toxic', label: 'Toxiques', color: '#a855f7' },
                  { key: 'spam', label: 'Spam', color: 'var(--orange)' },
                  { key: 'neutral', label: 'Neutres', color: 'var(--text-3)' },
                  { key: 'unanalyzed', label: 'Non analyses', color: 'var(--text-3)' },
                ].map(s => {
                  const count = commentSentiments[s.key] || 0
                  const total = Object.values(commentSentiments).reduce((a, b) => a + b, 0) || 1
                  const pct = Math.round((count / total) * 100)
                  return (
                    <div key={s.key}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
                        <span style={{ color: 'var(--text-2)' }}>{s.label}</span>
                        <span style={{ color: s.color, fontWeight: 600 }}>{count} ({pct}%)</span>
                      </div>
                      <div style={{ height: 4, borderRadius: 2, background: 'var(--bg-3)' }}>
                        <div style={{ height: '100%', width: `${pct}%`, borderRadius: 2, background: s.color, transition: 'width 0.5s ease' }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </Card>

            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 16 }}>Pipeline Workers</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Object.entries(pipelineServices).map(([key, svc]) => {
                  const s = svc as PipelineService
                  return (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', background: 'var(--bg-2)', borderRadius: 8 }}>
                      <StatusDot status={s.status} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 11, fontWeight: 500 }}>{serviceLabels[key] || key}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                          {s.queue_size !== undefined ? `Queue: ${s.queue_size}`
                            : s.processed_today !== undefined ? `Traites: ${s.processed_today}`
                            : s.last_run ? timeAgo(s.last_run)
                            : s.last_scan ? timeAgo(s.last_scan)
                            : s.last_update ? timeAgo(s.last_update)
                            : s.status}
                        </div>
                      </div>
                      <span style={{ fontSize: 10, color: s.status === 'running' || s.status === 'healthy' ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                        {s.status.toUpperCase()}
                      </span>
                    </div>
                  )
                })}
              </div>
            </Card>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 16 }}>Publications par statut</div>
              {Object.keys(postStatuses).length === 0 ? (
                <p style={{ fontSize: 12, color: 'var(--text-3)' }}>Aucun post</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {Object.entries(postStatuses).map(([key, count]) => (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', background: 'var(--bg-2)', borderRadius: 8 }}>
                      <span style={{ flex: 1, fontSize: 12 }}>{key}</span>
                      <span style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--font-display)' }}>{count}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 16 }}>Comptes connectes</div>
              {(data?.platforms || []).length === 0 ? (
                <p style={{ fontSize: 12, color: 'var(--text-3)' }}>Aucun compte</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {(data?.platforms || []).map((p, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: 'var(--bg-2)', borderRadius: 8 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 12, fontWeight: 500 }}>{p.account_name}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{p.platform}</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-display)', color: 'var(--accent-2)' }}>
                          {p.followers.toLocaleString()}
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)' }}>abonnes</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 16 }}>Alertes non acquittees</div>
              {Object.keys(alertSeverities).length === 0 ? (
                <p style={{ fontSize: 12, color: 'var(--text-3)' }}>Aucune alerte active</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {Object.entries(alertSeverities).map(([key, count]) => (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 8, background: 'var(--bg-2)' }}>
                      <span style={{ flex: 1, fontSize: 12 }}>{key}</span>
                      <span style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-display)' }}>{count}</span>
                    </div>
                  ))}
                </div>
              )}

              {kpis && (
                <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>KPIs globaux</div>
                  {[
                    { label: 'Total likes', value: kpis.total_likes.toLocaleString() },
                    { label: 'Total comments', value: kpis.total_comments.toLocaleString() },
                    { label: 'Portee totale', value: kpis.total_reach.toLocaleString() },
                    { label: 'Comments negatifs', value: kpis.negative_comments.toString(), color: 'var(--red)' },
                  ].map(item => (
                    <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                      <span style={{ color: 'var(--text-3)' }}>{item.label}</span>
                      <span style={{ fontWeight: 600, color: item.color || 'var(--text)' }}>{item.value}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
