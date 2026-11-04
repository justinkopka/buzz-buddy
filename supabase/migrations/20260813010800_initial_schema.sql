-- =====================================================================
-- Initial schema: BuzzBuddy knowledge base
--
-- Four tables:
--   products              the knowledge the agent reads and reasons over
--   product_embeddings    the search index over it; never read by the LLM
--   producers             distilleries / breweries / wineries
--   product_similarities  curated market-role knowledge (non-vector path)
--
-- Structural reasoning lives in ADR-0011 (single-table multi-vertical
-- schema), ADR-0005 (embeddings), ADR-0006 (curation), ADR-0001 (platform).
-- A human-readable overview with an ER diagram is in docs/schema.md.
-- Field-level rationale is commented inline below, deliberately kept here
-- rather than in a separate doc so it cannot drift from the schema.
--
-- User-facing tables (user_collections, user_preferences) are deferred.
-- =====================================================================

SET check_function_bodies = false;

-- pgvector: the vector type, distance operators, and vector index methods.
-- pg_trgm: trigram similarity, powering the fuzzy-match step of
-- resolve_bottle() (exact -> fuzzy -> semantic -> LLM disambiguation).
-- IF NOT EXISTS so this migration is idempotent against environments where
-- either extension was already enabled by hand.
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- Postgres has no built-in "touch this column on UPDATE" behavior. A column
-- with DEFAULT now() is set on insert and then never changes again, which is
-- silently wrong rather than merely absent. One shared function, attached as
-- a trigger to each table that carries updated_at.
CREATE FUNCTION public.set_updated_at()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  AS $function$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;


-- =====================================================================
-- producers
--
-- Distilleries, breweries, and wineries share one table: the fields are
-- identical across verticals, and some companies genuinely span them
-- (Constellation Brands owns wine, beer, and spirits), so a per-vertical
-- producer table would model them incorrectly. There is deliberately no
-- producer_type column -- it is derivable from the products referencing
-- the row, and forcing a single value would be wrong for those companies.
-- =====================================================================
CREATE TABLE public.producers (
  id                 uuid                     DEFAULT gen_random_uuid() NOT NULL,
  name               text                     NOT NULL,

  -- Self-reference for corporate ownership: Sazerac -> Buffalo Trace.
  -- Enables "show me everything Sazerac owns". NULL means either
  -- independent or not yet researched -- a low-stakes ambiguity, unlike
  -- products.bottler_id below.
  parent_producer_id uuid,

  region             text,
  country            text,
  founded_year       integer,

  -- Full prose: history and background. Too long to attach to every search
  -- result; fetched on demand when the producer itself is the subject.
  description        text,

  -- One line, house style ("known for wheated bourbons"). Short enough to
  -- inject alongside every product in a retrieval result. House style is a
  -- producer-level property that explains why someone who likes one of a
  -- distillery's expressions tends to like the others.
  signature_style    text,

  created_at         timestamp with time zone DEFAULT now() NOT NULL,
  updated_at         timestamp with time zone DEFAULT now() NOT NULL
);

-- RLS enabled with no policies on every table here. These tables are
-- backend-only: the FastAPI service reads and writes them with the Supabase
-- service role key, which bypasses RLS. The admin UI reaches them through
-- JWT-protected backend endpoints, never via the Supabase client directly.
-- No policies therefore means anon and authenticated are denied everything,
-- which is the intended posture.
ALTER TABLE public.producers
  ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.producers
  ADD CONSTRAINT producers_pkey PRIMARY KEY (id);

ALTER TABLE public.producers
  ADD CONSTRAINT producers_parent_producer_id_fkey FOREIGN KEY (parent_producer_id) REFERENCES public.producers(id);

GRANT MAINTAIN, REFERENCES, TRIGGER, TRUNCATE ON public.producers TO service_role;

-- Postgres does not auto-index foreign keys. Supports ownership traversal.
CREATE INDEX producers_parent_idx ON public.producers (parent_producer_id);

CREATE TRIGGER producers_set_updated_at
  BEFORE UPDATE ON public.producers
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();


