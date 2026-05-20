import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { downscaleImageFile, fileToDataUrl, mediaApi, type MediaItem } from '../lib/api'
import { Badge, Btn, Empty, Modal, PageHeader, Spinner } from '../components/ui'

const ALL_GROUPS = 'Tous'
const DEFAULT_GROUP = 'General'
const MEDIA_GROUPS_KEY = 'media_library_groups'

interface MediaGroup {
  id: string
  name: string
  createdAt: string
}

function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

function readGroups(): MediaGroup[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(MEDIA_GROUPS_KEY) || '[]')
    return Array.isArray(parsed) ? parsed.filter(group => group?.name) : []
  } catch {
    return []
  }
}

function saveGroups(groups: MediaGroup[]) {
  localStorage.setItem(MEDIA_GROUPS_KEY, JSON.stringify(groups))
}

function mergeGroups(groups: MediaGroup[], items: MediaItem[]): MediaGroup[] {
  const names = new Set(groups.map(group => group.name))
  const merged = [...groups]

  for (const item of items) {
    const name = item.category || DEFAULT_GROUP
    if (!names.has(name)) {
      names.add(name)
      merged.push({ id: genId(), name, createdAt: item.createdAt || new Date().toISOString() })
    }
  }

  if (merged.length === 0) {
    merged.push({ id: genId(), name: DEFAULT_GROUP, createdAt: new Date().toISOString() })
  }

  return merged
}

