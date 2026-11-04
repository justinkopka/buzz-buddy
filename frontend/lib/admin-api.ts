import { createClient } from '@/lib/supabase/client'
import type {
  Producer,
  ProducerWrite,
  Product,
  ProductSaved,
  ProductWrite,
  Similarity,
  SimilarityType,
  SimilarityWrite,
} from '@/lib/admin-types'

/** Thrown for any non-2xx. `detail` carries the backend's message verbatim. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const supabase = createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session) throw new ApiError(401, 'Not authenticated')

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
      ...init?.headers,
    },
  })

  if (!res.ok) {
    // FastAPI returns {detail: string} for HTTPException and
    // {detail: [{loc, msg, ...}]} for validation failures.
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((e: { loc?: (string | number)[]; msg?: string }) => {
            const field = e.loc?.filter(p => p !== 'body').join('.')
            return field ? `${field}: ${e.msg}` : e.msg
          })
          .join('; ')
      }
    } catch {
      // non-JSON body; keep the generic message
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

// --- producers -------------------------------------------------------------

export const listProducers = (limit = 200) =>
  request<Producer[]>(`/admin/producers?limit=${limit}`)

export const getProducer = (id: string) => request<Producer>(`/admin/producers/${id}`)

export const createProducer = (data: ProducerWrite) =>
  request<Producer>('/admin/producers', { method: 'POST', body: JSON.stringify(data) })

export const updateProducer = (id: string, data: ProducerWrite) =>
  request<Producer>(`/admin/producers/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })

export const deleteProducer = (id: string) =>
  request<void>(`/admin/producers/${id}`, { method: 'DELETE' })

// --- products --------------------------------------------------------------

export function listProducts(opts: { search?: string; limit?: number } = {}) {
  const params = new URLSearchParams({ limit: String(opts.limit ?? 200) })
  if (opts.search) params.set('search', opts.search)
  return request<Product[]>(`/admin/products?${params}`)
}

export const getProduct = (id: string) => request<Product>(`/admin/products/${id}`)

export const createProduct = (data: ProductWrite) =>
  request<ProductSaved>('/admin/products', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const updateProduct = (id: string, data: ProductWrite) =>
  request<ProductSaved>(`/admin/products/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })

export const deleteProduct = (id: string) =>
  request<void>(`/admin/products/${id}`, { method: 'DELETE' })

// --- similarities ----------------------------------------------------------

export const listSimilarities = () => request<Similarity[]>('/admin/similarities?limit=200')

export const createSimilarity = (data: SimilarityWrite) =>
  request<Similarity>('/admin/similarities', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const deleteSimilarity = (
  productAId: string,
  productBId: string,
  similarityType: SimilarityType
) =>
  request<void>(
    `/admin/similarities?product_a_id=${productAId}&product_b_id=${productBId}` +
      `&similarity_type=${similarityType}`,
    { method: 'DELETE' }
  )
