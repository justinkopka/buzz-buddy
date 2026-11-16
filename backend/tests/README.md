# Backend tests

| Suite | Path | Needs |
|---|---|---|
| Unit | `tests/unit/` | nothing |
| Integration | `tests/integration/` | the local Supabase stack, loaded with a copy of production data |

Neither suite calls OpenAI or any other paid API. `tests/integration/conftest.py`
replaces every embedding call with one that fails the test; tests that need a
query vector reuse one already stored in `product_embeddings`.

## Running

From `backend/`:

```powershell
uv run pytest tests                 # everything
uv run pytest tests/unit            # no database required
uv run pytest tests/integration -v  # one line per test
```

If the local stack is not running, integration tests skip with a message
rather than fail.

## Local database setup

The integration tests run against the local Supabase stack in Docker, rebuilt
from the migrations in `supabase/migrations/` and seeded with production data.
Production is only ever **read** from, by the dump in step 3.

All commands run from the **repo root** (the folder containing `supabase/`),
with Docker Desktop running.

> **Targets.** This CLI version defaults to the **local** stack. Commands
> that should talk to the hosted project need `--remote`. The one command
> that must **never** get `--remote` (or `--linked`) is `db reset` — with it,
> `db reset` wipes production.

### 1. Start the local stack

```powershell
npx supabase start
```

Starts Postgres, Studio, Auth, and the rest of the stack in Docker. Harmless
if already running.

### 2. Confirm the migrations match production

```powershell
npx supabase migration list --remote
```

Compares the files in `supabase/migrations/` against the migration history
table in production. Every migration should show a value in both the
**Local** and **Remote** columns.

```powershell
npx supabase db diff --remote
```

Catches changes made in production *outside* a migration — a column added in
the Studio table editor, a function edited in the SQL editor. It replays the
local migrations into a throwaway database and diffs that against
production. Empty output means the two match.

If it prints SQL, pull it into a new migration:

```powershell
npx supabase db pull --remote
```

This writes `supabase/migrations/<timestamp>_remote_schema.sql` and asks
**"Update remote migration history table?"** — answer **Y**. That marks the
new migration as already applied in production (it only writes a row to the
history table; schema and data are untouched). Answering N leaves
production unaware of the file, and the next `db push` will try to apply it.

Read the generated file before committing. The diff tool sometimes re-emits
functions whose bodies have not actually changed
(`custom_access_token_hook` has done this); those are harmless but noisy.

### 3. Dump production data

```powershell
npx supabase db dump --remote --data-only -x public.user_roles -f supabase/seed.sql
```

| Part | Meaning |
|---|---|
| `--remote` | Export from the hosted project. Without it, this dumps the *local* database. |
| `--data-only` | Rows only. Table definitions come from the migrations in step 4. |
| `-x public.user_roles` | Skip this table: its rows reference `auth.users`, which is not copied, so loading them would fail the foreign key. Nothing in retrieval reads it. |
| `-f supabase/seed.sql` | Output file. `supabase/config.toml` (`[db.seed]`) loads it on reset. |

`seed.sql` is gitignored: it contains the full curated knowledge base,
including `community_sentiment`, and should not be committed.

### 4. Rebuild the local database

```powershell
npx supabase db reset
```

Wipes the **local** database, replays every migration in order, then loads
`supabase/seed.sql`. Afterwards local has production's schema and data.

### 5. Check

```powershell
npx supabase status
```

Prints the local addresses. The **DB URL** should be
`postgresql://postgres:postgres@127.0.0.1:55322/postgres`, which is what the
integration tests use by default. To point them elsewhere, set
`TEST_DATABASE_URL` — `conftest.py` refuses any host other than localhost.

Studio is at `http://127.0.0.1:55323`. A quick sanity check in its SQL
editor:

```sql
SELECT (SELECT count(*) FROM products)             AS products,
       (SELECT count(*) FROM product_embeddings)   AS embeddings,
       (SELECT count(*) FROM product_similarities) AS similarities;
```

## Refreshing after curation

When the production knowledge base changes, repeat steps 3 and 4. Repeat
step 2 first if anything was changed in the Studio UI.

## Troubleshooting

**"The remote database's migration history does not match local files"**
— usually a command ran against the local stack when it was meant for
production (check for the `Target: local stack` line in the output and add
`--remote`). Do not run the `migration repair` commands the message
suggests; they mark migrations as applied without running them.

**Integration tests all skip** — the local stack is not running, or the
database is empty. Run steps 1 and 4.

**A test skips naming a specific bottle** — some tests anchor on pilot
bottles by `canonical_name` (Wild Turkey 101, Buffalo Trace, Russell's
Reserve 13 Year, New Riff Bottled-in-Bond). Renaming one in production
skips those tests rather than failing them; update the names in the tests.
