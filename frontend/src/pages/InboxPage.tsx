import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'

import { PageHeader, Card, Btn, Spinner, AccountScopeTabs, PlatformIcon } from '../components/ui'
import { dmApi, nlpApi, postsApi } from '../lib/api'
import { useAppStore, useResourceCache } from '../store'

function logInboxError(message: unknown, options?: unknown) {
  console.warn('[Inbox]', message, options || '')
}

type SentimentType = 'positive' | 'negative' | 'neutral' | 'spam' | 'toxic' | 'female' | 'human'
type InboxTab = 'messages' | 'posts'

const INBOX_REFRESH_MS = 300000
const POSTS_REFRESH_MS = 300000

interface DM {
  id: string
  account_id: string
  recipient_id?: string
  can_reply?: boolean
  reply_disabled_reason?: string
  reply_mode?: string
  reply_target_id?: string
  reply_parent_id?: string
  reply_action_label?: string
  author: string
  platform: string
  text: string
  messages?: ConversationMessage[]
  sourceType?: 'dm' | 'comment' | 'post'
  sentiment?: SentimentType
  sentimentScore?: number
  emotion?: string
  isQuestion?: boolean
  isLead?: boolean
  isToxic?: boolean
  isSpam?: boolean
  suggestedReply?: string
  timestamp: string
  analyzed?: boolean
  avatar?: string
  autoReplied?: boolean
  requiresHuman?: boolean
}

interface ConversationMessage {
  id: string
  text: string
  timestamp?: string
  author?: string
  isFromPage?: boolean
  label?: SentimentType
  sentimentScore?: number
  isQuestion?: boolean
  isLead?: boolean
  isToxic?: boolean
  isSpam?: boolean
  autoReplied?: boolean
  requiresHuman?: boolean
}

interface PostComment {
  id: string
  author: string
  platform: string
  text: string
  timestamp: string
  label?: SentimentType
  sentimentScore?: number
  isSpam?: boolean
  isToxic?: boolean
  canReply?: boolean
  replyMode?: string
  replyTargetId?: string
  replyParentId?: string
  replyActionLabel?: string
  autoReplied?: boolean
  requiresHuman?: boolean
  isReply?: boolean;
  parentCommentId?: string
}

interface Post {
  id: string
  account_id: string
  platform: string
  text: string
  timestamp: string
  likes: number
  commentsCount: number
  mediaUrl?: string
  mediaType?: string
  predictedEngagementPercent?: number
}

const SENTIMENT_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  positive: { bg: 'rgba(34,197,94,0.12)', color: 'var(--green)', border: 'rgba(34,197,94,0.25)' },
  negative: { bg: 'rgba(244,63,94,0.12)', color: 'var(--red)', border: 'rgba(244,63,94,0.25)' },
  neutral: { bg: 'rgba(90,90,112,0.15)', color: 'var(--text-2)', border: 'var(--border)' },
  spam: { bg: 'rgba(249,115,22,0.12)', color: 'var(--orange)', border: 'rgba(249,115,22,0.25)' },
  toxic: { bg: 'rgba(168,85,247,0.12)', color: '#a855f7', border: 'rgba(168,85,247,0.25)' },
  female: { bg: 'rgba(236,72,153,0.12)', color: '#ec4899', border: 'rgba(236,72,153,0.25)' },
  human: { bg: 'rgba(249,115,22,0.12)', color: 'var(--orange)', border: 'rgba(249,115,22,0.25)' },
}

function LabelBadge({ label, type }: { label: string; type?: string }) {
  const style = type ? SENTIMENT_COLORS[type] || SENTIMENT_COLORS.neutral : SENTIMENT_COLORS.neutral
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 999, fontSize: 10, fontWeight: 600,
      background: style.bg, color: style.color, border: `1px solid ${style.border}`,
    }}>{label}</span>
  )
}

function platformEmoji(p: string) {
  return { instagram: '📸', facebook: '📘', twitter: '🐦', linkedin: '💼', tiktok: '🎵', threads: '@' }[p] || '🌐'
}

function formatInboxTime(value?: string) {
  if (!value) return ''
  return new Date(value).toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function messengerPolicyHint(dm: DM) {
  if (dm.platform !== 'facebook' || dm.can_reply !== false) return ''
  return dm.reply_disabled_reason || "La fenetre Messenger de 24h est expiree. Le client doit renvoyer un message avant une reponse libre."
}

function MessageAnalysisBadges({ message }: { message: ConversationMessage }) {
  if (message.isFromPage) return null
  const hasAnalysis = message.label || message.isQuestion || message.isLead || message.isToxic || message.isSpam || message.requiresHuman
  if (!hasAnalysis) return null
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
      {message.label && <LabelBadge label={message.label} type={message.label} />}
      {message.isQuestion && <LabelBadge label="Question" />}
      {message.isLead && <LabelBadge label="Lead" />}
      {message.isToxic && <LabelBadge label="Toxique" type="toxic" />}
      {message.isSpam && <LabelBadge label="Spam" type="spam" />}
      {message.requiresHuman && <LabelBadge label="Humain requis" type="human" />}
    </div>
  )
}

function formatPlatformErrors(errors: any[] | undefined, label: string) {
  if (!errors?.length) return ''
  return errors
    .map((err) => {
      const platform = String(err?.platform || 'plateforme')
      const accountName = String(err?.account_name || '').trim()
      const detail = String(err?.error || 'Erreur inconnue').trim()
      return `${label} ${platform}${accountName ? ` (${accountName})` : ''}: ${detail}`
    })
    .join('\n')
}

function looksLikeVideo(post: Post | null) {
  if (!post) return false
  const mediaType = String(post.mediaType || '').toLowerCase()
  const mediaUrl = String(post.mediaUrl || '').toLowerCase()
  return mediaType === 'video' || mediaType === 'reel' || mediaType === 'reels' || mediaUrl.endsWith('.mp4') || mediaUrl.includes('.mp4?')
}

function readRagAutoReplySettings() {
  const confidenceThreshold = Number(localStorage.getItem('rag_confidenceThreshold') || '0.6')
  return {
    enabled: localStorage.getItem('rag_autoReply') === 'true',
    dms: localStorage.getItem('rag_scope_dms') !== 'false',
    comments: localStorage.getItem('rag_scope_comments') !== 'false',
    confidenceThreshold: Number.isFinite(confidenceThreshold) ? confidenceThreshold : 0.6,
    fallbackTemplates: {
      fr: localStorage.getItem('rag_fallback_fr') || 'Merci pour votre message. Notre equipe vous repondra dans les plus brefs delais.',
      ar: localStorage.getItem('rag_fallback_ar') || 'شكرا على رسالتك. سيرد عليك فريقنا في أقرب وقت.',
      darija: localStorage.getItem('rag_fallback_darija') || 'شكرا على الرسالة ديالك. الفريق ديالنا غادي يجاوبك فاقرب وقت.',
      en: localStorage.getItem('rag_fallback_en') || 'Thank you for your message. Our team will get back to you shortly.',
    },
    accountEnabled: (accountId?: string) => !accountId || localStorage.getItem(`rag_account_${accountId}`) !== 'false',
  }
}

function getHumanRequiredIds() {
  try {
    return new Set(JSON.parse(localStorage.getItem('rag_humanRequiredIds') || '[]'))
  } catch {
    return new Set<string>()
  }
}

