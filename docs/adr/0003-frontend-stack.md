# ADR-0003: Frontend Stack (Next.js PWA on Vercel)

**Status:** Accepted
**Date:** 2026-06-04

## Context

Needed a frontend framework and hosting approach for a client that could eventually support camera-based bottle-photo lookup in a future vision-model phase, without taking on native mobile app development.

## Decision

Next.js, configured as a PWA, deployed on Vercel — in the same repository as the backend rather than a separate one.

## Alternatives Considered

- **Remix** — good framework, smaller community/ecosystem.
- **SvelteKit** — excellent technically, but React skills transfer more directly to available jobs than Svelte's do.
- **Plain React + Vite** — would need routing and SSR bolted on by hand rather than coming built-in.
- **Two-repo split** (frontend and backend as separate repos) — considered alongside the monorepo choice.
- **AWS Amplify** (hosting) — considered as a way to keep an all-AWS story.

## Reasoning

Next.js is the dominant React meta-framework, handles routing/SSR/PWA configuration out of the box rather than assembled by hand, and is the framework hiring managers in this space expect to see behind a project like this.

The PWA choice directly answers the "avoid native app development" constraint: users install to their phone's home screen and get a native-feeling experience without writing a line of Swift or React Native — and critically, PWAs get camera access through the browser, which sets up the eventual vision-model phase (photograph a bottle label, get a recommendation) without ever touching a native mobile toolchain.

Remix and SvelteKit were both considered and are both good frameworks technically — Remix has a smaller community, and while SvelteKit's technical merits arguably rival Next.js's, React skills transfer more directly to available jobs than Svelte's do, which tipped it toward Next.js. Plain React + Vite was rejected because it would mean hand-rolling routing and SSR that Next.js provides natively.

On repo structure: one repository containing both `frontend/` and `backend/`, with Vercel configured to watch only the frontend directory for deploys, was chosen over two separate repositories — lower overhead, a single commit history, and no cross-repo coordination needed for changes touching both sides.

On hosting: AWS Amplify was considered as a way to keep the story purely within AWS, but was judged not worth it — recruiters don't penalize a Vercel deployment for a Next.js app, and Vercel is the more natural fit for Next.js specifically, being built by the same team with first-class support for every Next.js feature.

## Consequences

- Confirmed as implemented: `frontend/` uses Next.js (`frontend/package.json`), with PWA scaffolding in place — `frontend/app/manifest.ts`, `frontend/public/sw.js`, `frontend/components/register-service-worker.tsx`.
- The monorepo structure means backend and infrastructure changes live alongside frontend changes in one history — convenient for a solo developer, but means CI/CD (once built) will need path-based triggers to avoid redeploying the frontend on backend-only changes and vice versa.
- Vercel and Next.js are now a tightly coupled pair in this stack — moving off either would likely mean moving off both together, given how much of the PWA/SSR/build pipeline is Vercel-optimized Next.js behavior.
- The camera-access-via-PWA plan for the future vision phase is not yet built — this ADR documents intent, not current capability.

## References

- `frontend/package.json` — Next.js dependency
- `frontend/app/manifest.ts`, `frontend/public/sw.js`, `frontend/components/register-service-worker.tsx` — PWA implementation
- Repository root — single repo containing `frontend/`, `backend/`, `infrastructure/`, `docs/`
