# COGS 187A Assignment 3B - LLM Autograder

An intelligent LLM-based autograder system for evaluating student heuristic evaluation assignments. The system uses Google Gemini AI for automated analysis, includes a Human-in-the-Loop (HITL) review pipeline for quality assurance, and features an AI-to-AI prompt refinement system for continuous improvement.

## 📋 Table of Contents

- [Features](#features)
- [System Requirements](#system-requirements)
- [Download & Installation](#download--installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Usage Guide](#usage-guide)
- [Project Structure](#project-structure)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

## ✨ Features

- **Automated PDF Analysis**: Extracts and analyzes student heuristic evaluation PDFs
- **AI-Powered Grading**: Uses Google Gemini 2.5 Flash for multimodal analysis (text + images)
- **Comprehensive Scoring**: Evaluates 8 core criteria + 2 bonus criteria
- **Human-in-the-Loop**: Reviewer Mode allows TAs to review, correct, and override AI decisions
- **Prompt Refinement**: AI-to-AI critique system for iterative prompt improvement
- **Reference Site Comparison**: Compare student work against expert analysis
- **Real-Time Updates**: Live progress tracking and immediate UI feedback

## 💻 System Requirements

- **Python**: 3.8 or higher
- **Node.js**: 16.x or higher (for frontend)
- **npm**: Comes with Node.js
- **Operating System**: macOS, Linux, or Windows (with WSL recommended)
- **API Key**: Google Gemini API key (free tier available)

## 📥 Download & Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/ZiyaoZzz/cogs187a_A3b_autograder.git
cd cogs187a_A3b_autograder
```

### Step 2: Install Dependencies

#### Option A: Automated Installation (Recommended)

Run the installation script which will set up everything automatically:

```bash
# Make install script executable (Linux/macOS)
chmod +x install.sh

# Run installation
./install.sh
```

This script will:
- ✅ Check Python version (requires 3.8+)
- ✅ Create Python virtual environment (`.venv`)
- ✅ Install all Python dependencies
- ✅ Run governance guards to verify project structure
- ✅ Verify critical files and imports

#### Option B: Manual Installation

**1. Set up Python virtual environment:**

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate
```

**2. Install Python dependencies:**

```bash
# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install requirements
pip install -r requirements.txt
```

**3. Install frontend dependencies:**

```bash
npm install
```

**4. Install Playwright browsers (for web scraping scripts):**

```bash
python3 -m playwright install chromium
```

### Step 3: Configure Environment Variables

Create a `.env` file in the project root directory:

```bash
# Create .env file
touch .env
```

Add your Google Gemini API key:

```env
GEMINI_API_KEY=your_api_key_here
```

**How to get a Gemini API key:**
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key and paste it into your `.env` file

> **Note**: The `.env` file is already in `.gitignore` and won't be committed to Git.

## 🚀 Running the Application

### Quick Start (One Command)

The easiest way to start both frontend and backend:

```bash
npm start
```

Or using the shell script:

```bash
./start.sh
```

This will:
- ✅ Check and install dependencies if needed
- ✅ Start frontend server at `http://localhost:5173`
- ✅ Start backend server at `http://localhost:8000`
- ✅ Display both servers' output in the terminal

Press `Ctrl+C` to stop both servers.

### Manual Start (Separate Terminals)

If you prefer to run servers separately:

**Terminal 1 - Frontend:**
```bash
npm run dev
```
Frontend will be available at `http://localhost:5173`

**Terminal 2 - Backend:**
```bash
# Activate virtual environment first
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Start backend server
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Backend API will be available at `http://localhost:8000`

### Verify Installation

1. Open your browser and go to `http://localhost:5173`
2. You should see the Home page
3. Check backend is running by visiting `http://localhost:8000/docs` (FastAPI docs)

## 📖 Usage Guide

### For Students/TAs: Grading a Submission

1. **Navigate to Upload Page**: Click "Grade PDF" or go to `/upload`
2. **Upload PDF**: Drag and drop or select a PDF file
3. **Review Extracted Pages**: System extracts all pages and displays them
4. **Start Analysis**: Click "Analyze with Gemini" button
5. **Monitor Progress**: Watch real-time progress as pages are analyzed
6. **View Results**: See final scores, breakdown, and detailed feedback

### For TAs: Issue Reviewer (Human-in-the-Loop)

1. **Navigate to Issue Reviewer**: Go to `/issue-reviewer`
2. **Select Submission**: Pick a job ID (auto-fills from your latest upload)
3. **Review Issues**: Inspect aggregated issues + contributing pages/screenshots
4. **Add Rubric Comments**: Use the dropdown to log rubric feedback that feeds the next grading run
5. **Adjust Scores**: Override issue-level rationale or component scores when needed
6. **Re-run Grading**: Click “Run AI Grading” to regenerate Stage-2 scores with your comments
7. **Generate Prompt Analysis**: Produce a summary/draft prompt before deciding to update `grading_prompt.txt`

### For Instructors: Prompt Refinement

1. **Navigate to Prompt Refinement**: Go to `/prompt-refinement`
2. **Load Current Prompt**: System loads prompt from `saved_prompt.txt`
3. **Set Iterations**: Choose number of critique rounds (1-4)
4. **Start Refinement**: Click "Start Refinement Process"
5. **Review Iterations**: See how prompt improves through AI-to-AI critique
6. **Save Final Prompt**: Save the best prompt to backend permanently

## 📁 Project Structure

```
cogs187a_A3b_autograder/
├── backend/
│   └── main.py                 # FastAPI backend (2,465 lines)
├── src/                        # Frontend React code
│   ├── pages/
│   │   ├── HomePage.tsx
│   │   ├── UploadPage.tsx      # Main grading interface
│   │   ├── IssueReviewerPage.tsx # HITL issue-level review UI
│   │   ├── PromptRefinementPage.tsx # AI-to-AI critique
│   │   └── JulianPagesPage.tsx  # Reference site viewer
│   └── lib/
│       └── types.ts            # TypeScript type definitions
├── scripts/                    # Utility scripts
│   ├── crawl_to_pdfs.py        # Web crawler for reference site
│   ├── capture_mobile_screenshots.py
│   └── [governance guards]    # Code protection scripts
├── rubrics/
│   └── a3_rubric.json          # Grading rubric
├── output_static/              # Generated output (gitignored)
│   ├── saved_prompt.txt        # Current grading prompt
│   ├── student_analyses/       # Analysis results
│   ├── overrides/              # TA corrections
│   ├── corrections/            # AI error reports
│   └── prompt_refinement/       # Refinement sessions
├── .env                        # Environment variables (create this)
├── install.sh                  # Automated installation script
├── start.sh                    # Start script for both servers
├── requirements.txt            # Python dependencies
├── package.json                # Node.js dependencies
└── v3_governance.yml           # Governance configuration
```

## 🛠️ Development

### Frontend Development

```bash
# Install dependencies
npm install

# Start development server with hot reload
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

**Frontend Stack:**
- React 18.3 with TypeScript
- Vite 6.0 (build tool)
- Tailwind CSS 3.4 (styling)
- React Router DOM 7.0 (routing)

### Backend Development

```bash
# Activate virtual environment
source .venv/bin/activate

# Install new dependencies
pip install package_name

# Update requirements.txt
pip freeze > requirements.txt

# Start backend with auto-reload
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Backend Stack:**
- FastAPI 0.104+ (web framework)
- Google Gemini 2.5 Flash (AI model)
- pdfplumber 0.10+ (PDF processing)
- Pillow 10.0+ (image processing)

### Running Utility Scripts

**Crawl Reference Site:**
```bash
cd scripts
python3 crawl_to_pdfs.py
```

This will:
1. Crawl `visitjulian.com` and collect URLs
2. Convert each page to PDF using Playwright
3. Save PDFs to `output_static/pdfs/`
4. Generate `output_static/pages_index.json` with metadata

## 🔒 Governance & CI

This project uses governance guards to protect core structure from accidental modifications.

### Local Governance Checks

Run the installation script to verify governance:

```bash
./install.sh
```

This runs all governance guards:
1. **Hollow Repo Guard** - Ensures critical directories aren't empty
2. **Program Integrity Guard** - Verifies critical code roots exist
3. **Syntax Guard** - Validates Python syntax
4. **Critical Import Guard** - Ensures critical imports work
5. **Canon Guard** - Verifies canonical files exist

### CI Integration

GitHub Actions automatically runs governance guards on:
- Every push to `main`, `master`, or `develop` branches
- Every pull request targeting these branches

**Workflows:**
- `.github/workflows/governance.yml` - Runs all governance guards
- `.github/workflows/full-install.yml` - Tests complete installation process

If any guard fails, the CI will fail and the PR cannot be merged.

See `v3_governance.yml` for configuration details.

## 🔧 Troubleshooting

### Common Issues

#### 1. "GEMINI_API_KEY not configured" Error

**Problem**: Backend can't find API key.

**Solution**:
```bash
# Create .env file in project root
echo "GEMINI_API_KEY=your_key_here" > .env

# Restart backend server
```

#### 2. CORS Errors

**Problem**: Frontend can't connect to backend.

**Solution**:
- Ensure backend is running on `http://localhost:8000`
- Check that frontend URL is in CORS whitelist (see `backend/main.py`)
- Clear browser cache and hard refresh (Ctrl+Shift+R)

#### 3. "Module not found" Errors

**Problem**: Python dependencies not installed.

**Solution**:
```bash
# Activate virtual environment
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

#### 4. Port Already in Use

**Problem**: Port 5173 or 8000 is already in use.

**Solution**:
```bash
# Find process using port
lsof -ti:8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill process or use different port
# For backend, edit start.sh or use:
python -m uvicorn main:app --reload --port 8001
```

#### 5. npm install Fails

**Problem**: npm install errors or timeouts.

**Solution**:
```bash
# Clear npm cache
npm cache clean --force

# Delete node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

#### 6. Virtual Environment Not Activating

**Problem**: `.venv/bin/activate` not found or permission denied.

**Solution**:
```bash
# Recreate virtual environment
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Getting Help

- Check the [TECHNICAL_CHALLENGES.md](./TECHNICAL_CHALLENGES.md) for detailed troubleshooting
- Review the [PROJECT_REPORT.md](./PROJECT_REPORT.md) for architecture details
- Check backend logs in terminal for detailed error messages
- Frontend errors appear in browser console (F12)

## 📚 Additional Documentation

- **[PROJECT_REPORT.md](./PROJECT_REPORT.md)** - Comprehensive project report with architecture, features, and statistics
- **[TECHNICAL_CHALLENGES.md](./TECHNICAL_CHALLENGES.md)** - Detailed technical challenges and solutions
- **[FEATURE_SUMMARY.md](./FEATURE_SUMMARY.md)** - Feature-by-feature documentation

## 📝 License

This project is for educational use in COGS 187A at UC San Diego.

## 👥 Credits

Developed for COGS 187A Assignment 3B - LLM Autograder System

---

**Need help?** Check the troubleshooting section above or review the technical documentation.

