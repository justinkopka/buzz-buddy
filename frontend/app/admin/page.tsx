'use client'

import { useCallback, useEffect, useState } from 'react'
import { ChatHeader } from '@/components/chat/chat-header'
import { SectionBar, type AdminTab } from '@/components/admin/chrome'
import { ProducerForm } from '@/components/admin/producer-form'
import { ProductForm } from '@/components/admin/product-form'
import { RelationshipForm } from '@/components/admin/relationship-form'
import { listProducers, listProducts, listSimilarities } from '@/lib/admin-api'
import { createClient } from '@/lib/supabase/client'
import type { Producer, Product, Similarity } from '@/lib/admin-types'

/**
 * Tabs rather than routes, deliberately: the product form tells you to add a
 * missing producer on the Producers tab and come back, which only works if
 * the in-progress draft survives the switch. Routes would unmount it.
 *
 * Access is enforced in proxy.ts, which redirects non-admins before this
 * renders. The backend re-checks on every call regardless.
 */
export default function AdminPage() {
  const [tab, setTab] = useState<AdminTab>('products')
  const [email, setEmail] = useState<string | null>(null)

  const [products, setProducts] = useState<Product[]>([])
  const [producers, setProducers] = useState<Producer[]>([])
  const [similarities, setSimilarities] = useState<Similarity[]>([])

  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [editingProducer, setEditingProducer] = useState<Producer | null>(null)

  const [loadError, setLoadError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [prods, makers, sims] = await Promise.all([
        listProducts(),
        listProducers(),
        listSimilarities(),
      ])
      setProducts(prods)
      setProducers(makers)
      setSimilarities(sims)
      setLoadError(null)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const {
        data: { session },
      } = await createClient().auth.getSession()
      if (cancelled) return
      setEmail(session?.user.email ?? null)
      await refresh()
    })()
    return () => {
      cancelled = true
    }
  }, [refresh])

  return (
    <div className="min-h-svh">
      <ChatHeader />
      <SectionBar tab={tab} onTab={setTab} email={email} />

      <div className="mx-auto max-w-[1160px] px-5 pt-6 pb-32">
        {loadError && (
          <div className="mb-[18px] rounded-md border border-destructive/40 bg-destructive/10 px-3.5 py-3 text-[12.5px] text-destructive">
            Could not load knowledge base: {loadError}
          </div>
        )}

        {tab === 'products' && (
          <ProductForm
            products={products}
            producers={producers}
            editing={editingProduct}
            onSelect={setEditingProduct}
            onSaved={refresh}
          />
        )}

        {tab === 'producers' && (
          <ProducerForm
            producers={producers}
            editing={editingProducer}
            onSelect={setEditingProducer}
            onSaved={refresh}
          />
        )}

        {tab === 'relationships' && (
          <RelationshipForm
            products={products}
            similarities={similarities}
            onSaved={refresh}
          />
        )}
      </div>
    </div>
  )
}
