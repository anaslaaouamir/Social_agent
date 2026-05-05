import { useState, useCallback, useEffect, useRef } from 'react'
import { downscaleImageFile, fileToDataUrl, mediaApi, type MediaItem } from '../lib/api'
import { PageHeader, Btn, Modal, Badge, Spinner, Empty } from '../components/ui'
import toast from 'react-hot-toast'

const CATEGORIES = ['Tous', 'Produit', 'Lifestyle', 'Promotion', 'Evenement', 'Equipe', 'Temoignage', 'Infographie', 'Autre']

function genId() { return Date.now().toString(36) + Math.random().toString(36).slice(2) }

// CLIP-style image description via Claude API
async function describeImageWithClip(dataUrl: string): Promise<string> {
  try {
    const base64 = dataUrl.split(',')[1]
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        messages: [{
          role: 'user',
          content: [
            {
              type: 'image',
              source: { type: 'base64', media_type: 'image/jpeg', data: base64 }
            },
            {
              type: 'text',
              text: 'Décris cette image en 2-3 phrases courtes pour une médiathèque de contenu social media. Mentionne: les éléments principaux, l\'ambiance, et les couleurs dominantes. Sois concis et descriptif. Réponds uniquement en français.'
            }
          ]
        }]
      })
    })
    const data = await response.json()
    return data.content?.[0]?.text || 'Image téléchargée'
  } catch {
    return 'Image téléchargée'
  }
}

