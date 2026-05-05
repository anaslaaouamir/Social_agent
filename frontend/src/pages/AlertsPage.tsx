import { useState, useEffect } from 'react'
import { alertsApi } from '../lib/api'
import { useNotifStore } from '../store'
import { PageHeader, Card, Btn, Badge, Loading, Empty } from '../components/ui'
import toast from 'react-hot-toast'

const SEV_COLORS: Record<string, string> = {
  critical: 'var(--red)', high: 'var(--orange)', medium: 'var(--yellow)', low: 'var(--text-3)'
}
const SEV_BG: Record<string, string> = {
  critical: 'rgba(244,63,94,0.08)', high: 'rgba(249,115,22,0.08)',
  medium: 'rgba(234,179,8,0.08)', low: 'transparent',
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'unread'>('unread')
  const { setUnreadAlerts } = useNotifStore()

  const load = async () => {
    setLoading(true)
    try {
      const params = filter === 'unread' ? { acknowledged: false } : {}
      const res = await alertsApi.list(params)
      setAlerts(res.data)
    } catch { setAlerts([]) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [filter])

  const handleAck = async (id: string) => {
    try {
      await alertsApi.acknowledge(id)
      setAlerts(a => a.map(al => al.id === id ? { ...al, is_acknowledged: true } : al))
      setUnreadAlerts(Math.max(0, alerts.filter(a => !a.is_acknowledged).length - 1))
      toast.success('Alerte acquittée')
    } catch { toast.error('Erreur') }
  }

  const handleAckAll = async () => {
    const unread = alerts.filter(a => !a.is_acknowledged)
    await Promise.all(unread.map(a => alertsApi.acknowledge(a.id).catch(() => {})))
    setAlerts(a => a.map(al => ({ ...al, is_acknowledged: true })))
    setUnreadAlerts(0)
    toast.success('Toutes les alertes acquittées')
  }

  return (
    <div style={{ padding: '28px 32px' }}>
      <PageHeader
        title="Alertes"
        subtitle="Notifications de crise et événements importants"
        actions={
          <Btn variant="ghost" onClick={handleAckAll}>✓ Tout acquitter</Btn>
        }
      />
      <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
        {(['unread', 'all'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: '5px 12px', borderRadius: 7, fontSize: 12, fontWeight: 500, cursor: 'pointer',
            background: filter === f ? 'rgba(108,99,255,0.15)' : 'transparent',
            border: `1px solid ${filter === f ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
            color: filter === f ? 'var(--accent-2)' : 'var(--text-2)',
          }}>
            {f === 'unread' ? 'Non acquittées' : 'Toutes'}
          </button>
        ))}
      </div>

      {loading ? <Loading /> : alerts.length === 0 ? (
        <Empty icon="✅" title="Aucune alerte" desc="Tout va bien ! Aucune alerte active." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {alerts.map(alert => (
            <div key={alert.id} style={{
              padding: '14px 16px', borderRadius: 12,
              background: SEV_BG[alert.severity] || 'var(--bg-1)',
              border: `1px solid ${alert.is_acknowledged ? 'var(--border)' : SEV_COLORS[alert.severity] + '40'}`,
              borderLeft: `3px solid ${SEV_COLORS[alert.severity]}`,
              opacity: alert.is_acknowledged ? 0.6 : 1,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontSize: 16 }}>
                    {alert.severity === 'critical' ? '🚨' : alert.severity === 'high' ? '⚠️' : alert.severity === 'medium' ? '⚡' : 'ℹ️'}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{alert.title}</span>
                  <Badge label={alert.severity} type={alert.severity === 'critical' || alert.severity === 'high' ? 'negative' : 'neutral'} />
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{alert.created_at?.split('T')[0]}</span>
                  {!alert.is_acknowledged && (
                    <Btn size="sm" variant="ghost" onClick={() => handleAck(alert.id)}>✓ Acquitter</Btn>
                  )}
                </div>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 4 }}>{alert.description}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Type: {alert.alert_type}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
