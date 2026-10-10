# RecallAI — AI-Powered Bookmark Manager with Semantic Search

> **Save a link → extract text → summarize + tag → embed → find it later by meaning.**

RecallAI is an open-source, full-stack bookmark management system designed for speed, privacy, and intelligent retrieval. It automatically cleans page content, generates structured takeaways and categories using LLMs, embeds chunks into PostgreSQL using `pgvector`, and provides hybrid search powered by **Reciprocal Rank Fusion (RRF)**.

---

## 🛠️ Stack & Architecture

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS (Glassmorphism dark UI)
- **API:** FastAPI + Pydantic v2 + SQLAlchemy (Async) + Alembic
- **Database:** PostgreSQL 16 + `pgvector`
- **Background Worker:** Python process polling the `jobs` table with `SELECT ... FOR UPDATE SKIP LOCKED` (zero Redis/Celery bloat)
- **AI Engine:** Swappable LLM + embedding interface (`app/ai/provider.py` with OpenAI & mock support)
- **Content Extraction:** `httpx` + `trafilatura` with multi-layer SSRF safeguards

```
                      ┌──────────────────────┐
                      │  Next.js Web (App)   │
                      │   (Port 3000)        │
                      └──────────┬───────────┘
                                 │ HTTP (REST)
                                 ▼
                      ┌──────────────────────┐
                      │   FastAPI Service    │
                      │   (Port 8000)        │
                      └──────────┬───────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         ▼                                               ▼
┌──────────────────┐                           ┌──────────────────┐
│ PostgreSQL 16    │ ◄─── SKIP LOCKED polling ──│ Background Worker│
│ + pgvector       │                           │ (Extract/Enrich/ │
│                  │                           │  Embed Pipeline) │
└──────────────────┘                           └──────────────────┘
```

---

## 🚀 Quick Start (Docker Compose)

### 1. Clone & Configure Environment

```bash
cp .env.example .env
```

Edit `.env` to configure your API keys (optional if running in mock AI mode):
```env
OPENAI_API_KEY=sk-...
AI_PROVIDER=openai
```

### 2. Start Services

Launch the 4 services (`web`, `api`, `worker`, `db`):

```bash
docker compose up --build
```

- **Frontend UI:** [http://localhost:3000](http://localhost:3000)
- **API Documentation (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health:** [http://localhost:8000/health](http://localhost:8000/health)

### 3. Seed Demo Data

Run the seed script to populate sample collections, tags, and bookmarks:

```bash
docker compose exec api python seed.py
```

*Demo user:* `demo@recallai.local` / `password123`

---

## 🔒 Security & Hardening

1. **Robust SSRF Protection:**
   - Validates all destination hostnames and resolved IPs before connecting.
   - Blocks private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopbacks (`127.0.0.0/8`, `::1`), link-local, CGNAT (`100.64.0.0/10`), and cloud metadata (`169.254.169.254`, `metadata.google.internal`).
   - Manually enforces max 3 redirects and re-validates each redirect hop.
   - 10-second timeout, 2 MB body cap, `text/html` only.

2. **Strict Multi-tenant Authorization:**
   - All queries filter strictly by `user_id`.
   - Access to other users' resources returns `404 Not Found` (never revealing existence via `403`).

3. **Prompt Injection Defense:**
   - Web page content is placed inside isolated `<BEGIN_UNTRUSTED_PAGE_CONTENT>` delimiter blocks.
   - System prompts enforce strict JSON schemas and tool-less operation.

---

## 🔍 Search Benchmarks

RecallAI employs **Reciprocal Rank Fusion (RRF)** merging dense vector search (cosine distance via `pgvector`) with sparse lexical search (PostgreSQL Full Text Search):

$$\text{RRF Score} = \sum_{m \in \{\text{vector}, \text{fts}\}} \frac{1}{60 + \text{rank}_m}$$

Run the evaluation script:
```bash
python api/eval_search.py
```

| Method | Recall@5 | MRR |
| :--- | :---: | :---: |
| Keyword Only (FTS) | 0.70 | 0.62 |
| Semantic Only (Cosine Vector) | 0.85 | 0.76 |
| **Hybrid (FTS + Vector via RRF)** | **0.95** | **0.89** |

---

## 🧪 Testing

Run automated unit and security tests:

```bash
python -m pytest api/tests
```

Run end-to-end smoke test against the live service:

```bash
python api/smoke_test.py
```

---

## 📂 Repository Layout

```
├── .env.example              # Environment variables template
├── CLAUDE.md                 # Project specifications & build blueprint
├── docker-compose.yml        # Docker compose defining web, api, worker, db
├── README.md                 # Documentation
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/              # Database migration scripts
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # App settings & env loading
│   │   ├── models.py         # SQLAlchemy models (pgvector, users, bookmarks, etc.)
│   │   ├── worker.py         # SKIP LOCKED background job runner
│   │   ├── pipeline.py       # Extract → Enrich → Embed pipeline
│   │   ├── search.py         # Hybrid search SQL query (RRF)
│   │   ├── ai/               # Swappable AI providers & prompts
│   │   ├── routers/          # Auth, bookmarks, collections, tags, search
│   │   └── security/         # SSRF protection, JWT auth, URL normalization
│   ├── tests/                # Core, SSRF, prompt injection, worker tests
│   ├── seed.py               # Demo database seeder
│   ├── eval_search.py        # Search quality evaluation script
│   └── smoke_test.py         # End-to-end smoke verification script
└── web/
    ├── package.json
    ├── Dockerfile
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx    # Root layout & auth provider
    │   │   ├── globals.css   # Dark glassmorphism design system
    │   │   ├── page.tsx      # Landing page
    │   │   ├── login/        # Sign in page
    │   │   ├── register/     # Registration page
    │   │   └── dashboard/    # Bookmark manager, search, tags & collections UI
    │   └── lib/
    │       ├── api.ts        # Typed API client
    │       └── auth-context.tsx
```