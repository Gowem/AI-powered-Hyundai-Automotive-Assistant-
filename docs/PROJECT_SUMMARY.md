# Hyundai Assistant: Project Summary

A complete account of what was built, how it was built, which technologies were used, and how well
it performs, from the first scaffold to the deployed, evaluated application.

| | |
|---|---|
| **Live application** | https://hyundai-assistant.onrender.com |
| **Backend API** | https://hyundai-assistant-api.onrender.com/api/health (interactive docs at `/api/docs`) |
| **Demo login** | `demo@hyundai-assistant.app` / `Demo1234` (or register a new account) |
| **Demo video** | [`docs/demo/hyundai-assistant-demo.mp4`](demo/hyundai-assistant-demo.mp4), 4.5 min, recorded on the live site |
| **Source code** | `main` branch of this repository |

---

## 1. What the project is

**Hyundai Assistant** is a web application that acts as an AI automotive consultant for Hyundai cars.
Users sign in, upload official Hyundai PDF brochures, and then chat with an assistant that answers
**only from those brochures**, citing the exact brochure page for every fact.

It handles four kinds of question:

1. **Feature lists**: "List all features of the Hyundai Alcazar"
2. **Model comparisons**: "Compare the Alcazar and Creta on engine, safety, comfort and technology"
3. **Variant comparisons**: "Compare Alcazar Prestige vs Platinum", "Compare all Alcazar variants"
4. **Recommendations**: "I need a city car for a family of 4 with good mileage: i20 or Aura?"

The design principle throughout is **"a wrong answer is worse than no answer."** The assistant never
uses outside knowledge, never invents a number or price, and says *"Not specified in the uploaded
brochures"* when the information isn't there. If a vehicle has no uploaded brochure, it says so
instead of describing it from memory.

### Who it is for

- **Customers** comparing Hyundai models and trims before visiting a showroom.
- **Reviewers and evaluators**, who can log in with the demo account and immediately use eight
  indexed official brochures.

---

## 2. Features delivered

### 2.1 Authentication (secure email and password)
- Registration and login with email and password; logout; "who am I" endpoint.
- Passwords hashed with **Argon2id** (the current OWASP-recommended algorithm).
- Session held in a **JWT inside an httpOnly, SameSite=Lax, Secure cookie**, so JavaScript can't
  read the token (protection against XSS token theft).
- Password policy enforced on both frontend and backend: at least 8 characters, one letter and one number.
- **Rate limiting**: 5 login or registration attempts per minute per IP (brute-force protection).
- **Generic error messages** and a dummy hash check for unknown emails, so attackers can't find
  out which emails are registered.
- Protected pages (`/chat`, `/documents`) redirect to the login page when signed out.
- Users can only ever see their own conversations (every query is filtered by user id, with a test).

### 2.2 Brochure (document) management
- **Drag-and-drop upload** of one or many PDFs with a per-file progress bar.
- PDFs upload **directly from the browser to private Supabase Storage** through a short-lived signed
  URL, so large brochures never pass through the web servers.
- After upload, the backend verifies the file is really a PDF (checks the `%PDF-` header), checks
  its size, and computes a SHA-256 hash to **reject duplicate uploads**.
- The **vehicle model is pre-filled from the filename** (e.g. `alcazar-brochure.pdf` → Alcazar) and
  detected from the text if left blank.
- A documents table (cards on mobile) shows **document name, vehicle model, upload date, pages,
  chunks and processing status** (Queued → Processing with live progress such as "Embedding 15/18"
  → Ready, or Failed with the reason).
- Actions: **View PDF**, **Rename / change model**, **Reprocess**, **Delete** (with confirmation).
  Only the uploader can modify or delete; everyone signed in can read and chat over all brochures
  (a shared knowledge base).
- Search by name, filter by model and by status; the page refreshes itself every 3 seconds while
  anything is processing.

### 2.3 Automatic indexing (ingestion pipeline)
Every uploaded brochure is processed in the background:

1. **Download** from storage to a temporary file.
2. **Parse** each page with PyMuPDF. Normal pages give their text; pages containing ruled spec
   tables are **rebuilt row by row from word positions**, so a label like *"Max. power"* stays next
   to its values (*"84.4 kW (115 PS) | 85 kW (116 PS) | 117.5 kW (160 PS)"*).
