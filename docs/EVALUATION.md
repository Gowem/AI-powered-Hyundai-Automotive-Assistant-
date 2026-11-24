# RAG evaluation

Run against **production** (`https://hyundai-assistant-api.onrender.com`) on 2026-11-24 with the
official Hyundai India brochures for **Alcazar, Creta, i20, Aura, Venue, Verna and Exter** indexed
(Grand i10 Nios was added later, live, in the demo video). Model: Gemini Flash family via the fallback
chain in `docs/DECISIONS.md` (#2, #15), embeddings `gemini-embedding-001` (768-d).

Command: `python scripts/eval_rag.py --base-url … --email demo@hyundai-assistant.app --password Demo1234`.
Full answers with sources: [`docs/evaluation/run-2026-11-24-production.md`](evaluation/run-2026-11-24-production.md).

Every number below was checked by hand against the cited brochure page.

| # | Question | Intent | Result | Verdict |
|---|---|---|---|---|
| 1 | List all features of the Hyundai Alcazar | feature_list | Grouped feature list (engine, safety, comfort, tech, exterior, interior) with 13 cited sources; engine figures (160 PS / 253 Nm turbo petrol, 116 PS / 250 Nm diesel, 1 482 / 1 493 cm³) and dimensions match p.7 | ✅ Pass |
| 2 | Compare Alcazar and Creta across engine, safety, comfort, technology, performance | model_comparison | Per-aspect comparison tables with citations for both vehicles (per-vehicle retrieval works). Creta 1.5 MPi 115 PS @ 6 300 and turbo 160 PS @ 5 500 match Creta p.17. Failed once with a Gemini 503 during the scripted run and answered on retry (52 s) | ✅ Pass (after retry) |
| 3a | Compare all Alcazar variants | variant_comparison | 7-variant tables (engine, safety, comfort, tech, dimensions), "Not specified" for fuel efficiency and boot space | ⚠️ Partial: the per-variant engine/transmission row misreads the brochure's dense "Engine & trim plan" grid (e.g. Prestige is listed with a diesel option the brochure does not show). Safety, ADAS, dimension and comfort rows are correct |
| 3b | Compare Alcazar Prestige vs Platinum | variant_comparison | Feature-by-feature table (ADAS, seats, cluster, Bose, digital key, ventilated seats) consistent with the key-features matrix | ⚠️ Partial: same engine/trim-plan misreading as 3a; feature rows correct |
| 4 | i20 or Aura for city driving, family of 4, good mileage | recommendation | Restates requirements, comparison table, notes that **neither brochure lists mileage figures** so mileage can't decide it, highlights Aura's CNG option, asks 2 follow-up questions | ✅ Pass |
| 5 | Boot space of the Creta | spec_lookup | "The uploaded brochures don't specify this." The Creta brochure indeed contains no boot-space figure (only "Luggage lamp") | ✅ Pass |
| 6 | On-road price of the Alcazar in Bangalore | spec_lookup | States brochures don't list prices, suggests a dealer | ✅ Pass |
| 7 | Does the Aura have ADAS? | spec_lookup | Not specified for the Aura; the only ADAS mention in the Aura brochure is a cross-model promo page (p.12), which it cites | ✅ Pass |
| 8 | Compare Alcazar with Tucson | model_comparison | "No Tucson brochure has been uploaded yet; upload it on the Documents page." | ✅ Pass |
| 9 | Follow-up "What about its safety features?" after Q1 | feature_list | Resolved to Alcazar; full cited safety list (Level 2 ADAS items, 6 airbags, ESC/VSM/HAC/HDC, TPMS, ISOFIX…) | ✅ Pass |
| 10 | Who won the cricket match? | out_of_scope | Polite redirect, no retrieval, no LLM call | ✅ Pass |

**Summary:** 8 pass, 2 partial, 0 invented specs or prices. Tables render; every spec cell is cited.

## Findings and follow-ups

- **Dense variant matrices.** Spec tables are rebuilt from word positions so labels stay with values
  (see `pdf_parser.layout_rows`), but trim-plan grids whose row labels are vertically centred across
  several rows (e.g. *"1.5l Turbo GDi petrol"* spanning the 6/7-seater rows) are still ambiguous for the
  model. Improvement: propagate a spanning row label to the rows it covers before chunking.
- **Free-tier Gemini quotas** (≈5 requests/min and 20/day per model, frequent 503s) are the main source
  of latency (6–50 s) and occasional "busy" errors. With a paid key, set `LLM_QUERY_PLANNER=true` and
  a single chat model; answers then take a few seconds.
- Answers ran with the heuristic query planner (`LLM_QUERY_PLANNER=false`); it produced the intended
  intent, vehicles, variants, aspects, follow-up resolution and requirements for all ten questions.
