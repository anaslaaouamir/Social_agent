import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'

import { useAppStore } from '../store'
import { contentApi, hashtagsApi, mediaApi, postsApi, type HashtagGroup, type MediaItem } from '../lib/api'
import { Badge, Btn, Card, Loading, PageHeader, PlatformIcon, Spinner } from '../components/ui'

const CONTENT_TYPES = [
  { id: 'image', label: 'Image' },
  { id: 'video', label: 'Video' },
  { id: 'carousel', label: 'Carrousel' },
  { id: 'reel', label: 'Reel' },
  { id: 'story', label: 'Story' },
]

function toDatetimeLocal(value?: number | null) {
  if (!value) return ''
  const date = new Date(value * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  const year = date.getFullYear()
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

export default function CreatePostPage() {
  const { accounts, setSelectedAccount } = useAppStore()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  const isEditing = Boolean(editId)

  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([])
  const [contentType, setContentType] = useState('image')
  const [caption, setCaption] = useState('')
  const [hashtags, setHashtags] = useState<string[]>([])
  const [mediaUrls, setMediaUrls] = useState<string[]>([])
  const [scheduledAt, setScheduledAt] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loadingPost, setLoadingPost] = useState(false)
  const [generatingCaption, setGeneratingCaption] = useState(false)
  const [generatingHashtags, setGeneratingHashtags] = useState(false)

  const [showMediaLib, setShowMediaLib] = useState(false)
  const [showHashtagLib, setShowHashtagLib] = useState(false)
  const [mediaLib, setMediaLib] = useState<MediaItem[]>([])
  const [hashtagLib, setHashtagLib] = useState<HashtagGroup[]>([])
  const [activeMediaGroup, setActiveMediaGroup] = useState('Tous')
  const [activeHashtagGroupId, setActiveHashtagGroupId] = useState('')

  const [genDesc, setGenDesc] = useState('')
  const [genBrand, setGenBrand] = useState('')
  const [genTone, setGenTone] = useState('brand')
  const [captionVariants, setCaptionVariants] = useState<any[]>([])

  useEffect(() => {
    mediaApi.library.list()
      .then(setMediaLib)
      .catch(() => setMediaLib([]))
    const savedHashtags = hashtagsApi.library.list()
    setHashtagLib(savedHashtags)
    setActiveHashtagGroupId((current) => current || savedHashtags[0]?.id || '')
  }, [])

  const mediaGroups = ['Tous', ...Array.from(new Set(mediaLib.map(item => item.category || 'General')))]
  const filteredMediaLib = activeMediaGroup === 'Tous'
    ? mediaLib
    : mediaLib.filter(item => (item.category || 'General') === activeMediaGroup)
  const activeHashtagGroup = hashtagLib.find(group => group.id === activeHashtagGroupId) || hashtagLib[0] || null

  useEffect(() => {
    if (!editId) return
    setLoadingPost(true)
    postsApi.get(editId)
      .then((res) => {
        const post = res.data
        setSelectedAccounts(post.account_id ? [String(post.account_id)] : [])
        setContentType(post.content_type || 'image')
        setCaption(post.caption || '')
        setHashtags(post.hashtags || [])
        setMediaUrls(post.media_urls || [])
        setScheduledAt(toDatetimeLocal(post.scheduled_at))
        const account = accounts.find((item: any) => item.id === String(post.account_id))
        if (account) setSelectedAccount(account)
      })
      .catch(() => toast.error('Impossible de charger le post a modifier'))
      .finally(() => setLoadingPost(false))
  }, [editId, accounts, setSelectedAccount])

  const isSupportedFacebookMedia = (value: string) => {
    if (value.startsWith('data:image/') && value.includes(';base64,')) return true
    try {
      const parsed = new URL(value)
      return parsed.protocol === 'http:' || parsed.protocol === 'https:'
    } catch {
      return false
    }
  }

  const toggleAccount = (id: string) => {
    setSelectedAccounts((prev) => prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id])
  }

  const handleGenerateCaption = async () => {
    if (!genDesc) {
      toast.error('Decrivez votre contenu d abord')
      return
    }
    const platform = accounts.find((a: any) => selectedAccounts.includes(a.id))?.platform || 'instagram'
    setGeneratingCaption(true)
    try {
      const res = await contentApi.generate({
        platform,
        visual_description: genDesc,
        brand_name: genBrand,
        tone: genTone,
        languages: ['fr'],
        num_variants: 3,
      })
      setCaptionVariants(res.data.captions || [])
      if (res.data.hashtags?.length) {
        setHashtags((prev) => [...new Set([...prev, ...res.data.hashtags.slice(0, 5)])])
      }
      toast.success(`${res.data.captions?.length || 0} variantes generees`)
    } catch {
      toast.error('Erreur de generation')
    } finally {
      setGeneratingCaption(false)
    }
  }

  const handleGenerateHashtags = async () => {
    if (!caption && !genDesc) {
      toast.error('Ajoutez une legende d abord')
      return
    }
    const platform = accounts.find((a: any) => selectedAccounts.includes(a.id))?.platform || 'instagram'
    setGeneratingHashtags(true)
    try {
      const res = await hashtagsApi.generate({
        caption: caption || genDesc,
        topic: caption || genDesc,
        platform,
        n_hashtags: 6,
        languages: ['fr'],
      })
      const tags = res.data.hashtags?.slice(0, 6) || []
      setHashtags(tags)
      toast.success(`${tags.length} hashtags generes`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Erreur generation hashtags')
    } finally {
      setGeneratingHashtags(false)
    }
  }

  const handleSubmit = async () => {
    if (selectedAccounts.length === 0) {
      toast.error('Selectionnez au moins un compte')
      return
    }
    if (!caption) {
      toast.error('Ajoutez une legende')
      return
    }

    const selectedPlatformAccounts = accounts.filter((a: any) => selectedAccounts.includes(a.id))
    // if (contentType === 'story') {
    //   toast.error("Le type Story n'est pas encore pris en charge")
    //   return
    // }
    if (contentType === 'reel' && selectedPlatformAccounts.some((a: any) => a.platform !== 'instagram')) {
      toast.error('Le type Reel est pris en charge uniquement pour Instagram')
      return
    }
    if (contentType === 'carousel' && selectedPlatformAccounts.some((a: any) => a.platform === 'threads')) {
      toast.error("Le carrousel n'est pas encore pris en charge pour Threads")
      return
    }
    if (selectedPlatformAccounts.some((a: any) => a.platform === 'pinterest')) {
      if (mediaUrls.length === 0) {
        toast.error('Pinterest necessite une image (Pin)')
        return
      }
      if (contentType !== 'image' && contentType !== 'carousel') {
        toast.error('Pinterest ne prend en charge que les images pour le moment')
        return
      }
    } 

    setSubmitting(true)
    try {
      const ts = scheduledAt ? new Date(scheduledAt).getTime() / 1000 : null
      if (isEditing && editId) {
        await postsApi.update(editId, {
          content_type: contentType,
          caption,
          hashtags,
          media_urls: mediaUrls,
          scheduled_at: ts,
          status: ts ? 'scheduled' : 'draft',
        })
        toast.success('Publication mise a jour')
      } else {
        for (const accountId of selectedAccounts) {
          await postsApi.create({
            account_id: accountId,
            content_type: contentType,
            caption,
            hashtags,
            media_urls: mediaUrls,
            ...(ts ? { scheduled_at: ts } : {}),
          })
        }
        toast.success(`Publication creee sur ${selectedAccounts.length} compte(s)`)
      }

      const account = accounts.find((item: any) => item.id === selectedAccounts[0])
      if (account) setSelectedAccount(account)
      navigate('/posts')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Erreur de sauvegarde')
    } finally {
      setSubmitting(false)
    }
  }

  const addHashtag = (tag: string) => {
    const normalized = tag.startsWith('#') ? tag : `#${tag}`
    if (!hashtags.includes(normalized)) setHashtags((prev) => [...prev, normalized])
  }

  if (loadingPost) {
    return <Loading />
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1100 }}>
      <PageHeader
        title={isEditing ? 'Modifier la publication' : 'Nouvelle publication'}
        subtitle={isEditing ? 'Retrouvez vos contenus deja saisis et ajustez-les rapidement' : 'Creez et programmez vos posts sur plusieurs plateformes'}
        actions={
          <>
            <Btn variant="ghost" onClick={() => navigate('/posts')}>Annuler</Btn>
            <Btn onClick={handleSubmit} disabled={submitting}>
              {submitting ? <Spinner /> : isEditing ? 'Enregistrer' : scheduledAt ? 'Programmer' : 'Publier'}
            </Btn>
          </>
        }
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
              1. Choisir les plateformes
            </div>
            {accounts.length === 0 ? (
              <p style={{ color: 'var(--text-3)', fontSize: 13 }}>
                Aucun compte connecte. <a href="/accounts" style={{ color: 'var(--accent-2)' }}>Connecter un compte</a>
              </p>
            ) : (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {accounts.map((account: any) => {
                  const isSelected = selectedAccounts.includes(account.id)
                  const disabled = isEditing && !isSelected
                  return (
                    <button
                      key={account.id}
                      onClick={() => !disabled && toggleAccount(account.id)}
                      disabled={disabled}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '7px 12px',
                        borderRadius: 8,
                        fontSize: 12,
                        fontWeight: 500,
                        cursor: disabled ? 'not-allowed' : 'pointer',
                        border: '1px solid',
                        opacity: disabled ? 0.45 : 1,
                        background: isSelected ? 'rgba(108,99,255,0.15)' : 'transparent',
                        borderColor: isSelected ? 'rgba(108,99,255,0.4)' : 'var(--border)',
                        color: isSelected ? 'var(--accent-2)' : 'var(--text-2)',
                      }}
                    >
                      {isSelected && <span style={{ color: 'var(--green)' }}>OK</span>}
                      <PlatformIcon platform={account.platform} size={14} />
                      {account.account_name}
                    </button>
                  )
                })}
              </div>
            )}
            {isEditing && (
              <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 10 }}>
                Le compte source reste verrouille pendant la modification.
              </p>
            )}
          </Card>

          <Card>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
              2. Type de contenu
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {CONTENT_TYPES.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setContentType(item.id)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 500,
                    background: contentType === item.id ? 'rgba(108,99,255,0.15)' : 'var(--bg-2)',
                    border: `1px solid ${contentType === item.id ? 'rgba(108,99,255,0.4)' : 'var(--border)'}`,
                    color: contentType === item.id ? 'var(--accent-2)' : 'var(--text-2)',
                    cursor: 'pointer',
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </Card>

          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>
                3. Medias
              </div>
              <Btn size="sm" variant="outline" onClick={() => setShowMediaLib(!showMediaLib)}>Bibliotheque</Btn>
            </div>

            {showMediaLib && (
              <div style={{ marginBottom: 12, padding: 10, borderRadius: 10, border: '1px solid var(--border)', background: 'var(--bg-2)' }}>
                {mediaLib.length === 0 ? (
                  <p style={{ fontSize: 12, color: 'var(--text-3)', margin: 0 }}>Bibliotheque vide</p>
                ) : (
                  <>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                      {mediaGroups.map((group) => (
                        <button
                          key={group}
                          onClick={() => setActiveMediaGroup(group)}
                          style={{
                            padding: '4px 9px',
                            borderRadius: 7,
                            fontSize: 11,
                            cursor: 'pointer',
                            background: activeMediaGroup === group ? 'rgba(108,99,255,0.15)' : 'transparent',
                            border: `1px solid ${activeMediaGroup === group ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
                            color: activeMediaGroup === group ? 'var(--accent-2)' : 'var(--text-3)',
                          }}
                        >
                          {group}
                        </button>
                      ))}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, maxHeight: 220, overflowY: 'auto' }}>
                      {filteredMediaLib.map((item) => {
                        const isSelected = mediaUrls.includes(item.url)
                        return (
                          <div
                            key={item.id}
                            onClick={() => {
                              setMediaUrls((prev) => isSelected ? prev.filter(url => url !== item.url) : [...prev, item.url])
                            }}
                            title={item.name}
                            style={{
                              aspectRatio: '1',
                              borderRadius: 8,
                              overflow: 'hidden',
                              cursor: 'pointer',
                              background: 'var(--bg-1)',
                              border: '2px solid',
                              borderColor: isSelected ? 'var(--accent)' : 'transparent',
                              position: 'relative',
                            }}
                          >
                            {item.url ? <img src={item.url} alt={item.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : null}
                            {isSelected && (
                              <span style={{
                                position: 'absolute',
                                top: 6,
                                right: 6,
                                width: 18,
                                height: 18,
                                borderRadius: '50%',
                                background: 'var(--accent)',
                                color: '#fff',
                                fontSize: 11,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                              }}>
                                OK
                              </span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
                      <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{mediaUrls.length} media(s) selectionne(s)</span>
                      <Btn size="sm" variant="ghost" onClick={() => setShowMediaLib(false)}>Terminer</Btn>
                    </div>
                  </>
                )}
              </div>
            )}

            <input
              value={mediaUrls.join('\n')}
              onChange={(e) => setMediaUrls(e.target.value.split('\n').filter(Boolean))}
              placeholder="URLs des medias, une par ligne"
              style={{ minHeight: 60, resize: 'vertical' }}
            />

            {mediaUrls.length > 0 && (
              <div style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                {mediaUrls.filter(Boolean).map((url, index) => (
                  <div key={`${url}-${index}`} style={{ position: 'relative' }}>
                    <img src={url} style={{ width: 60, height: 60, borderRadius: 6, objectFit: 'cover' }} />
                    <button
                      onClick={() => setMediaUrls((prev) => prev.filter((_, itemIndex) => itemIndex !== index))}
                      style={{
                        position: 'absolute',
                        top: -4,
                        right: -4,
                        width: 16,
                        height: 16,
                        borderRadius: '50%',
                        background: 'var(--red)',
                        border: 'none',
                        color: '#fff',
                        fontSize: 10,
                        cursor: 'pointer',
                      }}
                    >
                      x
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
              4. Legende
            </div>

            <div style={{ background: 'var(--bg-2)', borderRadius: 10, padding: '12px 14px', marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--accent-2)' }}>Generer avec l IA</div>
              <textarea value={genDesc} onChange={(e) => setGenDesc(e.target.value)} placeholder="Decrivez votre image ou video" style={{ minHeight: 60, marginBottom: 8, resize: 'vertical' }} />
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <input value={genBrand} onChange={(e) => setGenBrand(e.target.value)} placeholder="Nom de la marque" style={{ flex: 1 }} />
                <select value={genTone} onChange={(e) => setGenTone(e.target.value)} style={{ flex: 1 }}>
                  <option value="brand">Brand</option>
                  <option value="fun">Fun</option>
                  <option value="informative">Informatif</option>
                  <option value="promotional">Promotionnel</option>
                  <option value="inspirational">Inspirationnel</option>
                </select>
              </div>
              <Btn size="sm" onClick={handleGenerateCaption} disabled={generatingCaption}>
                {generatingCaption ? <><Spinner /> Generation...</> : 'Generer des variantes'}
              </Btn>
            </div>

            {captionVariants.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8 }}>Choisissez une variante :</div>
                {captionVariants.map((variant, index) => (
                  <div
                    key={index}
                    onClick={() => setCaption(variant.text)}
                    style={{
                      padding: '8px 12px',
                      borderRadius: 8,
                      marginBottom: 6,
                      cursor: 'pointer',
                      background: caption === variant.text ? 'rgba(108,99,255,0.1)' : 'var(--bg-2)',
                      border: `1px solid ${caption === variant.text ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
                      fontSize: 12,
                    }}
                  >
                    <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                      <Badge label={variant.tone} />
                      <Badge label={variant.language} />
                      <Badge label={`${variant.char_count} car.`} />
                    </div>
                    {variant.text.slice(0, 120)}...
                  </div>
                ))}
              </div>
            )}

            <textarea value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Votre legende..." style={{ minHeight: 100, resize: 'vertical' }} />
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4, textAlign: 'right' }}>{caption.length} caracteres</div>
          </Card>

          <Card>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>
                5. Hashtags
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <Btn size="sm" variant="ghost" onClick={() => setShowHashtagLib(!showHashtagLib)}>Bibliotheque</Btn>
                <Btn size="sm" variant="outline" onClick={handleGenerateHashtags} disabled={generatingHashtags}>
                  {generatingHashtags ? <Spinner /> : 'IA'}
                </Btn>
              </div>
            </div>

            {showHashtagLib && (
              <div style={{ marginBottom: 12, padding: 10, borderRadius: 10, border: '1px solid var(--border)', background: 'var(--bg-2)' }}>
                {hashtagLib.length === 0 ? (
                  <p style={{ fontSize: 12, color: 'var(--text-3)', margin: 0 }}>Bibliotheque vide. Utilisez IA ou creez un groupe dans Hashtags.</p>
                ) : (
                  <>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                      {hashtagLib.map((group) => (
                        <button
                          key={group.id}
                          onClick={() => setActiveHashtagGroupId(group.id)}
                          style={{
                            padding: '4px 9px',
                            borderRadius: 7,
                            fontSize: 11,
                            cursor: 'pointer',
                            background: activeHashtagGroup?.id === group.id ? 'rgba(108,99,255,0.15)' : 'transparent',
                            border: `1px solid ${activeHashtagGroup?.id === group.id ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
                            color: activeHashtagGroup?.id === group.id ? 'var(--accent-2)' : 'var(--text-3)',
                          }}
                        >
                          {group.name}
                        </button>
                      ))}
                    </div>
                    {activeHashtagGroup && (
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                            {activeHashtagGroup.platform} - {activeHashtagGroup.topic || activeHashtagGroup.name}
                          </span>
                          <Btn size="sm" variant="ghost" onClick={() => activeHashtagGroup.hashtags.forEach(addHashtag)}>Tout ajouter</Btn>
                        </div>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {activeHashtagGroup.hashtags.map((tag) => {
                            const normalized = tag.startsWith('#') ? tag : `#${tag}`
                            const isSelected = hashtags.includes(normalized)
                            return (
                              <span
                                key={tag}
                                onClick={() => isSelected
                                  ? setHashtags((prev) => prev.filter((item) => item !== normalized))
                                  : addHashtag(tag)}
                                style={{
                                  padding: '2px 8px',
                                  borderRadius: 6,
                                  fontSize: 11,
                                  cursor: 'pointer',
                                  background: isSelected ? 'rgba(108,99,255,0.18)' : 'rgba(108,99,255,0.06)',
                                  color: 'var(--accent-2)',
                                  border: '1px solid rgba(108,99,255,0.15)',
                                }}
                              >
                                {normalized}
                              </span>
                            )
                          })}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
              {hashtags.map((tag) => (
                <span
                  key={tag}
                  style={{
                    padding: '3px 10px',
                    borderRadius: 6,
                    fontSize: 12,
                    background: 'rgba(108,99,255,0.1)',
                    color: 'var(--accent-2)',
                    border: '1px solid rgba(108,99,255,0.2)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  {tag}
                  <button onClick={() => setHashtags((prev) => prev.filter((item) => item !== tag))} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 12 }}>x</button>
                </span>
              ))}
            </div>

            <input
              placeholder="Ajouter un hashtag puis Entree"
              onKeyDown={(e) => {
                if (e.key !== 'Enter') return
                e.preventDefault()
                const value = (e.target as HTMLInputElement).value.trim()
                if (!value) return
                addHashtag(value)
                ;(e.target as HTMLInputElement).value = ''
              }}
            />
          </Card>

          <Card>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
              6. Programmation
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} style={{ flex: 1 }} />
              {scheduledAt && <Btn size="sm" variant="ghost" onClick={() => setScheduledAt('')}>Effacer</Btn>}
            </div>
            {!scheduledAt && <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>Sans date : le post restera en brouillon</p>}
          </Card>
        </div>

        <div>
          <Card style={{ position: 'sticky', top: 20 }}>
            <div style={{ fontSize: 12, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 16 }}>
              Apercu
            </div>
            <div style={{ background: 'var(--bg-2)', borderRadius: 12, padding: '14px', border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent), var(--accent-3))' }} />
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {selectedAccounts.length > 0 ? accounts.find((a: any) => a.id === selectedAccounts[0])?.account_name || 'Votre compte' : 'Votre compte'}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
                    {selectedAccounts.map((id) => {
                      const account = accounts.find((item: any) => item.id === id)
                      return account ? <PlatformIcon key={id} platform={account.platform} size={12} /> : null
                    })}
                    {scheduledAt ? ` · ${new Date(scheduledAt).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : ' · Maintenant'}
                  </div>
                </div>
              </div>

              {mediaUrls[0] ? (
                <img src={mediaUrls[0]} style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', borderRadius: 8, marginBottom: 10 }} />
              ) : (
                <div style={{ width: '100%', aspectRatio: '1', background: 'var(--bg-3)', borderRadius: 8, marginBottom: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-3)', fontSize: 32 }}>
                  {contentType === 'video' ? 'VIDEO' : contentType === 'story' ? 'STORY' : 'IMAGE'}
                </div>
              )}

              <div style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 8, wordBreak: 'break-word' }}>
                {caption || <span style={{ color: 'var(--text-3)' }}>Votre legende apparaitra ici...</span>}
              </div>

              {hashtags.length > 0 && (
                <div style={{ fontSize: 12, color: 'var(--accent-2)', lineHeight: 1.8 }}>
                  {hashtags.join(' ')}
                </div>
              )}
            </div>

            <div style={{ marginTop: 16 }}>
              <Btn onClick={handleSubmit} disabled={submitting} style={{ width: '100%', justifyContent: 'center' }}>
                {submitting ? <Spinner /> : isEditing ? 'Enregistrer les modifications' : scheduledAt ? 'Programmer' : 'Publier maintenant'}
              </Btn>
              {selectedAccounts.length > 1 && (
                <p style={{ fontSize: 11, color: 'var(--text-3)', textAlign: 'center', marginTop: 6 }}>
                  Sur {selectedAccounts.length} plateformes
                </p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
