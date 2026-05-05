import React from 'react'

// ── Page Header ──────────────────────────────────────────────────────────────
export function PageHeader({ title, subtitle, actions }: {
  title: string; subtitle?: string; actions?: React.ReactNode
}) {
  return (
    <div style={{
      padding: '28px 32px 0',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      marginBottom: 24,
    }}>
      <div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700, lineHeight: 1.2 }}>
          {title}
        </h1>
        {subtitle && <p style={{ color: 'var(--text-3)', fontSize: 13, marginTop: 4 }}>{subtitle}</p>}
      </div>
      {actions && <div style={{ display: 'flex', gap: 8 }}>{actions}</div>}
    </div>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────
export function Card({ children, style = {}, onClick }: { children: React.ReactNode; style?: React.CSSProperties; onClick?: () => void }) {
  return (
    <div className="glass" style={{ borderRadius: 12, padding: 20, ...style }} onClick={onClick}>
      {children}
    </div>
  )
}

// ── Button ───────────────────────────────────────────────────────────────────
interface BtnProps {
  children: React.ReactNode
  onClick?: React.MouseEventHandler<HTMLButtonElement>
  variant?: 'primary' | 'ghost' | 'danger' | 'outline'
  size?: 'sm' | 'md'
  disabled?: boolean
  type?: 'button' | 'submit'
  style?: React.CSSProperties
}
export function Btn({ children, onClick, variant = 'primary', size = 'md', disabled, type = 'button', style = {} }: BtnProps) {
  const base: React.CSSProperties = {
    border: 'none', borderRadius: 8, cursor: disabled ? 'not-allowed' : 'pointer',
    fontWeight: 600, fontFamily: 'var(--font-body)', opacity: disabled ? 0.5 : 1,
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: size === 'sm' ? '6px 12px' : '9px 16px',
    fontSize: size === 'sm' ? 12 : 13,
    whiteSpace: 'nowrap',
  }
  const variants: Record<string, React.CSSProperties> = {
    primary: { background: 'linear-gradient(135deg, var(--accent), #8b5cf6)', color: '#fff' },
    ghost: { background: 'transparent', color: 'var(--text-2)', border: '1px solid var(--border)' },
    danger: { background: 'rgba(244,63,94,0.15)', color: 'var(--red)', border: '1px solid rgba(244,63,94,0.25)' },
    outline: { background: 'transparent', color: 'var(--accent-2)', border: '1px solid rgba(108,99,255,0.3)' },
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} style={{ ...base, ...variants[variant], ...style }}>
      {children}
    </button>
  )
}

// ── Badge ────────────────────────────────────────────────────────────────────
export function Badge({ label, type = 'default' }: { label: string; type?: string }) {
  const cls = type === 'default' ? '' : `badge-${type}`
  return (
    <span className={cls} style={{
      padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 600,
      display: 'inline-flex', alignItems: 'center',
      ...(type === 'default' ? {
        background: 'var(--bg-3)', color: 'var(--text-2)',
        border: '1px solid var(--border)',
      } : {}),
    }}>
      {label}
    </span>
  )
}

// ── Stat card ────────────────────────────────────────────────────────────────
export function StatCard({ label, value, sub, color = 'var(--accent-2)' }: {
  label: string; value: string | number; sub?: string; color?: string
}) {
  return (
    <Card>
      <div style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-display)', color, lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>}
    </Card>
  )
}

// ── Spinner ──────────────────────────────────────────────────────────────────
export function Spinner() {
  return (
    <div style={{
      width: 20, height: 20, borderRadius: '50%',
      border: '2px solid var(--border)',
      borderTopColor: 'var(--accent)',
      animation: 'spin 0.7s linear infinite',
      display: 'inline-block',
    }} />
  )
}

// ── Loading full ─────────────────────────────────────────────────────────────
export function Loading() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
      <Spinner />
    </div>
  )
}

// ── Empty state ──────────────────────────────────────────────────────────────
export function Empty({ icon, title, desc, action }: {
  icon: string; title: string; desc?: string; action?: React.ReactNode
}) {
  return (
    <div style={{ textAlign: 'center', padding: '60px 20px' }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>{icon}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600, marginBottom: 6 }}>{title}</div>
      {desc && <p style={{ color: 'var(--text-3)', fontSize: 13, maxWidth: 320, margin: '0 auto 16px' }}>{desc}</p>}
      {action}
    </div>
  )
}

