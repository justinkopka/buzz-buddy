'use client'

import { useMemo, useState } from 'react'
import {
  AVAILABILITIES,
  CATEGORIES,
  DATA_QUALITIES,
  EMPTY_PRODUCT,
  VERTICALS,
  toProductWrite,
  type EmbeddingSync,
  type Producer,
  type Product,
  type ProductWrite,
  type Release,
} from '@/lib/admin-types'
import { ApiError, createProduct, updateProduct } from '@/lib/admin-api'
import {
  Banner,
  DraftNotice,
  PageHead,
  Panel,
  PanelRow,
  QualityPill,
  SaveBar,
} from './chrome'
import {
  Chips,
  Derived,
  Field,
  Fieldset,
  NumberInput,
  ScarcityRubric,
  Select,
  TextArea,
  TextInput,
  WordCount,
} from './form-primitives'
import { useDraft } from './use-draft'

// What "Add release" inserts: the guideline keys with empty values. Never
// example data -- an untouched example would save as a real release.
const RELEASE_TEMPLATE = {
  laser_code: '',
  batch: '',
  year: null,
  proof: null,
  msrp_usd: null,
  notes: '',
}

function releasesToText(releases: Release[] | null): string {
  return releases ? JSON.stringify(releases, null, 2) : ''
}

/** Text -> releases, exactly as typed. Empty text is null. */
function parseReleases(text: string): { releases: Release[] | null; error: string | null } {
  if (!text.trim()) return { releases: null, error: null }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { releases: null, error: 'Not valid JSON' }
  }
  if (
    !Array.isArray(parsed) ||
    !parsed.every(r => r !== null && typeof r === 'object' && !Array.isArray(r))
  ) {
    return { releases: null, error: 'Must be a list of objects: [ { … }, { … } ]' }
  }
  return { releases: parsed, error: null }
}

/**
 * Applied only to what is sent to the backend. Unfilled keys ("" or null) are
 * dropped -- an absent key already means "unknown" -- and a release left
 * entirely empty is dropped with them. The form and the local draft keep the
 * text exactly as typed.
 */
function cleanReleases(releases: Release[] | null): Release[] | null {
  if (!releases) return null
  const cleaned = releases
    .map(r => Object.fromEntries(Object.entries(r).filter(([, v]) => v !== '' && v !== null)))
    .filter(r => Object.keys(r).length > 0)
  return cleaned.length ? cleaned : null
}

