'use client'

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { SCARCITY_RUBRIC } from '@/lib/admin-types'

/* ---------------------------------------------------------------------------
 * Layout
 * ------------------------------------------------------------------------ */

export function Fieldset({
  legend,
  children,
}: {
  legend: string
  children: ReactNode
}) {
  return (
    <fieldset className="mb-3.5 rounded-lg border border-border bg-card px-[18px] pt-4 pb-5">
      <legend className="-ml-[7px] px-[7px] font-mono text-[10.5px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/70">
        {legend}
      </legend>
      <div className="grid grid-cols-12 gap-x-4 gap-y-3.5">{children}</div>
    </fieldset>
  )
}

const SPANS = {
  3: 'col-span-12 sm:col-span-3',
  4: 'col-span-12 sm:col-span-4',
  6: 'col-span-12 sm:col-span-6',
  12: 'col-span-12',
} as const

/**
 * One labelled control. `column` is the database column name, shown small and
 * right-aligned so the form doubles as a map back to the schema while curating.
 */
export function Field({
  label,
  column,
  required,
  hint,
  meta,
  span = 12,
  children,
}: {
  label: string
  column?: string
  required?: boolean
  hint?: ReactNode
  meta?: ReactNode
  span?: keyof typeof SPANS
  children: ReactNode
}) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-[5px]', SPANS[span])}>
      <label className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
        {label}
        {required && <span className="text-[15px] leading-none text-primary">*</span>}
        {column && (
          <span className="ml-auto font-mono text-[11px] text-muted-foreground/60">
            {column}
          </span>
        )}
        {meta}
      </label>
      {children}
      {hint && (
        <span className="text-[11.5px] leading-relaxed text-muted-foreground/70">
          {hint}
        </span>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Controls
 * ------------------------------------------------------------------------ */

const CONTROL =
  'w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm text-foreground ' +
  'placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none ' +
  'focus:ring-[3px] focus:ring-primary/20'

export function TextInput({
  value,
  onChange,
  ...rest
}: {
  value: string | null
  onChange: (v: string | null) => void
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'>) {
  return (
    <input
      type="text"
      className={CONTROL}
      value={value ?? ''}
      onChange={e => onChange(e.target.value === '' ? null : e.target.value)}
      {...rest}
    />
  )
}

/**
 * Empty stays `null`, never 0 -- the schema treats null as "not assessed" and
 * coercing a cleared box to zero would assert a fact the curator did not make.
 */
export function NumberInput({
  value,
  onChange,
  ...rest
}: {
  value: number | string | null
  onChange: (v: number | null) => void
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'>) {
  return (
    <input
      type="number"
      className={CONTROL}
      value={value ?? ''}
      onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))}
      {...rest}
    />
  )
}

export function TextArea({
  value,
  onChange,
  rows = 4,
  className,
  ...rest
}: {
  value: string | null
  onChange: (v: string | null) => void
  rows?: number
} & Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'value' | 'onChange'>) {
  // Grow with the content rather than scrolling inside a page that already
  // scrolls. `rows` stays the minimum height.
  const ref = useRef<HTMLTextAreaElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    // scrollHeight excludes the border; add it back so nothing clips.
    el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`
  }, [value])

  return (
    <textarea
      ref={ref}
      rows={rows}
      className={cn(CONTROL, 'resize-none overflow-hidden leading-relaxed', className)}
      value={value ?? ''}
      onChange={e => onChange(e.target.value === '' ? null : e.target.value)}
      {...rest}
    />
  )
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  placeholder,
  allowEmpty,
}: {
  value: T | null
  onChange: (v: T | null) => void
  options: readonly T[] | { value: T; label: string }[]
  placeholder?: string
  allowEmpty?: boolean
}) {
  const items = options.map(o =>
    typeof o === 'string' ? { value: o, label: o.replace(/_/g, ' ') } : o
  )
  return (
    <select
      className={cn(CONTROL, 'cursor-pointer')}
      value={value ?? ''}
      onChange={e => onChange(e.target.value === '' ? null : (e.target.value as T))}
    >
      {(allowEmpty || value === null) && (
        <option value="">{placeholder ?? '— none —'}</option>
      )}
      {items.map(i => (
        <option key={i.value} value={i.value}>
          {i.label}
        </option>
      ))}
    </select>
  )
}

/** A database-generated value. Dashed border signals "you cannot type here". */
export function Derived({ value }: { value: string | number | null }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-dashed border-input bg-background px-2.5 py-2 font-mono text-sm text-muted-foreground">
      <span className="text-[10px] uppercase tracking-[0.08em] text-muted-foreground/60">
        auto
      </span>
      {value ?? '—'}
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Chips (text[] columns)
 * ------------------------------------------------------------------------ */

export function Chips({
  values,
  onChange,
  placeholder = 'add…',
}: {
  values: string[]
  onChange: (v: string[]) => void
  placeholder?: string
}) {
  const [draft, setDraft] = useState('')

  function commit() {
    const tag = draft.trim().toLowerCase()
    if (tag && !values.includes(tag)) onChange([...values, tag])
    setDraft('')
  }

  return (
    <div className="flex min-h-[38px] flex-wrap items-center gap-1.5 rounded-md border border-input bg-background px-2 py-[7px] focus-within:border-primary focus-within:ring-[3px] focus-within:ring-primary/20">
      {values.map(tag => (
        <span
          key={tag}
          className="inline-flex items-center gap-1.5 rounded border border-border bg-muted px-1.5 py-[3px] font-mono text-xs"
        >
          {tag}
          <button
            type="button"
            aria-label={`Remove ${tag}`}
            className="leading-none text-muted-foreground/60 hover:text-destructive"
            onClick={() => onChange(values.filter(t => t !== tag))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="min-w-[90px] flex-1 bg-transparent px-0.5 py-[3px] text-sm focus:outline-none"
        placeholder={placeholder}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            commit()
          } else if (e.key === 'Backspace' && draft === '' && values.length) {
            onChange(values.slice(0, -1))
          }
        }}
        onBlur={commit}
      />
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Scarcity rubric
 * ------------------------------------------------------------------------ */

/**
 * The rubric IS the input. A bare 0-5 number box drifts across bottles because
 * the anchors are not in front of you while deciding.
 */
export function ScarcityRubric({
  value,
  onChange,
}: {
  value: number | null
  onChange: (v: number | null) => void
}) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-background">
      {SCARCITY_RUBRIC.map(({ tier, label, example }) => (
        <button
          key={tier}
          type="button"
          aria-pressed={value === tier}
          onClick={() => onChange(value === tier ? null : tier)}
          className={cn(
            'grid w-full grid-cols-[26px_1fr] gap-2.5 border-t border-border px-2.5 py-[5px] text-left first:border-t-0 hover:bg-white/[0.04]',
            value === tier && 'bg-primary/15'
          )}
        >
          <span className="font-mono text-[11.5px] font-medium text-primary">{tier}</span>
          <span className="text-[11.5px] text-muted-foreground">
            {label} <span className="text-muted-foreground/60">— {example}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Word count
 * ------------------------------------------------------------------------ */

/** Editorial target from docs/schema.md -- advisory, never enforced. */
export function WordCount({
  text,
  min,
  max,
}: {
  text: string | null
  min: number
  max: number
}) {
  const words = text?.trim() ? text.trim().split(/\s+/).length : 0
  const over = words > max
  return (
    <span
      className={cn(
        'ml-auto font-mono text-[11px]',
        over ? 'text-primary' : 'text-muted-foreground/60'
      )}
    >
      {words} / {min}–{max} words
    </span>
  )
}
