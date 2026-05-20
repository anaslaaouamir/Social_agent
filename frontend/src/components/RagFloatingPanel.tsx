import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'

import { nlpApi } from '../lib/api'
import { useAppStore } from '../store'
import { Btn, PlatformIcon, Spinner } from './ui'

interface KnowledgeDoc {
  id: string
  name: string
  type: 'text' | 'pdf' | 'excel' | 'word' | 'url'
  size?: string
  addedAt: string
}

interface AutoReplyLog {
  id: string
  time: string
  client: string
  type: 'dm' | 'comment'
  platform: string
  incoming: string
  reply: string
  confidence?: number
  deliveryStatus?: string
  requiresHuman?: boolean
}

const PRESETS = [
  { label: 'Service client', knowledge: 'Nous livrons en 3-5 jours ouvrables au Maroc. Retours acceptes sous 14 jours. Service client disponible 9h-18h du lundi au vendredi.' },
  { label: 'E-commerce', knowledge: 'Produits disponibles sur notre site. Paiement par carte bancaire ou livraison contre remboursement. Livraison gratuite a partir de 300 MAD.' },
  { label: 'Restaurant', knowledge: 'Ouvert du mardi au dimanche de 12h a 23h. Reservations au +212 6XX XXX XXX. Cuisine marocaine traditionnelle et fusion.' },
]

const FILE_TYPE_ICONS: Record<string, string> = {
  pdf: 'PDF',
  excel: 'XLS',
  word: 'DOC',
  text: 'TXT',
  url: 'URL',
}

function readBool(key: string, fallback: boolean) {
  const value = localStorage.getItem(key)
  if (value === null) return fallback
  return value === 'true'
}

function readNumber(key: string, fallback: number) {
  const value = Number(localStorage.getItem(key))
  return Number.isFinite(value) ? value : fallback
}

function readText(key: string, fallback: string) {
  const value = localStorage.getItem(key)
  return value === null ? fallback : value
}

function readAutoReplyHistory(): AutoReplyLog[] {
  try {
    const parsed = JSON.parse(localStorage.getItem('rag_autoReplyHistory') || '[]')
    return Array.isArray(parsed) ? parsed.slice(0, 10) : []
  } catch {
    return []
  }
}

function inferDocTypeFromSource(name: string): KnowledgeDoc['type'] {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  if (ext === 'pdf') return 'pdf'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return 'excel'
  if (['doc', 'docx'].includes(ext)) return 'word'
  if (ext === 'url') return 'url'
  return 'text'
}

function buildKnowledgeDoc(name: string, size?: string): KnowledgeDoc {
  return {
    id: name,
    name,
    type: inferDocTypeFromSource(name),
    size,
    addedAt: new Date().toISOString(),
  }
}