-- =====================================================================
-- products
--
-- One table for every vertical, discriminated by `vertical`, with
-- vertical-specific columns nullable (proof / age_years / age_statement
-- are whiskey-only; beer's IBU and wine's vintage will join them later).
--
-- Roughly 90% of the columns are shared across verticals, and every table
-- that hangs off a product -- embeddings, similarities, and eventually
-- user_collections -- needs exactly one foreign key target. Per-vertical
-- tables would force each of those into a polymorphic reference (which
-- Postgres cannot enforce with a real FK), triplicated tables, or
-- exclusive-arc nullable columns. See ADR-0011.
-- =====================================================================
CREATE TABLE public.products (
  id                        uuid                     DEFAULT gen_random_uuid() NOT NULL,

  -- --- Identity -----------------------------------------------------
  -- canonical_name is how the bottle is referred to conversationally,
  -- typically brand + expression. UNIQUE because duplicate rows would
  -- actively degrade resolve_bottle()'s fuzzy matching. Store picks and
  -- limited releases therefore need distinct canonical names.
  canonical_name            text                     NOT NULL,
  brand                     text,
  -- The specific variant within a brand's lineup: "10 Year", "Single
  -- Barrel", "Antique 107". Often legitimately NULL -- flagship bottles
  -- frequently carry no variant qualifier. Having it separate is what
  -- makes "what else does this brand make?" answerable without string
  -- surgery on canonical_name.
  expression                text,
  full_name                 text,

  -- --- Producer and origin ------------------------------------------
  -- Two roles, both foreign keys into producers, because a large share of
  -- American whiskey is distilled by one company and sold by another.
  -- Capturing that lets the agent identify when two differently-priced
  -- bottles are substantially the same liquid.
  --   bottler_id = distiller_id  -> not sourced (confirmed)
  --   bottler_id <> distiller_id -> sourced
  --   bottler_id IS NULL         -> not yet researched, or contested
  distiller_id              uuid,
  bottler_id                uuid,
  region                    text,
  country                   text,

  -- --- Classification -----------------------------------------------
  -- Three levels. `vertical` is the tool-boundary filter and is stable --
  -- it never gains values as new whiskey types are added, which is why it
  -- exists separately from `category`.
  --
  -- subcategory answers "what kind of thing is this?" (exactly one value);
  -- style_tags below answers "what attributes does it have?" (many). A
  -- label-based rule would not work, because label designations stack:
  -- Henry McKenna Single Barrel Bottled-in-Bond carries three of them.
  vertical                  text                     NOT NULL,
  category                  text                     NOT NULL,
  subcategory               text,

  -- --- Spec sheet ---------------------------------------------------
  -- abv_pct is canonical because ABV is universal across beer and wine
  -- while proof is meaningless there. proof is generated, never written
  -- directly, so the two can never drift apart. US proof is exactly 2x ABV.
  abv_pct                   numeric,
  age_years                 numeric,
  age_statement             text,

  -- --- Pricing ------------------------------------------------------
  -- Six columns rather than one because the gaps between them carry the
  -- recommendation: Weller 12 at $35 MSRP is an extraordinary find, at
  -- $150 shelf it is still good, at $300 secondary it is a different
  -- decision entirely. Secondary-market columns stay NULL except for
  -- allocated bottles where retail and secondary actually diverge.
  msrp_usd                  numeric,
  typical_retail_low_usd    numeric,
  typical_retail_high_usd   numeric,
  secondary_market_low_usd  numeric,
  secondary_market_high_usd numeric,
  pricing_notes             text,

  -- --- Availability -------------------------------------------------
  -- Two orthogonal axes. `availability` is WHY something is hard to get;
  -- `scarcity_tier` (0-5) is HOW hard. The tier is not derivable from the
  -- category: Blanton's, Weller 12, and Pappy 23 are all 'allocated' but
  -- span "findable if you check a few stores" to "effectively never on a
  -- shelf". The 0-5 anchors are documented in docs/schema.md; keep that
  -- rubric visible while curating or the values drift across bottles.
  --
  -- Left nullable deliberately: NULL means "not yet assessed", whereas
  -- defaulting to 0 would make every unresearched bottle silently claim
  -- to be always in stock.
  availability              text,
  scarcity_tier             integer,

  -- --- Descriptive (drives semantic search) -------------------------
  -- community_sentiment is the highest-value field in the schema and the
  -- actual product moat. Distilleries produce marketing copy; the
  -- community produces honest assessment, and that cannot be scraped
  -- wholesale or fine-tuned into existence. See ADR-0006.
  -- Target lengths (editorial, not enforced): description 100-300 words,
  -- tasting_notes 50-150, community_sentiment 100-200.
  description               text,
  tasting_notes             text,
  community_sentiment       text,

  -- --- Ratings ------------------------------------------------------
  -- distiller_score is populated only during deep manual curation of top
  -- bottles, so it stays NULL for the LLM-assisted long tail rather than
  -- being fabricated. independent_review_scores is an intentionally
  -- schemaless bag so new sources do not require a migration.
  whiskey_advocate_score    integer,
  distiller_score           numeric,
  independent_review_scores jsonb,

  -- --- Metadata -----------------------------------------------------
  -- data_quality lets the agent reason about its own confidence and caveat
  -- accordingly. Defaults to 'low': new records start unproven and get
  -- promoted, rather than silently claiming high confidence.
  data_quality              text                     DEFAULT 'low'::text NOT NULL,
  -- Internal curation notes. Never surface this in user-facing output.
  notes                     text,
  created_at                timestamp with time zone DEFAULT now() NOT NULL,
  updated_at                timestamp with time zone DEFAULT now() NOT NULL,

  -- --- Tags ---------------------------------------------------------
  -- Open vocabularies, deliberately unconstrained. NOT NULL DEFAULT '{}'
  -- so "nothing tagged yet" has exactly one representation.
  --
  -- style_tags earns its place because grain character (wheated, high-rye)
  -- is not derivable from anything else: mash bill percentage columns were
  -- deliberately excluded, since exact recipes are trade secrets and
  -- community figures are guesses. It is not on the label either --
  -- "wheated" is enthusiast vocabulary for a real, decision-relevant
  -- property. There is intentionally no 'high-proof' tag: that duplicates
  -- the proof column, and `WHERE proof >= 100` is more precise than a
  -- fuzzy bucket.
  flavor_profile            text[]                   DEFAULT '{}'::text[] NOT NULL,
  style_tags                text[]                   DEFAULT '{}'::text[] NOT NULL,

  -- --- Generated ----------------------------------------------------
  proof                     numeric                  GENERATED ALWAYS AS ((abv_pct * (2)::numeric)) STORED,

  -- Keyword half of hybrid retrieval, auto-maintained on every write.
  -- The explicit 'english' regconfig is required, not stylistic: the
  -- single-argument form of to_tsvector() is only STABLE, and generated
  -- columns demand an IMMUTABLE expression.
  --
  -- Note this is Postgres full-text search, not literally BM25 -- ts_rank
  -- uses a different weighting scheme. Close enough to fuse with vector
  -- distance via Reciprocal Rank Fusion, but worth not mislabeling.
  search_vector             tsvector                 GENERATED ALWAYS AS (
    to_tsvector('english'::regconfig,
      COALESCE(canonical_name, ''::text)      || ' '::text ||
      COALESCE(description, ''::text)         || ' '::text ||
      COALESCE(tasting_notes, ''::text)       || ' '::text ||
      COALESCE(community_sentiment, ''::text)
    )
  ) STORED
);

