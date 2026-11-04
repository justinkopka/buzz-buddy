'use client'

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type AdminTab = 'products' | 'producers' | 'relationships'

const TABS: { id: AdminTab; label: string }[] = [
  { id: 'products', label: 'Products' },
  { id: 'producers', label: 'Producers' },
  { id: 'relationships', label: 'Relationships' },
]

/** Row two of the chrome. Row one is the app-wide ChatHeader. */
export function SectionBar({
  tab,
  onTab,
  email,
}: {
  tab: AdminTab
  onTab: (t: AdminTab) => void
  email: string | null
}) {
  return (
    <div className="sticky top-0 z-20 flex h-11 items-center gap-3.5 border-b border-border bg-background px-4">
      <span className="rounded bg-primary/15 px-[7px] py-1 font-mono text-[10px] font-medium uppercase tracking-[0.09em] text-primary">
        Admin
      </span>
      <div className="flex gap-0.5" role="tablist">
        {TABS.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => onTab(t.id)}
            className={cn(
              'rounded-md px-3 py-1.5 text-[13.5px]',
              tab === t.id
                ? 'bg-muted text-foreground'
                : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {email && (
        <div className="ml-auto truncate font-mono text-[11.5px] text-muted-foreground/60">
          {email}
        </div>
      )}
    </div>
  )
}

export function PageHead({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-5 flex flex-wrap items-baseline gap-3">
      <h1 className="text-[21px] font-semibold tracking-[-0.02em] text-balance">{title}</h1>
      <p className="text-[13px] text-muted-foreground">{subtitle}</p>
    </div>
  )
}

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <h2 className="border-b border-border px-3.5 py-3 font-mono text-[10.5px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/70">
        {title}
      </h2>
      {children}
    </div>
  )
}

/**
 * `onClick` is optional: a row with nothing to open (a relationship has no
 * edit form) renders as plain text, so a click can't do something surprising.
 * `action` sits beside the row content rather than inside it, since a button
 * cannot be nested in another button.
 */
export function PanelRow({
  name,
  meta,
  active,
  onClick,
  action,
}: {
  name: string
  meta: ReactNode
  active?: boolean
  onClick?: () => void
  action?: ReactNode
}) {
  const content = (
    <>
      <span className="block truncate text-[13px]">{name}</span>
      <span className="mt-[3px] flex items-center gap-[7px] font-mono text-[11px] text-muted-foreground/60">
        {meta}
      </span>
    </>
  )
  return (
    <div
      className={cn(
        'flex items-center border-t border-border first:border-t-0',
        active && 'bg-primary/10'
      )}
    >
      {onClick ? (
        <button
          onClick={onClick}
          className="block min-w-0 flex-1 px-3.5 py-2.5 text-left hover:bg-white/[0.04]"
        >
          {content}
        </button>
      ) : (
        <div className="min-w-0 flex-1 px-3.5 py-2.5">{content}</div>
      )}
      {action && <div className="shrink-0 pr-2">{action}</div>}
    </div>
  )
}

export function QualityPill({ quality }: { quality: string }) {
  const tone =
    quality === 'high'
      ? 'text-[#5fb98a] bg-[#5fb98a]/15'
      : quality === 'medium'
        ? 'text-primary bg-primary/15'
        : 'text-destructive bg-destructive/15'
  return (
    <span
      className={cn(
        'rounded px-1.5 py-[3px] font-mono text-[10px] font-medium uppercase tracking-[0.05em]',
        tone
      )}
    >
      {quality}
    </span>
  )
}

/**
 * Fixed footer. Deliberately always visible: the product form is long enough
 * that a save button at the bottom would sit below several screens of prose.
 */
export function SaveBar({
  savedAt,
  status,
  onDiscard,
  onSaveAndNew,
  onSave,
  saveLabel,
  busy,
  disabled,
  children,
}: {
  savedAt: Date | null
  status?: ReactNode
  onDiscard: () => void
  onSaveAndNew?: () => void
  onSave: () => void
  saveLabel: string
  busy?: boolean
  // Can't save yet (invalid or incomplete input), as distinct from `busy`,
  // which means a save is in flight and relabels the button.
  disabled?: boolean
  children?: ReactNode
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1160px] flex-wrap items-center gap-3.5 px-5 py-3">
        {status ?? (
          <span className="flex items-center gap-[7px] text-[12.5px] text-muted-foreground/70">
            {savedAt && (
              <>
                <span className="size-1.5 rounded-full bg-[#5fb98a]" />
                Draft saved locally ·{' '}
                {savedAt.toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </>
            )}
          </span>
        )}
        {children}
        <span className="ml-auto" />
        <button
          type="button"
          onClick={onDiscard}
          className="rounded-md px-4 py-2 text-sm hover:bg-muted"
        >
          Discard draft
        </button>
        {onSaveAndNew && (
          <button
            type="button"
            onClick={onSaveAndNew}
            disabled={busy || disabled}
            className="rounded-md border border-input bg-muted px-4 py-2 text-sm hover:bg-muted/70 disabled:opacity-50"
          >
            Save &amp; add another
          </button>
        )}
        <button
          type="button"
          onClick={onSave}
          disabled={busy || disabled}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {busy ? 'Saving…' : saveLabel}
        </button>
      </div>
    </div>
  )
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <div className="mb-[18px] rounded-r-md border border-l-2 border-border border-l-primary bg-card px-3.5 py-3 text-[12.5px] text-muted-foreground">
      {children}
    </div>
  )
}

/**
 * Shown while the form holds a draft restored from this browser rather than
 * what the server returned. Without it a stale draft is indistinguishable
 * from the saved record, and saving it would quietly revert newer changes.
 */
export function DraftNotice({
  at,
  editing,
  onDiscard,
}: {
  at: Date | null
  editing: boolean
  onDiscard: () => void
}) {
  const when = at
    ? ` from ${at.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}`
    : ''
  return (
    <div className="mb-[18px] flex flex-wrap items-center gap-3 rounded-md border border-primary/40 bg-primary/10 px-3.5 py-3 text-[12.5px] text-primary">
      <span>
        {editing
          ? `Showing an unsaved draft${when}, not the saved record.`
          : `Restored an unsaved draft${when}.`}
      </span>
      <button
        type="button"
        onClick={onDiscard}
        className="ml-auto rounded-md border border-primary/40 px-2.5 py-1 hover:bg-primary/15"
      >
        Discard draft
      </button>
    </div>
  )
}

export function Banner({ tone, children }: { tone: 'ok' | 'error'; children: ReactNode }) {
  return (
    <div
      className={cn(
        'mb-[18px] rounded-md border px-3.5 py-3 text-[12.5px]',
        tone === 'ok'
          ? 'border-[#5fb98a]/40 bg-[#5fb98a]/10 text-[#5fb98a]'
          : 'border-destructive/40 bg-destructive/10 text-destructive'
      )}
    >
      {children}
    </div>
  )
}
