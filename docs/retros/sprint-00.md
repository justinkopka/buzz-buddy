# Sprint 0 Retro — Project Planning (Dates: June 2-7, 2026)

## Sprint Goal
Scope a defensible v1 of an AI engineering portfolio project, including 
architecture, KB design, UI sketch, tracking system, and roadmap, before 
writing any code.

## Outcome
Goal hit. BuzzBuddy chosen after comparing 12+ project options; full 
stack, architecture, KB schema, UI flow, tracking system, and 15-sprint 
roadmap locked in; eval framework designed with 6 seed test cases drafted 
and committed to repo. Project is fully scoped and ready for Sprint 1 
execution.

## Planned vs. Actual
- Shipped: #1, #11
- Slipped: None
- Unplanned: None (sprint was open-ended planning by design)

## Hours
- Planned: N/A (open-ended) | Actual: 15

## Went Well
- Stayed disciplined about thin MVP scope rather than committing to an 
  ambitious initial v1 that would have been months longer
- Identified the multi-vertical expansion path (whiskey → beer → wine) 
  as a way to turn scope-creep risk into a growth narrative
- Designed the eval framework before any code exists, so the agent will 
  be built to be evaluable from day one rather than retrofitted

## Went Poorly
- Initial scope of v1 was over-ambitious before being deliberately 
  trimmed to the thin MVP; could have started leaner faster

## Adjustments
- Track time per session in real-time going forward, rather than 
  reconstructing at retro time
- Use the lean retro template every Monday night to make weekly 
  retros a habit
- Front-load admin UI work in Sprint 2 before any meaningful KB 
  curation, to avoid pain entering bottles via SQL

## Resume/Interview Notes
- "Scoped the project deliberately across two planning sessions, 
  comparing 12+ ideas across AI engineering value, monetization 
  potential, and personal fit before committing" — strong interview 
  story about engineering judgment
- "Made the architectural decision to design evals before building 
  the system, which surfaced runner requirements (trace capture, 
  retrieval access, joint grading) that would have been expensive 
  to retrofit" — concrete example of eval-driven architectural thinking
- "Identified the 'shared constraint template' pattern across three 
  eval categories (preference, collection, budget) during case 
  drafting, leading to a single parameterized grader instead of 
  three duplicated implementations" — small but real example of 
  refactoring-during-design
- The full set of 8 ADRs (to be written in Sprint 1) will be its 
  own ammunition — each ADR is one interview story

## Metrics
| Metric | Value | Δ |
|---|---|---|
| Hours actual | 15 | — |
| Points completed | N/A (no estimated work) | — |
| Estimation accuracy | N/A | — |
| KB size | 0 | — |
| Eval acc | — | — |

# Next Sprint Planned Work
- Issue #2, Initialize monorepo and push to public GitHub, Estimate: 1
- Issue #8, Write Sprint 0 retrospective, Estimate: 0.5
- Issue #3, Set up GitHub repo infrastructure (templates, labels, project board) Labels: sprint-01, infra, chore, Estimate: 1
- Issue #9, Set up tracking infrastructure (time log, metrics, planning docs), Estimate: 1
- Issue #10, Polish README and document setup steps, Estimate: 1
- Issue #7, Write ADRs 0001-0008 documenting key architectural decisions, Estimate: 4
- Issue #6, Scaffold Python FastAPI backend on AWS Lambda, Estimate: 5
- Issue #4, Set up Supabase project with auth, Estimate: 3
- Issue #5, Scaffold Next.js frontend and deploy to Vercel Estimate: 3