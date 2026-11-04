SET local check_function_bodies = off;

CREATE TABLE "public"."user_roles" (
  "user_id"    uuid                        NOT NULL,
  "created_at" timestamp without time zone DEFAULT now()
);

ALTER TABLE "public"."user_roles"
  ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."user_roles" FROM "anon", "authenticated";

-- releases: per-batch detail for bottles sold in distinct batches (barrel
-- proof lines, annual limited editions). Product-level columns describe the
-- bottle in general; this records how individual releases differ from it.
-- NULL means no releases recorded, which is the normal case for a
-- non-batched bottle.
--
-- A JSON array, one object per release. The shape is a guideline, not
-- enforced -- every key is optional and new keys need no migration:
--   [
--     {
--       "laser_code": "L23182",
--       "batch":      "Batch 3",
--       "year":       2023,
--       "proof":      114.8,
--       "msrp_usd":   70,
--       "notes":      "First release after the age statement returned"
--     }
--   ]
-- Excluded from embeddings deliberately: batch-level detail adds noise to
-- product-level similarity, and the agent reads it from the row once
-- retrieval has found the product.
ALTER TABLE "public"."products"
  ADD COLUMN "releases" jsonb;

CREATE TYPE "public"."app_role" AS ENUM (
  'admin'
);

ALTER TABLE "public"."user_roles"
  ADD COLUMN "role" public.app_role NOT NULL;

CREATE OR REPLACE FUNCTION public.custom_access_token_hook (
  event jsonb
)
  RETURNS jsonb
  LANGUAGE plpgsql
  AS $function$declare
  claims jsonb;
  user_roles jsonb;
begin
  select coalesce(jsonb_agg(role), '[]'::jsonb)
  into user_roles
  from public.user_roles
  where user_id = (event->>'user_id')::uuid;

  claims := event->'claims';
  claims := jsonb_set(claims, '{user_roles}', user_roles);
  event := jsonb_set(event, '{claims}', claims);

  return event;
end;$function$;

REVOKE ALL ON FUNCTION "public"."custom_access_token_hook"(jsonb) FROM PUBLIC, "anon", "authenticated";

CREATE OR REPLACE FUNCTION public.rls_auto_enable()
  RETURNS event_trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'pg_catalog'
  AS $function$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$function$;

ALTER TABLE "public"."user_roles"
  ADD CONSTRAINT "user_roles_pkey" PRIMARY KEY (user_id, ROLE);

ALTER TABLE "public"."user_roles"
  ADD CONSTRAINT "user_roles_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON UPDATE CASCADE ON DELETE CASCADE;

CREATE POLICY "Allow auth admin to read user roles" ON "public"."user_roles"
  FOR SELECT
  TO PUBLIC
  USING (true);

CREATE EVENT TRIGGER "ensure_rls"
  ON ddl_command_end
  WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
  EXECUTE FUNCTION "public"."rls_auto_enable"();

REVOKE ALL ON FUNCTION "public"."custom_access_token_hook"(jsonb) FROM "postgres";

GRANT EXECUTE ON FUNCTION "public"."custom_access_token_hook"(jsonb) TO "postgres";

GRANT EXECUTE ON FUNCTION "public"."custom_access_token_hook"(jsonb) TO "service_role", "supabase_auth_admin";

GRANT EXECUTE ON FUNCTION "public"."rls_auto_enable"() TO PUBLIC, "anon", "authenticated";

REVOKE ALL ON FUNCTION "public"."rls_auto_enable"() FROM "postgres";

GRANT EXECUTE ON FUNCTION "public"."rls_auto_enable"() TO "postgres";

GRANT EXECUTE ON FUNCTION "public"."rls_auto_enable"() TO "service_role";

REVOKE ALL ON SCHEMA "public" FROM "supabase_auth_admin";

GRANT USAGE ON SCHEMA "public" TO "supabase_auth_admin";

REVOKE ALL ON TABLE "public"."user_roles" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."user_roles" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."user_roles" TO "service_role";

GRANT SELECT ON TABLE "public"."user_roles" TO "supabase_auth_admin";

