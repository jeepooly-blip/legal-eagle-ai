# Legal Eagle AI

Multi-agent cross-jurisdictional legal research platform. Parallel US (CourtListener) and EU (EUR-Lex + EuroVoc) queries with structured synthesis, verification, and provenance.

![Status](https://img.shields.io/badge/status-MVP-blue) ![Version](https://img.shields.io/badge/version-0.1.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

> **Live demo:** [https://legal-eagle-ai.vercel.app](https://legal-eagle-ai.vercel.app) (configure your API URL in `app.js`)

## What it does

Given a research question like *"Compare US Fourth Amendment with EU GDPR for employee monitoring"*, Legal Eagle AI:

1. **Orchestrator** decomposes the query and asks the **EuroVoc suggest** tool for relevant EU concept labels.
2. **US Retriever** and **EU Retriever** run **in parallel** — CourtListener for US case law, EUR-Lex SPARQL for EU regulations/directives (with EuroVoc concept filters when available).
3. **Summarizer** produces structured holdings, key facts, and legal basis for each bundle, aggregating `eurovoc_descriptors`.
4. **Synthesis Agent** calls the **EuroVoc bridge** + **hierarchy** tools to map US concepts to EU taxonomy, then produces a comparative narrative, alignment matrix, and divergences.
5. **Verification Agent** checks citation format and provenance.
6. Report is persisted to Supabase and returned via REST.

## Architecture (v1.1, EuroVoc Enhanced)

```
Query ─► Orchestrator ─► eurlex_eurovoc_suggest ─► [US Retriever, EU Retriever]   (parallel)
                │                                          │
                │                                          └─► eurlex_eurovoc_search (primary EU path)
                │                                              │
                │                                              └─► Summarizer (enriched with EuroVoc descriptors)
                └─► Synthesis Agent ─► eurlex_eurovoc_bridge + hierarchy ─► Verification Agent ─► Report
```

All inter-agent communication uses the `TaskHandoff` JSON schemas in `src/legal_eagle/schemas/task_handoff.py`. Every `LegalDocument` is normalized to a single unified shape regardless of source, and EU documents are tagged with `eurovoc_descriptors` for semantic bridging.

## Quickstart (local)

```bash
# 1. Install
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# edit .env with your real keys (MINIMAX_API_KEY, etc.)

# 3. Run the CLI
legal-eagle research "Compare US Fourth Amendment search-and-seizure doctrine with EU GDPR data-protection enforcement on employee monitoring"

# 4. Or start the API
uvicorn legal_eagle.api.main:app --reload
# Open Swagger UI: http://127.0.0.1:8000/docs
```

## Tests

```bash
pytest -v                       # 23 tests, ~25s
ruff check src tests            # lint
```

## Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the full GitHub + Vercel + Railway guide.

TL;DR:
- **Frontend** (this `index.html` + `app.js` + `style.css`) is a static site → deploy to **Vercel**.
- **Backend** (FastAPI in `src/legal_eagle/api/`) → deploy to **Railway.app** (no timeout, free tier).
- Both auto-deploy from the same GitHub repo on every push to `main`.

## Project layout

```
legal-eagle-ai/
├── index.html              # Vercel static dashboard
├── app.js                  # Frontend logic
├── style.css               # Dashboard styles
├── vercel.json             # Vercel config (static + headers)
├── railway.toml            # Railway config (uvicorn start command)
├── Procfile                # Backup start command for Railway/Heroku
├── runtime.txt             # Python version for Railway
├── .github/workflows/ci.yml # GitHub Actions: lint + test on push
├── pyproject.toml
├── README.md
├── DEPLOYMENT.md           # Step-by-step deploy guide
├── LICENSE                 # MIT
├── .env.example
├── .gitignore
├── src/
│   └── legal_eagle/
│       ├── api/main.py     # FastAPI app (with CORS)
│       ├── cli.py          # Typer CLI
│       ├── pipeline.py     # ResearchPipeline orchestrator
│       ├── config.py
│       ├── agents/         # orchestrator, us/eu_retriever, summarizer, synthesis, verification
│       ├── mcp_clients/    # courtlistener, eurlex, eurovoc, _terminology_bridge
│       ├── middleware/     # router, rate_limiter, normalizer, provenance, cache
│       ├── schemas/        # LegalDocument, task handoffs, reports
│       ├── llm/            # LiteLLM wrapper + prompts
│       └── db/             # Supabase client + schema.sql
└── tests/                  # 23 tests, all green
```

Key modules:

- `mcp_clients/courtlistener.py` — CourtListener REST client (US)
- `mcp_clients/eurlex.py` — EUR-Lex REST + SPARQL client; populates `eurovoc_descriptors` on each document
- `mcp_clients/eurovoc.py` — all 5 PRD v1.1 tools: `eurovoc_search`, `concept_details`, `hierarchy`, `suggest`, `bridge`
- `mcp_clients/_terminology_bridge.py` — static US ↔ EuroVoc terminology table (21 entries)
- `middleware/` — router, rate limiter, normalizer, provenance, cache
- `agents/` — orchestrator (now EuroVoc-aware), US/EU retrievers, summarizer, synthesis (uses bridge), verification
- `schemas/` — Pydantic models for `LegalDocument` (with `eurovoc_descriptors`), the 5 handoff types, plus `EuroVocConcept` and `EuroVocBridgeEntry`
- `db/` — Supabase persistence (schema in `db/schema.sql`)
- `api/main.py` — FastAPI with CORS middleware
- `cli.py` — Typer CLI

## PRD status

v1.1 (EuroVoc Enhanced). All 5 new MCP tools implemented, terminology bridge populated, agents wired to use them.

## License

MIT — see [LICENSE](LICENSE).