ALTER TABLE public.products
  ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.products
  ADD CONSTRAINT products_pkey PRIMARY KEY (id);

ALTER TABLE public.products
  ADD CONSTRAINT products_canonical_name_key UNIQUE (canonical_name);

ALTER TABLE public.products
  ADD CONSTRAINT products_distiller_id_fkey FOREIGN KEY (distiller_id) REFERENCES public.producers(id);

ALTER TABLE public.products
  ADD CONSTRAINT products_bottler_id_fkey FOREIGN KEY (bottler_id) REFERENCES public.producers(id);

-- Constrained vocabularies use CHECK rather than Postgres ENUM types.
-- Extending a CHECK is a drop-and-recreate in one migration; ENUM has no
-- DROP VALUE syntax at all, so removing or renaming a value requires
-- creating a new type and migrating the column. `category` is guaranteed
-- to gain values as verticals are added.
ALTER TABLE public.products
  ADD CONSTRAINT products_vertical_check CHECK (vertical = ANY (ARRAY['whiskey'::text, 'beer'::text, 'wine'::text]));

ALTER TABLE public.products
  ADD CONSTRAINT products_category_check
    CHECK (category = ANY (ARRAY['bourbon'::text, 'rye'::text, 'scotch'::text, 'irish'::text, 'japanese'::text, 'canadian'::text, 'tennessee'::text, 'american_single_malt'::text]));

