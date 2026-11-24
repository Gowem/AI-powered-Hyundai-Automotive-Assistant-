"""Run the evaluation question set against a running backend and write a Markdown report.

Usage:
  python scripts/eval_rag.py --base-url http://localhost:8000 --email demo@hyundai-assistant.app \
      --password Demo1234 --out ../docs/eval_run.md

Check every number in the report by hand against the cited brochure page, then record the
verdicts in docs/EVALUATION.md.
"""

import argparse
import sys
import time
from datetime import UTC, datetime

import httpx

QUESTIONS: list[tuple[str, str, bool]] = [
    # (id, question, follow-up of previous conversation?)
    ("Q1", "List all features of the Hyundai Alcazar.", False),
    ("Q9", "What about its safety features?", True),
    ("Q2", "Compare Alcazar and Creta across engine, safety, comfort, technology and performance.", False),
    ("Q3a", "Compare all Alcazar variants.", False),
    ("Q3b", "Compare Alcazar Prestige vs Platinum.", False),
    ("Q4", "I drive in the city with a family of 4 and want good mileage: i20 or Aura?", False),
    ("Q5", "What is the boot space of the Creta?", False),
    ("Q6", "What is the on-road price of the Alcazar in Bangalore?", False),
    ("Q7", "Does the Aura have ADAS?", False),
    ("Q8", "Compare Alcazar with Tucson.", False),
    ("Q10", "Who won the cricket match?", False),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    out: list[str] = [
        f"# RAG evaluation run ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)",
        "",
        f"Backend: `{args.base_url}`",
        "",
    ]
    with httpx.Client(base_url=args.base_url, timeout=180) as c:
        r = c.post("/api/auth/login", json={"email": args.email, "password": args.password})
        r.raise_for_status()
        docs = c.get("/api/documents").json()
        out.append(
            "Ready brochures: "
            + ", ".join(f"{d['display_name']} ({d['vehicle_model']})" for d in docs["items"] if d["status"] == "ready")
            + "\n"
        )
        conv_id = None
        for qid, question, follow_up in QUESTIONS:
            if not follow_up or conv_id is None:
                conv_id = c.post("/api/chat/conversations", json={}).json()["id"]
            t0 = time.perf_counter()
            r = c.post(f"/api/chat/conversations/{conv_id}/messages?stream=false", json={"content": question})
            dt = time.perf_counter() - t0
            out.append(f"## {qid}: {question}\n")
            if r.status_code != 200:
                out.append(f"**HTTP {r.status_code}**: {r.text}\n")
                continue
            ans = r.json()
            out.append(f"_intent: `{ans['intent']}` · {dt:.1f}s · {len(ans['sources'])} cited sources_\n")
            out.append(ans["content"] + "\n")
            if ans["sources"]:
                out.append("**Sources**\n")
                out += [
                    f"- [{s['n']}] {s['document_name']}, p.{s['page']}: {s['snippet'][:120]}…" for s in ans["sources"]
                ]
                out.append("")
            print(f"{qid} done in {dt:.1f}s ({ans['intent']})", file=sys.stderr)
    text = "\n".join(out)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
