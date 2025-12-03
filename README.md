# COGS 187A – LLM Autograder (A3B)

LLM-powered pipeline for grading heuristic-evaluation assignments. It ingests PDF submissions, asks Gemini 2.5 Flash to analyze every page (text + screenshots), aggregates issue-level scores, and gives TAs a full reviewer console plus AI-to-AI prompt refinement.

---

## 🚀 TL;DR / Quick Start

```bash
# clone and enter
git clone https://github.com/ZiyaoZzz/cogs187a_A3b_autograder.git
cd cogs187a_A3b_autograder

# one-step bootstrap (installs deps, creates .env, starts both servers)
npm start
```

Notes:
- On first run, `start.sh` copies `env.template → .env`; open `.env` and paste your real `GEMINI_API_KEY`.
- The script auto-creates `.venv`, installs Python + npm deps, then runs backend + frontend in parallel.
- Stop everything with `Ctrl+C`.

For screenshots and troubleshooting, see **[QUICK_START.md](./QUICK_START.md)**.

---

## ✨ Updated Feature Highlights

| Area | What’s new |
| --- | --- |
| **Upload Page** | Manual load of prior submissions (no auto-navigation), cancel-able analysis, “running analyze” badges, AI Opportunities surfaced inline. |
| **Issue Reviewer** | Fresh view each rerun, manual “Load Analysis Results”, page role editor, metadata editor, rubric comments tied to reruns, prompt backup/restore, navigation guard when processes run. |
| **Final Detail Page** | Shows final grade + overrides with normalized schema (pageNumber/originalValue/overrideValue). |
| **Prompt Refinement** | Enhanced/Classic modes share safer fetch helpers, auto key feedback, improved expected-benefits display. |
| **Professor-friendly setup** | `env.template`, smarter `start.sh`, `npm run frontend/backend/dev:full`, and a Quick Start doc meant for non-technical reviewers. |

---

## 🔧 System Requirements

- macOS / Linux / Windows (WSL recommended)
- Node.js ≥ 18 (includes npm)
- Python ≥ 3.10
- Google Gemini API key (free tier ok)

---

## 🗺️ Key Pages & Workflow

1. **Upload (`/upload`)**  
   - Upload a PDF, review extracted pages, click “Analyze with Gemini”.  
   - Shows AI opportunities, duplicates detection, manual load of previous runs.

2. **Issue Reviewer (`/issue-reviewer`)**  
   - Pick a job → inspect issues, rubric comments, screenshots.  
   - Edit page roles/metadata, rerun grading, back up/restore prompt, generate TA-comment prompt analysis.

3. **Final Detail (`/final-detail?jobId=...`)**  
   - Summary of overrides, which pages changed, final grade + notes.

4. **Prompt Refinement (`/prompt-refinement`)**  
   - Enhanced multi-plan comparison or classic critique loop, ruthless audit, save to backend prompt.

---

## 🧱 Project Structure (simplified)

```
cogs187a_A3b_autograder/
├── backend/main.py              # FastAPI + Gemini logic
├── src/
│   ├── pages/
│   │   ├── UploadPage.tsx
│   │   ├── IssueReviewerPage.tsx
│   │   ├── FinalDetailPage.tsx
│   │   └── PromptRefinementPage.tsx
│   └── lib/
│       ├── types.ts             # TS types shared by frontend
│       └── api.ts               # shared fetch helpers
├── env.template                 # copy to .env, set GEMINI_API_KEY
├── start.sh / QUICK_START.md    # professor-friendly bootstrap
├── requirements.txt / package.json
└── output_static/               # generated artifacts (gitignored)
```

---

## 👨‍💻 Development Tips

| Command | Description |
| --- | --- |
| `npm run dev` | Frontend only (Vite dev server). |
| `npm run backend` | Backend only (uses `.venv` if present). |
| `npm run dev:full` | Front + back via `concurrently` (no dependency checks). |
| `npm run build` / `npm run preview` | Frontend production build / preview. |

Backend tips:
```bash
source .venv/bin/activate    # or .venv\Scripts\activate on Windows
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🔎 Troubleshooting (short list)

| Symptom | Fix |
| --- | --- |
| `GEMINI_API_KEY not configured` | Edit `.env`, set real key, restart `npm start`. |
| Ports 5173/8000 busy | Close other apps or run backend on `--port 8001`. |
| Missing deps | Delete `.venv` / `node_modules` and re-run `npm start`. |
| Need more help | See `QUICK_START.md` and `TECHNICAL_CHALLENGES.md`. |

---

## 📚 Related Docs

- [QUICK_START.md](./QUICK_START.md) – screenshot-heavy professor guide.
- [PROJECT_REPORT.md](./PROJECT_REPORT.md) – full architecture write-up.
- [TECHNICAL_CHALLENGES.md](./TECHNICAL_CHALLENGES.md) – deep dives + future work.
- [FEATURE_SUMMARY.md](./FEATURE_SUMMARY.md) – change log for user-visible features.

---

MIT-style educational license for UCSD COGS 187A coursework. For any questions, open an issue or reach out via the course Discord. Happy grading! 🎓🤖

