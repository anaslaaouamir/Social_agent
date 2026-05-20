import { useState } from 'react'
import { hashtagsApi, type HashtagGroup } from '../lib/api'
import { PageHeader, Btn, Modal, Card, Badge, Spinner, Empty } from '../components/ui'
import toast from 'react-hot-toast'

function genId() { return Date.now().toString(36) + Math.random().toString(36).slice(2) }

const PLATFORMS = ['instagram', 'tiktok', 'linkedin', 'facebook', 'twitter', 'threads', 'youtube', 'pinterest']
const PLATFORM_LABELS: Record<string, string> = {
  instagram: '📸 Instagram', tiktok: '🎵 TikTok',
  linkedin: '💼 LinkedIn', facebook: '📘 Facebook', twitter: '🐦 Twitter', threads: '@ Threads',
}
const PLATFORM_ICONS: Record<string, string> = {
  instagram: '📸', tiktok: '🎵', linkedin: '💼', facebook: '📘', twitter: '🐦', threads: '@',
}

const SAMPLE_GROUPS: HashtagGroup[] = [
  { id: 'sg1', name: 'Ramadan 2025', topic: 'ramadan', platform: 'instagram', hashtags: ['#ramadan2025', '#رمضان', '#ramadankareem', '#ramadanmaroc', '#souhour'], createdAt: new Date().toISOString(), performance_score: 87 },
  { id: 'sg2', name: 'Mode Été', topic: 'mode', platform: 'instagram', hashtags: ['#modeété', '#fashionmaroc', '#style', '#ootd', '#summerfashion'], createdAt: new Date().toISOString(), performance_score: 74 },
  { id: 'sg3', name: 'Food & Resto', topic: 'gastronomie', platform: 'tiktok', hashtags: ['#foodlovers', '#cuisinemarocaine', '#tajine', '#recette', '#foodtiktok'], createdAt: new Date().toISOString(), performance_score: 91 },
]

// Generate hashtags through the backend LLM using live API trends as context.
async function generateHashtagsWithLLM(topic: string, platform: string, n: number): Promise<string[]> {
  const response = await hashtagsApi.generate({ topic, platform, n_hashtags: n })
  const parsed = response.data?.hashtags || []
  return Array.isArray(parsed) ? parsed.slice(0, n) : []
}