export function ProductForm({
  products,
  producers,
  editing,
  onSelect,
  onSaved,
}: {
  products: Product[]
  producers: Producer[]
  editing: Product | null
  onSelect: (p: Product | null) => void
  onSaved: () => void
}) {
  const draftKey = `admin:product:${editing?.id ?? 'new'}`
  const initial: ProductWrite = editing ? toProductWrite(editing) : EMPTY_PRODUCT
  const { value, setField, savedAt, restored, restoredAt, clear, reset } = useDraft(
    draftKey,
    initial
  )

  // The textarea holds raw text; value.releases holds its last valid parse.
  // Resync the text when value.releases changes from outside -- switching
  // bottles, restoring a draft, resetting after save. Edits made here record
  // the reference they set, so they never trigger the resync.
  const [releasesText, setReleasesText] = useState(() => releasesToText(value.releases))
  const [releasesSynced, setReleasesSynced] = useState(value.releases)
  if (value.releases !== releasesSynced) {
    setReleasesSynced(value.releases)
    setReleasesText(releasesToText(value.releases))
  }
  const releasesError = parseReleases(releasesText).error

  function editReleases(text: string) {
    setReleasesText(text)
    const { releases, error } = parseReleases(text)
    if (error) return
    setReleasesSynced(releases)
    setField('releases')(releases)
  }

  function addRelease() {
    const current = parseReleases(releasesText).releases ?? []
    editReleases(JSON.stringify([...current, RELEASE_TEMPLATE], null, 2))
  }

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ name: string; sync: EmbeddingSync } | null>(null)
  const [search, setSearch] = useState('')

  const producerOptions = producers.map(p => ({ value: p.id, label: p.name }))

  // Mirrors the generated column: proof = abv_pct * 2. Shown, never submitted.
  const proof = useMemo(() => {
    const abv = value.abv_pct === null ? null : Number(value.abv_pct)
    return abv === null || Number.isNaN(abv) ? null : String(abv * 2)
  }, [value.abv_pct])

  const sourced =
    !!value.distiller_id && !!value.bottler_id && value.distiller_id !== value.bottler_id

  const visible = products.filter(p =>
    search ? p.canonical_name.toLowerCase().includes(search.toLowerCase()) : true
  )

  async function save(thenReset: boolean) {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const payload = { ...value, releases: cleanReleases(value.releases) }
      const saved = editing
        ? await updateProduct(editing.id, payload)
        : await createProduct(payload)
      onSaved()
      setResult({ name: saved.product.canonical_name, sync: saved.embeddings })
      if (thenReset) {
        reset(EMPTY_PRODUCT)
        onSelect(null)
      } else {
        clear()
        onSelect(saved.product)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e))
    } finally {
      setBusy(false)
    }
  }

  function discard() {
    reset(initial)
    setResult(null)
    setError(null)
  }

  return (
    <>
      <PageHead
        title={editing ? `Edit ${editing.canonical_name}` : 'New bottle'}
        subtitle={
          savedAt
            ? 'Draft kept in this browser · never sent to the server until you save'
            : 'Everything here is hand-curated — the embeddings are generated on save'
        }
      />

      {restored && <DraftNotice at={restoredAt} editing={!!editing} onDiscard={discard} />}
      {error && <Banner tone="error">{error}</Banner>}
      {result && (
        <Banner tone={result.sync.ok ? 'ok' : 'error'}>
          {result.sync.ok ? (
            <>
              Saved <b>{result.name}</b>. Embeddings: {result.sync.written} written,{' '}
              {result.sync.unchanged} unchanged
              {result.sync.removed > 0 && `, ${result.sync.removed} removed`}.
            </>
          ) : (
            <>
              Saved <b>{result.name}</b> — but embedding failed ({result.sync.error}). The bottle
              is stored; regenerate from the list when the service is back.
            </>
          )}
        </Banner>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_268px]">
        <div>
          <Fieldset legend="Identity">
            <Field
              label="Canonical name"
              column="canonical_name"
              required
              span={6}
              hint="How you'd say it out loud. Must be unique — store picks need distinct names."
            >
              <TextInput
                value={value.canonical_name}
                onChange={v => setField('canonical_name')(v ?? '')}
                placeholder="Eagle Rare 10 Year"
              />
            </Field>
            <Field label="Brand" column="brand" span={3}>
              <TextInput value={value.brand} onChange={setField('brand')} placeholder="Eagle Rare" />
            </Field>
            <Field label="Expression" column="expression" span={3}>
              <TextInput
                value={value.expression}
                onChange={setField('expression')}
                placeholder="often empty"
              />
            </Field>
            <Field label="Full label text" column="full_name">
              <TextInput value={value.full_name} onChange={setField('full_name')} />
            </Field>
          </Fieldset>

          <Fieldset legend="Classification">
            <Field label="Vertical" column="vertical" required span={4}>
              <Select
                value={value.vertical}
                onChange={v => setField('vertical')(v ?? 'whiskey')}
                options={VERTICALS}
              />
            </Field>
            <Field label="Category" column="category" required span={4}>
              <Select
                value={value.category}
                onChange={v => setField('category')(v ?? 'bourbon')}
                options={CATEGORIES}
              />
            </Field>
            <Field
              label="Subcategory"
              column="subcategory"
              span={4}
              hint="Primary class only — one answer. Attributes go in style tags."
            >
              <TextInput
                value={value.subcategory}
                onChange={setField('subcategory')}
                placeholder="straight bourbon"
              />
            </Field>
          </Fieldset>

          <Fieldset legend="Producer & origin">
            <Field label="Distilled by" column="distiller_id" span={6}>
              <Select
                value={value.distiller_id}
                onChange={setField('distiller_id')}
                options={producerOptions}
                placeholder="— not researched —"
                allowEmpty
              />
            </Field>
            <Field
              label="Bottled & sold by"
              column="bottler_id"
              span={6}
              hint={
                <>
                  Same as distiller = not sourced. Different ={' '}
                  <b className="text-muted-foreground">sourced</b>, worth calling out. Not in the
                  list? Add it on the Producers tab — this draft will still be here.
                </>
              }
            >
              <Select
                value={value.bottler_id}
                onChange={setField('bottler_id')}
                options={producerOptions}
                placeholder="— not researched —"
                allowEmpty
              />
            </Field>
            {sourced && (
              <div className="col-span-12 -mt-1 font-mono text-[11.5px] text-primary">
                sourced — distiller and bottler differ
              </div>
            )}
            <Field label="Region" column="region" span={6}>
              <TextInput value={value.region} onChange={setField('region')} placeholder="Kentucky" />
            </Field>
            <Field label="Country" column="country" span={6}>
              <TextInput value={value.country} onChange={setField('country')} placeholder="USA" />
            </Field>
          </Fieldset>

          <Fieldset legend="Spec">
            <Field label="ABV %" column="abv_pct" span={3}>
              <NumberInput value={value.abv_pct} onChange={setField('abv_pct')} step="0.1" />
            </Field>
            <Field label="Proof" column="proof" span={3} hint="Computed by the database.">
              <Derived value={proof} />
            </Field>
            <Field label="Age (years)" column="age_years" span={3}>
              <NumberInput value={value.age_years} onChange={setField('age_years')} step="0.5" />
            </Field>
            <Field label="Age statement" column="age_statement" span={3}>
              <TextInput
                value={value.age_statement}
                onChange={setField('age_statement')}
                placeholder="10 Year"
              />
            </Field>
          </Fieldset>

          <Fieldset legend="Tags">
            <Field label="Flavor profile" column="flavor_profile" span={6}>
              <Chips values={value.flavor_profile} onChange={setField('flavor_profile')} />
            </Field>
            <Field
              label="Style tags"
              column="style_tags"
              span={6}
              hint={
                <>
                  Attributes the bottle <b className="text-muted-foreground">has</b>. No{' '}
                  <b className="text-muted-foreground">high-proof</b> tag — filter on the proof
                  column instead.
                </>
              }
            >
              <Chips values={value.style_tags} onChange={setField('style_tags')} />
            </Field>
          </Fieldset>

          <Fieldset legend="Pricing">
            <Field label="MSRP" column="msrp_usd" span={4}>
              <NumberInput value={value.msrp_usd} onChange={setField('msrp_usd')} />
            </Field>
            <Field label="Typical shelf — low" column="typical_retail_low_usd" span={4}>
              <NumberInput
                value={value.typical_retail_low_usd}
                onChange={setField('typical_retail_low_usd')}
              />
            </Field>
            <Field label="Typical shelf — high" column="typical_retail_high_usd" span={4}>
              <NumberInput
                value={value.typical_retail_high_usd}
                onChange={setField('typical_retail_high_usd')}
              />
            </Field>
            <Field label="Secondary — low" column="secondary_market_low_usd" span={4}>
              <NumberInput
                value={value.secondary_market_low_usd}
                onChange={setField('secondary_market_low_usd')}
                placeholder="allocated only"
              />
            </Field>
            <Field label="Secondary — high" column="secondary_market_high_usd" span={4}>
              <NumberInput
                value={value.secondary_market_high_usd}
                onChange={setField('secondary_market_high_usd')}
                placeholder="allocated only"
              />
            </Field>
            <Field label="Pricing notes" column="pricing_notes" span={4}>
              <TextInput value={value.pricing_notes} onChange={setField('pricing_notes')} />
            </Field>
          </Fieldset>

          <Fieldset legend="Releases">
            <Field
              label="Releases"
              column="releases"
              hint="One object per batch. Keys left empty are not saved."
            >
              <TextArea
                value={releasesText}
                onChange={t => editReleases(t ?? '')}
                rows={8}
                className="font-mono text-[12.5px]"
                placeholder="No releases recorded"
              />
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={addRelease}
                  disabled={!!releasesError}
                  className="rounded-md border border-border px-2.5 py-1 text-[12.5px] text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  + Add release
                </button>
                {releasesError && (
                  <span className="font-mono text-[11.5px] text-destructive">
                    {releasesError} — fix before saving
                  </span>
                )}
              </div>
            </Field>
          </Fieldset>

          <Fieldset legend="Availability">
            <Field
              label="Availability"
              column="availability"
              span={4}
              hint={
                <>
                  <b className="text-muted-foreground">Why</b> it&apos;s hard to get.
                </>
              }
            >
              <Select
                value={value.availability}
                onChange={setField('availability')}
                options={AVAILABILITIES}
                placeholder="— not assessed —"
                allowEmpty
              />
            </Field>
            <Field
              label="Scarcity tier"
              column="scarcity_tier"
              span={6}
              hint={
                <>
                  <b className="text-muted-foreground">How</b> hard, independent of why. Click again
                  to clear if you haven&apos;t assessed it.
                </>
              }
            >
              <ScarcityRubric value={value.scarcity_tier} onChange={setField('scarcity_tier')} />
            </Field>
            {value.availability === 'widely_available' &&
              value.scarcity_tier !== null &&
              value.scarcity_tier !== 0 && (
                <div className="col-span-12 font-mono text-[11.5px] text-destructive">
                  widely available requires tier 0 — the database will reject this
                </div>
              )}
          </Fieldset>

          <Fieldset legend="Prose">
            <Field
              label="Description"
              meta={<WordCount text={value.description} min={100} max={300} />}
            >
              <TextArea value={value.description} onChange={setField('description')} rows={4} />
            </Field>
            <Field
              label="Tasting notes"
              meta={<WordCount text={value.tasting_notes} min={50} max={150} />}
            >
              <TextArea value={value.tasting_notes} onChange={setField('tasting_notes')} rows={3} />
            </Field>
            <Field
              label="Community sentiment"
              meta={<WordCount text={value.community_sentiment} min={100} max={200} />}
              hint={
                <>
                  The highest-value field here. Reputation tier, price-to-quality, common
                  comparisons, batch variance, criticisms.{' '}
                  <b className="text-muted-foreground">Your own words — never paste source text.</b>
                </>
              }
            >
              <TextArea
                value={value.community_sentiment}
                onChange={setField('community_sentiment')}
                rows={6}
              />
            </Field>
          </Fieldset>

          <Fieldset legend="Ratings & metadata">
            <Field label="Whiskey Advocate" column="whiskey_advocate_score" span={3}>
              <NumberInput
                value={value.whiskey_advocate_score}
                onChange={setField('whiskey_advocate_score')}
              />
            </Field>
            <Field label="Distiller score" column="distiller_score" span={3}>
              <NumberInput
                value={value.distiller_score}
                onChange={setField('distiller_score')}
                step="0.1"
                placeholder="top-tier only"
              />
            </Field>
            <Field
              label="Data quality"
              column="data_quality"
              span={3}
              hint="Starts low; promote when confident."
            >
              <Select
                value={value.data_quality}
                onChange={v => setField('data_quality')(v ?? 'low')}
                options={DATA_QUALITIES}
              />
            </Field>
            <Field label="Internal notes" column="notes" span={3}>
              <TextInput
                value={value.notes}
                onChange={setField('notes')}
                placeholder="never shown to users"
              />
            </Field>
          </Fieldset>
        </div>

        <aside className="flex flex-col gap-3.5 lg:sticky lg:top-[60px]">
          <Panel title={`Find a bottle · ${products.length}`}>
            <div className="px-3.5 py-3">
              <input
                className="w-full rounded-md border border-input bg-background px-2.5 py-2 text-sm placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-[3px] focus:ring-primary/20"
                placeholder="Search by name…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
            <div className="max-h-[360px] overflow-y-auto">
              {visible.length === 0 && (
                <p className="px-3.5 py-3 text-[12.5px] text-muted-foreground/70">
                  {products.length === 0 ? 'No bottles yet.' : 'No match.'}
                </p>
              )}
              {visible.map(p => (
                <PanelRow
                  key={p.id}
                  name={p.canonical_name}
                  active={editing?.id === p.id}
                  meta={
                    <>
                      <QualityPill quality={p.data_quality} />
                      {new Date(p.updated_at).toLocaleDateString()}
                    </>
                  }
                  onClick={() => onSelect(editing?.id === p.id ? null : p)}
                />
              ))}
            </div>
          </Panel>

          <Panel title="Counts">
            <div className="px-3.5 py-3 font-mono text-[12.5px] leading-[1.9] text-muted-foreground">
              <div className="flex justify-between">
                <span>products</span>
                <span className="text-foreground">{products.length}</span>
              </div>
              <div className="flex justify-between">
                <span>producers</span>
                <span className="text-foreground">{producers.length}</span>
              </div>
            </div>
          </Panel>
        </aside>
      </div>

      <SaveBar
        savedAt={savedAt}
        busy={busy}
        disabled={!!releasesError}
        saveLabel="Save bottle"
        onSave={() => save(false)}
        onSaveAndNew={() => save(true)}
        onDiscard={discard}
      />
    </>
  )
}