ALTER TABLE public.products
  ADD CONSTRAINT products_availability_check CHECK (availability = ANY (ARRAY['widely_available'::text, 'regional'::text, 'allocated'::text, 'discontinued'::text]));

ALTER TABLE public.products
  ADD CONSTRAINT products_data_quality_check CHECK (data_quality = ANY (ARRAY['high'::text, 'medium'::text, 'low'::text]));

ALTER TABLE public.products
  ADD CONSTRAINT products_scarcity_tier_range CHECK (scarcity_tier >= 0 AND scarcity_tier <= 5);

-- Loose on purpose: widely available implies tier 0, but discontinued and
-- regional bottles are free to carry a high tier. A discontinued cult
-- bottle is genuinely hard to find. Passes when scarcity_tier is NULL
-- (not yet assessed), which is intended.
ALTER TABLE public.products
  ADD CONSTRAINT products_scarcity_consistency CHECK (availability <> 'widely_available'::text OR scarcity_tier = 0);

GRANT MAINTAIN, REFERENCES, TRIGGER, TRUNCATE ON public.products TO service_role;

-- Postgres does not auto-index foreign keys.
CREATE INDEX products_distiller_idx ON public.products (distiller_id);

CREATE INDEX products_bottler_idx ON public.products (bottler_id);

-- Array containment filters: WHERE style_tags @> ARRAY['wheated']
CREATE INDEX products_style_tags_idx ON public.products USING gin (style_tags);

CREATE INDEX products_flavor_profile_idx ON public.products USING gin (flavor_profile);

-- Keyword retrieval.
CREATE INDEX products_search_vector_idx ON public.products USING gin (search_vector);

-- Fuzzy name resolution, so resolve_bottle() does not compute similarity
-- against every row.
CREATE INDEX products_canonical_name_trgm_idx ON public.products USING gin (canonical_name extensions.gin_trgm_ops);

-- The tool-boundary filter path.
CREATE INDEX products_vertical_category_idx ON public.products (vertical, category);

CREATE TRIGGER products_set_updated_at
  BEFORE UPDATE ON public.products
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at();


