'use client'

import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import type { Product, Similarity, SimilarityType } from '@/lib/admin-types'
import { ApiError, createSimilarity, deleteSimilarity } from '@/lib/admin-api'
import { Banner, Note, PageHead, Panel, PanelRow, SaveBar } from './chrome'
import { Field, Fieldset, TextArea } from './form-primitives'

const RELATIONS: { value: SimilarityType; label: string }[] = [
  { value: 'step_up', label: 'a step up from' },
  { value: 'alternative', label: 'an alternative to' },
]

const SELECT =
  'min-w-[150px] rounded-md border border-input bg-background px-2.5 py-2 text-sm ' +
  'cursor-pointer focus:border-primary focus:outline-none focus:ring-[3px] focus:ring-primary/20'

export function RelationshipForm({
  products,
  similarities,
  onSaved,
}: {
  products: Product[]
  similarities: Similarity[]
  onSaved: () => void
}) {
  // Deliberately not drafted to localStorage: three dropdowns and a note is
  // not enough typing to be worth restoring, unlike the product form.
  const [subject, setSubject] = useState('')
  const [relation, setRelation] = useState<SimilarityType>('step_up')
  const [object, setObject] = useState('')
  const [notes, setNotes] = useState<string | null>(null)

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  const byId = new Map(products.map(p => [p.id, p.canonical_name]))
  const name = (id: string) => byId.get(id) ?? '(deleted)'

  async function save() {
    setBusy(true)
    setError(null)
    setOk(null)
    try {
      // The sentence reads "A is a step up from B", but the stored convention
      // is that similarity_type describes what B is relative to A. So the
      // sentence's subject is product_b_id, and its object is product_a_id.
      await createSimilarity({
        product_a_id: object,
        product_b_id: subject,
        similarity_type: relation,
        notes,
      })
      setOk(`Recorded: ${name(subject)} is ${RELATIONS.find(r => r.value === relation)!.label} ${name(object)}.`)
      setSubject('')
      setObject('')
      setNotes(null)
      onSaved()
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove(s: Similarity) {
    try {
      await deleteSimilarity(s.product_a_id, s.product_b_id, s.similarity_type)
      onSaved()
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e))
    }
  }

  const complete = subject && object && subject !== object

  return (
    <>
      <PageHead
        title="New relationship"
        subtitle="Market-role knowledge the embeddings can't find on their own"
      />

      <Note>
        <b className="font-semibold text-foreground">Read it as a sentence.</b> Direction is easy to
        get backwards in a two-dropdown form, and a reversed row silently produces backwards
        recommendations. Only <b className="font-semibold text-foreground">step up</b> and{' '}
        <b className="font-semibold text-foreground">alternative</b> are stored —{' '}
        <b className="font-semibold text-foreground">step down</b> is the same row read the other
        way.
      </Note>

      {error && <Banner tone="error">{error}</Banner>}
      {ok && <Banner tone="ok">{ok}</Banner>}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_268px]">
        <div>
          <Fieldset legend="Relationship">
            <Field label="" span={12}>
              <div className="flex flex-wrap items-center gap-2.5 rounded-md border border-input bg-background p-3.5 text-[15px]">
                <select
                  className={SELECT}
                  value={subject}
                  onChange={e => setSubject(e.target.value)}
                >
                  <option value="">— pick a bottle —</option>
                  {products.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.canonical_name}
                    </option>
                  ))}
                </select>
                <span className="text-muted-foreground">is</span>
                <select
                  className={SELECT}
                  value={relation}
                  onChange={e => setRelation(e.target.value as SimilarityType)}
                >
                  {RELATIONS.map(r => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <select className={SELECT} value={object} onChange={e => setObject(e.target.value)}>
                  <option value="">— pick a bottle —</option>
                  {products.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.canonical_name}
                    </option>
                  ))}
                </select>
              </div>
              {subject && object && subject === object && (
                <span className="font-mono text-[11.5px] text-destructive">
                  a bottle cannot relate to itself
                </span>
              )}
            </Field>

            <Field label="Why" column="notes">
              <TextArea
                value={notes}
                onChange={setNotes}
                rows={3}
                placeholder="Common next step for someone moving past entry-level. Similar profile family, noticeably more depth for about ten dollars more."
              />
            </Field>
          </Fieldset>
        </div>

        <aside className="flex flex-col gap-3.5 lg:sticky lg:top-[60px]">
          <Panel title={`Existing · ${similarities.length}`}>
            <div className="max-h-[420px] overflow-y-auto">
              {similarities.length === 0 && (
                <p className="px-3.5 py-3 text-[12.5px] text-muted-foreground/70">
                  {products.length < 2
                    ? 'Needs at least two bottles.'
                    : 'None yet.'}
                </p>
              )}
              {similarities.map(s => (
                <PanelRow
                  key={`${s.product_a_id}-${s.product_b_id}-${s.similarity_type}`}
                  name={name(s.product_b_id)}
                  meta={
                    <>
                      {s.similarity_type.replace('_', ' ')} from · {name(s.product_a_id)}
                    </>
                  }
                  action={
                    <button
                      type="button"
                      onClick={() => remove(s)}
                      aria-label={`Delete relationship: ${name(s.product_b_id)} ${s.similarity_type.replace('_', ' ')} from ${name(s.product_a_id)}`}
                      title="Delete relationship"
                      className="rounded-md p-1.5 text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  }
                />
              ))}
            </div>
          </Panel>
        </aside>
      </div>

      <SaveBar
        savedAt={null}
        busy={busy}
        disabled={!complete}
        saveLabel="Save relationship"
        onSave={save}
        onDiscard={() => {
          setSubject('')
          setObject('')
          setNotes(null)
          setOk(null)
          setError(null)
        }}
      />
    </>
  )
}
