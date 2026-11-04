'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Keeps form state in localStorage so a reload, a stray back-navigation, or a
 * tab switch never costs typed prose. Nothing here touches the server.
 *
 * Keyed per record ("product:new" vs "product:<id>") so a half-finished new
 * bottle and an in-progress edit cannot overwrite each other.
 */
/**
 * Stored shape. The timestamp lets the form say how old a restored draft is,
 * which matters because a restored draft silently replaces the saved record
 * in the form. Drafts written before this shape existed are bare values.
 */
type StoredDraft<T> = { v: 1; value: Partial<T>; savedAt: string }

function isStoredDraft<T>(parsed: unknown): parsed is StoredDraft<T> {
  return typeof parsed === 'object' && parsed !== null && (parsed as { v?: unknown }).v === 1
}

export function useDraft<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial)
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  const [restored, setRestored] = useState(false)
  // When the restored draft was last written. Null for legacy drafts.
  const [restoredAt, setRestoredAt] = useState<Date | null>(null)
  const loaded = useRef(false)
  const skip = useRef<T | null>(null)

  // Load once per key. Switching keys re-runs this with the new record.
  useEffect(() => {
    loaded.current = false
    let next = initial
    let wasRestored = false
    let draftTime: Date | null = null
    try {
      const raw = window.localStorage.getItem(key)
      if (raw) {
        const parsed: unknown = JSON.parse(raw)
        if (isStoredDraft<T>(parsed)) {
          next = { ...initial, ...parsed.value }
          const t = new Date(parsed.savedAt)
          draftTime = Number.isNaN(t.getTime()) ? null : t
        } else {
          next = { ...initial, ...(parsed as Partial<T>) }
        }
        wasRestored = true
      }
    } catch {
      // corrupt or unavailable storage -- fall back to the clean initial value
    }
    /* eslint-disable react-hooks/set-state-in-effect --
       The rule prefers deriving state during render, but localStorage cannot
       be read during render here: /admin is prerendered on the server, where
       no storage exists, so a render-time read would produce markup the client
       disagrees with and break hydration. Restoring after mount is the correct
       trade and costs exactly one extra render. */
    setValue(next)
    setRestored(wasRestored)
    setRestoredAt(draftTime)
    setSavedAt(null)
    /* eslint-enable react-hooks/set-state-in-effect */
    // Defer enabling writes so this load does not immediately re-persist.
    const id = window.setTimeout(() => {
      loaded.current = true
    }, 0)
    return () => window.clearTimeout(id)
    // `initial` is intentionally excluded: callers rebuild it inline, and
    // depending on it would reset the form on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => {
    if (!loaded.current) return
    // Set by reset(). Compared by reference, so any edit after a reset --
    // which always produces a new object -- persists as normal.
    if (value === skip.current) return
    const id = window.setTimeout(() => {
      try {
        const now = new Date()
        const stored: StoredDraft<T> = { v: 1, value, savedAt: now.toISOString() }
        window.localStorage.setItem(key, JSON.stringify(stored))
        setSavedAt(now)
      } catch {
        // quota or private-mode failure -- drafting is best-effort
      }
    }, 400)
    return () => window.clearTimeout(id)
  }, [key, value])

  const clear = useCallback(() => {
    try {
      window.localStorage.removeItem(key)
    } catch {
      // nothing to do
    }
    setSavedAt(null)
    setRestored(false)
    setRestoredAt(null)
  }, [key])

  /**
   * Replace the form value and drop the stored draft, without the change
   * being persisted as a new draft. A plain setValue after clear() would be
   * written straight back by the effect above -- an untouched form would
   * then come back as a "restored draft".
   */
  const reset = useCallback(
    (next: T) => {
      skip.current = next
      clear()
      setValue(next)
    },
    [clear]
  )

  /** Update one field without clobbering the rest. */
  const setField = useCallback(
    <K extends keyof T>(field: K) =>
      (v: T[K]) =>
        setValue(prev => ({ ...prev, [field]: v })),
    []
  )

  return { value, setValue, setField, savedAt, restored, restoredAt, clear, reset }
}
