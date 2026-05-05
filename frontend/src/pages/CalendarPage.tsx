import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { calendarApi } from '../lib/api'
import { useAppStore } from '../store'
import { AccountScopeTabs, Badge, Btn, Card, Loading, PageHeader, PlatformIcon } from '../components/ui'

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate()
}

function getFirstDayOfMonth(year: number, month: number) {
  return new Date(year, month, 1).getDay()
}

const MONTHS = ['Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre']
const DAYS = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam']

export default function CalendarPage() {
  const { accounts, selectedAccount, setSelectedAccount } = useAppStore()
  const navigate = useNavigate()
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [events, setEvents] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedDay, setSelectedDay] = useState<number | null>(null)
  const [showAllEvents, setShowAllEvents] = useState(false)

  useEffect(() => {
    const start = new Date(year, month, 1).getTime() / 1000
    const end = new Date(year, month + 1, 0, 23, 59, 59).getTime() / 1000
    setLoading(true)
    calendarApi.get(start, end, selectedAccount?.id)
      .then((r) => setEvents(r.data))
      .catch(() => setEvents([]))
      .finally(() => setLoading(false))
  }, [year, month, selectedAccount?.id])

  const prevMonth = () => {
    if (month === 0) {
      setYear((y) => y - 1)
      setMonth(11)
      return
    }
    setMonth((m) => m - 1)
  }

  const nextMonth = () => {
    if (month === 11) {
      setYear((y) => y + 1)
      setMonth(0)
      return
    }
    setMonth((m) => m + 1)
  }

  const daysInMonth = getDaysInMonth(year, month)
  const firstDay = getFirstDayOfMonth(year, month)

  const getEventsForDay = (day: number) => {
    return events.filter((event) => {
      if (!event.scheduled_at) return false
      const date = new Date(event.scheduled_at * 1000)
      return date.getFullYear() === year && date.getMonth() === month && date.getDate() === day
    })
  }

  const selectedEvents = selectedDay ? getEventsForDay(selectedDay) : []
  const visibleEvents = showAllEvents ? events : selectedEvents
  const accountNames = Array.from(new Set(events.map((event) => event.account_name).filter(Boolean)))

  const statusColors: Record<string, string> = {
    published: 'var(--green)',
    scheduled: 'var(--accent)',
    draft: 'var(--text-3)',
    failed: 'var(--red)',
  }

  return (
    <div style={{ padding: '28px 32px' }}>
      <PageHeader
        title="Calendrier"
        subtitle="Planification et suivi de vos publications"
        actions={<Btn onClick={() => navigate('/posts/new')}>+ Programmer un post</Btn>}
      />

      <AccountScopeTabs
        accounts={accounts}
        selectedAccount={selectedAccount}
        onChange={setSelectedAccount}
        allowAll
        allLabel="Tous les comptes"
      />

      {accountNames.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          {accountNames.map((name) => (
            <div
              key={name}
              style={{
                padding: '6px 10px',
                borderRadius: 999,
                background: 'var(--bg-1)',
                border: '1px solid var(--border)',
                fontSize: 12,
                color: 'var(--text-2)',
              }}
            >
              {name}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20 }}>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <button onClick={prevMonth} style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: 18, cursor: 'pointer', padding: '4px 8px' }}>{'<'}</button>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700 }}>
              {MONTHS[month]} {year}
            </div>
            <button onClick={nextMonth} style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: 18, cursor: 'pointer', padding: '4px 8px' }}>{'>'}</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, marginBottom: 4 }}>
            {DAYS.map((day) => (
              <div key={day} style={{ textAlign: 'center', fontSize: 11, color: 'var(--text-3)', padding: '4px 0', fontWeight: 600 }}>
                {day}
              </div>
            ))}
          </div>

          {loading ? <Loading /> : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2 }}>
              {Array.from({ length: firstDay }).map((_, i) => <div key={`empty-${i}`} />)}
              {Array.from({ length: daysInMonth }).map((_, i) => {
                const day = i + 1
                const dayEvents = getEventsForDay(day)
                const isToday = year === today.getFullYear() && month === today.getMonth() && day === today.getDate()
                const isSelected = selectedDay === day

                return (
                  <div
                    key={day}
                    onClick={() => {
                      setShowAllEvents(false)
                      setSelectedDay(isSelected ? null : day)
                    }}
                    style={{
                      minHeight: 64,
                      borderRadius: 8,
                      padding: '6px',
                      cursor: 'pointer',
                      background: isSelected ? 'rgba(108,99,255,0.12)' : isToday ? 'rgba(108,99,255,0.06)' : 'transparent',
                      border: `1px solid ${isSelected ? 'rgba(108,99,255,0.3)' : isToday ? 'rgba(108,99,255,0.15)' : 'var(--border)'}`,
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: isToday ? 700 : 500, color: isToday ? 'var(--accent-2)' : 'var(--text)', marginBottom: 4 }}>
                      {day}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      {dayEvents.slice(0, 3).map((event, index) => (
                        <div
                          key={`${event.id}-${index}`}
                          style={{
                            fontSize: 9,
                            padding: '1px 4px',
                            borderRadius: 3,
                            background: statusColors[event.status] || 'var(--accent)',
                            color: '#fff',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {event.caption_preview?.slice(0, 15) || event.content_type}
                        </div>
                      ))}
                      {dayEvents.length > 3 && <div style={{ fontSize: 9, color: 'var(--text-3)' }}>+{dayEvents.length - 3}</div>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        <div>
          {selectedDay || showAllEvents ? (
            <Card>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 8 }}>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700 }}>
                  {showAllEvents ? `Tout afficher • ${MONTHS[month]}` : `${selectedDay} ${MONTHS[month]}`}
                </div>
                <Btn size="sm" variant={showAllEvents ? 'outline' : 'ghost'} onClick={() => setShowAllEvents((curr) => !curr)}>
                  {showAllEvents ? 'Vue du jour' : 'Tout afficher'}
                </Btn>
              </div>

              {visibleEvents.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  <div style={{ fontSize: 28, marginBottom: 8 }}>[]</div>
                  <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 12 }}>Aucun post pour cette selection</p>
                  <Btn size="sm" onClick={() => navigate('/posts/new')}>Programmer un post</Btn>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {visibleEvents.map((event) => {
                    const account = accounts.find((item: any) => item.id === event.account_id)
                    return (
                      <div key={event.id} style={{ background: 'var(--bg-2)', borderRadius: 10, padding: '10px 12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            {account && <PlatformIcon platform={account.platform} size={14} />}
                            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{event.account_name}</span>
                          </div>
                          <Badge label={event.status} type={event.status === 'published' ? 'positive' : event.status === 'failed' ? 'negative' : 'neutral'} />
                        </div>
                        <div style={{ fontSize: 12, marginBottom: 4, color: 'var(--text)' }}>
                          {event.caption_preview || '(sans legende)'}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                          {event.content_type} · {event.hashtags_count} hashtags
                          {event.scheduled_at && ` · ${new Date(event.scheduled_at * 1000).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>
          ) : (
            <Card>
              <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--text-3)' }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>[]</div>
                <p style={{ fontSize: 13 }}>Cliquez sur un jour pour voir les posts</p>
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
                <Btn size="sm" variant="outline" onClick={() => setShowAllEvents(true)}>Tout afficher</Btn>
              </div>
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16, marginTop: 8 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8 }}>Ce mois :</div>
                <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-display)', marginBottom: 2 }}>
                  {events.length}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>publications programmees</div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
