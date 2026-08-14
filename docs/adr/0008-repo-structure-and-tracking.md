# ADR-0008: Repo Structure and Tracking Approach

**Status:** Accepted
**Date:** 2026-08-09

## Context

Needed a repository structure, visibility posture, documentation organization, and project/time-tracking approach for a solo-developer project with a dual purpose (real product, visible demonstration of process). The original version of this decision assumed a sprint-based, time-boxed cadence with weekly retrospectives; that assumption didn't survive contact with how the work actually happened.

## Decision

Monorepo (reasoning covered in ADR-0003) and public visibility survive unchanged. Sprints and weekly retrospectives are retired entirely. GitHub Projects Milestones (goal-based) replace sprint labels (time-based) for grouping work. Time tracking moves to GitHub Projects custom number fields (`Estimate (hrs)`, `Actual (hrs)`) per issue, with a small script against GitHub's GraphQL API needed to compute estimate-vs-actual variance, since Projects doesn't support formula fields.

## Alternatives Considered

- **Private repository** — considered and rejected in favor of public visibility.
- **Sprint-based, time-boxed tracking with weekly retros** — the original system this ADR retires.
- **Markdown-file time logging** (`docs/metrics/time-log.md`) — the original system this ADR retires.

## Reasoning

Public visibility means recruiters (or anyone evaluating the work) can clone the repo directly and observe how it was actually built — ADRs, structured issues, commit history — which becomes evidence of process on its own, without needing it explained or pointed at separately. That's a stronger, more credible signal than a private repo plus a description of the process.

Sprints and retros were dropped because the cadence didn't hold up in practice, not just as a preference shift. The original plan committed to a retro "every Monday night" to build the habit — but only the Sprint 0 retro was ever written, despite Sprint 1 covering substantial real work (the infrastructure buildout and this ADR series itself). A time-boxed process that isn't actually followed provides false structure, not real signal. Milestones (goal-based, no calendar attached) fit solo work better than sprints (time-based, built for team cadence-setting) — there's no team to synchronize with, so the coordination problem sprints solve doesn't exist here.

Time tracking moved into GitHub Projects rather than staying a separate markdown file to avoid maintaining two parallel systems (an issue tracker and a hand-maintained log) that could silently drift out of sync. The goal also shifted: the old system implicitly tracked toward velocity, a team/sprint-cadence concept that doesn't apply to solo work. The new fields target per-issue estimation calibration instead — getting better over time at predicting how long a task actually takes, which is useful signal regardless of whether sprints exist.

The GraphQL script requirement is a real limitation worth documenting plainly: GitHub Projects' custom fields don't support formulas, so `Estimate` and `Actual` are just two disconnected numbers in the UI until something computes variance between them. That script is also a legitimate side artifact in its own right — real tooling, not just process overhead.

## Consequences

- **Partially transitional, not fully operational yet.** `docs/retros/` and the old `docs/metrics/time-log.md` are already deleted, matching this decision — but the `Estimate`/`Actual` custom fields and the variance-calculation script don't exist yet in GitHub Projects.
- **Stale references not covered by this ADR:** `docs/metrics/README.md`, `CLAUDE.md`, and `backend/evals/README.md` all still reference the sprint-numbered roadmap this ADR retires (flagged separately, cleaned up alongside this ADR).
- GitHub Projects becomes the sole source of tracking truth — unlike the old markdown log, which lived in the repo itself immune to a third-party service's availability, losing access to GitHub Projects now means losing task and time-tracking history together.
- The variance script is required, not optional, for the new time-tracking approach to actually deliver its stated purpose (estimation calibration) rather than just recording two numbers nobody compares.
- Public visibility means the abandoned sprint/retro system remains visible in commit and file history even after being retired, unless history is rewritten (not planned) — arguably a feature, showing real iteration, but worth knowing it isn't erased, just superseded.

## References

- ADR-0003 — monorepo decision, not re-litigated here
- `docs/adr/` — the ADR system itself, a live instance of this decision
- `docs/metrics/README.md` — contains a stale Sprint 7 reference needing follow-up
