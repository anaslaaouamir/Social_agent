import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || ''

export const api = axios.create({ baseURL: BASE })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('access_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  async err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// Auth
export const authApi = {
  register: (data: { email: string; password: string; full_name: string }) =>
    api.post('/api/auth/register', data),
  login: (email: string, password: string) => {
    const fd = new FormData()
    fd.append('username', email)
    fd.append('password', password)
    return api.post('/api/auth/login', fd)
  },
  me: () => api.get('/api/auth/me'),
}

// Accounts
export const accountsApi = {
  list: () => api.get('/api/accounts/'),
  connect: (data: any) => api.post('/api/accounts/', data),
  disconnect: (id: string) => api.delete(`/api/accounts/${id}`),
  getFacebookAuthUrl: () => api.get('/api/auth/facebook/login'),
  getInstagramAuthUrl: () => api.get('/api/auth/instagram/login'),
  getLinkedInAuthUrl: () => api.get('/api/auth/linkedin/login'),
  getTwitterAuthUrl: () => api.get('/api/auth/twitter/login'),
  getTikTokAuthUrl: () => api.get('/api/auth/tiktok/login'),
  getThreadsAuthUrl: () => api.get('/api/auth/threads/login'),
  getYouTubeAuthUrl: () => api.get('/api/auth/youtube/login'),
  publishFacebookWithFile: (accountId: string, message: string, image: File) => {
    const fd = new FormData()
    fd.append('message', message)
    fd.append('image', image)
    return api.post(`/api/auth/facebook/publish-with-file/${accountId}`, fd)
  },
}

// Posts
export const postsApi = {
  list: (params?: any) => api.get('/api/posts/', { params }),
  liveList: (params?: any) => api.get('/api/posts/live/feed', { params }),
  liveComments: (account_id: string, platform_post_id: string) =>
    api.get('/api/posts/live/comments', { params: { account_id, platform_post_id } }),
  get: (id: string) => api.get(`/api/posts/${id}`),
  create: (data: any) => api.post('/api/posts/', data),
  update: (id: string, data: any) => api.patch(`/api/posts/${id}`, data),
  delete: (id: string) => api.delete(`/api/posts/${id}`),
  publish: (id: string) => api.post(`/api/posts/${id}/publish`),
}

// Media
export const mediaApi = {
  library: {
    list: () => listMediaLibraryItems(),
    add: (item: MediaItem) => addMediaLibraryItem(item), /*
            ? 'Stockage navigateur saturé'
            : 'Impossible d’enregistrer le média'
    */ delete: (id: string) => deleteMediaLibraryItem(id),
  }
}

// Hashtags
export const hashtagsApi = {
  recommend: (data: any) => api.post('/api/hashtags/recommend', data),
  generate: (data: any) => api.post('/api/hashtags/generate', data),
  trending: (platform?: string) => api.get('/api/hashtags/trending', { params: { platform } }),
  // Library
  library: {
    list: (): HashtagGroup[] => JSON.parse(localStorage.getItem('hashtag_library') || '[]'),
    save: (group: HashtagGroup) => {
      const lib = hashtagsApi.library.list()
      const idx = lib.findIndex(g => g.id === group.id)
      if (idx >= 0) lib[idx] = group
      else lib.unshift(group)
      localStorage.setItem('hashtag_library', JSON.stringify(lib))
    },
    delete: (id: string) => {
      const lib = hashtagsApi.library.list().filter(g => g.id !== id)
      localStorage.setItem('hashtag_library', JSON.stringify(lib))
    },
  }
}

// Comments & Inbox
export const commentsApi = {
  analyze: (text: string, context?: string) =>
    api.post('/api/comments/analyze', { text, post_context: context }),
  analyzeBatch: (texts: string[], baseline?: number) =>
    api.post('/api/comments/analyze-batch', { texts, baseline_volume: baseline }),
  list: (post_id: string) => api.get('/api/comments/', { params: { post_id } }),
}

// NLP / RAG
export const nlpApi = {
  ragChat: (data: {
    message: string
    history?: { role: string; content: string }[]
    brand_name?: string
    language?: string
    brand_knowledge?: string
  }) => api.post('/api/nlp/rag/chat', data),
  ragIngestFile: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/api/nlp/rag/ingest', fd)
  },
  ragIngestText: (name: string, text: string) =>
    api.post('/api/nlp/rag/ingest-text', { name, text }),
  ragSources: () => api.get('/api/nlp/rag/sources'),
  ragDeleteSource: (source: string) => api.delete(`/api/nlp/rag/sources/${encodeURIComponent(source)}`),
  ragAutoReply: (data: {
    message_id: string
    content: string
    platform: string
    type: 'dm' | 'comment'
    brand_name?: string
    language?: string
    confidence_threshold?: number
    fallback_templates?: Record<string, string>
    account_id?: string
    recipient_id?: string
    reply_mode?: string
    reply_target_id?: string
    reply_parent_id?: string
  }) => api.post('/api/nlp/rag-autoreply', data),
}

