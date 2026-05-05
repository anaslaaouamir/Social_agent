import { useState, useRef, useEffect } from 'react'
import { Btn, Spinner } from '../components/ui'
import { nlpApi } from '../lib/api'
import toast from 'react-hot-toast'

interface Message {
  role: 'user' | 'assistant'
  content: string
  intent?: string
  requires_human?: boolean
  timestamp: string
}

interface KnowledgeDoc {
  id: string
  name: string
  type: 'text' | 'pdf' | 'excel' | 'word' | 'url'
  size?: string
  addedAt: string
}

const PRESETS = [
  { label: 'Service client', knowledge: 'Nous livrons en 3-5 jours ouvrables au Maroc. Retours acceptes sous 14 jours. Service client disponible 9h-18h du lundi au vendredi.' },
  { label: 'E-commerce', knowledge: 'Produits disponibles sur notre site. Paiement par carte bancaire ou livraison contre remboursement. Livraison gratuite a partir de 300 MAD.' },
  { label: 'Restaurant', knowledge: 'Ouvert du mardi au dimanche de 12h a 23h. Reservations au +212 6XX XXX XXX. Cuisine marocaine traditionnelle et fusion.' },
]

const FILE_TYPE_ICONS: Record<string, string> = {
  pdf: '📄',
  excel: '📊',
  word: '📝',
  text: '📃',
  url: '🔗',
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

export default function ChatbotPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [brandName, setBrandName] = useState('Notre Marque')
  const [language, setLanguage] = useState('fr')
  const [showConfig, setShowConfig] = useState(true)
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDoc[]>([])
  const [addDocModal, setAddDocModal] = useState(false)
  const [textInput, setTextInput] = useState('')
  const [textName, setTextName] = useState('')
  const [uploadingDoc, setUploadingDoc] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const loadSources = async () => {
      try {
        const res = await nlpApi.ragSources()
        const sources = Array.isArray(res.data?.sources) ? res.data.sources : []
        setKnowledgeDocs(sources.map((source: string) => buildKnowledgeDoc(source)))
      } catch {
        toast.error('Impossible de charger la base RAG')
      }
    }

    loadSources()
  }, [])

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = {
      role: 'user',
      content: input,
      timestamp: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
    }
    const history = messages.slice(-10).map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, userMsg])
    setInput('')
    setLoading(true)
    try {
      const result = await nlpApi.ragChat({
        message: input,
        history,
        brand_name: brandName,
        language,
      })
      setMessages(m => [...m, {
        role: 'assistant',
        content: result.data?.message || 'Desole, une erreur est survenue.',
        intent: result.data?.intent,
        requires_human: Boolean(result.data?.requires_human),
        timestamp: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
      }])
    } catch {
      toast.error('Erreur du chatbot')
    } finally {
      setLoading(false)
    }
  }

  const addTextDoc = async () => {
    if (!textInput.trim() || !textName.trim()) return
    try {
      await nlpApi.ragIngestText(textName, textInput)
      const doc = buildKnowledgeDoc(textName, `${textInput.length} chars`)
      setKnowledgeDocs(d => d.find(x => x.name === doc.name) ? d : [...d, doc])
      setTextInput('')
      setTextName('')
      setAddDocModal(false)
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
      setKnowledgeDocs(d => d.find(x => x.name === doc.name) ? d : [...d, doc])
      toast.success(`${file.name} ajoute a la base de connaissance`)
    } catch {
      toast.error('Erreur lors de la lecture du fichier')
    } finally {
      setUploadingDoc(false)
    }
  }

  const handleFilesUpload = async (files: FileList | File[]) => {
    const fileArray = Array.from(files).filter(Boolean)
    if (fileArray.length === 0) return

    for (const file of fileArray) {
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
      setKnowledgeDocs(d => d.filter(x => x.id !== doc.id))
      toast.success('Document retire')
    } catch {
      toast.error('Erreur lors de la suppression')
    }
  }

  const loadPreset = async (preset: typeof PRESETS[0]) => {
    try {
      await nlpApi.ragIngestText(preset.label, preset.knowledge)
      const doc = buildKnowledgeDoc(preset.label, `${preset.knowledge.length} chars`)
      setKnowledgeDocs(d => d.find(x => x.name === preset.label) ? d : [...d, doc])
      toast.success(`Preset "${preset.label}" charge`)
    } catch {
      toast.error('Erreur lors du chargement du preset')
    }
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {showConfig && (
        <div style={{
          width: 320,
          flexShrink: 0,
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: 'var(--bg-1)',
        }}>
          <div style={{ padding: '20px 20px 16px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 14, fontFamily: 'var(--font-display)' }}>
              Configuration RAG
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--text-3)', marginBottom: 5 }}>Nom de la marque</label>
                <input value={brandName} onChange={e => setBrandName(e.target.value)} style={{ fontSize: 12 }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 11, color: 'var(--text-3)', marginBottom: 5 }}>Langue de reponse</label>
                <select value={language} onChange={e => setLanguage(e.target.value)} style={{ fontSize: 12 }}>
                  <option value="fr">Francais</option>
                  <option value="ar">Arabe</option>
                  <option value="en">English</option>
                  <option value="darija">Darija</option>
                </select>
              </div>
            </div>
          </div>

          <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Presets rapides</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {PRESETS.map(p => (
                <button key={p.label} onClick={() => loadPreset(p)} style={{
                  padding: '6px 10px',
                  background: 'var(--bg-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 7,
                  fontSize: 11,
                  cursor: 'pointer',
                  color: 'var(--text-2)',
                  textAlign: 'left',
                }}>+ {p.label}</button>
              ))}
            </div>
          </div>

          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: '12px 20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1 }}>
                Base de connaissance ({knowledgeDocs.length})
              </div>
              <Btn size="sm" onClick={() => setAddDocModal(!addDocModal)}>
                {addDocModal ? 'Fermer' : '+ Texte'}
              </Btn>
            </div>

            <div style={{ marginBottom: 12, padding: 12, background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, fontWeight: 600 }}>
                Import de fichiers
              </div>
              <div
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
                style={{
                  width: '100%',
                  padding: '14px 12px',
                  background: dragOver ? 'rgba(108,99,255,0.08)' : 'transparent',
                  border: `1px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
                  borderRadius: 8,
                  fontSize: 11,
                  cursor: 'pointer',
                  color: 'var(--text-3)',
                  textAlign: 'center',
                  lineHeight: 1.5,
                }}
              >
                {uploadingDoc ? 'Chargement...' : 'Deposez un ou plusieurs fichiers ici'}
                <div style={{ fontSize: 10, marginTop: 4, opacity: 0.8 }}>
                  Toutes les extensions sont acceptees. Cliquez pour parcourir vos fichiers.
                </div>
              </div>
            </div>

            {addDocModal && (
              <div style={{ marginBottom: 12, padding: 12, background: 'var(--bg-2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, fontWeight: 600 }}>Ajouter du texte</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  <input value={textName} onChange={e => setTextName(e.target.value)} placeholder="Nom du document" style={{ fontSize: 11 }} />
                  <textarea value={textInput} onChange={e => setTextInput(e.target.value)} placeholder="Collez du texte, FAQ, politique de retour, infos produit..." style={{ minHeight: 80, fontSize: 11, resize: 'vertical' }} />
                  <Btn size="sm" onClick={addTextDoc} disabled={!textInput.trim() || !textName.trim()}>
                    Ajouter le texte
                  </Btn>
                </div>
              </div>
            )}

            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {knowledgeDocs.length === 0 ? (
                <div style={{ fontSize: 11, color: 'var(--text-3)', textAlign: 'center', marginTop: 20, lineHeight: 1.6 }}>
                  Aucun document.
                  <br />
                  Ajoutez des infos sur votre marque pour que le chatbot puisse repondre a vos clients.
                </div>
              ) : (
                knowledgeDocs.map(doc => (
                  <div key={doc.id} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '7px 10px',
                    background: 'var(--bg-2)',
                    borderRadius: 8,
                    border: '1px solid var(--border)',
                  }}>
                    <span style={{ fontSize: 16 }}>{FILE_TYPE_ICONS[doc.type] || '📁'}</span>
                    <div style={{ flex: 1, overflow: 'hidden' }}>
                      <div style={{ fontSize: 11, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.name}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{doc.size}</div>
                    </div>
                    <button onClick={() => removeDoc(doc)} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 14 }}>x</button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexShrink: 0,
          background: 'var(--bg-1)',
        }}>
          <button onClick={() => setShowConfig(!showConfig)} style={{
            background: 'var(--bg-2)',
            border: '1px solid var(--border)',
            borderRadius: 7,
            padding: '5px 10px',
            cursor: 'pointer',
            fontSize: 12,
            color: 'var(--text-2)',
          }}>Config</button>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Chatbot RAG - {brandName}</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Repond aux messages clients avec votre base de connaissance. {knowledgeDocs.length} doc{knowledgeDocs.length !== 1 ? 's' : ''}
            </div>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: 60, color: 'var(--text-3)' }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Chatbot RAG pret</div>
              <div style={{ fontSize: 12, maxWidth: 360, margin: '0 auto', lineHeight: 1.6 }}>
                Simulez un message client entrant. Le chatbot repondra en utilisant votre base de connaissance.
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '70%',
                padding: '10px 14px',
                borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                background: msg.role === 'user' ? 'linear-gradient(135deg, var(--accent), #8b5cf6)' : 'var(--bg-2)',
                color: msg.role === 'user' ? '#fff' : 'var(--text)',
                border: msg.role === 'assistant' ? '1px solid var(--border)' : 'none',
              }}>
                <div style={{ fontSize: 13, lineHeight: 1.5 }}>{msg.content}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
                  <span style={{ fontSize: 10, opacity: 0.6 }}>{msg.timestamp}</span>
                  {msg.requires_human && (
                    <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 999, background: 'rgba(249,115,22,0.2)', color: 'var(--orange)' }}>
                      Humain requis
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{ padding: '10px 14px', borderRadius: '14px 14px 14px 4px', background: 'var(--bg-2)', border: '1px solid var(--border)' }}>
                <Spinner />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg-1)' }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <div style={{ flex: 1, position: 'relative' }}>
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                placeholder="Simulez un message client entrant..."
                style={{ width: '100%', paddingRight: 48 }}
                disabled={loading}
              />
            </div>
            <Btn onClick={sendMessage} disabled={loading || !input.trim()}>
              {loading ? <Spinner /> : 'Envoyer'}
            </Btn>
            <Btn variant="ghost" onClick={() => setMessages([])} disabled={messages.length === 0}>
              Vider
            </Btn>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-3)' }}>
            Le chatbot repond uniquement selon votre base de connaissance.
          </div>
        </div>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="*/*"
        multiple
        style={{ display: 'none' }}
        onChange={async e => {
          if (e.target.files?.length) {
            await handleFilesUpload(e.target.files)
          }
          e.target.value = ''
        }}
      />
    </div>
  )
}