function saveHumanRequiredIds(ids: Set<unknown>) {
  localStorage.setItem('rag_humanRequiredIds', JSON.stringify(Array.from(ids).slice(-500)))
}

function getAutoRepliedIds() {
  try {
    return new Set(JSON.parse(localStorage.getItem('rag_autoRepliedIds') || '[]'))
  } catch {
    return new Set<string>()
  }
}

function saveAutoRepliedIds(ids: Set<unknown>) {
  localStorage.setItem('rag_autoRepliedIds', JSON.stringify(Array.from(ids).slice(-500)))
}

function stableTextKey(text: string) {
  return String(text || '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180)
}

function stableAutoReplyKey(parts: Array<string | undefined>) {
  return parts.map(part => String(part || '').trim()).join(':')
}

function appendAutoReplyHistory(entry: {
  id: string
  client: string
  type: 'dm' | 'comment'
  platform: string
  incoming: string
  reply: string
  confidence?: number
  deliveryStatus?: string
  requiresHuman?: boolean
}) {
  try {
    const current = JSON.parse(localStorage.getItem('rag_autoReplyHistory') || '[]')
    const history = Array.isArray(current) ? current : []
    const next = [
      { ...entry, time: new Date().toISOString() },
      ...history.filter(item => item?.id !== entry.id),
    ].slice(0, 10)
    localStorage.setItem('rag_autoReplyHistory', JSON.stringify(next))
    window.dispatchEvent(new Event('rag-history:changed'))
  } catch {
    localStorage.setItem('rag_autoReplyHistory', JSON.stringify([{ ...entry, time: new Date().toISOString() }]))
    window.dispatchEvent(new Event('rag-history:changed'))
  }
}

function isAfterAutoReplyEnabled(timestamp?: string) {
  const enabledAt = localStorage.getItem('rag_autoReplyEnabledAt')
  if (!enabledAt || !timestamp) return false
  const enabledMs = Date.parse(enabledAt)
  const itemMs = Date.parse(timestamp)
  if (Number.isNaN(enabledMs) || Number.isNaN(itemMs)) return false
  return itemMs >= enabledMs
}

async function analyzeMessage(text: string): Promise<Partial<DM>> {
  try {
    const response = await dmApi.analyze({ message: text })
    return response.data || { sentiment: 'neutral', analyzed: true }
  } catch {
    return { sentiment: 'neutral', analyzed: true }
  }
}

export default function InboxPage() {
  const [searchParams] = useSearchParams()
  const { accounts, selectedAccount, setSelectedAccount } = useAppStore()
  const { getResource, setResource } = useResourceCache()
  const [tab, setTab] = useState<InboxTab>('messages')
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [loadingPosts, setLoadingPosts] = useState(true)
  const [loadingComments, setLoadingComments] = useState(false)
  const [dms, setDms] = useState<DM[]>([])
  const [posts, setPosts] = useState<Post[]>([])
  const [comments, setComments] = useState<PostComment[]>([])
  const [dmFilter, setDmFilter] = useState('all')
  const [commentFilter, setCommentFilter] = useState('all')
  const [selectedDm, setSelectedDm] = useState<DM | null>(null)
  const [selectedPost, setSelectedPost] = useState<Post | null>(null)
  const [replyingCommentId, setReplyingCommentId] = useState<string | null>(null)
  const [commentReplyText, setCommentReplyText] = useState('')
  const [sendingCommentReply, setSendingCommentReply] = useState(false)
  const [postReplyText, setPostReplyText] = useState('')
  const [sendingPostReply, setSendingPostReply] = useState(false)
  const [analyzingId, setAnalyzingId] = useState<string | null>(null)
  const [analyzingAll, setAnalyzingAll] = useState(false)
  const [replyText, setReplyText] = useState('')
  const [sendingReply, setSendingReply] = useState(false)
  const messagesRefreshInFlight = useRef(false)
  const commentsRefreshInFlight = useRef(false)

  const activeAccountId = selectedAccount?.id
  const targetTab = searchParams.get('tab')
  const targetDm = searchParams.get('dm')
  const targetPost = searchParams.get('post')
  const targetFilter = searchParams.get('filter')
  const messagesCacheKey = `inbox:messages:${activeAccountId || 'all'}`
  const postsCacheKey = `inbox:posts:${activeAccountId || 'all'}`
  const dmPlatforms = Array.from(new Set(dms.map((dm) => dm.platform)))
  const postPlatforms = Array.from(new Set(posts.map((post) => post.platform)))

  const applyDmAutoReplies = async (items: DM[]) => {
    const settings = readRagAutoReplySettings()
    if (!settings.enabled || !settings.dms) return items

    const replied = getAutoRepliedIds()
    const humanRequired = getHumanRequiredIds()
    const next = items.map(item => ({ ...item, messages: item.messages ? [...item.messages] : [] }))
    for (const dm of next) {
      if (!settings.accountEnabled(dm.account_id)) continue
      const incomingMessages = (dm.messages?.length ? dm.messages : [{
        id: dm.id,
        text: dm.text,
        timestamp: dm.timestamp,
        isFromPage: false,
      }]).filter(message => !message.isFromPage && message.text && isAfterAutoReplyEnabled(message.timestamp)).slice(-1)

      for (const message of incomingMessages) {
        const legacyKey = `dm:${dm.platform}:${message.id}`
        const key = stableAutoReplyKey([
          'dm',
          dm.account_id,
          dm.platform,
          dm.recipient_id || dm.reply_target_id || dm.id,
          message.timestamp || dm.timestamp,
          stableTextKey(message.text),
        ])
        if (replied.has(key) || replied.has(legacyKey)) {
          replied.add(key)
          message.autoReplied = true
          dm.autoReplied = true
          if (humanRequired.has(key) || humanRequired.has(legacyKey)) {
            humanRequired.add(key)
            message.requiresHuman = true
            dm.requiresHuman = true
          }
          continue
        }
        try {
          const response = await nlpApi.ragAutoReply({
            message_id: message.id,
            content: message.text,
            platform: dm.platform,
            type: 'dm',
            language: 'auto',
            confidence_threshold: settings.confidenceThreshold,
            fallback_templates: settings.fallbackTemplates,
            account_id: dm.account_id,
            recipient_id: dm.recipient_id,
            reply_mode: dm.reply_mode || 'dm',
            reply_target_id: dm.reply_target_id || dm.recipient_id || message.id,
            reply_parent_id: dm.reply_parent_id,
          })
          const payload = response.data || {}
          replied.add(key)
          replied.add(legacyKey)
          message.autoReplied = true
          dm.autoReplied = true
          if (payload.requires_human || payload.delivery_status === 'delivery_failed' || payload.delivery_status === 'account_not_found') {
            humanRequired.add(key)
            humanRequired.add(legacyKey)
            message.requiresHuman = true
            dm.requiresHuman = true
          }
          appendAutoReplyHistory({
            id: key,
            client: dm.author,
            type: 'dm',
            platform: dm.platform,
            incoming: message.text,
            reply: String(payload.reply || ''),
            confidence: Number(payload.confidence ?? 0),
            deliveryStatus: payload.delivery_status,
            requiresHuman: !!payload.requires_human,
          })
        } catch (err) {
          logInboxError('Auto-reponse RAG DM ignoree', err)
        }
      }
    }
    saveAutoRepliedIds(replied)
    saveHumanRequiredIds(humanRequired)
    return next
  }

  const applyCommentAutoReplies = async (items: PostComment[]) => {
    const settings = readRagAutoReplySettings()
    if (!settings.enabled || !settings.comments) return items

    const replied = getAutoRepliedIds()
    const humanRequired = getHumanRequiredIds()
    const next = items.map(item => ({ ...item }))
    if (!settings.accountEnabled(selectedPost?.account_id)) return next
    for (const comment of next) {
      if (comment.isFromPage) continue
      if (!isAfterAutoReplyEnabled(comment.timestamp)) continue
      const legacyKey = `comment:${comment.platform}:${comment.id}`
      const key = stableAutoReplyKey([
        'comment',
        selectedPost?.account_id,
        comment.platform,
        selectedPost?.id || comment.replyParentId,
        comment.replyTargetId || comment.id,
        comment.timestamp,
        stableTextKey(comment.text),
      ])
      if (replied.has(key) || replied.has(legacyKey)) {
        replied.add(key)
        comment.autoReplied = true
        if (humanRequired.has(key) || humanRequired.has(legacyKey)) {
          humanRequired.add(key)
          comment.requiresHuman = true
        }
        continue
      }
      try {
        const response = await nlpApi.ragAutoReply({
          message_id: comment.replyTargetId || comment.id,
          content: comment.text,
          platform: comment.platform,
          type: 'comment',
          language: 'auto',
          confidence_threshold: settings.confidenceThreshold,
          fallback_templates: settings.fallbackTemplates,
          account_id: selectedPost?.account_id,
          reply_mode: comment.replyMode || 'comment',
          reply_target_id: comment.replyTargetId || comment.id,
          reply_parent_id: comment.replyParentId || selectedPost?.id,
        })
        const payload = response.data || {}
        replied.add(key)
        replied.add(legacyKey)
        comment.autoReplied = true
        if (payload.requires_human || payload.delivery_status === 'delivery_failed' || payload.delivery_status === 'account_not_found') {
          humanRequired.add(key)
          humanRequired.add(legacyKey)
          comment.requiresHuman = true
        }
        appendAutoReplyHistory({
          id: key,
          client: comment.author,
          type: 'comment',
          platform: comment.platform,
          incoming: comment.text,
          reply: String(payload.reply || ''),
          confidence: Number(payload.confidence ?? 0),
          deliveryStatus: payload.delivery_status,
          requiresHuman: !!payload.requires_human,
        })
      } catch (err) {
        logInboxError('Auto-reponse RAG commentaire ignoree', err)
      }
    }
    saveAutoRepliedIds(replied)
    saveHumanRequiredIds(humanRequired)
    return next
  }

  const loadMessages = async (options: { background?: boolean } = {}) => {
    if (options.background && messagesRefreshInFlight.current) return
    if (options.background) messagesRefreshInFlight.current = true
    const cached = getResource<DM[]>(messagesCacheKey)
    if (!options.background && cached?.data?.length) {
      setDms(cached.data)
      setSelectedDm(curr => cached.data.find((item: DM) => item.id === curr?.id) || curr || cached.data[0] || null)
      setLoadingMessages(false)
    } else if (!options.background) {
      setLoadingMessages(true)
    }
    try {
      const res = await dmApi.liveInbox(activeAccountId ? { account_id: activeAccountId, kind: 'dm' } : { kind: 'dm' })
      const rawItems = (res.data.items || []).map((item: any) => ({
        id: String(item.id),
        account_id: String(item.account_id),
        recipient_id: item.recipient_id ? String(item.recipient_id) : '',
        can_reply: item.can_reply !== false,
        reply_disabled_reason: item.reply_disabled_reason || '',
        reply_mode: item.reply_mode || 'dm',
        reply_target_id: item.reply_target_id ? String(item.reply_target_id) : '',
        reply_parent_id: item.reply_parent_id ? String(item.reply_parent_id) : '',
        reply_action_label: item.reply_action_label || 'Repondre',
        author: item.sender_name || 'Utilisateur',
        platform: item.platform,
        text: item.message || '',
        messages: (item.messages || []).map((message: any) => ({
          id: String(message.id),
          text: message.text || '',
          timestamp: message.timestamp || '',
          author: message.author || '',
          isFromPage: !!message.is_from_page,
          label: message.label || undefined,
          sentimentScore: message.sentiment_score ?? 0,
          isQuestion: !!message.is_question,
          isLead: !!message.is_lead,
          isToxic: !!message.is_toxic,
          isSpam: !!message.is_spam,
          autoReplied: getAutoRepliedIds().has(`dm:${item.platform}:${String(message.id)}`),
          requiresHuman: getHumanRequiredIds().has(`dm:${item.platform}:${String(message.id)}`),
        })),
        sourceType: item.source_type || 'dm',
        sentiment: item.label || item.sentiment || 'neutral',
        sentimentScore: item.sentiment_score ?? 0,
        isSpam: !!item.is_spam,
        isToxic: !!item.is_toxic,
        isQuestion: !!item.is_question,
        isLead: !!item.is_lead,
        suggestedReply: item.suggested_reply || '',
        timestamp: item.timestamp || '',
        avatar: (item.sender_name || '?').charAt(0).toUpperCase(),
        analyzed: !!item.label,
        autoReplied: getAutoRepliedIds().has(`dm:${item.platform}:${String(item.id)}`),
        requiresHuman: getHumanRequiredIds().has(`dm:${item.platform}:${String(item.id)}`),
      }))
      const items = await applyDmAutoReplies(rawItems)
      setDms(items)
      setResource(messagesCacheKey, items)
      setSelectedDm(curr => items.find((item: DM) => item.id === curr?.id) || items[0] || null)
      if (res.data.errors?.length) {
        logInboxError(formatPlatformErrors(res.data.errors, 'Inbox') || `Certaines inbox n'ont pas pu etre chargees (${res.data.errors.length})`, {
          duration: 9000,
        })
      }
    } catch {
      if (!cached?.data?.length) logInboxError('Erreur de chargement des messages')
    } finally {
      setLoadingMessages(false)
      if (options.background) messagesRefreshInFlight.current = false
    }
  }

  const loadPosts = async (options: { background?: boolean } = {}) => {
    const cached = getResource<Post[]>(postsCacheKey)
    if (!options.background && cached?.data?.length) {
      setPosts(cached.data)
      setSelectedPost(curr => cached.data.find((item: Post) => item.id === curr?.id) || curr || cached.data[0] || null)
      setLoadingPosts(false)
    } else if (!options.background) {
      setLoadingPosts(true)
    }
    try {
      const res = await postsApi.liveList(activeAccountId ? { account_id: activeAccountId, limit: 20 } : { limit: 20 })
      const items = (res.data.items || []).map((item: any) => ({
        id: String(item.id),
        account_id: String(item.account_id),
        platform: item.platform,
        text: item.text || '',
        timestamp: item.timestamp || '',
        likes: item.likes || 0,
        commentsCount: item.comments_count || 0,
        mediaUrl: item.media_url || '',
        mediaType: item.media_type || '',
        predictedEngagementPercent: item.predicted_engagement_percent ?? undefined,
      }))
      setPosts(items)
      setResource(postsCacheKey, items)
      setSelectedPost(curr => items.find((item: Post) => item.id === curr?.id) || items[0] || null)
      if (res.data.errors?.length) {
        logInboxError(formatPlatformErrors(res.data.errors, 'Plateforme') || `Certaines plateformes n'ont pas pu etre chargees (${res.data.errors.length})`, {
          duration: 9000,
        })
      }
    } catch {
      if (!cached?.data?.length) logInboxError('Erreur de chargement des publications')
    } finally {
      setLoadingPosts(false)
    }
  }

  const loadComments = async (post: Post | null, options: { background?: boolean } = {}) => {
    if (options.background && commentsRefreshInFlight.current) return
    if (options.background) commentsRefreshInFlight.current = true
    if (!post) {
      setComments([])
      setReplyingCommentId(null)
      setCommentReplyText('')
      setPostReplyText('')
      if (options.background) commentsRefreshInFlight.current = false
      return
    }
    const key = `inbox:comments:${post.account_id}:${post.id}`
    const cached = getResource<PostComment[]>(key)
    if (!options.background && cached?.data?.length) {
      setComments(cached.data)
      setLoadingComments(false)
    } else if (!options.background) {
      setLoadingComments(true)
    }
    try {
      const res = await postsApi.liveComments(post.account_id, post.id)
      const rawItems = (res.data.items || []).map((item: any) => ({
        id: String(item.id),
        author: item.author || 'Utilisateur',
        platform: item.platform,
        text: item.text || '',
        timestamp: item.timestamp || '',
        label: item.label || 'neutral',
        sentimentScore: item.sentiment_score ?? 0,
        isSpam: !!item.is_spam,
        isToxic: !!item.is_toxic,
        canReply: item.can_reply !== false,
        isFromPage: !!item.is_from_page,
        replyMode: item.reply_mode || 'comment',
        replyTargetId: item.reply_target_id ? String(item.reply_target_id) : '',
        replyParentId: item.reply_parent_id ? String(item.reply_parent_id) : '',
        replyActionLabel: item.reply_action_label || 'Repondre au commentaire',
        autoReplied: getAutoRepliedIds().has(`comment:${item.platform}:${String(item.id)}`),
        requiresHuman: getHumanRequiredIds().has(`comment:${item.platform}:${String(item.id)}`),
        isReply: !!item.is_reply,
        parentCommentId: item.parent_comment_id || undefined,
      }))
      const items = await applyCommentAutoReplies(rawItems)
      setComments(items)
      setResource(key, items)
      setReplyingCommentId(null)
      setCommentReplyText('')
      setPostReplyText('')
    } catch {
      if (!cached?.data?.length) {
        setComments([])
        logInboxError('Erreur de chargement des commentaires')
      }
    } finally {
      setLoadingComments(false)
      if (options.background) commentsRefreshInFlight.current = false
    }
  }

  useEffect(() => {
    if (!accounts.length) {
      setDms([])
      setPosts([])
      setComments([])
      return
    }
    loadMessages()
    loadPosts()
    const refreshMessages = () => {
      if (!document.hidden) loadMessages({ background: true })
    }
    const refreshAll = () => {
      if (document.hidden) return
      loadMessages({ background: true })
      loadPosts({ background: true })
    }
    const messagesInterval = window.setInterval(refreshMessages, INBOX_REFRESH_MS)
    const postsInterval = window.setInterval(() => {
      if (!document.hidden) loadPosts({ background: true })
    }, POSTS_REFRESH_MS)
    window.addEventListener('focus', refreshAll)
    document.addEventListener('visibilitychange', refreshAll)
    return () => {
      window.clearInterval(messagesInterval)
      window.clearInterval(postsInterval)
      window.removeEventListener('focus', refreshAll)
      document.removeEventListener('visibilitychange', refreshAll)
    }
  }, [activeAccountId, accounts.length])

  useEffect(() => {
    if (targetTab === 'posts') setTab('posts')
    if (targetTab === 'messages') setTab('messages')
  }, [targetTab])

  useEffect(() => {
    if (!targetDm || !dms.length) return
    const match = dms.find((dm) => dm.id === targetDm || dm.reply_target_id === targetDm)
    if (match) {
      setTab('messages')
      setSelectedDm(match)
    }
  }, [targetDm, dms])

  useEffect(() => {
    if (!targetPost || !posts.length) return
    const match = posts.find((post) => post.id === targetPost)
    if (match) {
      setTab('posts')
      setSelectedPost(match)
      if (targetFilter) setCommentFilter(targetFilter)
    }
  }, [targetPost, targetFilter, posts])

  useEffect(() => {
    loadComments(selectedPost)
    if (!selectedPost) return
    const refreshComments = () => {
      if (!document.hidden) loadComments(selectedPost, { background: true })
    }
    const interval = window.setInterval(refreshComments, INBOX_REFRESH_MS)
    window.addEventListener('focus', refreshComments)
    document.addEventListener('visibilitychange', refreshComments)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', refreshComments)
      document.removeEventListener('visibilitychange', refreshComments)
    }
  }, [selectedPost?.id])

  const postReplyConfig = useMemo(() => {
    if (!selectedPost) return null
    if (selectedPost.platform === 'facebook') {
      return {
        canReply: true,
        replyMode: 'comment',
        replyTargetId: selectedPost.id,
        replyParentId: selectedPost.id,
        actionLabel: 'Commenter sur la publication',
      }
    }
    if (selectedPost.platform === 'linkedin') {
      return {
        canReply: true,
        replyMode: 'post_reply',
        replyTargetId: selectedPost.id,
        replyParentId: selectedPost.id,
        actionLabel: 'Commenter sur le post',
      }
    }
    if (selectedPost.platform === 'twitter') {
      return {
        canReply: true,
        replyMode: 'post_reply',
        replyTargetId: selectedPost.id,
        replyParentId: selectedPost.id,
        actionLabel: 'Repondre au post',
      }
    }
    return null
  }, [selectedPost])

  const handleAnalyzeDm = async (dm: DM) => {
    setAnalyzingId(dm.id)
    try {
      const result = await analyzeMessage(dm.text)
      setDms(ms => ms.map(m => m.id === dm.id ? { ...m, ...result, analyzed: true } : m))
      if (selectedDm?.id === dm.id) setSelectedDm(d => d ? { ...d, ...result, analyzed: true } : d)
      toast.success('Message analyse')
    } catch {
      logInboxError("Erreur d'analyse")
    } finally {
      setAnalyzingId(null)
    }
  }

  const handleAnalyzeAll = async () => {
    const unanalyzed = dms.filter(m => !m.analyzed)
    if (!unanalyzed.length) {
      toast('Tous deja analyses')
      return
    }
    setAnalyzingAll(true)
    for (const dm of unanalyzed) {
      const result = await analyzeMessage(dm.text)
      setDms(ms => ms.map(m => m.id === dm.id ? { ...m, ...result, analyzed: true } : m))
    }
    setAnalyzingAll(false)
    toast.success(`${unanalyzed.length} messages analyses !`)
  }

  const handleSendReply = async () => {
    if (!selectedDm || !replyText.trim()) return
    if (selectedDm.can_reply === false) {
      logInboxError(selectedDm.reply_disabled_reason || "La reponse n'est pas disponible pour cette conversation")
      return
    }
    if (selectedDm.reply_mode === 'dm' && !selectedDm.recipient_id) {
      logInboxError("Ce message ne contient pas d'identifiant destinataire exploitable")
      return
    }
    setSendingReply(true)
    const sentText = replyText.trim()
    try {
      await dmApi.send({
        account_id: selectedDm.account_id,
        message: sentText,
        recipient_id: selectedDm.recipient_id,
        reply_mode: selectedDm.reply_mode,
        reply_target_id: selectedDm.reply_target_id,
        reply_parent_id: selectedDm.reply_parent_id,
        conversation_id: selectedDm.id,
        source_type: selectedDm.sourceType,
      })
      const sentMessage: ConversationMessage = {
        id: `local:${selectedDm.id}:${Date.now()}`,
        text: sentText,
        timestamp: new Date().toISOString(),
        author: 'Vous',
        isFromPage: true,
      }
      const appendSentMessage = (dm: DM): DM => ({
        ...dm,
        text: sentText,
        timestamp: sentMessage.timestamp || dm.timestamp,
        messages: [...(dm.messages?.length ? dm.messages : selectedConversationMessages), sentMessage],
      })
      const nextDms = dms.map(dm => dm.id === selectedDm.id ? appendSentMessage(dm) : dm)
      setDms(nextDms)
      setResource(messagesCacheKey, nextDms)
      setSelectedDm(dm => dm && dm.id === selectedDm.id ? appendSentMessage(dm) : dm)
      toast.success('Reponse envoyee')
      setReplyText('')
    } catch (err: any) {
      logInboxError(err.response?.data?.detail || "Erreur d'envoi")
    } finally {
      setSendingReply(false)
    }
  }

  const handleSendCommentReply = async (comment: PostComment) => {
    if (!selectedPost || !commentReplyText.trim()) return
    if (comment.canReply === false) {
      logInboxError("La reponse n'est pas disponible pour ce commentaire")
      return
    }
    setSendingCommentReply(true)
    try {
      await dmApi.send({
        account_id: selectedPost.account_id,
        message: commentReplyText.trim(),
        reply_mode: comment.replyMode,
        reply_target_id: comment.replyTargetId,
        reply_parent_id: comment.replyParentId,
        source_type: 'comment',
      })
      toast.success('Reponse au commentaire envoyee')
      setReplyingCommentId(null)
      setCommentReplyText('')
    } catch (err: any) {
      logInboxError(err.response?.data?.detail || "Erreur d'envoi")
    } finally {
      setSendingCommentReply(false)
    }
  }

  const handleSendPostReply = async () => {
    if (!selectedPost || !postReplyConfig || !postReplyText.trim()) return
    setSendingPostReply(true)
    try {
      await dmApi.send({
        account_id: selectedPost.account_id,
        message: postReplyText.trim(),
        reply_mode: postReplyConfig.replyMode,
        reply_target_id: postReplyConfig.replyTargetId,
        reply_parent_id: postReplyConfig.replyParentId,
        source_type: 'post',
      })
      toast.success('Reponse a la publication envoyee')
      setPostReplyText('')
    } catch (err: any) {
      logInboxError(err.response?.data?.detail || "Erreur d'envoi")
    } finally {
      setSendingPostReply(false)
    }
  }

  const DM_FILTERS = [
    { key: 'all', label: 'Tous' }, { key: 'positive', label: 'Positifs' },
    { key: 'negative', label: 'Negatifs' }, { key: 'neutral', label: 'Neutres' },
    { key: 'spam', label: 'Spam' }, { key: 'toxic', label: 'Toxiques' },
    { key: 'leads', label: 'Leads' },
  ]

  const filteredDms = dms.filter(m => {
    if (dmFilter === 'all') return true
    if (dmFilter === 'leads') return m.isLead
    return m.sentiment === dmFilter
  })

  const filteredComments = useMemo(() => {
    if (commentFilter === 'all') return comments
    return comments.filter((comment) => comment.label === commentFilter)
  }, [comments, commentFilter])

  const dmStats = {
    positive: dms.filter(m => m.sentiment === 'positive').length,
    negative: dms.filter(m => m.sentiment === 'negative').length,
    toxic: dms.filter(m => m.sentiment === 'toxic').length,
    spam: dms.filter(m => m.sentiment === 'spam').length,
    leads: dms.filter(m => m.isLead).length,
  }

  const selectedConversationMessages: ConversationMessage[] = selectedDm?.messages?.length
    ? selectedDm.messages
    : selectedDm
      ? [{
          id: selectedDm.id,
          text: selectedDm.text,
          timestamp: selectedDm.timestamp,
          author: selectedDm.author,
          isFromPage: false,
          label: selectedDm.sentiment,
          sentimentScore: selectedDm.sentimentScore,
          isQuestion: selectedDm.isQuestion,
          isLead: selectedDm.isLead,
          isToxic: selectedDm.isToxic,
          isSpam: selectedDm.isSpam,
        }]
      : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <div style={{ flexShrink: 0 }}>
        <PageHeader
          title="Boite de reception"
          subtitle="Messages directs et commentaires reels de vos comptes connectes"
          actions={tab === 'messages' ? <Btn onClick={handleAnalyzeAll} disabled={analyzingAll || loadingMessages}>{analyzingAll ? 'Analyse...' : 'Analyser tout'}</Btn> : undefined}
        />

        <div style={{ padding: '0 32px' }}>
          <AccountScopeTabs
            accounts={accounts}
            selectedAccount={selectedAccount}
            onChange={setSelectedAccount}
            allowAll
            allLabel="Tous les comptes"
          />
        </div>

        <div style={{ padding: '0 32px', display: 'flex', gap: 4, borderBottom: '1px solid var(--border)' }}>
          {[
            { key: 'messages', label: 'Messages', count: dms.length },
            { key: 'posts', label: 'Posts & Commentaires', count: posts.length },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key as InboxTab)}
              style={{
                padding: '10px 16px', background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 13, fontWeight: 600, borderBottom: `2px solid ${tab === t.key ? 'var(--accent)' : 'transparent'}`,
                color: tab === t.key ? 'var(--text)' : 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 8, marginBottom: -1,
              }}
            >
              {t.label}
              <span style={{ padding: '1px 6px', borderRadius: 999, fontSize: 10, fontWeight: 700, background: tab === t.key ? 'rgba(108,99,255,0.2)' : 'var(--bg-2)', color: tab === t.key ? 'var(--accent-2)' : 'var(--text-3)' }}>{t.count}</span>
            </button>
          ))}
        </div>
      </div>

      {tab === 'messages' && (
        <div style={{ display: 'flex', flexDirection: 'column', padding: '16px 32px 32px' }}>
          {dmPlatforms.length > 0 && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap', flexShrink: 0 }}>
              {dmPlatforms.map((platform) => (
                <div key={platform} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 999, background: 'var(--bg-1)', border: '1px solid var(--border)', fontSize: 12 }}>
                  <PlatformIcon platform={platform} size={14} />
                  <span style={{ color: 'var(--text-2)' }}>{platform}</span>
                </div>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap', flexShrink: 0 }}>
            {[
              { label: 'Positifs', count: dmStats.positive, color: 'var(--green)' },
              { label: 'Negatifs', count: dmStats.negative, color: 'var(--red)' },
              { label: 'Toxiques', count: dmStats.toxic, color: '#a855f7' },
              { label: 'Spam', count: dmStats.spam, color: 'var(--orange)' },
              { label: 'Leads', count: dmStats.leads, color: 'var(--accent-3)' },
            ].map(s => (
              <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 8, background: 'var(--bg-1)', border: '1px solid var(--border)', fontSize: 12 }}>
                <span style={{ fontWeight: 700, color: s.color, fontFamily: 'var(--font-display)' }}>{s.count}</span>
                <span style={{ color: 'var(--text-3)' }}>{s.label}</span>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '360px minmax(0, 1fr)', gap: 18, alignItems: 'start' }}>
            <div style={{ width: '100%', display: 'flex', flexDirection: 'column', position: 'sticky', top: 12 }}>
              <div style={{ display: 'flex', gap: 4, marginBottom: 10, flexWrap: 'wrap', flexShrink: 0 }}>
                {DM_FILTERS.map(f => (
                  <button key={f.key} onClick={() => setDmFilter(f.key)} style={{ padding: '3px 8px', borderRadius: 6, fontSize: 10, fontWeight: 500, cursor: 'pointer', background: dmFilter === f.key ? 'rgba(108,99,255,0.15)' : 'transparent', border: `1px solid ${dmFilter === f.key ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`, color: dmFilter === f.key ? 'var(--accent-2)' : 'var(--text-3)' }}>{f.label}</button>
                ))}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {loadingMessages ? <Spinner /> : filteredDms.map(dm => (
                  <div
                    key={dm.id}
                    onClick={() => { setSelectedDm(dm); setReplyText('') }}
                    style={{ padding: '10px 12px', borderRadius: 10, cursor: 'pointer', background: selectedDm?.id === dm.id ? 'rgba(108,99,255,0.1)' : 'var(--bg-1)', border: `1px solid ${selectedDm?.id === dm.id ? 'rgba(108,99,255,0.25)' : 'var(--border)'}` }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <div style={{ width: 26, height: 26, borderRadius: '50%', flexShrink: 0, background: 'var(--bg-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>{dm.avatar}</div>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>{dm.author}</span>
                      </div>
                      <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{formatInboxTime(dm.timestamp)}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 6 }}>{dm.text}</div>
                    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                      <PlatformIcon platform={dm.platform} size={14} />
                      {dm.sourceType && dm.sourceType !== 'dm' && <LabelBadge label={dm.sourceType} />}
                      {dm.analyzed && dm.sentiment && <LabelBadge label={dm.sentiment} type={dm.sentiment} />}
                      {dm.isLead && <LabelBadge label="Lead" />}
                      {dm.autoReplied && <LabelBadge label="Auto-repondu" type="positive" />}
                      {dm.requiresHuman && <LabelBadge label="Humain requis" type="human" />}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ width: '100%', minWidth: 0 }}>
              {!selectedDm ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-3)' }}>Selectionnez un message</div>
              ) : (
                <>
                <div style={{ width: '100%', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', background: 'var(--bg-1)', border: '1px solid var(--border)', borderRadius: 12 }}>
                  <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ height: 66, padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(255,255,255,0.02)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                        <div style={{ width: 38, height: 38, borderRadius: '50%', background: 'linear-gradient(135deg, #22c55e, #3b82f6)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, flexShrink: 0 }}>{selectedDm.avatar}</div>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: 700, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selectedDm.author}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 6 }}>Actif via <PlatformIcon platform={selectedDm.platform} size={14} /> {selectedDm.platform}</div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        {selectedDm.analyzed && selectedDm.sentiment && <LabelBadge label={selectedDm.sentiment} type={selectedDm.sentiment} />}
                        {selectedDm.isQuestion && <LabelBadge label="Question" />}
                        {selectedDm.isLead && <LabelBadge label="Lead" />}
                        {selectedDm.isToxic && <LabelBadge label="Toxique" type="toxic" />}
                        {selectedDm.isSpam && <LabelBadge label="Spam" type="spam" />}
                        {selectedDm.autoReplied && <LabelBadge label="Auto-repondu" type="positive" />}
                        {selectedDm.requiresHuman && <LabelBadge label="Humain requis" type="human" />}
                        {!selectedDm.analyzed && (
                          <Btn size="sm" variant="ghost" onClick={() => handleAnalyzeDm(selectedDm)} disabled={analyzingId === selectedDm.id}>
                            {analyzingId === selectedDm.id ? <Spinner /> : 'Analyser'}
                          </Btn>
                        )}
                      </div>
                    </div>

                    <div style={{ padding: '28px 28px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <div style={{ alignSelf: 'center', color: 'var(--text-3)', fontSize: 11, background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 999, padding: '4px 10px' }}>
                        {formatInboxTime(selectedDm.timestamp)}
                      </div>
                      {selectedConversationMessages.map((message) => (
                        <div
                          key={message.id}
                          style={{
                            alignSelf: message.isFromPage ? 'flex-end' : 'flex-start',
                            display: 'flex',
                            alignItems: 'flex-end',
                            gap: 8,
                            maxWidth: '78%',
                            flexDirection: message.isFromPage ? 'row-reverse' : 'row',
                          }}
                        >
                          <div style={{ width: 28, height: 28, borderRadius: '50%', background: message.isFromPage ? 'linear-gradient(135deg, #6c63ff, #4f8cff)' : 'var(--bg-3)', color: message.isFromPage ? 'white' : 'var(--text)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
                            {message.isFromPage ? 'A' : selectedDm.avatar}
                          </div>
                          <div>
                            <div style={{ background: message.isFromPage ? 'linear-gradient(135deg, #6c63ff, #4f8cff)' : 'var(--bg-2)', color: message.isFromPage ? 'white' : 'var(--text)', border: message.isFromPage ? 'none' : '1px solid var(--border)', borderRadius: message.isFromPage ? '18px 18px 6px 18px' : '18px 18px 18px 6px', padding: '11px 14px', lineHeight: 1.55, fontSize: 14 }}>
                              {message.text}
                            </div>
                            {!message.isFromPage && <MessageAnalysisBadges message={message} />}
                            {!message.isFromPage && message.autoReplied && (
                              <div style={{ marginTop: 6 }}>
                                <LabelBadge label="Auto-repondu" type="positive" />
                              </div>
                            )}
                            <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 4, textAlign: message.isFromPage ? 'right' : 'left' }}>
                              {formatInboxTime(message.timestamp)}
                            </div>
                          </div>
                        </div>
                      ))}

                      {messengerPolicyHint(selectedDm) && (
                        <div style={{ alignSelf: 'center', maxWidth: 560, padding: '10px 12px', borderRadius: 10, background: 'rgba(249,115,22,0.10)', border: '1px solid rgba(249,115,22,0.25)', color: 'var(--text-2)', fontSize: 12, lineHeight: 1.5 }}>
                          {messengerPolicyHint(selectedDm)}
                        </div>
                      )}

                    </div>

                    <div style={{ padding: 18, borderTop: '1px solid var(--border)', background: 'rgba(255,255,255,0.02)' }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
                        <textarea
                          value={replyText}
                          onChange={e => setReplyText(e.target.value)}
                          placeholder={selectedDm.can_reply === false ? 'Reponse bloquee par la politique Messenger' : 'Message...'}
                          disabled={selectedDm.can_reply === false}
                          style={{ minHeight: 84, resize: 'vertical', borderRadius: 16, marginBottom: 0, flex: 1, fontSize: 14, lineHeight: 1.5 }}
                        />
                        <Btn size="sm" disabled={!replyText.trim() || sendingReply || selectedDm.can_reply === false} onClick={handleSendReply}>
                          {sendingReply ? 'Envoi...' : 'Envoyer'}
                        </Btn>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'none' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '8px 0 16px', borderBottom: '1px solid var(--border)', marginBottom: 14 }}>
                      <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'linear-gradient(135deg, #22c55e, #3b82f6)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 18 }}>{selectedDm.avatar}</div>
                      <div style={{ fontWeight: 700, textAlign: 'center' }}>{selectedDm.author}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 6 }}><PlatformIcon platform={selectedDm.platform} size={14} /> {selectedDm.platform}</div>
                    </div>

                    {selectedDm.suggestedReply && (
                      <div style={{ marginBottom: 14 }}>
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Suggestion IA</div>
                        <div style={{ background: 'rgba(108,99,255,0.08)', border: '1px solid rgba(108,99,255,0.18)', borderRadius: 10, padding: '10px 12px', fontSize: 12, lineHeight: 1.5, marginBottom: 8 }}>{selectedDm.suggestedReply}</div>
                        <Btn size="sm" variant="ghost" onClick={() => setReplyText(selectedDm.suggestedReply || '')}>Utiliser</Btn>
                      </div>
                    )}

                    {selectedDm.analyzed && (
                      <div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>Analyse IA</div>
                        <div style={{ display: 'grid', gap: 8 }}>
                          {[
                            { label: 'Sentiment', value: selectedDm.sentiment, type: selectedDm.sentiment },
                            { label: 'Question', value: selectedDm.isQuestion ? 'Oui' : 'Non' },
                            { label: 'Lead', value: selectedDm.isLead ? 'Oui' : 'Non' },
                            { label: 'Toxique', value: selectedDm.isToxic ? 'Oui' : 'Non' },
                          ].map(item => (
                            <div key={item.label} style={{ padding: '8px 10px', background: 'var(--bg-2)', borderRadius: 8 }}>
                              <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 3 }}>{item.label}</div>
                              {item.type ? <LabelBadge label={String(item.value)} type={item.type} /> : <div style={{ fontSize: 13, fontWeight: 600 }}>{item.value}</div>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'none' }}>
                  <Card>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 2 }}>{selectedDm.author}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 6 }}>via <PlatformIcon platform={selectedDm.platform} size={14} /> {selectedDm.platform}</div>
                        {selectedDm.sourceType && selectedDm.sourceType !== 'dm' && (
                          <div style={{ marginTop: 6 }}>
                            <LabelBadge label={`Source: ${selectedDm.sourceType}`} />
                          </div>
                        )}
                      </div>
                      {!selectedDm.analyzed && (
                        <Btn size="sm" onClick={() => handleAnalyzeDm(selectedDm)} disabled={analyzingId === selectedDm.id}>
                          {analyzingId === selectedDm.id ? <Spinner /> : 'Analyser'}
                        </Btn>
                      )}
                    </div>
                    <div style={{ background: 'var(--bg-2)', borderRadius: 10, padding: '12px 14px', fontSize: 14, lineHeight: 1.6 }}>{selectedDm.text}</div>
                  </Card>

                  {selectedDm.analyzed && (
                    <Card>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Analyse IA</div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        {[
                          { label: 'Sentiment', value: selectedDm.sentiment, type: selectedDm.sentiment },
                          { label: 'Emotion', value: selectedDm.emotion || '—' },
                          { label: 'Score', value: selectedDm.sentimentScore ? `${(Math.abs(selectedDm.sentimentScore) * 100).toFixed(0)}%` : '—' },
                          { label: 'Lead potentiel', value: selectedDm.isLead ? 'Oui' : 'Non' },
                          { label: 'Question', value: selectedDm.isQuestion ? 'Oui' : 'Non' },
                          { label: 'Toxique', value: selectedDm.isToxic ? 'Oui' : 'Non' },
                        ].map(item => (
                          <div key={item.label} style={{ padding: '8px 10px', background: 'var(--bg-2)', borderRadius: 8 }}>
                            <div style={{ fontSize: 10, color: 'var(--text-3)', marginBottom: 3 }}>{item.label}</div>
                            {item.type ? <LabelBadge label={String(item.value)} type={item.type} /> : <div style={{ fontSize: 13, fontWeight: 600 }}>{item.value}</div>}
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                  {selectedDm.suggestedReply && (
                    <Card>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Reponse suggeree</div>
                      <div style={{ background: 'rgba(108,99,255,0.08)', borderRadius: 8, padding: '10px 12px', fontSize: 13, marginBottom: 10, border: '1px solid rgba(108,99,255,0.15)' }}>{selectedDm.suggestedReply}</div>
                      <Btn size="sm" onClick={() => setReplyText(selectedDm.suggestedReply || '')}>Utiliser cette reponse</Btn>
                    </Card>
                  )}

                  <Card>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>{selectedDm.reply_action_label || 'Repondre'}</div>
                    {selectedDm.can_reply === false && (
                      <div style={{
                        marginBottom: 10,
                        padding: '10px 12px',
                        borderRadius: 8,
                        background: 'rgba(249,115,22,0.10)',
                        border: '1px solid rgba(249,115,22,0.22)',
                        color: 'var(--text-2)',
                        fontSize: 12,
                        lineHeight: 1.5,
                      }}>
                        {selectedDm.reply_disabled_reason || "La reponse directe n'est pas disponible pour cette conversation."}
                      </div>
                    )}
                    <textarea value={replyText} onChange={e => setReplyText(e.target.value)} placeholder="Votre reponse..." style={{ minHeight: 80, resize: 'vertical', marginBottom: 10 }} />
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Btn size="sm" disabled={!replyText.trim() || sendingReply || selectedDm.can_reply === false} onClick={handleSendReply}>{sendingReply ? 'Envoi...' : (selectedDm.reply_action_label || 'Envoyer')}</Btn>
                      <Btn size="sm" variant="ghost" onClick={() => setReplyText('')}>Effacer</Btn>
                    </div>
                  </Card>
                </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {tab === 'posts' && (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', gap: 0, padding: '16px 32px 24px' }}>
          <div style={{ width: 300, flexShrink: 0, overflowY: 'auto', paddingRight: 16 }}>
            {postPlatforms.length > 0 && (
              <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                {postPlatforms.map((platform) => (
                  <div key={platform} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 999, background: 'var(--bg-1)', border: '1px solid var(--border)', fontSize: 12 }}>
                    <PlatformIcon platform={platform} size={14} />
                    <span style={{ color: 'var(--text-2)' }}>{platform}</span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Vos publications reelles</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {loadingPosts ? <Spinner /> : posts.map(post => (
                <div
                  key={`${post.account_id}-${post.id}`}
                  onClick={() => { setSelectedPost(post); setCommentFilter('all') }}
                  style={{ padding: '12px 14px', borderRadius: 10, cursor: 'pointer', background: selectedPost?.id === post.id ? 'rgba(108,99,255,0.1)' : 'var(--bg-1)', border: `1px solid ${selectedPost?.id === post.id ? 'rgba(108,99,255,0.3)' : 'var(--border)'}` }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <PlatformIcon platform={post.platform} size={14} />
                    <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{post.timestamp ? new Date(post.timestamp).toLocaleString('fr-FR') : ''}</span>
                  </div>
                  <div style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', marginBottom: 8, lineHeight: 1.4 }}>{post.text}</div>
                  {!!post.mediaUrl && (
                    <div style={{ marginBottom: 8 }}>
                      {looksLikeVideo(post) ? (
                        <video src={post.mediaUrl} style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 8, background: 'var(--bg-2)' }} muted />
                      ) : (
                        <img src={post.mediaUrl} alt={post.text || 'Media du post'} style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 8, background: 'var(--bg-2)' }} />
                      )}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 10, fontSize: 11, color: 'var(--text-3)' }}>
                    <span>❤ {post.likes}</span>
                    <span>💬 {post.commentsCount}</span>
                  </div>
                  {typeof post.predictedEngagementPercent === 'number' && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                      <LabelBadge label={`ER ${post.predictedEngagementPercent.toFixed(2)}%`} type="positive" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', paddingLeft: 16, borderLeft: '1px solid var(--border)' }}>
            {!selectedPost ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-3)' }}>Selectionnez un post</div>
            ) : (
              <>
                <div style={{ marginBottom: 16, padding: '12px 14px', background: 'var(--bg-1)', borderRadius: 10, border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>Publication <PlatformIcon platform={selectedPost.platform} size={16} /></span>
                    <div style={{ display: 'flex', gap: 10, fontSize: 12, color: 'var(--text-3)' }}>
                      <span>❤ {selectedPost.likes}</span>
                      <span>💬 {comments.length} commentaires</span>
                    </div>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{selectedPost.text}</div>
                  {typeof selectedPost.predictedEngagementPercent === 'number' && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                      {typeof selectedPost.predictedEngagementPercent === 'number' && (
                        <LabelBadge label={`Engagement predit ${selectedPost.predictedEngagementPercent.toFixed(2)}%`} type="positive" />
                      )}
                    </div>
                  )}
                  {!!selectedPost.mediaUrl && (
                    <div style={{ marginTop: 12 }}>
                      {looksLikeVideo(selectedPost) ? (
                        <video
                          src={selectedPost.mediaUrl}
                          controls
                          preload="metadata"
                          style={{ width: '100%', maxHeight: 380, borderRadius: 12, background: 'var(--bg-2)' }}
                        />
                      ) : (
                        <img
                          src={selectedPost.mediaUrl}
                          alt={selectedPost.text || 'Media du post'}
                          style={{ width: '100%', maxHeight: 380, objectFit: 'cover', borderRadius: 12, background: 'var(--bg-2)' }}
                        />
                      )}
                    </div>
                  )}
                  {postReplyConfig && (
                    <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
                        {postReplyConfig.actionLabel}
                      </div>
                      <textarea
                        value={postReplyText}
                        onChange={e => setPostReplyText(e.target.value)}
                        placeholder="Votre reponse a cette publication..."
                        style={{ minHeight: 72, resize: 'vertical', marginBottom: 8 }}
                      />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <Btn size="sm" disabled={!postReplyText.trim() || sendingPostReply} onClick={handleSendPostReply}>
                          {sendingPostReply ? 'Envoi...' : postReplyConfig.actionLabel}
                        </Btn>
                        <Btn size="sm" variant="ghost" onClick={() => setPostReplyText('')}>Effacer</Btn>
                      </div>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: 4, marginBottom: 12, flexWrap: 'wrap' }}>
                  {[
                    { key: 'all', label: 'Tous' },
                    { key: 'positive', label: 'Positifs' },
                    { key: 'negative', label: 'Negatifs' },
                    { key: 'neutral', label: 'Neutres' },
                    { key: 'spam', label: 'Spam' },
                    { key: 'toxic', label: 'Toxiques' },
                  ].map(f => (
                    <button key={f.key} onClick={() => setCommentFilter(f.key)} style={{ padding: '3px 8px', borderRadius: 6, fontSize: 10, fontWeight: 500, cursor: 'pointer', background: commentFilter === f.key ? 'rgba(108,99,255,0.15)' : 'transparent', border: `1px solid ${commentFilter === f.key ? 'rgba(108,99,255,0.3)' : 'var(--border)'}`, color: commentFilter === f.key ? 'var(--accent-2)' : 'var(--text-3)' }}>{f.label}</button>
                  ))}
                  <Btn size="sm" variant="ghost" onClick={() => loadComments(selectedPost)}>Tout afficher</Btn>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {loadingComments ? <Spinner /> : (() => {
                    const topLevel = filteredComments.filter(c => !c.isReply);
                    const repliesByParent = filteredComments.filter(c => c.isReply).reduce((acc, reply) => {
                      if (reply.parentCommentId) {
                        acc[reply.parentCommentId] = acc[reply.parentCommentId] || [];
                        acc[reply.parentCommentId].push(reply);
                      }
                      return acc;
                    }, {} as Record<string, PostComment[]>);

                    const renderCommentCard = (comment: PostComment, isReply: boolean = false) => (
                      <div key={comment.id} style={{ padding: '10px 14px', borderRadius: 10, background: 'var(--bg-1)', border: '1px solid var(--border)', marginLeft: isReply ? 32 : 0, position: 'relative' }}>
                        {isReply && <div style={{ position: 'absolute', left: -20, top: 18, color: 'var(--text-3)', fontSize: 16 }}>↳</div>}
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontWeight: 600, fontSize: 13 }}>{comment.author}</span>
                            {comment.label && <LabelBadge label={comment.label} type={comment.label} />}
                            {comment.autoReplied && <LabelBadge label="Auto-repondu" type="positive" />}
                            {comment.requiresHuman && <LabelBadge label="Humain requis" type="human" />}
                          </div>
                          <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{comment.timestamp ? new Date(comment.timestamp).toLocaleString('fr-FR') : ''}</span>
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.4 }}>{comment.text}</div>
                        <div style={{ display: 'flex', gap: 10, marginTop: 8, fontSize: 11, color: 'var(--text-3)' }}>
                          <span>{comment.platform}</span>
                          <span>Score {(Math.abs(comment.sentimentScore || 0) * 100).toFixed(0)}%</span>
                        </div>
                        {comment.canReply && (
                          <div style={{ marginTop: 10 }}>
                            {replyingCommentId === comment.id ? (
                              <>
                                <textarea
                                  value={commentReplyText}
                                  onChange={e => setCommentReplyText(e.target.value)}
                                  placeholder="Votre reponse a ce commentaire..."
                                  style={{ minHeight: 72, resize: 'vertical', marginBottom: 8 }}
                                />
                                <div style={{ display: 'flex', gap: 8 }}>
                                  <Btn size="sm" disabled={!commentReplyText.trim() || sendingCommentReply} onClick={() => handleSendCommentReply(comment)}>
                                    {sendingCommentReply ? 'Envoi...' : (comment.replyActionLabel || 'Repondre')}
                                  </Btn>
                                  <Btn size="sm" variant="ghost" onClick={() => { setReplyingCommentId(null); setCommentReplyText('') }}>
                                    Annuler
                                  </Btn>
                                </div>
                              </>
                            ) : (
                              <Btn size="sm" variant="ghost" onClick={() => { setReplyingCommentId(comment.id); setCommentReplyText('') }}>
                                {comment.replyActionLabel || 'Repondre'}
                              </Btn>
                            )}
                          </div>
                        )}
                      </div>
                    );

                    return topLevel.flatMap(comment => [
                      renderCommentCard(comment, false),
                      ...(repliesByParent[comment.id] || []).map(reply => renderCommentCard(reply, true))
                    ]);
                  })()}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
