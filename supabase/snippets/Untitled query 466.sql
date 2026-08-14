-- FK indexes Postgres doesn't create automatically.
-- Supports "what else does this distillery make?" and cascade behavior.
CREATE INDEX products_distiller_idx ON products (distiller_id);
CREATE INDEX products_bottler_idx   ON products (bottler_id);

-- These tables are backend-only via the service role. anon/authenticated
-- need none of these privileges — TRUNCATE especially, since RLS does not
-- apply to it.
REVOKE MAINTAIN, REFERENCES, TRIGGER, TRUNCATE
  ON products, producers, product_embeddings, product_similarities
  FROM anon, authenticated;

-- Close the NULL bypass on the data_quality CHECK constraint.
ALTER TABLE products ALTER COLUMN data_quality SET NOT NULL;
