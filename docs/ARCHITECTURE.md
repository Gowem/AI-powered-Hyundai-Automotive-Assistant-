# Architecture

## System overview

```
Browser (Next.js frontend)
  │  same-origin requests to /api/*   (Next.js rewrites /api/* → BACKEND_URL/api/*)
  │  ← httpOnly auth cookie is first-party because of the rewrite
  │
  │  PDF bytes go DIRECTLY to Supabase Storage via a short-lived signed upload URL
  ▼
FastAPI backend
  ├── /api/auth/*        register, login, logout, me
  ├── /api/documents/*   upload-url, confirm, list, get, view-url, rename, reprocess, delete
  ├── /api/chat/*        conversations CRUD, send message (SSE stream or ?stream=false JSON)
  ├── ingestion worker   (FastAPI BackgroundTasks, in-process; re-queued on startup)
  └── RAG agent          intent → query plan → hybrid retrieval → grounded generation → citations
        │
        ▼
Supabase: Postgres + pgvector (users, documents, chunks, conversations, messages)
          Storage bucket "brochures" (private)
Gemini API (embeddings: gemini-embedding-001 @ 768 dims, chat: flash model)  — OpenAI switchable
```

Why the two structural decisions matter:

1. **Next.js rewrites proxy `/api/*`** so the browser only ever talks to the frontend origin. The auth
   cookie is first-party (`SameSite=Lax`, `httpOnly`), no CORS in production, no third-party-cookie issues.
2. **PDFs upload directly from the browser to Supabase Storage** with a signed upload URL issued by the
   backend, avoiding proxy body limits and request timeouts for 10–40 MB brochures. The backend then
   downloads the object to verify `%PDF-` magic bytes, size and SHA-256 (duplicate detection).

For reviewers without Supabase, `STORAGE_BACKEND=local` stores files under `backend/uploads` and the
browser uploads through `PUT /api/documents/{id}/upload?token=…` (a signed, single-purpose JWT).

## Ingestion pipeline (`backend/app/ingestion`)

| Step | Module | Notes |
|---|---|---|
| Download | `storage.py` | streamed to a temp file |
| Parse | `pdf_parser.py` | PyMuPDF per page: body text blocks + `find_tables()` → Markdown tables (cell text read by bbox); text inside tables is not duplicated |
| OCR fallback | `pipeline.py` | pages with <40 chars rendered at 150 dpi and transcribed by the LLM's vision model (max 40 pages, 3 at a time), `content_type="ocr"` |
| Clean | `pdf_parser.clean_pages` | drops lines repeated on >50% of pages, page numbers, pure legal boilerplate; keeps qualifying disclaimers (ARAI, test conditions…) |
| Metadata | `metadata.py` | keyword-scored section (Specifications, Safety, …), variant tokens (names only), vehicle detection from first pages, model year |
| Chunk | `chunker.py` | ~500 tokens / 80 overlap, never across pages; tables are their own chunk, split by rows with the header repeated above 900 tokens; every chunk prefixed with `[Vehicle: … \| Document: … \| Page n \| Section: …]` |
| Embed | `llm/*` | batches of 50, `RETRIEVAL_DOCUMENT` task type, 768 dims, tenacity backoff on 429/5xx |
| Insert | `pipeline.py` | one transaction; `page_count`, `chunk_count`, `status=ready` |

Status (`queued → processing (+status_detail) → ready | failed`) is written at every stage; the
documents page polls every 3 s while anything is in flight.

## RAG pipeline (`backend/app/rag`)

```
user message + last 6 messages
   │
   ▼ (1) intent.py      one JSON-mode LLM call → QueryPlan (validated with Pydantic);
   │                    heuristic fallback; vehicle aliases normalised; follow-ups resolved from history;
   │                    default aspects for comparisons; sub-queries per vehicle × aspect
   ▼ (2) retriever.py   per vehicle: pgvector cosine top-20 + Postgres FTS top-20 per sub-query,
   │                    Reciprocal Rank Fusion (k=60), boosts for variant/section/table matches,
   │                    top-K per vehicle (6 for 2 vehicles, 5 for 3+), + top-3 spec tables per vehicle,
   │                    12k-token cap; vehicles without a ready brochure → MISSING_VEHICLES
   ▼ (3) citations.py   context ordered by vehicle → section → page and numbered [1..N]
   ▼ (4) agent.py       grounded, streamed generation with the strict system prompt + intent template
   ▼ (5) citations.py   invalid [n] stripped, only cited sources saved (top-3 fallback), SSE `sources` + `done`
```

Short circuits (no generation LLM call): out-of-scope questions, no retrieved chunks
(*"I couldn't find anything about this in the uploaded brochures…"*), and questions only about
vehicles with no uploaded brochure.

## Data model

`users` · `documents` (shared knowledge base, owner-only modify) · `chunks` (`vector(768)` with HNSW
cosine index, generated `tsvector` with GIN index) · `conversations` / `messages` (always filtered by
the current user's id).

## Security

Argon2id password hashing (pwdlib), HS256 JWT in an `httpOnly`, `SameSite=Lax`, `Secure` (prod)
cookie, slowapi rate limiting 5/min/IP on login and register (client IP from `X-Forwarded-For`),
dummy hash verification for unknown users, Pydantic validation on every input, user-scoped chat
queries, private storage bucket with 10-minute signed view URLs, service-role key on the backend only.
