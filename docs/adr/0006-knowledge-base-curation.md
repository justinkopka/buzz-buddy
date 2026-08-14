# ADR-0006: Knowledge Base Curation Approach (Hybrid Manual + LLM-Assisted)

**Status:** Accepted
**Date:** 2026-06-04

## Context

Needed a strategy for populating and maintaining the bottle knowledge base: how much manual curation versus automated/LLM-assisted extraction, what actually makes a recommendation trustworthy rather than generic, and what legal/ethical constraints apply to gathering information from community and review sources online.

## Decision

A hybrid approach: the top 50–100 bottles curated manually (25–35 min each), with the long tail populated via LLM-assisted extraction plus human review (8–12 min each). Launch target is 150 bottles minimum, 150–200 ideal. Information is gathered by reading sources as a human, the LLM is used only to structure what's been gathered, and all prose is written fresh — never redistributing copyrighted content verbatim, never scraping at scale.

## Alternatives Considered

- **Fully manual curation for every bottle** — highest quality per entry, but too slow/expensive to reach a usable launch catalog size.
- **Fully automated extraction with no human review** — fast and cheap, but risks factual inaccuracy, real legal/ethical exposure around scraping and redistribution, and — critically — dilutes the one field that actually differentiates the product (see Reasoning).

## Reasoning

The central insight driving this whole decision: `community_sentiment` is the highest-value field in the schema, and it's the actual competitive moat. Distilleries produce marketing copy; the community produces honest assessment. A sentence like "widely regarded as one of the best value plays on the standard shelf, though some find it oak-heavy" isn't something a distillery would ever write, and it's exactly what makes a recommendation feel trustworthy instead of generic. That sentence can't be scraped wholesale or fine-tuned into existence — it requires a human reading real community discussion and synthesizing it. That's why hybrid curation is central to the decision, not a stopgap compromise.

The effort tiering follows directly: the top 50–100 bottles are the ones actually driving most recommendations, so quality there has outsized impact and earns the deeper manual treatment. The long tail gets faster LLM-assisted extraction with human review to reach a usable catalog size without paying full manual cost on every bottle. 150–200 bottles is calibrated as enough breadth to be genuinely useful without requiring manual-curation cost across the whole catalog.

The legal/ethical stance — gather as a human reader, use the LLM only to structure what's been gathered, write original prose, never redistribute copyrighted content verbatim, don't scrape at scale since many sources' ToS prohibit it — mirrors how legitimate content sites operate. It avoids both real legal risk and the more basic ethical problem of free-riding on other people's original writing.

The four source tiers (distillery sites/TTB COLA/Whiskey Advocate; Distiller.com/Breaking Bourbon/Bourbonr; r/bourbon, r/whiskey, FlyerTalk; pricing sources) give a structured reliability hierarchy, feeding directly into data-quality tagging (high/medium/low) so the agent can reason about its own confidence and caveat accordingly, rather than presenting everything with false uniform certainty.

Building the admin UI before meaningful curation begins is a straightforward effort-payoff call: half a day of work against the alternative of entering hundreds of bottles via raw SQL. Making it pleasant (autocomplete on distillery names, keyboard-driven save) is justified specifically because this tool gets used for months of ongoing work — friction there compounds, unlike a one-off script.

Several schema decisions emerged during design, each with its own reasoning: aliases were dropped in favor of a `resolve_bottle()` tool (fuzzy match plus embeddings), since enumerating every variant name up front doesn't scale. Mash bill percentages were dropped (not reliably public) in favor of categorical `style_tags` (wheated/high-rye) that can actually be sourced. `distiller_score` stays nullable, populated only during top-bottle curation, so it's never fabricated for bottles that haven't received deep treatment. Custom aggregated community ratings were dropped as false rigor — a single number implies a precision and consensus that doesn't actually exist behind genuinely scattered community opinion. Multi-field pricing kept nullable secondary-market fields specifically for allocated bottles, where secondary pricing exists but MSRP doesn't reflect real availability. `bottle_similarities` stays a curated table rather than an embedding-derived one, because "if not X, try Y" relationships are about market role and cultural knowledge, not flavor — two bottles can be reasonable substitutes in a purchase decision without tasting anything alike, which is exactly the kind of relationship embeddings structurally can't capture.

## Consequences

- **Not yet implemented.** No bottles schema, migrations, or `resolve_bottle()` tool exist in the repo. `frontend/app/admin/page.tsx` exists as a stub route, already gated behind an `admin` role check in `proxy.ts`, but none of the actual curation UI (entry forms, autocomplete, keyboard save) is built.
- Curation is an ongoing human process, not a one-time script run — the admin UI investment is justified by months of continued use, not just the initial launch push.
- Recommendation quality is bottlenecked by curation quality, not just retrieval/embedding sophistication — a technically excellent RAG pipeline over thin or generic content wouldn't produce the differentiated value this decision is built around.
- Growing the catalog later always costs real human curation time, not just compute — there's no faster bulk-automated path without abandoning the legal/ethical stance and the community_sentiment quality bar.
- `bottle_similarities` being curated rather than derived means it needs its own ongoing maintenance as bottles are added — it won't self-populate the way an embedding-based relationship would.

## References

- `frontend/app/admin/page.tsx`, `frontend/proxy.ts` — admin route and role-gating scaffolding already in place
- ADR-0001 — Postgres/Supabase as the storage layer this schema will live in
- ADR-0005 — embedding strategy that `resolve_bottle()` and similarity search build on
