# COGS 187 LLM Autograder

LLM-based heuristic evaluation autograder for COGS 187A Assignment 3a.

## Project Structure

```
your-project/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── postcss.config.cjs
├── tailwind.config.cjs
├── src/                  # fronted code
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   ├── pages/
│   │   ├── HomePage.tsx
│   │   ├── UploadPage.tsx
│   │   ├── ResultPage.tsx
│   │   └── PromptLabPage.tsx
│   └── lib/
│       └── types.ts
├── scripts/  
│   ├── crawl_to_pdfs.py
│   └── (maybe analyze_with_ai.py)
├── output_static/ 
│   ├── pdfs/
│   │   ├── 001_historic-julian.pdf
│   │   └── ...
│   └── pages_index.json
└── README.md
```

## Quick Start

### One-Command Start (Recommended)

Start both frontend and backend servers:

```bash
# Method 1: Using npm (Recommended)
npm start

# Method 2: Using shell script
./start.sh

# Method 3: Using Python script
python3 start.py
```

All methods will:
- Automatically check and install dependencies (if needed)
- Start both frontend (http://localhost:5173) and backend (http://localhost:8000) simultaneously
- Use Ctrl+C to stop both servers

### Manual Setup

If you need to start manually:

#### Frontend (React + Vite)

```bash
npm install
npm run dev
```

#### Backend (FastAPI)

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
cd backend
python -m uvicorn main:app --reload
```

### Python Scripts

```bash
# Install Python dependencies
pip install playwright beautifulsoup4 requests

# Install Playwright browsers
python3 -m playwright install chromium
```

## Usage

### Running the Crawler

```bash
cd scripts
python3 crawl_to_pdfs.py
```

This will:
1. Crawl `visitjulian.com` and collect URLs
2. Convert each page to PDF using Playwright
3. Save PDFs to `output_static/pdfs/`
4. Generate `output_static/pages_index.json` with metadata

## Development

- Frontend runs on `http://localhost:5173` (Vite default)
- Backend API integration: TODO

## Governance & CI

This project uses governance guards to protect core structure from accidental modifications.

### Local Setup

Run the installation script to set up the environment and verify governance:

```bash
./install.sh
```

This will:
- Check Python version (3.8+)
- Create/activate virtual environment
- Install all dependencies
- Run governance guards to verify project structure
- Verify critical files and imports

### CI Integration

GitHub Actions automatically runs governance guards on:
- Every push to `main`, `master`, or `develop` branches
- Every pull request targeting these branches

**Workflows:**
- `.github/workflows/governance.yml` - Runs all governance guards
- `.github/workflows/full-install.yml` - Tests complete installation process

If any guard fails, the CI will fail and the PR cannot be merged. This prevents bad code from entering the main branch.

### Governance Guards

The following guards protect the project structure:

1. **Hollow Repo Guard** - Ensures critical directories aren't empty
2. **Program Integrity Guard** - Verifies critical code roots exist
3. **Syntax Guard** - Validates Python syntax
4. **Critical Import Guard** - Ensures critical imports work
5. **Canon Guard** - Verifies canonical files exist

See `v3_governance.yml` for configuration details.

