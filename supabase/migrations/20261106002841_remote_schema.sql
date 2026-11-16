SET local check_function_bodies = off;

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