export default function MediaLibraryPage() {
  const [items, setItems] = useState<MediaItem[]>([])
  const [groups, setGroups] = useState<MediaGroup[]>(() => readGroups())
  const [activeGroup, setActiveGroup] = useState(ALL_GROUPS)
  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [uploading, setUploading] = useState(false)
  const [selected, setSelected] = useState<MediaItem | null>(null)
  const [uploadModal, setUploadModal] = useState(false)
  const [groupModal, setGroupModal] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [uploadForm, setUploadForm] = useState({ group: DEFAULT_GROUP, tags: '' })
  const fileRef = useRef<HTMLInputElement>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const reload = useCallback(async () => {
    const loaded = await mediaApi.library.list()
    setItems(loaded)
    setGroups(current => {
      const merged = mergeGroups(current, loaded)
      saveGroups(merged)
      return merged
    })
  }, [])

  useEffect(() => {
    reload().catch(() => {
      toast.error('Impossible de charger la mediatheque')
    })
  }, [reload])

  const groupCounts = groups.reduce<Record<string, number>>((acc, group) => {
    acc[group.name] = items.filter(item => (item.category || DEFAULT_GROUP) === group.name).length
    return acc
  }, {})

  const selectedUploadGroup = activeGroup === ALL_GROUPS
    ? groups[0]?.name || DEFAULT_GROUP
    : activeGroup

  const openUpload = (file: File) => {
    setUploadForm(form => ({ ...form, group: selectedUploadGroup }))
    setPendingFile(file)
    setPreviewUrl(URL.createObjectURL(file))
    setUploadModal(true)
  }

  const closeUpload = () => {
    setUploadModal(false)
    setPendingFile(null)
    setPreviewUrl(null)
  }

  const handleCreateGroup = (e: React.FormEvent) => {
    e.preventDefault()
    const name = newGroupName.trim()
    if (!name) return
    if (groups.some(group => group.name.toLowerCase() === name.toLowerCase())) {
      toast.error('Ce groupe existe deja')
      return
    }

    const next = [{ id: genId(), name, createdAt: new Date().toISOString() }, ...groups]
    setGroups(next)
    saveGroups(next)
    setActiveGroup(name)
    setUploadForm(form => ({ ...form, group: name }))
    setNewGroupName('')
    setGroupModal(false)
    toast.success('Groupe cree')
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) openUpload(file)
  }, [selectedUploadGroup])

  const handleUpload = async () => {
    if (!pendingFile) return
    setUploading(true)
    try {
      const persistentUrl = pendingFile.type.startsWith('image/')
        ? await downscaleImageFile(pendingFile)
        : await fileToDataUrl(pendingFile)
      const group = uploadForm.group || DEFAULT_GROUP
      const item: MediaItem = {
        id: genId(),
        name: pendingFile.name,
        url: persistentUrl,
        type: pendingFile.type.startsWith('video') ? 'video' : 'image',
        mimeType: pendingFile.type,
        size: pendingFile.size,
        tags: uploadForm.tags.split(',').map(t => t.trim()).filter(Boolean),
        category: group,
        createdAt: new Date().toISOString(),
      }
      await mediaApi.library.add(item)
      if (!groups.some(existing => existing.name === group)) {
        const next = [{ id: genId(), name: group, createdAt: new Date().toISOString() }, ...groups]
        setGroups(next)
        saveGroups(next)
      }
      await reload()
      setActiveGroup(group)
      closeUpload()
      toast.success('Media ajoute a la bibliotheque')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Erreur lors de l'upload")
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Supprimer ce media ?')) return
    await mediaApi.library.delete(id)
    await reload()
    if (selected?.id === id) setSelected(null)
    toast.success('Media supprime')
  }

  const filtered = items.filter(item => {
    const q = search.toLowerCase()
    const itemGroup = item.category || DEFAULT_GROUP
    const groupMatch = activeGroup === ALL_GROUPS || itemGroup === activeGroup
    const searchMatch = !q ||
      item.name.toLowerCase().includes(q) ||
      item.tags.some(tag => tag.toLowerCase().includes(q))
    return groupMatch && searchMatch
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <div style={{ flexShrink: 0 }}>
        <PageHeader
          title="Mediatheque"
          subtitle={`${items.length} medias dans ${groups.length} groupe(s)`}
          actions={
            <div style={{ display: 'flex', gap: 8 }}>
              <Btn variant="ghost" size="sm" onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}>
                {viewMode === 'grid' ? 'Liste' : 'Grille'}
              </Btn>
              <Btn variant="outline" onClick={() => setGroupModal(true)}>+ Nouveau groupe</Btn>
              <Btn onClick={() => fileRef.current?.click()}>+ Ajouter un media</Btn>
            </div>
          }
        />
      </div>

      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '0 32px 24px' }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap', flexShrink: 0 }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Rechercher par nom ou tag..."
            style={{ flex: 1, minWidth: 200, maxWidth: 320 }}
          />
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {[{ id: ALL_GROUPS, name: ALL_GROUPS, createdAt: '' }, ...groups].map(group => (
              <button
                key={group.id}
                onClick={() => setActiveGroup(group.name)}
                style={{
                  padding: '4px 10px',
                  borderRadius: 6,
                  fontSize: 11,
                  fontWeight: 500,
                  cursor: 'pointer',
                  background: activeGroup === group.name ? 'rgba(108,99,255,0.15)' : 'transparent',
                  border: `1px solid ${activeGroup === group.name ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`,
                  color: activeGroup === group.name ? 'var(--accent-2)' : 'var(--text-3)',
                }}
              >
                {group.name}
                {group.name !== ALL_GROUPS ? ` (${groupCounts[group.name] || 0})` : ` (${items.length})`}
              </button>
            ))}
          </div>
        </div>

        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          style={{
            marginBottom: 16,
            padding: 20,
            borderRadius: 10,
            flexShrink: 0,
            border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
            background: dragOver ? 'rgba(108,99,255,0.05)' : 'transparent',
            textAlign: 'center',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
        >
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Glissez un fichier ici ou cliquez pour selectionner. Il sera ajoute au groupe "{selectedUploadGroup}".
          </span>
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {filtered.length === 0 ? (
            <Empty icon="" title="Aucun media" desc="Ajoutez vos premiers medias dans le groupe choisi." />
          ) : viewMode === 'grid' ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
              {filtered.map(item => (
                <div
                  key={item.id}
                  onClick={() => setSelected(selected?.id === item.id ? null : item)}
                  style={{
                    borderRadius: 10,
                    overflow: 'hidden',
                    cursor: 'pointer',
                    border: `1px solid ${selected?.id === item.id ? 'var(--accent)' : 'var(--border)'}`,
                    background: 'var(--bg-1)',
                    transition: 'all 0.15s',
                  }}
                >
                  <div style={{ width: '100%', aspectRatio: '1', background: 'var(--bg-2)', position: 'relative', overflow: 'hidden' }}>
                    {item.type === 'image' ? (
                      <img src={item.url} alt={item.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 14 }}>Video</div>
                    )}
                  </div>
                  <div style={{ padding: '8px 10px' }}>
                    <div style={{ fontSize: 11, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 2 }}>
                      {item.name}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--accent-2)', marginTop: 2 }}>{item.category || DEFAULT_GROUP}</div>
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
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 14px',
                    borderRadius: 10,
                    cursor: 'pointer',
                    background: selected?.id === item.id ? 'rgba(108,99,255,0.08)' : 'var(--bg-1)',
                    border: `1px solid ${selected?.id === item.id ? 'rgba(108,99,255,0.25)' : 'var(--border)'}`,
                  }}
                >
                  <div style={{ width: 48, height: 48, borderRadius: 8, overflow: 'hidden', flexShrink: 0, background: 'var(--bg-2)' }}>
                    {item.type === 'image' ? (
                      <img src={item.url} alt={item.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 10 }}>Video</div>
                    )}
                  </div>
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{item.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{item.tags.map(tag => `#${tag}`).join(' ')}</div>
                  </div>
                  <Badge label={item.category || DEFAULT_GROUP} />
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{(item.size / 1024).toFixed(0)} Ko</div>
                  <Btn size="sm" variant="danger" onClick={e => { e.stopPropagation(); handleDelete(item.id) }}>x</Btn>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {selected && (
        <div
          style={{
            position: 'fixed',
            right: 0,
            top: 0,
            bottom: 0,
            width: 320,
            background: 'var(--bg-1)',
            borderLeft: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 50,
            overflowY: 'auto',
          }}
        >
          <div style={{ padding: 16, borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>Details</span>
            <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: 'var(--text-3)', fontSize: 18, cursor: 'pointer' }}>x</button>
          </div>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ borderRadius: 10, overflow: 'hidden', aspectRatio: '1', background: 'var(--bg-2)' }}>
              {selected.type === 'image' ? (
                <img src={selected.url} alt={selected.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 14 }}>Video</div>
              )}
            </div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{selected.name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                Groupe: {selected.category || DEFAULT_GROUP} - {(selected.size / 1024).toFixed(0)} Ko
              </div>
            </div>
            {selected.tags.length > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {selected.tags.map(tag => <Badge key={tag} label={`#${tag}`} />)}
              </div>
            )}
            <Btn variant="danger" onClick={() => handleDelete(selected.id)}>Supprimer</Btn>
          </div>
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept="image/*,video/*"
        style={{ display: 'none' }}
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) openUpload(file)
          e.target.value = ''
        }}
      />

      <Modal open={uploadModal} onClose={closeUpload} title="Ajouter un media" width={480}>
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
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Groupe</label>
            <select value={uploadForm.group} onChange={e => setUploadForm(form => ({ ...form, group: e.target.value }))}>
              {groups.map(group => <option key={group.id} value={group.name}>{group.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Tags separes par virgule</label>
            <input value={uploadForm.tags} onChange={e => setUploadForm(form => ({ ...form, tags: e.target.value }))} placeholder="ex: ete, promo, produit" />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={closeUpload}>Annuler</Btn>
            <Btn onClick={handleUpload} disabled={uploading}>
              {uploading ? <Spinner /> : 'Ajouter a la bibliotheque'}
            </Btn>
          </div>
        </div>
      </Modal>

      <Modal open={groupModal} onClose={() => setGroupModal(false)} title="Nouveau groupe media" width={380}>
        <form onSubmit={handleCreateGroup} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>Nom du groupe</label>
            <input
              value={newGroupName}
              onChange={e => setNewGroupName(e.target.value)}
              placeholder="ex: Campagne ete, Produits, Stories..."
              required
            />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={() => setGroupModal(false)}>Annuler</Btn>
            <Btn type="submit">Creer</Btn>
          </div>
        </form>
      </Modal>
    </div>
  )
}
