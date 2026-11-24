# Demo video script (3–5 minutes)

Record at 1080p, upload as *Unlisted* (or public Drive link) and test the link in an incognito window.

1. **0:00 Intro** — "Hyundai Assistant is an AI automotive consultant that answers only from uploaded
   Hyundai brochures, with page-level citations. Next.js frontend, FastAPI backend, Postgres + pgvector,
   Gemini."
2. **0:20 Auth** — open `/chat` logged out → redirected to `/login`. Show validation, sign in with the
   demo account (or register).
3. **0:45 Documents** — Upload brochure → drag a PDF, model pre-filled from the filename, progress bar →
   status Queued → Processing ("Embedding 50/180") → Ready. Point out name, model, upload date, pages,
   chunks, status; View PDF.
4. **1:30 Feature list** — "List all features of the Hyundai Alcazar" → grouped headings with cited
   bullets → click a source chip → the PDF opens at that page.
5. **2:10 Comparison** — "Compare the Alcazar and Creta on engine, safety, comfort and technology" →
   Markdown comparison tables with a citation in every cell; click a `[n]` badge to highlight its source.
6. **2:40 Variants** — "Compare all Alcazar variants" → variant table.
7. **3:10 Recommendation** — "I need a city car for a family of 4 with good mileage: i20 or Aura?" →
   requirements, comparison against needs, recommendation, follow-up questions.
8. **3:40 Honesty** — "What is the on-road price of the Alcazar in Bangalore?" → brochures don't list
   prices; "Compare Alcazar with Tucson" → no Tucson brochure uploaded.
9. **4:00 Wrap-up** — architecture diagram (`docs/ARCHITECTURE.md`), README, mobile view, dark mode.
