# CLAUDE.md — RecallAI (bookmark manager with semantic search)

Save a link → extract text → summarize + tag → embed → find it later by meaning.
Build the **bare-minimum** version below. Do not add anything from "Cut for now".

## Stack (minimum)
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind
- **API:** FastAPI + Pydantic + SQLAlchemy + Alembic
- **DB:** PostgreSQL 16 + pgvector (users, bookmarks, tags, chunks, jobs — one DB)
- **Worker:** one Python process polling the `jobs` table (`SELECT ... FOR UPDATE SKIP LOCKED`). No Redis, no Celery.
- **AI:** one LLM (summary + tags, JSON output) and one embedding model, behind a small `ai/provider.py` interface so the provider is swappable.
- **Extraction:** `httpx` + `trafilatura`
- **Run:** Docker Compose with 4 services: `web`, `api`, `worker`, `db`

## Cut for now (out of scope)
Redis/Celery, separate vector DB, browser extension, AI chat/RAG, knowledge graph, collections join table (use nullable `collection_id`), shared collections, PDF/YouTube, mobile, OpenTelemetry, Playwright (use pytest + one smoke script).

## Repo layout
```
/web                  Next.js app
/api
  app/main.py
  app/routers/        auth.py bookmarks.py search.py tags.py collections.py
  app/models.py       SQLAlchemy models
  app/security/       ssrf.py  urls.py  auth.py
  app/ai/             provider.py  prompts.py
  app/worker.py       job loop
  app/pipeline.py     extract -> enrich -> embed
  app/search.py       hybrid search
  alembic/  tests/
docker-compose.yml  .env.example  CLAUDE.md
```

## Data model
- `users(id uuid, email unique, password_hash, display_name, created_at)`
- `collections(id, user_id, name, created_at)`
- `bookmarks(id, user_id, url, canonical_url, title, description, content_text, summary, key_takeaways jsonb, notes, status enum[pending,processing,completed,failed], error_message, content_hash, collection_id null, archived bool, created_at, updated_at)` — unique `(user_id, canonical_url)`
- `tags(id, user_id, name)` unique `(user_id, lower(name))`; `bookmark_tags(bookmark_id, tag_id, source enum[ai,user])`
- `content_chunks(id, bookmark_id, user_id, chunk_index, chunk_text, tsv tsvector, embedding vector(N), model_name)` — denormalize `user_id` so search filters on it directly
- `jobs(id, bookmark_id, user_id, status enum[queued,running,completed,failed], stage, attempt_count, error_message, run_after, created_at)`

Index after measuring: HNSW on `embedding`, GIN on `tsv`, btree on `(user_id, created_at)`.

## API (`/api/v1`)
`POST /auth/register|login` · `GET|POST /bookmarks` · `GET|PATCH|DELETE /bookmarks/{id}` · `POST /bookmarks/{id}/process` · `GET /bookmarks/{id}/status` · `GET /search?q=` · CRUD `/tags`, `/collections`.
Never return embeddings. Return 404 (not 403) for other users' resources.

## Pipeline (worker)
1. `POST /bookmarks`: validate URL, normalize, dedupe, insert `pending` bookmark + `queued` job, return immediately.
2. Worker claims job → `processing`.
3. **Extract:** SSRF-safe fetch → trafilatura → store text + `content_hash`. Skip re-processing if hash unchanged.
4. **Enrich:** one LLM call → JSON `{summary, takeaways[3-5], tags[3-8]}`. Pass existing user tags so the model reuses them. Never overwrite `source='user'` tags.
5. **Embed:** chunk (~500 tokens, ~50 overlap), embed, store with `model_name`. Replace old chunks in the same transaction.
6. Mark `completed`. On error: sanitized `error_message`, retry up to 3 times with exponential backoff (`run_after`), then `failed`. Every stage must be idempotent.

## Search (one SQL query)
Query embedding → top 30 chunks by cosine (pgvector) + top 30 by `ts_rank` (Postgres FTS) → merge with **Reciprocal Rank Fusion** (`1/(60+rank)`) → group by bookmark, best chunk as excerpt → apply tag/collection/date filters. **Always** `WHERE user_id = :current_user`.

## Security rules (non-negotiable)
- **SSRF:** http/https only; resolve DNS and reject loopback, private, link-local, reserved, and cloud-metadata IPs (169.254.169.254); connect to the validated IP; re-validate every redirect (max 3); 10s timeout; 2 MB cap; allow `text/html` only; no JS execution.
- **Authorization:** every query filters by `user_id`. Add cross-user tests for bookmarks, tags, collections, jobs, search.
- **Prompt injection:** page text goes in a delimited data block; system prompt says it is untrusted data; LLM has no tools; output is validated against a JSON schema.
- **Sanitize** any HTML before rendering; render AI output as plain text/markdown.
- Secrets only in env vars. Per-user rate limit on `POST /bookmarks` and `/search`. Keep page content out of logs.
- Account deletion removes bookmarks, chunks, embeddings, jobs.

## Logging per job
Stage, duration, model name, input/output tokens, error. Store on `jobs` or a small `ai_usage` table.

## Tests (must pass before moving on)
- Unit: URL normalization, dedupe, tag normalization, chunking.
- Security: SSRF (localhost, 10.x, 169.254.x, redirect to private, DNS rebinding), cross-user access, prompt-injection fixture page.
- Worker: retry, timeout, duplicate job, partial failure.
- Search: 20–30 labeled queries → report Recall@5 and MRR for keyword-only vs semantic vs hybrid.
- Smoke: save → process → search → open → delete.

## Build order (do one phase at a time, commit after each)
1. **Foundation:** Compose, DB, migrations, auth, ownership helper, dashboard shell.
2. **Save + extract:** CRUD, URL validation, SSRF module + tests, job table, worker loop, extraction, statuses.
3. **Enrich:** summary/takeaways/tags, retries, token logging, tag edit UI.
4. **Search:** chunking, embeddings, hybrid query, eval script.
5. **UI:** dashboard, detail page, filters, collections, failed-item retry.
6. **Harden + ship:** security tests, README, `.env.example`, seed demo data, deploy.

## Conventions
Type hints everywhere, Pydantic schemas for all I/O, no business logic in routers, small functions, tests alongside features. Ask before adding a dependency not listed here.

## Definition of done
Register/login; save/edit/archive/delete; async extraction; editable AI summary + tags; hybrid search by meaning; collections + filters; no cross-user access; failures visible and retryable; SSRF + injection tests pass; eval numbers recorded; deployed with README.
