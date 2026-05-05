import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'

import { postsApi } from '../lib/api'
import { useAppStore } from '../store'
import { PageHeader, Btn, Card, Badge, Loading, Empty, PlatformIcon, AccountScopeTabs } from '../components/ui'

const STATUS_COLORS: Record<string, string> = {
  published: 'positive', scheduled: 'neutral', draft: 'neutral',
  failed: 'negative', publishing: 'neutral', cancelled: 'negative',
  live: 'neutral',
}

const STATUS_LABELS: Record<string, string> = {
  all: 'Tous', draft: 'Brouillons', scheduled: 'Planifies', published: 'Publies', failed: 'Echoues',
}

function looksLikeVideo(post: any) {
  const mediaType = String(post.media_type || '').toLowerCase()
  const mediaUrl = String(post.media_url || '').toLowerCase()
  return mediaType === 'video' || mediaType === 'reel' || mediaType === 'reels' || mediaUrl.endsWith('.mp4') || mediaUrl.includes('.mp4?')
}

export default function PostsPage() {
  const { accounts, selectedAccount, setSelectedAccount } = useAppStore()
  const [posts, setPosts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const navigate = useNavigate()

  const acc = selectedAccount
  const uniquePlatforms = Array.from(new Set(posts.map((post) => post.account?.platform || post.platform || 'instagram')))

  const load = async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (acc?.id) params.account_id = acc.id

      if (filter === 'all') {
        const res = await postsApi.liveList(params)
        setPosts(res.data.items || [])
        if (res.data.errors?.length) {
          toast.error(`Certaines plateformes n'ont pas pu etre chargees (${res.data.errors.length})`)
        }
      } else {
        params.status = filter
        const res = await postsApi.list(params)
        setPosts(res.data)
      }
    } catch {
      toast.error('Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [acc?.id, filter])

  const handleDelete = async (id: string) => {
    if (!confirm('Supprimer ce post ?')) return
    try {
      await postsApi.delete(id)
      setPosts(p => p.filter(post => post.id !== id))
      toast.success('Post supprime')
    } catch {
      toast.error('Impossible de supprimer un post publie')
    }
  }

  const handlePublish = async (id: string) => {
    try {
      await postsApi.publish(id)
      toast.success('Publication en cours !')
      load()
    } catch {
      toast.error('Erreur de publication')
    }
  }

  return (
    <div style={{ padding: '28px 32px', minHeight: '100%', overflowY: 'auto' }}>
      <PageHeader
        title="Publications"
        subtitle={filter === 'all'
          ? `${posts.length} publication${posts.length !== 1 ? 's' : ''} en temps reel`
          : `${posts.length} post${posts.length !== 1 ? 's' : ''}`}
        actions={<Btn onClick={() => navigate('/posts/new')}>+ Nouvelle publication</Btn>}
      />

      <AccountScopeTabs
        accounts={accounts}
        selectedAccount={selectedAccount}
        onChange={setSelectedAccount}
        allowAll
        allLabel="Tous les comptes"
      />

      {uniquePlatforms.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          {uniquePlatforms.map((platform) => (
            <div
              key={platform}
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px',
                borderRadius: 999, background: 'var(--bg-1)', border: '1px solid var(--border)',
                fontSize: 12, color: 'var(--text-2)',
              }}
            >
              <PlatformIcon platform={platform} size={14} />
              {platform}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
        {Object.entries(STATUS_LABELS).map(([key, label]) => (
          <button key={key} onClick={() => setFilter(key)} style={{
            padding: '5px 12px', borderRadius: 7, fontSize: 12, fontWeight: 500, cursor: 'pointer',
            background: filter === key ? 'rgba(108,99,255,0.15)' : 'transparent',
            border: `1px solid ${filter === key ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
            color: filter === key ? 'var(--accent-2)' : 'var(--text-2)',
          }}>{label}</button>
        ))}
      </div>

      {loading ? <Loading /> : posts.length === 0 ? (
        <Empty icon="📝" title="Aucun post" desc="Connectez un compte ou creez votre premiere publication."
          action={<Btn onClick={() => navigate('/posts/new')}>Creer un post</Btn>} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {posts.map((post: any) => {
            const text = post.caption || post.text || ''
            const status = post.status || 'live'
            const when = post.scheduled_at
              ? new Date(post.scheduled_at * 1000).toLocaleString('fr-FR')
              : post.timestamp
                ? new Date(post.timestamp).toLocaleString('fr-FR')
                : 'Publie'

            return (
              <Card key={`${post.account_id || 'live'}-${post.id}`} style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
                <div style={{ width: 44, height: 44, borderRadius: 12, background: 'var(--bg-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <PlatformIcon platform={post.account?.platform || post.platform || 'instagram'} size={26} />
                </div>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Badge label={status} type={STATUS_COLORS[status] || 'default'} />
                    <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{when}</span>
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 8, color: 'var(--text-2)' }}>
                    {text.slice(0, 200)}{text.length > 200 ? '...' : ''}
                  </div>
                  {!!post.media_url && (
                    <div style={{ marginBottom: 10 }}>
                      {looksLikeVideo(post) ? (
                        <video
                          src={post.media_url}
                          controls
                          preload="metadata"
                          style={{ width: '100%', maxHeight: 340, borderRadius: 12, background: 'var(--bg-2)' }}
                        />
                      ) : (
                        <img
                          src={post.media_url}
                          alt={text || 'Media du post'}
                          style={{ width: '100%', maxHeight: 340, objectFit: 'cover', borderRadius: 12, background: 'var(--bg-2)' }}
                        />
                      )}
                    </div>
                  )}
                  {filter === 'all' && (
                    <div style={{ display: 'flex', gap: 10, fontSize: 11, color: 'var(--text-3)', marginBottom: 8 }}>
                      <span>❤ {post.likes ?? post.likes_count ?? 0}</span>
                      <span>💬 {post.comments_count ?? 0}</span>
                      <span>↗ {post.shares_count ?? 0}</span>
                    </div>
                  )}
                  {post.hashtags?.length > 0 && (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
                      {post.hashtags.slice(0, 5).map((tag: string) => (
                        <span key={tag} style={{ fontSize: 11, color: 'var(--accent-2)', background: 'rgba(108,99,255,0.08)', padding: '1px 7px', borderRadius: 999 }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {filter === 'all' && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                      {typeof post.predicted_engagement_percent === 'number' && (
                        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent-2)', background: 'rgba(108,99,255,0.08)', padding: '4px 8px', borderRadius: 999, border: '1px solid rgba(108,99,255,0.16)' }}>
                          Engagement predit {post.predicted_engagement_percent.toFixed(2)}%
                        </span>
                      )}
                      {typeof post.predicted_reach === 'number' && (
                        <span style={{ fontSize: 11, color: 'var(--text-2)', background: 'var(--bg-1)', padding: '4px 8px', borderRadius: 999, border: '1px solid var(--border)' }}>
                          Reach predit {post.predicted_reach.toLocaleString('fr-FR')}
                        </span>
                      )}
                      {typeof post.engagement_confidence === 'number' && (
                        <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                          Confiance {(post.engagement_confidence * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 6 }}>
                    {post.status === 'draft' && (
                      <Btn size="sm" onClick={() => handlePublish(post.id)}>Publier</Btn>
                    )}
                    {post.status && <Btn size="sm" variant="ghost" onClick={() => navigate(`/posts/new?edit=${post.id}`)}>Modifier</Btn>}
                    {post.status && <Btn size="sm" variant="danger" onClick={() => handleDelete(post.id)}>Supprimer</Btn>}
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