// DM Chatbot
export const dmApi = {
  liveInbox: (params?: any) => api.get('/api/dm/live', { params }),
  analyze: (data: any) => api.post('/api/dm/analyze', data),
  send: (data: {
    account_id: string
    message: string
    recipient_id?: string
    reply_mode?: string
    reply_target_id?: string
    reply_parent_id?: string
    conversation_id?: string
    source_type?: string
  }) => api.post('/api/dm/send', data),
  respond: (data: any) => api.post('/api/dm/respond', data),
}

// Analytics
export const analyticsApi = {
  overview: (account_id: string, days?: number) =>
    api.get('/api/analytics/overview', { params: { account_id, days } }),
  predict: (data: any) => api.post('/api/analytics/predict-engagement', data),
}

// Calendar
export const calendarApi = {
  get: (start: number, end: number, account_id?: string) =>
    api.get('/api/calendar/', { params: { start_ts: start, end_ts: end, account_id } }),
  stats: (start: number, end: number) =>
    api.get('/api/calendar/stats', { params: { start_ts: start, end_ts: end } }),
}

// Content
export const contentApi = {
  generate: (data: any) => api.post('/api/content/generate', data),
}

// Alerts
export const alertsApi = {
  list: (params?: any) => api.get('/api/alerts/', { params }),
  acknowledge: (id: string) => api.patch(`/api/alerts/${id}/acknowledge`),
}

// Types
export interface MediaItem {
  id: string
  name: string
  url: string
  type: 'image' | 'video'
  mimeType: string
  size: number
  tags: string[]
  category: string
  createdAt: string
  analysis?: any
}

const MEDIA_LIBRARY_DB = 'social-agent-media-library'
const MEDIA_LIBRARY_STORE = 'items'
let mediaLibraryDbPromise: Promise<IDBDatabase> | null = null
let mediaLibraryMigrationPromise: Promise<void> | null = null

function openMediaLibraryDb(): Promise<IDBDatabase> {
  if (mediaLibraryDbPromise) return mediaLibraryDbPromise

  mediaLibraryDbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB indisponible'))
      return
    }

    const request = indexedDB.open(MEDIA_LIBRARY_DB, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(MEDIA_LIBRARY_STORE)) {
        db.createObjectStore(MEDIA_LIBRARY_STORE, { keyPath: 'id' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Impossible d’ouvrir la médiathèque'))
  })

  return mediaLibraryDbPromise
}

function runMediaLibraryTransaction<T>(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore, resolve: (value: T) => void, reject: (reason?: unknown) => void) => void
): Promise<T> {
  return openMediaLibraryDb().then((db) => new Promise((resolve, reject) => {
    const transaction = db.transaction(MEDIA_LIBRARY_STORE, mode)
    const store = transaction.objectStore(MEDIA_LIBRARY_STORE)
    transaction.onerror = () => reject(transaction.error || new Error('Transaction IndexedDB échouée'))
    operation(store, resolve, reject)
  }))
}

async function migrateLegacyMediaLibraryIfNeeded(): Promise<void> {
  if (localStorage.getItem('media_library_migrated') === '1') return
  if (mediaLibraryMigrationPromise) return mediaLibraryMigrationPromise

  mediaLibraryMigrationPromise = (async () => {
    const legacyRaw = localStorage.getItem('media_library')
    if (!legacyRaw) {
      localStorage.setItem('media_library_migrated', '1')
      return
    }
    if (legacyRaw.length > 8_000_000) {
      localStorage.removeItem('media_library')
      localStorage.setItem('media_library_migrated', '1')
      throw new Error('Ancienne médiathèque locale trop volumineuse, réinitialisée pour éviter un crash navigateur')
    }

    let legacyItems: MediaItem[] = []
    try {
      const parsed = JSON.parse(legacyRaw)
      legacyItems = Array.isArray(parsed) ? parsed : []
    } catch {
      localStorage.removeItem('media_library')
      localStorage.setItem('media_library_migrated', '1')
      return
    }

    await runMediaLibraryTransaction<void>('readwrite', (store, resolve, reject) => {
      const clearRequest = store.clear()
      clearRequest.onerror = () => reject(clearRequest.error || new Error('Impossible de migrer la médiathèque'))
      clearRequest.onsuccess = () => {
        const trimmedItems = legacyItems
          .filter((item): item is MediaItem => Boolean(item && item.id))
          .sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))
          .slice(0, 500)

        let index = 0
        const writeNext = () => {
          if (index >= trimmedItems.length) {
            resolve()
            return
          }
          const putRequest = store.put(trimmedItems[index])
          putRequest.onerror = () => reject(putRequest.error || new Error('Impossible de migrer un média'))
          putRequest.onsuccess = () => {
            index += 1
            writeNext()
          }
        }
        writeNext()
      }
    })

    localStorage.removeItem('media_library')
    localStorage.setItem('media_library_migrated', '1')
  })()

  try {
    await mediaLibraryMigrationPromise
  } finally {
    mediaLibraryMigrationPromise = null
  }
}

