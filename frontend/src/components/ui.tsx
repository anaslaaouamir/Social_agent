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