3. **Split side-by-side tables**: some brochures print several tables next to each other on one
   wide page. These are separated using their *"Variant"* / *"Items"* header cells.
4. **OCR fallback**: image-only pages (e.g. covers) are transcribed by Gemini's vision model.
5. **Clean**: remove headers and footers repeated on most pages, page numbers and boilerplate, while
   **keeping disclaimers that qualify specs** (e.g. "ARAI certified").
6. **Tag** each block with a section (Specifications, Safety, Comfort, Technology, Exterior,
   Interior, Dimensions, Variants, Colours) and the variant names it mentions.
7. **Chunk** into ~500-token pieces with 80-token overlap, **never crossing a page** (so page
   citations stay exact). Tables are never split mid-row; long tables repeat their header in every
   piece. Every chunk starts with a context header such as
   `[Vehicle: Alcazar | Document: Hyundai Alcazar Brochure | Page 7 | Section: Specifications]`.
8. **Embed** each chunk with Gemini embeddings (768 dimensions), in batches with retries.
9. **Store** all chunks in one database transaction and mark the document Ready.

If the server restarts mid-processing, interrupted documents are re-queued automatically at startup.

### 2.4 The AI consultant (chat)
- **Streaming answers**: text appears live, with a progress indicator ("Understanding your question…
  → Searching brochures… → Writing answer…") and a Stop button.
- **Markdown answers** with headings, bullet lists and **comparison tables** (striped rows, sticky
  first column, horizontal scrolling on phones).
- **Inline citations**: every `[n]` becomes a small clickable badge that highlights its source.
- **Source chips** under each answer ("Hyundai Alcazar Brochure · p.7"). Hovering shows a snippet;
  clicking opens the actual PDF **at that page** in a new tab.
- **Conversation history** in a sidebar, with rename and delete; follow-up questions understand
  context ("What about its safety features?" resolves to the car discussed before).
- Copy-answer and **Regenerate** buttons; suggested prompt cards on an empty chat; a banner when no
  brochures are indexed yet.
- Out-of-scope questions ("Who won the cricket match?") get a polite redirect, with no AI cost.

### 2.5 User interface
- Professional, responsive design: Hyundai-like deep navy (`#002C5F`), white cards, Inter font,
  generic car icon (no Hyundai logo, for trademark reasons), and the footer *"Unofficial demo.
  Answers are generated from uploaded brochures."*
- **Light and dark mode**.
- Desktop sidebar (≥1024 px), slide-out drawer on mobile; checked at 375 px, 768 px and 1440 px with
  no horizontal overflow.
- Accessible: labelled inputs, visible focus rings, Enter to send and Shift+Enter for a new line,
  `aria-live` for streaming text.

---

## 3. Technology stack (everything used)

### 3.1 Frontend
| Technology | Version | Used for |
|---|---|---|
| **Next.js** (App Router) | 15.5.29 | React framework, server rendering, routing, `/api` proxy |
| **React** | 19.1 | UI |
| **TypeScript** (strict mode) | 5 | Type safety across the frontend |
| **Tailwind CSS** | 4 | Styling, light/dark theme variables |
| **shadcn/ui** pattern + **Radix UI** (`radix-ui`) | 1.8.1 | Accessible dialogs, menus, selects, tooltips, drawers, progress bars |
| **TanStack Query** | 5.108.4 | Server data fetching, caching, 3-second polling while processing |
| **react-markdown** + **remark-gfm** | 10.1.0 / 4.0.1 | Rendering answers and GitHub-style tables |
| **lucide-react** | 1.79.0 | Icons |
| **sonner** | 2.0.8 | Toast notifications |
| **next-themes** | 0.4.6 | Light / dark / system theme |
| **zod** | 4.6.7 | Form validation on login and registration |
| **@supabase/supabase-js** | 2.119.2 | Signed direct-to-storage uploads (fallback path) |
| **@fontsource-variable/inter** | – | Self-hosted Inter font (builds don't depend on Google Fonts) |

### 3.2 Backend
| Technology | Version | Used for |
|---|---|---|
| **Python** | 3.12 | Language |
| **FastAPI** + **Uvicorn** | 0.165.0 / 0.54.0 | REST API and Server-Sent Events streaming |
| **SQLAlchemy 2 (async)** + **asyncpg** | 2.0.58 / 0.32.0 | Database access |
| **Alembic** | 1.20.1 | Database migrations (run automatically on every deploy) |
| **Pydantic** + **pydantic-settings** | 2.14.4 / 2.16.3 | Request/response models, configuration from environment |
| **pgvector** (Python) | 0.5.1 | Vector column type |
| **PyMuPDF** | 2.1 | PDF text, table detection, page rendering for OCR |
| **google-genai** | 3.6.1 | Gemini embeddings, chat, streaming and vision |
| **openai** | 3.58.0 | Alternative LLM provider (switchable by one setting) |
| **pwdlib[argon2]** | 0.4.2 | Argon2id password hashing |
| **PyJWT** | 2.15.1 | Session tokens |
| **slowapi** | 0.1.10 | Rate limiting |
| **tenacity** | 9.1.4 | Retries with exponential backoff |
| **httpx** | 0.28.1 | Supabase Storage API client |
| **pytest**, **pytest-asyncio**, **ruff** | 9.2 / 1.5 / 0.17.6 | Tests, linting and formatting |

### 3.3 AI models (Google Gemini)
| Purpose | Model |
|---|---|
| Embeddings (search vectors) | `gemini-embedding-001`, reduced to **768 dimensions** |
| Answer generation | `gemini-3.6-flash` first, then a fallback chain: `gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.5-flash`, `gemini-3.1-flash-lite` |
| Image-only page OCR | The same Gemini chain (vision input) |

Model names were verified against the live Gemini API: at startup the backend lists the models
available to the key and logs an error if the configured one is missing.

### 3.4 Data and infrastructure
| Service | Used for |
|---|---|
| **Supabase PostgreSQL 17 + pgvector 0.8.2** | Users, documents, chunks with vectors, conversations, messages |
| **Supabase Storage** (private bucket `brochures`, 50 MB limit, PDF only) | Brochure files |
| **Render** (2 web services, Singapore region) | Backend (`hyundai-assistant-api`) and frontend (`hyundai-assistant`), auto-deploying from `main` |
| **GitHub Actions** | CI on every push: backend lint, format check, migration and tests (against a real pgvector database); frontend lint, type check and production build |
| **Docker Compose** (`pgvector/pgvector:pg16`) | Local development database |

---

## 4. Architecture

```
Browser (Next.js frontend on Render)
  │  same-origin requests to /api/*  ──(Next.js rewrite)──▶  FastAPI backend on Render
  │  httpOnly auth cookie stays first-party because of the rewrite
  │
  │  PDF bytes go DIRECTLY to Supabase Storage via a short-lived signed upload URL
  ▼
FastAPI backend
  ├── /api/auth/*        register, login, logout, me
  ├── /api/documents/*   upload-url, confirm, list, get, view-url, rename, reprocess, delete
  ├── /api/chat/*        conversations CRUD, send message (SSE stream or JSON)
  ├── ingestion worker   (background tasks; one document at a time; re-queued after restarts)
  └── RAG agent          plan → hybrid retrieval → grounded generation → citations
        │
        ▼
Supabase: Postgres + pgvector (HNSW vector index + full-text GIN index) · private Storage bucket
Google Gemini API: embeddings, chat, streaming, vision OCR
```

Two decisions shape this design:

1. **The frontend proxies `/api/*` to the backend.** The browser only ever talks to one domain, so
   the auth cookie is first-party: no CORS problems and no third-party-cookie blocking in Safari or Chrome.
2. **PDFs upload straight to Supabase Storage.** Brochures are 1.5–40 MB, so this avoids web-server
   body-size limits and timeouts.

### Database schema
| Table | Contents |
|---|---|
| `users` | email (unique), Argon2id hash, name, created/last-login times |
| `documents` | owner, filename, display name, vehicle model, model year, storage path, size, SHA-256, pages, chunk count, status and status detail, timestamps |
| `chunks` | document, vehicle model, page number, section, variant names, content type (`text`/`table`/`ocr`), content, token count, **768-d embedding** (HNSW cosine index), **generated full-text vector** (GIN index) |
| `conversations` | user, title, timestamps |
| `messages` | conversation, role, Markdown content, cited sources (JSON), intent |

---

## 5. How the RAG (Retrieval-Augmented Generation) works

For every user message:

1. **Understand the question.** A query planner works out the **intent** (feature list, model
   comparison, variant comparison, recommendation, spec lookup, general, out-of-scope), the
   **vehicles** (with fuzzy names: "alcazr", "Hyundai Alcazar"), **variants**, **aspects** (engine,
   safety, comfort…), the customer's **requirements** (seats, fuel, transmission, city/highway), and
   search **sub-queries**. Follow-ups are resolved from the last 6 messages.
   The planner can be an LLM call (JSON output) or a rule-based heuristic. Production uses the
   heuristic to halve AI calls; it produced the correct plan for all ten evaluation questions.
2. **Retrieve evidence (hybrid search).** For each sub-query, two searches run:
   - **Vector search** (meaning-based) with pgvector cosine similarity, top 20;
   - **Keyword search** with PostgreSQL full-text search, top 20.

   They are merged with **Reciprocal Rank Fusion** and boosted when the section or variant matches.
3. **Balance per vehicle.** For comparisons each vehicle is searched **separately** with its own
   quota (6 chunks each for two vehicles, 5 for three or more), so one long brochure can't crowd out
   the other. Spec tables are always included. Total context is capped at ~12,000 tokens.
4. **Handle missing vehicles.** If a requested car has no ready brochure (e.g. Tucson), it isn't
   searched, and the answer states *"No Tucson brochure has been uploaded yet."*
5. **Generate a grounded answer.** Gemini receives numbered sources and a strict system prompt:
   use only the sources, cite every fact as `[n]`, write "Not specified" for gaps, never guess, never
   quote outside prices, keep variant-specific facts attached to the variant. An intent-specific
   template shapes the answer (e.g. comparison tables per aspect, then "Key differences" and "Which
   one suits whom").
6. **Post-process citations.** Invalid citation numbers are removed and only the **cited** sources
   are saved and shown, each with document, page and snippet.

**Short-circuits** that skip the AI entirely: out-of-scope questions, questions where nothing
relevant was found (*"I couldn't find anything about this in the uploaded brochures"*), and questions
only about cars with no brochure.

---

## 6. How it was built, from beginning to end

The project followed the 9-phase build plan, with each phase tested and committed before the next.

### Phase 1–2: scaffold, database and authentication
- Created the monorepo (`backend/`, `frontend/`, `docs/`), `.gitignore`, `.env.example` files and
  `docker-compose.yml`.
- Wrote the SQLAlchemy models and a hand-written Alembic migration that enables `vector`, creates
  all tables, the HNSW vector index and the full-text GIN index.
- Built the auth endpoints, Argon2id hashing, JWT cookie handling, rate limiting and a
  `create_user.py` script for the demo account.
- **Checked by** 10 authentication tests (register/login/me/logout, wrong password, duplicate email,
  weak password, protected endpoints, tampered token, disabled registration, user isolation).

### Phase 3–4: documents, storage and ingestion
- Implemented the storage layer with two backends: **Supabase** (signed URLs) and **local disk**, so
  anyone can run the project without a Supabase account.
- Built the document endpoints, PDF validation, duplicate detection and owner-only rules.
- Built the provider interface with **Gemini**, **OpenAI** and a deterministic **offline "fake"
  provider** (used by tests and for running with no API key).
- Built the parser, cleaner, section/variant tagging and table-aware chunker.
- **Checked by** 11 parser/chunker and document tests using small synthetic PDFs generated inside
  the tests (no real brochure data in tests).

### Phase 5: retrieval, agent and chat API
- Built the query planner, hybrid retriever with per-vehicle balancing, prompts, citations and the
  agent, plus the chat API with **SSE streaming** and a **non-streaming JSON fallback**.
- **Checked by** retrieval-balancing and grounding tests: no context means no AI call,
  missing-vehicle notice, citation parsing, follow-up resolution, intent detection, SSE event order.

### Phase 6: frontend
- Next.js app with login/register, the app shell (sidebar, conversation list, theme toggle, user
  menu, mobile drawer), the streaming chat, and the documents page.
- The shadcn/ui component registry was blocked from the build environment, so the components were
  written by hand in shadcn's format on top of Radix UI (documented in `DECISIONS.md`).
- **Checked by** a scripted browser (Playwright) run of the full flow: registration validation,
  login redirects, uploading three PDFs including a 22 MB file, duplicate rejection, streaming chat
  with citations, opening the PDF from a source chip, logout, and layouts at 375/768/1440 px, with
  zero console errors.

### Phase 7: hardening, CI and documentation
- GitHub Actions CI, structured JSON logging with request ids, global error handlers, input limits
  (messages ≤ 2,000 characters), cleanup of abandoned uploads.
- Docs: `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `DEMO_SCRIPT.md`, `EVALUATION.md`.

### Phase 8: deployment
Done through the Supabase and Render APIs:
1. **Supabase**: enabled pgvector, created the private `brochures` bucket (50 MB, PDF only), and a
   dedicated `hyundai_app` database role, so the account owner's password was never touched.
2. **Render backend**: created the service, set environment variables, ran migrations on start.
3. **Frontend**: the provided Vercel token could read but not create projects, so the frontend was
   deployed as a **second Render service**. The architecture is unchanged (still a same-origin proxy).
4. Created the demo account, then downloaded and uploaded the official brochures for **Alcazar,
   Creta, i20, Aura, Venue, Verna and Exter** (plus Grand i10 Nios, uploaded live in the video).

### Problems found in production and how they were fixed
| Problem | Cause | Fix |
|---|---|---|
| Backend crashed while indexing | PyMuPDF's layout-based table detection used ~575 MB, over the 512 MB free-tier limit | Line-based detection only on pages with ruled lines, cache release between pages, one document at a time. **Peak memory 575 MB → 78 MB**, parse time per brochure **74–126 s → 0.5–1.6 s** |
| Spec-table rows lost their labels | Brochure labels sit outside the ruled cells | Rows rebuilt from word positions; side-by-side tables split into panels; overprinted duplicate text removed |
| Every chat failed with 404 | The model alias `gemini-flash-latest` doesn't exist on the API version the SDK uses | Startup check that lists real models; switched to verified names |
| Frequent 429/503 errors | Free-tier Gemini key: ~5 requests/minute and 20/day per model, plus "high demand" outages | Six-model fallback chain, instant switch on quota errors, heuristic planner (half the calls) |
| Answers cut off mid-way | Gemini returned 503 in the middle of a stream | The agent discards the partial text and regenerates the full answer with fallback; the browser receives a `reset` event |
| Requests hung for minutes | Overloaded endpoints sometimes hung instead of failing | 40 s per-call timeout and a 90 s total budget, then a clear "service busy, try again in a minute" message |
| Chat page crash (`ChunkLoadError`) | Route-group folders put `(app)` in JavaScript file URLs; a proxy that percent-encodes parentheses got a 404 | Removed the route-group folders; same URLs, no parentheses in asset paths |
| Table cell drawn over the message box | Sticky table column had a higher stacking order | Message box given a higher z-index |

### Phase 9: evaluation, video and handover
- Ran the 10-question evaluation against production and hand-checked every number against the
  cited brochure pages (section 7).
- Recorded the demo video with a scripted browser on the live site, with on-screen captions, a
  mobile segment and an architecture card. Encoded to 1080p MP4.
- Merged everything to `main`; switched both Render services to auto-deploy from `main`.

---

## 7. How well it performs

### 7.1 Answer quality (production evaluation, 10 questions)
| # | Question | Result |
|---|---|---|
| 1 | List all features of the Hyundai Alcazar | ✅ Grouped, cited feature list; engine and dimension figures match the brochure |
| 2 | Compare Alcazar and Creta across 5 aspects | ✅ Cited tables for both cars (passed on retry after a Gemini 503) |
| 3a | Compare all Alcazar variants | ⚠️ Partial: misreads the dense engine/trim grid (e.g. gives Prestige a diesel option); other rows correct |
| 3b | Compare Prestige vs Platinum | ⚠️ Partial: same engine-grid misreading; feature rows correct |
| 4 | i20 or Aura for a city family of 4 | ✅ Notes that neither brochure lists mileage, so mileage can't decide it; highlights Aura's CNG option; asks follow-ups |
| 5 | Boot space of the Creta | ✅ "Not specified" (correct: the brochure has no boot-space figure) |
| 6 | On-road price of the Alcazar in Bangalore | ✅ Says brochures don't list prices; suggests a dealer |
| 7 | Does the Aura have ADAS? | ✅ Not specified for the Aura (it appears only on a cross-model promo page, which is cited) |
| 8 | Compare Alcazar with Tucson | ✅ "No Tucson brochure has been uploaded yet" |
| 9 | Follow-up: "What about its safety features?" | ✅ Resolved to Alcazar; full cited safety list |
| 10 | Who won the cricket match? | ✅ Polite redirect; no AI call |

**8 pass, 2 partial, 0 fail.** No invented specs or prices; every spec cell is cited; tables render.
Full answers: [`docs/evaluation/run-2026-11-24-production.md`](evaluation/run-2026-11-24-production.md).

### 7.2 Speed and resources
| Measure | Result |
|---|---|
| Brochure parsing (7 official brochures, 8–21 pages each) | 0.5–1.6 s per brochure, 78 MB peak memory |
| Indexing a brochure end to end in production (download, parse, embed, store) | about 20–40 s; 13–23 chunks per brochure |
| Simple answers (spec lookups, honesty cases) | 6–18 s |
| Large answers (feature lists, comparisons) | 10–50 s, dominated by free-tier Gemini queuing |
| Out-of-scope answers | ~3 s (no AI call) |
| Backend cold start (Render free tier, after 15 min idle) | ~50 s for the first request |

### 7.3 Test and code quality
| Check | Result |
|---|---|
| Backend automated tests | **39 passing**: auth 10, parser/chunker 6, documents 5, retriever 3, agent grounding 9, Gemini fallback 6 |
| Lint / format | `ruff check` and `ruff format` clean |
| Frontend | ESLint clean, TypeScript strict with no errors, production build succeeds |
| CI | GitHub Actions green on every recent push |
| End-to-end browser run | Full flow passes with zero console errors |
| Code size | ~4,000 lines of backend Python, ~840 lines of tests, ~3,100 lines of frontend TypeScript, 20 commits |

---

## 8. Security summary
- Argon2id password hashing; generic login errors; dummy hash check against user enumeration.
- httpOnly, SameSite=Lax, Secure session cookie; JWT with expiry; rate-limited login and registration.
- Pydantic validation on every input; message length limit; PDF magic-byte check and size limits.
- Private storage bucket; 10-minute signed links for viewing PDFs; service-role key only on the server.
- Every conversation query scoped to the signed-in user (tested).
- No secrets in git (`.env` files ignored; `.env.example` templates provided); brochures not committed.
- A dedicated least-privilege database role for the app.

---

## 9. Known limitations and next steps
1. **Free-tier Gemini key.** It is the main source of latency and occasional "busy" messages.
   Enabling billing on the key (Flash models cost very little at this volume) would make answers
   take a few seconds. Then set `LLM_QUERY_PLANNER=true` and use a single chat model.
2. **Dense variant matrices.** Row labels that span several rows of a trim-plan grid are still
   ambiguous to the model (evaluation items 3a/3b). Next step: copy a spanning label onto each row it
   covers before chunking.
3. **Cold starts** on Render's free tier (~50 s). An uptime monitor pinging `/api/health` every
   10 minutes, or the Starter plan, removes this.
4. **Brochures rarely contain prices or mileage**, so those questions are answered as "not
   specified" by design.
5. **Background processing runs inside the web process.** A restart re-queues documents safely, but
   a separate worker would scale better.

---

## 10. Repository map

```
backend/                FastAPI app
  app/main.py           app, middleware, error handlers, startup recovery + model check
  app/routers/          auth.py, documents.py, chat.py
  app/ingestion/        pdf_parser.py, chunker.py, metadata.py, pipeline.py
  app/rag/              intent.py, retriever.py, prompts.py, agent.py, citations.py
  app/llm/              base.py, gemini.py (fallback chain), openai.py, fake.py, retry.py
  app/vehicles.py       Hyundai model names and aliases only (no specs)
  alembic/              database migration
  scripts/              create_user.py, eval_rag.py
  tests/                39 tests with synthetic PDFs
frontend/               Next.js app
  app/                  login, register, chat, chat/[id], documents
  components/           chat UI, documents UI, layout (sidebar, app shell), ui primitives
  lib/                  api client, SSE reader, upload helper, types
docs/                   ARCHITECTURE, DECISIONS, EVALUATION, DEMO_SCRIPT, this summary,
                        demo video, screenshots, raw evaluation run
render.yaml             Render blueprint for both services
docker-compose.yml      local pgvector database
.github/workflows/ci.yml
```

---

*Unofficial project, not affiliated with Hyundai Motor Company or Hyundai Motor India. Brochure
contents belong to Hyundai Motor India Ltd. and are not included in this repository.*
