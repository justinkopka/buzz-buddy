# BuzzBuddy

An AI agent for bourbon decision support. Tell it what bottles you're 
looking at in a store, and it helps you decide which to buy based on 
your preferences, collection, and budget.

**Status:** 🚧 In early development. Currently scoping and building 
the thin MVP.

## What It Does (Eventually)

You're standing in a liquor store looking at three or four bourbons. 
You don't know which is the best value, which is allocated and worth 
grabbing, or which matches your taste. You open BuzzBuddy, tell it 
what's in front of you, and get a clear, reasoned recommendation.

Long-term, the platform will expand to cover craft beer and wine using 
the same underlying agent architecture.

## Why This Exists

This project is being built as:

1. An AI engineering portfolio piece demonstrating production-grade 
   agentic systems (RAG, tool use, evals, observability).
2. A potential micro-SaaS with a passionate target audience.
3. A genuinely useful tool for bourbon enthusiasts.

The build is happening in public — see `docs/` for architectural 
decisions, sprint retros, and progress metrics.

## Tech Stack

- **Frontend:** Next.js (TypeScript) deployed as a PWA on Vercel
- **Backend:** Python + FastAPI on AWS Lambda + API Gateway
- **Database & Auth:** Supabase (Postgres + pgvector + Supabase Auth)
- **LLM:** Anthropic Claude for reasoning; OpenAI for embeddings
- **Observability:** LangSmith for LLM tracing; CloudWatch for infra; 
  loguru for application logging
- **Agent Framework:** Custom agent loop with native tool use APIs; 
  selective use of LangChain components for document loading/chunking

See `docs/adr/` for the reasoning behind these choices.

## Repository Structure

    buzzbuddy/
    ├── frontend/            # Next.js application
    ├── backend/             # Python FastAPI application
    │   └── evals/           # Evaluation framework and test cases
    ├── infrastructure/      # AWS deployment configuration
    ├── shared/              # Shared types and OpenAPI specs
    ├── docs/
    │   ├── adr/             # Architectural Decision Records
    │   ├── retros/          # Weekly sprint retrospectives
    │   ├── metrics/         # Project metrics and time tracking
    │   ├── planning/        # Roadmap and planning documents
    │   ├── evals/           # Eval framework design
    │   └── blog/            # Draft posts about the build
    └── scripts/             # One-off utility scripts

## Project Documentation

- **[Roadmap](docs/planning/roadmap.md)** — The 15-sprint plan from 
  thin MVP through v1.0
- **[Architectural Decisions](docs/adr/README.md)** — Index of ADRs 
  documenting major technical choices
- **[Sprint Retros](docs/retros/)** — Weekly reflections on progress 
  and learnings
- **[Eval Framework](docs/evals/README.md)** — How agent quality is 
  measured
- **[Metrics](docs/metrics/)** — Time tracking, weekly metrics, and 
  eval history

## Development

> Setup instructions will be added as the build progresses. For now, 
> this section is a placeholder.

### Prerequisites
- Node.js (version TBD)
- Python 3.11+
- AWS account
- Supabase account
- API keys: Anthropic, OpenAI, LangSmith

### Environment Variables
See `.env.example` for the full list of required environment variables. 
Never commit real values.

### Running Locally
_Setup instructions coming in Sprint 1._

## Contributing

This is a solo project for now. Issues and discussions are welcome 
for feedback or suggestions.

## License

_License to be determined. Currently all rights reserved._

## Contact

_Contact information to be added._