export default function RagFloatingPanel() {
  const { accounts } = useAppStore()
  const [open, setOpen] = useState(false)
  const [autoReply, setAutoReply] = useState(() => readBool('rag_autoReply', false))
  const [scopeDms, setScopeDms] = useState(() => readBool('rag_scope_dms', true))
  const [scopeComments, setScopeComments] = useState(() => readBool('rag_scope_comments', true))
  const [confidenceThreshold, setConfidenceThreshold] = useState(() => readNumber('rag_confidenceThreshold', 0.6))
  const [fallbackFr, setFallbackFr] = useState(() => readText('rag_fallback_fr', 'Merci pour votre message. Notre equipe vous repondra dans les plus brefs delais.'))
  const [fallbackAr, setFallbackAr] = useState(() => readText('rag_fallback_ar', 'شكرا على رسالتك. سيرد عليك فريقنا في أقرب وقت.'))
  const [fallbackDarija, setFallbackDarija] = useState(() => readText('rag_fallback_darija', 'شكرا على الرسالة ديالك. الفريق ديالنا غادي يجاوبك فاقرب وقت.'))
  const [fallbackEn, setFallbackEn] = useState(() => readText('rag_fallback_en', 'Thank you for your message. Our team will get back to you shortly.'))
  const [accountStates, setAccountStates] = useState<Record<string, boolean>>({})
  const [history, setHistory] = useState<AutoReplyLog[]>(() => readAutoReplyHistory())
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDoc[]>([])
  const [textInput, setTextInput] = useState('')
  const [textName, setTextName] = useState('')
  const [uploadingDoc, setUploadingDoc] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const accountSignature = accounts.map((account: any) => account.id).join('|')

  useEffect(() => {
    setAccountStates(prev => {
      const next: Record<string, boolean> = {}
      accounts.forEach((account: any) => {
        const id = String(account.id)
        next[id] = prev[id] ?? readBool(`rag_account_${id}`, true)
      })
      return next
    })
  }, [accountSignature])

  useEffect(() => {
    localStorage.setItem('rag_autoReply', String(autoReply))
    if (autoReply && !localStorage.getItem('rag_autoReplyEnabledAt')) {
      localStorage.setItem('rag_autoReplyEnabledAt', new Date().toISOString())
    }
    if (!autoReply) {
      localStorage.removeItem('rag_autoReplyEnabledAt')
    }
    window.dispatchEvent(new Event('rag-settings:changed'))
  }, [autoReply])

  useEffect(() => {
    localStorage.setItem('rag_scope_dms', String(scopeDms))
    window.dispatchEvent(new Event('rag-settings:changed'))
  }, [scopeDms])

  useEffect(() => {
    localStorage.setItem('rag_scope_comments', String(scopeComments))
    window.dispatchEvent(new Event('rag-settings:changed'))
  }, [scopeComments])

  useEffect(() => {
    localStorage.setItem('rag_confidenceThreshold', String(confidenceThreshold))
    window.dispatchEvent(new Event('rag-settings:changed'))
  }, [confidenceThreshold])

  useEffect(() => {
    localStorage.setItem('rag_fallback_fr', fallbackFr)
    localStorage.setItem('rag_fallback_ar', fallbackAr)
    localStorage.setItem('rag_fallback_darija', fallbackDarija)
    localStorage.setItem('rag_fallback_en', fallbackEn)
    window.dispatchEvent(new Event('rag-settings:changed'))
  }, [fallbackFr, fallbackAr, fallbackDarija, fallbackEn])

  useEffect(() => {
    Object.entries(accountStates).forEach(([id, enabled]) => {
      localStorage.setItem(`rag_account_${id}`, String(enabled))
    })
    window.dispatchEvent(new Event('rag-settings:changed'))
  }, [accountStates])

  useEffect(() => {
    const refreshHistory = () => setHistory(readAutoReplyHistory())
    window.addEventListener('rag-history:changed', refreshHistory)
    window.addEventListener('storage', refreshHistory)
    return () => {
      window.removeEventListener('rag-history:changed', refreshHistory)
      window.removeEventListener('storage', refreshHistory)
    }
  }, [])

  const loadSources = async () => {
    try {
      const res = await nlpApi.ragSources()
      const sources = Array.isArray(res.data?.sources) ? res.data.sources : []
      setKnowledgeDocs(sources.map((source: string) => buildKnowledgeDoc(source)))
    } catch {
      toast.error('Impossible de charger la base RAG')
    }
  }

  useEffect(() => {
    loadSources()
  }, [])

  const addTextDoc = async () => {
    if (!textInput.trim() || !textName.trim()) return
    try {
      await nlpApi.ragIngestText(textName, textInput)
      const doc = buildKnowledgeDoc(textName, `${textInput.length} chars`)
      setKnowledgeDocs(docs => docs.find(docItem => docItem.name === doc.name) ? docs : [...docs, doc])
      setTextInput('')
      setTextName('')
      toast.success('Document ajoute a la base de connaissance')
    } catch {
      toast.error('Erreur lors de l ajout du texte')
    }
  }

  const handleFileUpload = async (file: File) => {
    setUploadingDoc(true)
    try {
      await nlpApi.ragIngestFile(file)
      const doc = buildKnowledgeDoc(file.name, `${(file.size / 1024).toFixed(0)} Ko`)
      setKnowledgeDocs(docs => docs.find(docItem => docItem.name === doc.name) ? docs : [...docs, doc])
      toast.success(`${file.name} ajoute a la base de connaissance`)
    } catch {
      toast.error('Erreur lors de la lecture du fichier')
    } finally {
      setUploadingDoc(false)
    }
  }

  const handleFilesUpload = async (files: FileList | File[]) => {
    for (const file of Array.from(files).filter(Boolean)) {
      await handleFileUpload(file)
    }
  }

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files?.length) {
      await handleFilesUpload(e.dataTransfer.files)
    }
  }

  const removeDoc = async (doc: KnowledgeDoc) => {
    try {
      await nlpApi.ragDeleteSource(doc.name)
      setKnowledgeDocs(docs => docs.filter(item => item.id !== doc.id))
      toast.success('Document retire')
    } catch {
      toast.error('Erreur lors de la suppression')
    }
  }

  const loadPreset = async (preset: typeof PRESETS[0]) => {
    try {
      await nlpApi.ragIngestText(preset.label, preset.knowledge)
      const doc = buildKnowledgeDoc(preset.label, `${preset.knowledge.length} chars`)
      setKnowledgeDocs(docs => docs.find(item => item.name === preset.label) ? docs : [...docs, doc])
      toast.success(`Preset "${preset.label}" charge`)
    } catch {
      toast.error('Erreur lors du chargement du preset')
    }
  }

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          title="RAG Assistant"
          style={{
            position: 'fixed',
            right: 0,
            top: '50%',
            transform: 'translateY(-50%)',
            width: 48,
            height: 56,
            borderRadius: '14px 0 0 14px',
            border: '1px solid rgba(139,92,246,0.45)',
            borderRight: 'none',
            background: 'linear-gradient(135deg, #6c63ff, #8b5cf6)',
            color: '#fff',
            boxShadow: '0 0 24px rgba(139,92,246,0.5)',
            zIndex: 999,
            cursor: 'pointer',
            fontSize: 22,
            fontWeight: 800,
          }}
        >
          <span aria-hidden="true">🤖</span>
          <span
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: 8,
              left: 8,
              width: 10,
              height: 10,
              borderRadius: '50%',
              background: autoReply ? '#22c55e' : '#6b7280',
              border: '2px solid var(--bg-0)',
              boxShadow: autoReply ? '0 0 10px rgba(34,197,94,0.75)' : 'none',
            }}
          />
        </button>
      )}

      <aside
        style={{
          position: 'fixed',
          right: open ? 0 : -360,
          top: 0,
          height: '100vh',
          width: 340,
          zIndex: 1000,
          background: 'var(--bg-1)',
          borderLeft: '1px solid var(--border)',
          boxShadow: open ? '-18px 0 60px rgba(0,0,0,0.35)' : 'none',
          transition: 'right 0.22s ease',
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          overflowX: 'hidden',
          overscrollBehavior: 'contain',
        }}
      >
        <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 800, fontSize: 16 }}>RAG Assistant</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>Base de connaissance et auto-reponse</div>
          </div>
          <button onClick={() => setOpen(false)} style={{ background: 'var(--bg-2)', color: 'var(--text-2)', border: '1px solid var(--border)', borderRadius: 8, width: 30, height: 30, cursor: 'pointer' }}>
            x
          </button>
        </div>

        <div style={{ padding: 16, borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, cursor: 'pointer' }}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>Reponse automatique</span>
            <span style={{ width: 46, height: 24, borderRadius: 999, padding: 3, background: autoReply ? 'linear-gradient(135deg, #6c63ff, #8b5cf6)' : 'var(--bg-3)', border: '1px solid var(--border)', transition: 'background 0.2s ease' }}>
              <span style={{ display: 'block', width: 18, height: 18, borderRadius: '50%', background: '#fff', transform: autoReply ? 'translateX(20px)' : 'translateX(0)', transition: 'transform 0.2s ease' }} />
            </span>
            <input type="checkbox" checked={autoReply} onChange={e => setAutoReply(e.target.checked)} style={{ display: 'none' }} />
          </label>

          <div style={{ display: 'grid', gap: 8, marginTop: 14 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-2)' }}>
              <input type="checkbox" checked={scopeDms} onChange={e => setScopeDms(e.target.checked)} />
              Messages (DMs)
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-2)' }}>
              <input type="checkbox" checked={scopeComments} onChange={e => setScopeComments(e.target.checked)} />
              Commentaires de posts
            </label>
          </div>

          {accounts.length > 0 && (
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Comptes actifs</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {accounts.map((account: any) => {
                  const id = String(account.id)
                  const enabled = accountStates[id] !== false
                  return (
                    <label key={id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, fontSize: 12, color: 'var(--text-2)' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                        <PlatformIcon platform={account.platform} size={14} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{account.account_name || account.username || account.platform}</span>
                      </span>
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={e => setAccountStates(prev => ({ ...prev, [id]: e.target.checked }))}
                      />
                    </label>
                  )
                })}
              </div>
            </div>
          )}

          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 700 }}>Seuil de confiance</span>
              <span style={{ fontSize: 11, color: 'var(--accent-2)', fontWeight: 700 }}>{confidenceThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0.2"
              max="0.95"
              step="0.05"
              value={confidenceThreshold}
              onChange={e => setConfidenceThreshold(Number(e.target.value))}
              style={{ width: '100%' }}
            />
            <div style={{ fontSize: 10, color: 'var(--text-3)', lineHeight: 1.5 }}>Sous ce score, le bot envoie le fallback et marque le message humain requis.</div>
          </div>
        </div>

        <div style={{ flex: 'none', overflowY: 'visible', padding: '16px 16px 28px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>
            Templates fallback
          </div>
          <div style={{ display: 'grid', gap: 8, marginBottom: 16 }}>
            {[
              { label: 'Francais', value: fallbackFr, onChange: setFallbackFr },
              { label: 'Arabe', value: fallbackAr, onChange: setFallbackAr },
              { label: 'Darija', value: fallbackDarija, onChange: setFallbackDarija },
              { label: 'Anglais', value: fallbackEn, onChange: setFallbackEn },
            ].map(item => (
              <label key={item.label} style={{ display: 'grid', gap: 5 }}>
                <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 700 }}>{item.label}</span>
                <textarea
                  value={item.value}
                  onChange={e => item.onChange(e.target.value)}
                  style={{ minHeight: 54, fontSize: 11, resize: 'vertical' }}
                />
              </label>
            ))}
          </div>

          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>
            Historique auto-reponses
          </div>
          <div style={{ display: 'grid', gap: 8, marginBottom: 18 }}>
            {history.length === 0 ? (
              <div style={{ color: 'var(--text-3)', fontSize: 12, lineHeight: 1.5, padding: '10px 0' }}>Aucune auto-reponse envoyee.</div>
            ) : history.map(item => (
              <div key={item.id} style={{ padding: '9px 10px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 9 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 5 }}>
                  <span style={{ fontSize: 11, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.client}</span>
                  <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{new Date(item.time).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 5 }}>
                  <PlatformIcon platform={item.platform} size={13} />
                  <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{item.type === 'dm' ? 'DM' : 'Commentaire'}</span>
                  {typeof item.confidence === 'number' && <span style={{ fontSize: 10, color: 'var(--text-3)' }}>Score {item.confidence.toFixed(2)}</span>}
                  {item.requiresHuman && <span style={{ fontSize: 10, color: 'var(--orange)' }}>Humain requis</span>}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.incoming}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 3 }}>{item.reply}</div>
              </div>
            ))}
          </div>

          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>
            Base de connaissance ({knowledgeDocs.length})
          </div>

          <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
            {PRESETS.map(preset => (
              <button key={preset.label} onClick={() => loadPreset(preset)} style={{ padding: '5px 8px', borderRadius: 7, border: '1px solid var(--border)', background: 'var(--bg-2)', color: 'var(--text-2)', fontSize: 11, cursor: 'pointer' }}>
                + {preset.label}
              </button>
            ))}
          </div>

          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            style={{
              padding: '16px 12px',
              borderRadius: 10,
              border: `1px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
              background: dragOver ? 'rgba(108,99,255,0.08)' : 'var(--bg-2)',
              color: 'var(--text-3)',
              textAlign: 'center',
              fontSize: 12,
              lineHeight: 1.5,
              cursor: 'pointer',
              marginBottom: 12,
            }}
          >
            {uploadingDoc ? <Spinner /> : 'Deposez vos fichiers ici'}
            <div style={{ fontSize: 10, marginTop: 5 }}>PDF, DOCX, CSV, TXT, JSON, etc.</div>
          </div>

          <div style={{ padding: 12, background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 10, marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, fontWeight: 700 }}>Ajouter du texte</div>
            <input value={textName} onChange={e => setTextName(e.target.value)} placeholder="Nom du document" style={{ fontSize: 12, marginBottom: 8 }} />
            <textarea value={textInput} onChange={e => setTextInput(e.target.value)} placeholder="FAQ, politique de retour, infos produit..." style={{ minHeight: 86, fontSize: 12, resize: 'vertical', marginBottom: 8 }} />
            <Btn size="sm" onClick={addTextDoc} disabled={!textName.trim() || !textInput.trim()}>Ajouter</Btn>
          </div>

          <div style={{ display: 'grid', gap: 8 }}>
            {knowledgeDocs.length === 0 ? (
              <div style={{ color: 'var(--text-3)', fontSize: 12, lineHeight: 1.6, textAlign: 'center', padding: '20px 8px' }}>
                Aucun document. Ajoutez une base pour guider les reponses.
              </div>
            ) : knowledgeDocs.map(doc => (
              <div key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 9 }}>
                <span style={{ minWidth: 28, color: 'var(--accent-2)', fontSize: 10, fontWeight: 800 }}>{FILE_TYPE_ICONS[doc.type] || 'DOC'}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{doc.size || 'source RAG'}</div>
                </div>
                <button onClick={() => removeDoc(doc)} style={{ border: 'none', background: 'transparent', color: 'var(--text-3)', cursor: 'pointer', fontSize: 15 }}>x</button>
              </div>
            ))}
          </div>
        </div>

        <input
          ref={fileRef}
          type="file"
          multiple
          style={{ display: 'none' }}
          onChange={async e => {
            if (e.target.files?.length) await handleFilesUpload(e.target.files)
            e.target.value = ''
          }}
        />
      </aside>
    </>
  )
}