async function listMediaLibraryItems(): Promise<MediaItem[]> {
  await migrateLegacyMediaLibraryIfNeeded()

  return runMediaLibraryTransaction<MediaItem[]>('readonly', (store, resolve, reject) => {
    const request = store.getAll()
    request.onsuccess = () => {
      const items = (request.result || []) as MediaItem[]
      items.sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))
      resolve(items)
    }
    request.onerror = () => reject(request.error || new Error('Impossible de lire la médiathèque'))
  })
}

async function addMediaLibraryItem(item: MediaItem): Promise<void> {
  await migrateLegacyMediaLibraryIfNeeded()

  const items = await listMediaLibraryItems()
  const deduped = items.filter((existing) => existing.id !== item.id)
  const trimmedItems = [item, ...deduped].slice(0, 500)

  await runMediaLibraryTransaction<void>('readwrite', (store, resolve, reject) => {
    const clearRequest = store.clear()
    clearRequest.onerror = () => reject(clearRequest.error || new Error('Impossible de mettre à jour la médiathèque'))
    clearRequest.onsuccess = () => {
      let index = 0
      const writeNext = () => {
        if (index >= trimmedItems.length) {
          resolve()
          return
        }

        const putRequest = store.put(trimmedItems[index])
        putRequest.onerror = () => reject(new Error('Impossible d’enregistrer le média'))
        putRequest.onsuccess = () => {
          index += 1
          writeNext()
        }
      }

      writeNext()
    }
  }).catch((error) => {
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      throw new Error('Stockage navigateur saturé')
    }
    throw error
  })
}

async function deleteMediaLibraryItem(id: string): Promise<void> {
  await migrateLegacyMediaLibraryIfNeeded()

  return runMediaLibraryTransaction<void>('readwrite', (store, resolve, reject) => {
    const request = store.delete(id)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error || new Error('Impossible de supprimer le média'))
  })
}

export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Unable to read file'))
    reader.readAsDataURL(file)
  })
}

export function downscaleImageFile(
  file: File,
  options?: {
    maxWidth?: number
    maxHeight?: number
    quality?: number
    outputType?: string
  }
): Promise<string> {
  const {
    maxWidth = 1600,
    maxHeight = 1600,
    quality = 0.82,
    outputType = 'image/jpeg',
  } = options || {}

  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        const ratio = Math.min(1, maxWidth / img.width, maxHeight / img.height)
        const width = Math.max(1, Math.round(img.width * ratio))
        const height = Math.max(1, Math.round(img.height * ratio))
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height

        const ctx = canvas.getContext('2d')
        if (!ctx) {
          reject(new Error('Canvas unavailable'))
          return
        }

        ctx.drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL(outputType, quality))
      }
      img.onerror = () => reject(new Error('Unable to decode image'))
      img.src = String(reader.result || '')
    }

    reader.onerror = () => reject(new Error('Unable to read file'))
    reader.readAsDataURL(file)
  })
}

export function dataUrlToFile(dataUrl: string, filename = 'upload.jpg'): File {
  const [header, payload] = dataUrl.split(',', 2)
  if (!header || !payload || !header.startsWith('data:')) {
    throw new Error('Invalid data URL')
  }

  const mimeMatch = header.match(/^data:([^;]+);base64$/)
  if (!mimeMatch) {
    throw new Error('Unsupported data URL format')
  }

  const mimeType = mimeMatch[1]
  const binary = atob(payload)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new File([bytes], filename, { type: mimeType })
}

export interface HashtagGroup {
  id: string
  name: string
  topic: string
  platform: string
  hashtags: string[]
  createdAt: string
  performance_score?: number
}

export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
  preferred_language: string
}
