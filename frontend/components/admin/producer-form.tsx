'use client'

import { useState } from 'react'
import {
  EMPTY_PRODUCER,
  toProducerWrite,
  type Producer,
  type ProducerWrite,
} from '@/lib/admin-types'
import { ApiError, createProducer, updateProducer } from '@/lib/admin-api'
import { Banner, DraftNotice, PageHead, Panel, PanelRow, SaveBar } from './chrome'
import { Field, Fieldset, NumberInput, Select, TextArea, TextInput } from './form-primitives'
import { useDraft } from './use-draft'

export function ProducerForm({
  producers,
  editing,
  onSelect,
  onSaved,
}: {
  producers: Producer[]
  editing: Producer | null
  onSelect: (p: Producer | null) => void
  onSaved: () => void
}) {
  const draftKey = `admin:producer:${editing?.id ?? 'new'}`
  const initial: ProducerWrite = editing ? toProducerWrite(editing) : EMPTY_PRODUCER
  const { value, setField, savedAt, restored, restoredAt, clear, reset } = useDraft(
    draftKey,
    initial
  )

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  // A producer cannot be its own parent, and the list is small enough that
  // filtering the option out is clearer than validating after the fact.
  const parentOptions = producers
    .filter(p => p.id !== editing?.id)
    .map(p => ({ value: p.id, label: p.name }))

  async function save(thenReset: boolean) {
    setBusy(true)
    setError(null)
    setOk(null)
    try {
      const saved = editing
        ? await updateProducer(editing.id, value)
        : await createProducer(value)
      onSaved()
      if (thenReset) {
        reset(EMPTY_PRODUCER)
        onSelect(null)
        setOk(`Saved ${saved.name}. Form cleared for the next one.`)
      } else {
        clear()
        onSelect(saved)
        setOk(`Saved ${saved.name}.`)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e))
    } finally {
      setBusy(false)
    }
  }

  function discard() {
    reset(initial)
    setOk(null)
    setError(null)
  }

  return (
    <>
      <PageHead
        title={editing ? `Edit ${editing.name}` : 'New producer'}
        subtitle="Distilleries, breweries, wineries — one table, since the fields are identical"
      />

      {restored && <DraftNotice at={restoredAt} editing={!!editing} onDiscard={discard} />}
      {error && <Banner tone="error">{error}</Banner>}
      {ok && <Banner tone="ok">{ok}</Banner>}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_268px]">
        <div>
          <Fieldset legend="Producer">
            <Field label="Name" column="name" required span={6}>
              <TextInput
                value={value.name}
                onChange={v => setField('name')(v ?? '')}
                placeholder="Buffalo Trace Distillery"
              />
            </Field>

            <Field
              label="Parent company"
              column="parent_producer_id"
              span={6}
              hint="Corporate ownership, e.g. Sazerac owns Buffalo Trace. Leave empty if independent or not yet researched."
            >
              <Select
                value={value.parent_producer_id}
                onChange={setField('parent_producer_id')}
                options={parentOptions}
                placeholder="— none / independent —"
                allowEmpty
              />
            </Field>

            <Field label="Region" column="region" span={4}>
              <TextInput value={value.region} onChange={setField('region')} placeholder="Kentucky" />
            </Field>

            <Field label="Country" column="country" span={4}>
              <TextInput value={value.country} onChange={setField('country')} placeholder="USA" />
            </Field>

            <Field label="Founded" column="founded_year" span={4}>
              <NumberInput
                value={value.founded_year}
                onChange={setField('founded_year')}
                placeholder="1870"
              />
            </Field>

            <Field
              label="Signature style"
              column="signature_style"
              hint={
                <>
                  One line. This rides along with <b className="text-muted-foreground">every</b>{' '}
                  search result, so keep it short.
                </>
              }
            >
              <TextInput
                value={value.signature_style}
                onChange={setField('signature_style')}
                placeholder="Known for wheated bourbons"
              />
            </Field>

            <Field
              label="Description"
              column="description"
              hint="Full prose. Only fetched when someone asks about the producer directly."
            >
              <TextArea
                value={value.description}
                onChange={setField('description')}
                placeholder="History, house philosophy, anything worth knowing when the distillery itself is the question."
              />
            </Field>
          </Fieldset>
        </div>

        <aside className="flex flex-col gap-3.5 lg:sticky lg:top-[60px]">
          <Panel title={`Existing · ${producers.length}`}>
            <div className="max-h-[420px] overflow-y-auto">
              {producers.length === 0 && (
                <p className="px-3.5 py-3 text-[12.5px] text-muted-foreground/70">
                  None yet. Producers come first — products reference them.
                </p>
              )}
              {producers.map(p => (
                <PanelRow
                  key={p.id}
                  name={p.name}
                  active={editing?.id === p.id}
                  meta={
                    <>
                      {producers.find(x => x.id === p.parent_producer_id)?.name ?? 'independent'}
                      {p.region && ` · ${p.region}`}
                    </>
                  }
                  onClick={() => onSelect(editing?.id === p.id ? null : p)}
                />
              ))}
            </div>
          </Panel>
        </aside>
      </div>

      <SaveBar
        savedAt={savedAt}
        busy={busy}
        saveLabel={editing ? 'Save producer' : 'Save producer'}
        onSave={() => save(false)}
        onSaveAndNew={() => save(true)}
        onDiscard={discard}
      />
    </>
  )
}