-- =====================================================================
-- product_embeddings
--
-- The search index over products, not knowledge in its own right. The
-- vectors are never shown to the LLM -- retrieval joins back to products
-- and returns prose from there. Three embeddings per product, selected at
-- retrieval time by query intent (ADR-0005):
--
--   full_profile         overall similarity ("what's like Henry McKenna?")
--   tasting_notes        flavor queries ("something sweet, not too oaky")
--   community_sentiment  reputation queries ("an underrated value pick")
--
-- All three are generated from day one even though retrieval initially
-- queries full_profile only, because backfilling embeddings across a
-- populated KB later is far more expensive than generating them up front.
-- =====================================================================
CREATE TABLE public.product_embeddings (
  id             uuid                     DEFAULT gen_random_uuid() NOT NULL,
  product_id     uuid                     NOT NULL,
  embedding_type text                     NOT NULL,

  -- OpenAI text-embedding-3-large, requested at dimensions=1536 (native is
  -- 3072). The column WIDTH is locked; the model is not. Both v3 models accept
  -- a `dimensions` parameter, so switching models is a re-embedding script
  -- with no migration -- as long as the replacement also emits 1536.
  embedding      extensions.vector(1536),

  -- Exactly what was embedded. Source text must be natural-language prose
  -- generated from the structured fields, never serialized JSON --
  -- embeddings perform markedly worse on {"proof": 100} than on "a
  -- 100-proof Kentucky straight bourbon...". Retained so retrieval
  -- failures can be debugged and a model change can re-embed cleanly.
  source_text    text,

  created_at     timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.product_embeddings
  ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.product_embeddings
  ADD CONSTRAINT product_embeddings_pkey PRIMARY KEY (id);

-- One embedding of each type per product. Note the PK is on id, NOT on
-- product_id -- a PK on product_id would silently permit only a single
-- embedding per product and break the multi-resolution design entirely.
-- This constraint also serves as the lookup index for joins filtered by
-- embedding_type, so no separate index is needed.
ALTER TABLE public.product_embeddings
  ADD CONSTRAINT product_embeddings_product_type_uniq UNIQUE (product_id, embedding_type);

ALTER TABLE public.product_embeddings
  ADD CONSTRAINT product_embeddings_type_check CHECK (embedding_type = ANY (ARRAY['full_profile'::text, 'tasting_notes'::text, 'community_sentiment'::text]));

-- CASCADE matters here: a container-image Lambda invoking retrieval would
-- otherwise surface orphaned vectors pointing at deleted products.
ALTER TABLE public.product_embeddings
  ADD CONSTRAINT product_embeddings_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON UPDATE CASCADE ON DELETE CASCADE;

GRANT MAINTAIN, REFERENCES, TRIGGER, TRUNCATE ON public.product_embeddings TO service_role;

-- No HNSW index yet, deliberately. At roughly 1,500 vectors an exact scan
-- returns in single-digit milliseconds with perfect recall, whereas HNSW
-- is approximate and would trade recall for speed that is not needed.
-- Adding it later is one CREATE INDEX with no schema or query changes --
-- and keeping exact results now provides the ground truth to measure
-- recall loss against when the index is eventually added.


-- =====================================================================
-- product_similarities
--
-- Curated market-role knowledge, and a non-vector retrieval path. This
-- table exists precisely because embeddings cannot derive these
-- relationships: two bottles can be sensible substitutes in a purchase
-- decision without tasting anything alike. Russell's Reserve is the
-- commonly-cited alternative to Eagle Rare on price tier and enthusiast
-- positioning, not flavor.
--
-- Entirely hand-curated with no automation path; target ~50-100 rows.
-- A 'similar_profile' type was deliberately dropped -- that is the one
-- relation a tasting_notes vector search would find on its own, so it
-- would consume curation budget duplicating the embeddings.
-- =====================================================================
CREATE TABLE public.product_similarities (
  -- CONVENTION: similarity_type describes what B is, RELATIVE TO A.
  --   (wild_turkey_101, buffalo_trace, 'step_up')
  --   reads: "Buffalo Trace is a step up from Wild Turkey 101"
  product_a_id    uuid                     NOT NULL,
  product_b_id    uuid                     NOT NULL,

  -- 'step_down' is deliberately NOT a stored value -- it is a step_up row
  -- read backwards, derived at query time by inverting the label when the
  -- match lands on product_b_id. Storing both directions would mean two
  -- rows per fact with no guarantee they stay consistent.
  --   forward:  SELECT product_b_id WHERE product_a_id = $1
  --   backward: SELECT product_a_id WHERE product_b_id = $1  -> step_down
  -- 'alternative' is symmetric: stored in whichever direction it was
  -- entered, found from either side.
  similarity_type text                     NOT NULL,

  notes           text,
  created_at      timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.product_similarities
  ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.product_similarities
  ADD CONSTRAINT product_similarities_pkey PRIMARY KEY (product_a_id, product_b_id, similarity_type);

ALTER TABLE public.product_similarities
  ADD CONSTRAINT product_similarities_type_check CHECK (similarity_type = ANY (ARRAY['step_up'::text, 'alternative'::text]));

ALTER TABLE public.product_similarities
  ADD CONSTRAINT product_similarities_no_self CHECK (product_a_id <> product_b_id);

ALTER TABLE public.product_similarities
  ADD CONSTRAINT product_similarities_product_a_id_fkey FOREIGN KEY (product_a_id) REFERENCES public.products(id) ON UPDATE CASCADE ON DELETE CASCADE;

ALTER TABLE public.product_similarities
  ADD CONSTRAINT product_similarities_product_b_id_fkey FOREIGN KEY (product_b_id) REFERENCES public.products(id) ON UPDATE CASCADE ON DELETE CASCADE;

GRANT MAINTAIN, REFERENCES, TRIGGER, TRUNCATE ON public.product_similarities TO service_role;

-- Reverse lookup. The primary key indexes (a, b, type), which serves
-- forward queries; the derived step_down direction reads product_b_id.
CREATE INDEX product_similarities_reverse_idx ON public.product_similarities (product_b_id, similarity_type);