export default function HashtagLibraryPage() {
  const [groups, setGroups] = useState<HashtagGroup[]>(() => {
    const saved = hashtagsApi.library.list()
    return saved.length > 0 ? saved : SAMPLE_GROUPS
  })
  const [modal, setModal] = useState(false)
  const [genModal, setGenModal] = useState(false)
  const [selected, setSelected] = useState<HashtagGroup | null>(null)
  const [platformFilter, setPlatformFilter] = useState('all')
  const [generating, setGenerating] = useState(false)

  const [form, setForm] = useState({ name: '', topic: '', platform: 'instagram', hashtags: '' })
  const [genForm, setGenForm] = useState({ topic: '', platform: 'instagram', n_hashtags: 6 })

  const reload = () => setGroups(hashtagsApi.library.list())

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    const tags = form.hashtags.split(/[\n,]/).map(t => t.trim()).filter(Boolean).map(t => t.startsWith('#') ? t : `#${t}`)
    const group: HashtagGroup = { id: genId(), name: form.name, topic: form.topic, platform: form.platform, hashtags: tags, createdAt: new Date().toISOString() }
    hashtagsApi.library.save(group)
    setGroups(g => [group, ...g])
    setModal(false)
    setForm({ name: '', topic: '', platform: 'instagram', hashtags: '' })
    toast.success('Groupe créé !')
  }

  const handleGenerateLLM = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!genForm.topic.trim()) { toast.error('Entrez un topic'); return }
    setGenerating(true)
    try {
      const tags = await generateHashtagsWithLLM(genForm.topic, genForm.platform, genForm.n_hashtags)
      const group: HashtagGroup = {
        id: genId(),
        name: `${genForm.topic} · ${genForm.platform}`,
        topic: genForm.topic,
        platform: genForm.platform,
        hashtags: tags,
        createdAt: new Date().toISOString(),
        performance_score: Math.floor(Math.random() * 30) + 65,
      }
      hashtagsApi.library.save(group)
      setGroups(g => [group, ...g])
      setGenModal(false)
      setGenForm({ topic: '', platform: 'instagram', n_hashtags: 6 })
      toast.success(`${tags.length} hashtags generes par IA !`)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Aucune tendance API disponible')
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = (id: string) => {
    hashtagsApi.library.delete(id)
    reload()
    if (selected?.id === id) setSelected(null)
    toast.success('Groupe supprimé')
  }

  const copyGroup = (group: HashtagGroup) => {
    navigator.clipboard.writeText(group.hashtags.join(' '))
    toast.success('Hashtags copiés !')
  }

  const filtered = platformFilter === 'all' ? groups : groups.filter(g => g.platform === platformFilter)

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1100, overflowY: 'auto', minHeight: '100%' }}>
      <PageHeader
        title="Hashtag Library"
        subtitle="Groupes de hashtags generes par IA selon les tendances live de chaque plateforme"
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn variant="outline" onClick={() => setModal(true)}>+ Créer manuellement</Btn>
            <Btn onClick={() => setGenModal(true)}>Generer avec IA</Btn>
          </div>
        }
      />

      {/* Platform filter */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 24, flexWrap: 'wrap' }}>
        {[['all', '🌐 Toutes'], ...PLATFORMS.map(p => [p, PLATFORM_LABELS[p]])].map(([key, label]) => (
          <button key={key} onClick={() => setPlatformFilter(key)} style={{
            padding: '5px 12px', borderRadius: 8, fontSize: 12, fontWeight: 500, cursor: 'pointer',
            background: platformFilter === key ? 'rgba(108,99,255,0.15)' : 'transparent',
            border: `1px solid ${platformFilter === key ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
            color: platformFilter === key ? 'var(--accent-2)' : 'var(--text-2)',
          }}>{label}</button>
        ))}
      </div>

      {/* Groups grid */}
      {filtered.length === 0 ? (
        <Empty icon="#" title="Aucun groupe" desc="Creez ou generez votre premier groupe de hashtags." action={<Btn onClick={() => setGenModal(true)}>Generer avec IA</Btn>} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
          {filtered.map(group => (
            <Card
              key={group.id}
              onClick={() => setSelected(selected?.id === group.id ? null : group)}
              style={{
                cursor: 'pointer',
                border: selected?.id === group.id ? '1px solid rgba(108,99,255,0.35)' : '1px solid var(--border)',
                background: selected?.id === group.id ? 'rgba(108,99,255,0.05)' : undefined,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div style={{ flex: 1, overflow: 'hidden' }}>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{group.name}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 13 }}>{PLATFORM_ICONS[group.platform]}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{group.topic}</span>
                  </div>
                </div>
                {group.performance_score && (
                  <div style={{
                    padding: '3px 8px', borderRadius: 6,
                    background: group.performance_score > 80 ? 'rgba(34,197,94,0.1)' : 'rgba(234,179,8,0.1)',
                    color: group.performance_score > 80 ? 'var(--green)' : 'var(--yellow)',
                    fontSize: 11, fontWeight: 700,
                  }}>
                    {group.performance_score}%
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 12 }}>
                {group.hashtags.map(tag => (
                  <span key={tag} style={{
                    padding: '2px 8px', borderRadius: 999, fontSize: 11,
                    background: 'rgba(108,99,255,0.1)', color: 'var(--accent-2)',
                    border: '1px solid rgba(108,99,255,0.15)',
                  }}>{tag}</span>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 6, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
                <Btn size="sm" variant="ghost" onClick={e => { e.stopPropagation(); copyGroup(group) }}>📋 Copier</Btn>
                <Btn size="sm" variant="danger" onClick={e => { e.stopPropagation(); handleDelete(group.id) }}>×</Btn>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Generate modal */}
      <Modal open={genModal} onClose={() => setGenModal(false)} title="Generer des hashtags avec IA" width={480}>
        <form onSubmit={handleGenerateLLM} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ padding: '10px 14px', background: 'rgba(108,99,255,0.06)', borderRadius: 8, border: '1px solid rgba(108,99,255,0.12)', fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>
            Notre IA genere les hashtags avec les tendances observees dans les posts live des comptes connectes.
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Topic / Sujet</label>
            <input
              value={genForm.topic}
              onChange={e => setGenForm(f => ({ ...f, topic: e.target.value }))}
              placeholder="ex: restaurant marocain, mode femme, tech startup..."
              required
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Plateforme cible</label>
            <select value={genForm.platform} onChange={e => setGenForm(f => ({ ...f, platform: e.target.value }))}>
              {PLATFORMS.map(p => <option key={p} value={p}>{PLATFORM_LABELS[p]}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>
              Nombre de hashtags: <strong>{genForm.n_hashtags}</strong>
            </label>
            <input
              type="range" min={3} max={10} value={genForm.n_hashtags}
              onChange={e => setGenForm(f => ({ ...f, n_hashtags: parseInt(e.target.value) }))}
              style={{ width: '100%' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-3)' }}>
              <span>3</span><span>10</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={() => setGenModal(false)}>Annuler</Btn>
            <Btn type="submit" disabled={generating}>
              {generating ? <><Spinner /> Generation...</> : 'Generer avec IA'}
            </Btn>
          </div>
        </form>
      </Modal>

      {/* Manual create modal */}
      <Modal open={modal} onClose={() => setModal(false)} title="Créer un groupe manuellement" width={440}>
        <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Nom du groupe</label>
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="ex: Été 2025 Instagram" required />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Topic</label>
            <input value={form.topic} onChange={e => setForm(f => ({ ...f, topic: e.target.value }))} placeholder="ex: mode, food, tech..." />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Plateforme</label>
            <select value={form.platform} onChange={e => setForm(f => ({ ...f, platform: e.target.value }))}>
              {PLATFORMS.map(p => <option key={p} value={p}>{PLATFORM_LABELS[p]}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Hashtags (séparés par virgule ou saut de ligne)</label>
            <textarea
              value={form.hashtags}
              onChange={e => setForm(f => ({ ...f, hashtags: e.target.value }))}
              placeholder="#hashtag1, #hashtag2, #hashtag3..."
              style={{ minHeight: 80, resize: 'vertical' }}
              required
            />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={() => setModal(false)}>Annuler</Btn>
            <Btn type="submit">Créer</Btn>
          </div>
        </form>
      </Modal>
    </div>
  )
}