// ── Modal ────────────────────────────────────────────────────────────────────
export function Modal({ open, onClose, title, children, width = 500 }: {
  open: boolean; onClose: () => void; title: string; children: React.ReactNode; width?: number
}) {
  if (!open) return null
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="animate-fade glass"
        style={{ width: '100%', maxWidth: width, borderRadius: 16, padding: 28, maxHeight: '90vh', overflowY: 'auto' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700 }}>{title}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-3)', fontSize: 20, cursor: 'pointer' }}>×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── Platform icon ─────────────────────────────────────────────────────────────
export function PlatformIcon({ platform, size = 20 }: { platform: string; size?: number }) {
  const key = String(platform || '').toLowerCase()
  const common = { width: size, height: size, display: 'inline-block', verticalAlign: 'middle', flexShrink: 0 } as const

  if (key === 'facebook') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#1877F2" />
      <path fill="#fff" d="M15.1 8.1h-1.9c-.3 0-.7.4-.7.9v1.3h2.6l-.4 2.7h-2.2v6.5H9.7V13H7.5v-2.7h2.2V8.8c0-2.3 1.4-3.8 3.6-3.8.9 0 1.7.1 1.8.1v3z" />
    </svg>
  )
  if (key === 'instagram') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <defs>
        <linearGradient id={`igGradient-${size}`} x1="4" x2="20" y1="20" y2="4" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FEDA75" /><stop offset=".25" stopColor="#FA7E1E" /><stop offset=".5" stopColor="#D62976" /><stop offset=".75" stopColor="#962FBF" /><stop offset="1" stopColor="#4F5BD5" />
        </linearGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill={`url(#igGradient-${size})`} />
      <rect x="6.2" y="6.2" width="11.6" height="11.6" rx="3.4" fill="none" stroke="#fff" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="3" fill="none" stroke="#fff" strokeWidth="1.8" />
      <circle cx="16" cy="8" r="1.1" fill="#fff" />
    </svg>
  )
  if (key === 'linkedin') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <rect width="24" height="24" rx="3" fill="#0A66C2" />
      <path fill="#fff" d="M6.7 9.8h3v8.9h-3V9.8zm1.5-4.4a1.7 1.7 0 1 1 0 3.4 1.7 1.7 0 0 1 0-3.4zm3.2 4.4h2.9V11c.4-.7 1.2-1.5 2.7-1.5 2.9 0 3.4 1.9 3.4 4.4v4.8h-3v-4.3c0-1 0-2.3-1.4-2.3s-1.6 1.1-1.6 2.2v4.4h-3V9.8z" />
    </svg>
  )
  if (key === 'youtube') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <rect x="2" y="5" width="20" height="14" rx="4" fill="#FF0000" />
      <path d="M10 8.7v6.6l5.7-3.3L10 8.7z" fill="#fff" />
    </svg>
  )
  if (key === 'twitter' || key === 'x') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <rect width="24" height="24" rx="4" fill="#000" />
      <path fill="#fff" d="M14.3 10.7 20 4h-1.4l-4.9 5.8L9.7 4H5l6 8.7L5 20h1.4l5.2-6.2 4.2 6.2h4.7l-6.2-9.3zm-1.8 2.1-.6-.9-4.8-6.8H9l3.9 5.6.6.9 5 7.2h-1.9l-4.1-6z" />
    </svg>
  )
  if (key === 'tiktok') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <rect width="24" height="24" rx="5" fill="#000" />
      <path d="M15.2 5.2c.5 1.8 1.7 3 3.6 3.2v2.8a6 6 0 0 1-3.6-1.2v4.6a4.7 4.7 0 1 1-4.7-4.7c.3 0 .6 0 .9.1v3a2 2 0 1 0 1.3 1.9V5.2h2.5z" fill="#fff" />
      <path d="M13.1 5.2v9.6a2 2 0 0 1-3.3 1.5 2 2 0 0 0 3.9-.7V5.2h-.6z" fill="#25F4EE" />
      <path d="M15.2 5.2c.5 1.8 1.7 3 3.6 3.2v.7c-1.5-.2-2.7-.9-3.6-2v-2z" fill="#FE2C55" />
    </svg>
  )
  if (key === 'threads') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <rect width="24" height="24" rx="5" fill="#000" />
      <path fill="none" stroke="#fff" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M16.5 10.5c-.3-2.8-1.9-4.4-4.5-4.4-3.1 0-5.1 2.3-5.1 5.9s2.1 5.9 5.4 5.9c2.8 0 4.8-1.5 4.8-3.6 0-1.7-1.3-2.8-3.7-2.8h-1.1c-1.6 0-2.5.8-2.5 1.9 0 1.2 1 2 2.4 2 1.8 0 3-1.1 3-3.1 0-2.4-1.5-3.8-3.7-3.8" />
    </svg>
  )
  if (key === 'pinterest') return (
    <svg viewBox="0 0 24 24" style={common} aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#BD081C" />
      <path fill="#fff" d="M12.2 4.8c-4 0-6.1 2.6-6.1 5.4 0 1.3.7 3 1.8 3.5.2.1.3 0 .4-.2l.4-1.5c0-.1 0-.3-.1-.4-.4-.5-.7-1.1-.7-2 0-2 1.5-3.8 4-3.8 2.2 0 3.7 1.5 3.7 3.6 0 2.4-1.2 4.1-2.8 4.1-.9 0-1.6-.8-1.4-1.7.3-1.1.8-2.3.8-3.1 0-.7-.4-1.3-1.2-1.3-1 0-1.7 1-1.7 2.3 0 .8.3 1.4.3 1.4l-1.2 5c-.3 1.4 0 3.1 0 3.3 0 .1.2.1.2 0 .1-.1 1.8-2.2 2.3-3.5l.7-2.5c.4.7 1.4 1.3 2.5 1.3 3.3 0 5.6-3 5.6-6.6 0-3.1-2.6-5.9-6.5-5.9z" />
    </svg>
  )

  return <span title={platform} style={{ ...common, borderRadius: '50%', background: 'var(--bg-3)', color: 'var(--text-2)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: size * 0.55, fontWeight: 700 }}>{String(platform || '?').slice(0, 1).toUpperCase()}</span>
  const map: Record<string, { emoji: string; color: string }> = {
    instagram: { emoji: '📸', color: '#e1306c' },
    facebook:  { emoji: '📘', color: '#1877f2' },
    twitter:   { emoji: '🐦', color: '#1da1f2' },
    linkedin:  { emoji: '💼', color: '#0a66c2' },
    tiktok:    { emoji: '🎵', color: '#ff0050' },
    threads:   { emoji: '@', color: '#000000' },
    youtube:   { emoji: 'YT', color: '#ff0000' },
    pinterest: { emoji: 'P', color: '#bd081c' },
  }
  const p = map[platform] || { emoji: '🌐', color: 'var(--text-2)' }
  return <span title={platform} style={{ fontSize: size * 0.8 }}>{p.emoji}</span>
}

export function AccountScopeTabs({
  accounts,
  selectedAccount,
  onChange,
  allowAll = false,
  allLabel = 'Tout afficher',
}: {
  accounts: any[]
  selectedAccount: any | null
  onChange: (account: any | null) => void
  allowAll?: boolean
  allLabel?: string
}) {
  if (!accounts.length) return null

  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
      {allowAll && (
        <button
          onClick={() => onChange(null)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
            borderRadius: 8, border: '1px solid', fontSize: 13, fontWeight: 500, cursor: 'pointer',
            borderColor: selectedAccount == null ? 'rgba(108,99,255,0.4)' : 'var(--border)',
            background: selectedAccount == null ? 'rgba(108,99,255,0.1)' : 'transparent',
            color: selectedAccount == null ? 'var(--accent-2)' : 'var(--text-2)',
          }}
        >
          <span>∞</span>
          {allLabel}
        </button>
      )}
      {accounts.map((a: any) => (
        <button
          key={a.id}
          onClick={() => onChange(a)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
            borderRadius: 8, border: '1px solid', fontSize: 13, fontWeight: 500, cursor: 'pointer',
            borderColor: selectedAccount?.id === a.id ? 'rgba(108,99,255,0.4)' : 'var(--border)',
            background: selectedAccount?.id === a.id ? 'rgba(108,99,255,0.1)' : 'transparent',
            color: selectedAccount?.id === a.id ? 'var(--accent-2)' : 'var(--text-2)',
          }}
        >
          <PlatformIcon platform={a.platform} size={16} />
          {a.account_name}
        </button>
      ))}
    </div>
  )
}

// ── Select ────────────────────────────────────────────────────────────────────
export function Select({ value, onChange, options, placeholder }: {
  value: string; onChange: (v: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
}) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}>
      {placeholder && <option value="">{placeholder}</option>}
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}