export default function MediaLibraryPage() {
  const [items, setItems] = useState<MediaItem[]>([])
  const [category, setCategory] = useState('Tous')
  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [uploading, setUploading] = useState(false)
  const [selected, setSelected] = useState<MediaItem | null>(null)
  const [uploadModal, setUploadModal] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [uploadForm, setUploadForm] = useState({ category: 'Produit', tags: '' })
  const fileRef = useRef<HTMLInputElement>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [describing, setDescribing] = useState(false)
  const [clipDescription, setClipDescription] = useState('')

  const reload = useCallback(async () => {
    setItems(await mediaApi.library.list())
  }, [])

  useEffect(() => {
    reload().catch(() => {
      toast.error('Impossible de charger la médiathèque')
    })
  }, [reload])

  const openUpload = async (file: File) => {
    const url = URL.createObjectURL(file)
    setPendingFile(file)
    setPreviewUrl(url)
    setClipDescription('')
    setUploadModal(true)
    // Auto-describe with CLIP-style
    if (file.type.startsWith('image/')) {
      setDescribing(true)
      try {
        const dataUrl = await fileToDataUrl(file)
        const desc = await describeImageWithClip(dataUrl)
        setClipDescription(desc)
      } catch {
        setClipDescription('Description non disponible')
      } finally {
        setDescribing(false)
      }
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) openUpload(file)
  }, [])

  const handleUpload = async () => {
    if (!pendingFile) return
    setUploading(true)
    try {
      const persistentUrl = pendingFile.type.startsWith('image/')
        ? await downscaleImageFile(pendingFile)
        : await fileToDataUrl(pendingFile)
      const item: MediaItem = {
        id: genId(),
        name: pendingFile.name,
        url: persistentUrl,
        type: pendingFile.type.startsWith('video') ? 'video' : 'image',
        mimeType: pendingFile.type,
        size: pendingFile.size,
        tags: uploadForm.tags.split(',').map(t => t.trim()).filter(Boolean),
        category: uploadForm.category,
        createdAt: new Date().toISOString(),
        analysis: clipDescription ? { description: clipDescription } : null,
      }
      await mediaApi.library.add(item)
      await reload()
      setUploadModal(false)
      setPendingFile(null)
      setPreviewUrl(null)
      setClipDescription('')
      toast.success('Média ajouté à la bibliothèque')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Erreur lors de l\'upload')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Supprimer ce média ?')) return
    await mediaApi.library.delete(id)
    await reload()
    if (selected?.id === id) setSelected(null)
    toast.success('Média supprimé')
  }

  const filtered = items.filter(i => {
    const catMatch = category === 'Tous' || i.category === category
    const searchMatch = !search || i.name.toLowerCase().includes(search.toLowerCase()) ||
      i.tags.some(t => t.toLowerCase().includes(search.toLowerCase())) ||
      (i.analysis?.description || '').toLowerCase().includes(search.toLowerCase())
    return catMatch && searchMatch
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <div style={{ flexShrink: 0 }}>
        <PageHeader
          title="Médiathèque"
          subtitle={`${items.length} médias · descriptions auto par IA (CLIP)`}
          actions={
            <div style={{ display: 'flex', gap: 8 }}>
              <Btn variant="ghost" size="sm" onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}>
                {viewMode === 'grid' ? '☰' : '⊞'}
              </Btn>
              <Btn onClick={() => fileRef.current?.click()}>+ Ajouter un média</Btn>
            </div>
          }
        />
      </div>

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '0 32px 24px' }}>
        {/* Filters */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap', flexShrink: 0 }}>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Rechercher par nom, tag ou description..."
            style={{ flex: 1, minWidth: 200, maxWidth: 320 }}
          />
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {CATEGORIES.map(cat => (
              <button key={cat} onClick={() => setCategory(cat)} style={{
                padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500, cursor: 'pointer',
                background: category === cat ? 'rgba(108,99,255,0.15)' : 'transparent',
                border: `1px solid ${category === cat ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
                color: category === cat ? 'var(--accent-2)' : 'var(--text-3)',
              }}>{cat}</button>
            ))}
          </div>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          style={{
            marginBottom: 16, padding: '20px', borderRadius: 10, flexShrink: 0,
            border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
            background: dragOver ? 'rgba(108,99,255,0.05)' : 'transparent',
            textAlign: 'center', cursor: 'pointer', transition: 'all 0.2s',
          }}
          onClick={() => fileRef.current?.click()}
        >
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
            📎 Glissez un fichier ici ou cliquez pour sélectionner · Image, Vidéo, GIF
          </span>
        </div>

        {/* Grid */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {filtered.length === 0 ? (
            <Empty icon="🖼️" title="Aucun média" desc="Ajoutez vos premiers médias pour commencer." />
          ) : viewMode === 'grid' ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
              {filtered.map(item => (
                <div
                  key={item.id}
                  onClick={() => setSelected(selected?.id === item.id ? null : item)}
                  style={{
                    borderRadius: 10, overflow: 'hidden', cursor: 'pointer',
                    border: `1px solid ${selected?.id === item.id ? 'var(--accent)' : 'var(--border)'}`,
                    background: 'var(--bg-1)',
                    transition: 'all 0.15s',
                  }}
                >
                  <div style={{ width: '100%', aspectRatio: '1', background: 'var(--bg-2)', position: 'relative', overflow: 'hidden' }}>
                    {item.type === 'image' ? (
                      <img src={item.url} alt={item.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 32 }}>🎬</div>
                    )}
                  </div>
                  <div style={{ padding: '8px 10px' }}>
                    <div style={{ fontSize: 11, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 2 }}>
                      {item.name}
                    </div>
                    {item.analysis?.description && (
                      <div style={{ fontSize: 10, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.analysis.description}
                      </div>
                    )}
                    <div style={{ fontSize: 10, color: 'var(--accent-2)', marginTop: 2 }}>{item.category}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {filtered.map(item => (
                <div
                  key={item.id}
                  onClick={() => setSelected(selected?.id === item.id ? null : item)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                    borderRadius: 10, cursor: 'pointer',
                    background: selected?.id === item.id ? 'rgba(108,99,255,0.08)' : 'var(--bg-1)',
                    border: `1px solid ${selected?.id === item.id ? 'rgba(108,99,255,0.25)' : 'var(--border)'}`,
                  }}
                >
                  <div style={{ width: 48, height: 48, borderRadius: 8, overflow: 'hidden', flexShrink: 0, background: 'var(--bg-2)' }}>
                    {item.type === 'image' ? (
                      <img src={item.url} alt={item.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>🎬</div>}
                  </div>
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{item.name}</div>
                    {item.analysis?.description && (
                      <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.analysis.description}
                      </div>
                    )}
                  </div>
                  <Badge label={item.category} />
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{(item.size / 1024).toFixed(0)} Ko</div>
                  <Btn size="sm" variant="danger" onClick={e => { e.stopPropagation(); handleDelete(item.id) }}>×</Btn>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selected && (
        <div style={{
          position: 'fixed', right: 0, top: 0, bottom: 0, width: 320,
          background: 'var(--bg-1)', borderLeft: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', zIndex: 50, overflowY: 'auto',
        }}>
          <div style={{ padding: '16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>Détails</span>
            <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: 'var(--text-3)', fontSize: 18, cursor: 'pointer' }}>×</button>
          </div>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ borderRadius: 10, overflow: 'hidden', aspectRatio: '1', background: 'var(--bg-2)' }}>
              {selected.type === 'image' ? (
                <img src={selected.url} alt={selected.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 40 }}>🎬</div>}
            </div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{selected.name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{selected.category} · {(selected.size / 1024).toFixed(0)} Ko</div>
            </div>
            {selected.analysis?.description && (
              <div style={{ padding: '10px 12px', background: 'rgba(108,99,255,0.06)', borderRadius: 8, border: '1px solid rgba(108,99,255,0.12)' }}>
                <div style={{ fontSize: 10, color: 'var(--accent-2)', marginBottom: 5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1 }}>
                  🤖 Description IA (CLIP)
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{selected.analysis.description}</div>
              </div>
            )}
            {selected.tags.length > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {selected.tags.map(t => <Badge key={t} label={`#${t}`} />)}
              </div>
            )}
            <Btn variant="danger" onClick={() => handleDelete(selected.id)}>🗑 Supprimer</Btn>
          </div>
        </div>
      )}

      <input ref={fileRef} type="file" accept="image/*,video/*" style={{ display: 'none' }} onChange={e => { const f = e.target.files?.[0]; if (f) openUpload(f); e.target.value = '' }} />

      {/* Upload modal */}
      <Modal open={uploadModal} onClose={() => { setUploadModal(false); setPendingFile(null); setPreviewUrl(null); setClipDescription('') }} title="Ajouter un média" width={480}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {previewUrl && (
            <div style={{ borderRadius: 10, overflow: 'hidden', maxHeight: 220, background: 'var(--bg-2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {pendingFile?.type.startsWith('video') ? (
                <video src={previewUrl} controls style={{ maxWidth: '100%', maxHeight: 220 }} />
              ) : (
                <img src={previewUrl} alt="preview" style={{ maxWidth: '100%', maxHeight: 220, objectFit: 'contain' }} />
              )}
            </div>
          )}
          {/* CLIP description */}
          <div style={{ padding: '10px 12px', background: 'rgba(108,99,255,0.06)', borderRadius: 8, border: '1px solid rgba(108,99,255,0.12)', minHeight: 56 }}>
            <div style={{ fontSize: 10, color: 'var(--accent-2)', marginBottom: 5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1, display: 'flex', alignItems: 'center', gap: 6 }}>
              🤖 Description IA automatique (CLIP)
              {describing && <Spinner />}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>
              {describing ? 'Analyse en cours...' : clipDescription || 'Description générée après l\'upload'}
            </div>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Catégorie</label>
            <select value={uploadForm.category} onChange={e => setUploadForm(f => ({ ...f, category: e.target.value }))}>
              {CATEGORIES.slice(1).map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Tags (séparés par virgule)</label>
            <input value={uploadForm.tags} onChange={e => setUploadForm(f => ({ ...f, tags: e.target.value }))} placeholder="ex: été, promo, produit" />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={() => { setUploadModal(false); setPendingFile(null); setPreviewUrl(null) }}>Annuler</Btn>
            <Btn onClick={handleUpload} disabled={uploading || describing}>
              {uploading ? <Spinner /> : '📁 Ajouter à la bibliothèque'}
            </Btn>
          </div>
        </div>
      </Modal>
    </div>
  )
}
