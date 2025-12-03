from __future__ import annotations
from typing import List, Dict, Any, Optional
import os
import json
import base64
import io
import re
import time
from datetime import datetime
import pdfplumber
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# CORS configuration - allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://localhost:5174",  # Vite HMR port
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Configure Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    MODEL = genai.GenerativeModel("models/gemini-2.5-flash")
else:
    MODEL = None

# Load rubric (includes heuristics list)
RUBRIC_PATH = Path(__file__).parent.parent / "rubrics" / "a3_rubric.json"
RUBRIC_DATA = None
if RUBRIC_PATH.exists():
    with open(RUBRIC_PATH, "r", encoding="utf-8") as f:
        RUBRIC_DATA = json.load(f)

def render_page_image(page: pdfplumber.page.Page, resolution: int = 200) -> str:
    """
    Render a PDF page to PNG bytes and return as base64 data URL.
    Uses 200 DPI for high quality output.
    """
    pil_img = page.to_image(resolution=resolution).original
    buffer = io.BytesIO()
    pil_img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


@app.post("/api/extract-heuristic-pages")
async def extract_heuristic_pages(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    content = await file.read()
    pdf_bytes = io.BytesIO(content)

    try:
        heuristic_pages: List[Dict[str, Any]] = []
        with pdfplumber.open(pdf_bytes) as pdf:
            for idx, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                clean = text.strip()
                if not clean:
                    continue

                # Extract all pages (not just heuristic pages) for analysis
                # Truncate the snippet to 2000 characters for display
                snippet = clean[:2000]
                
                # Render image with high quality (default 200 DPI)
                image_base64 = None
                try:
                    image_base64 = render_page_image(page)  # Uses default 200 DPI for high quality
                except Exception:
                    image_base64 = None

                heuristic_pages.append(
                    {
                        "page_number": idx + 1,
                        "snippet": snippet,
                        "image_base64": image_base64,
                    }
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {e}")

    # Generate job ID
    job_id = f"job-{int(time.time() * 1000)}"
    
    # Save extraction result for Reviewer Mode
    extraction_data = {
        "jobId": job_id,
        "fileName": file.filename,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "pageCount": len(heuristic_pages),
        "pages": heuristic_pages,
    }
    
    extraction_file = ANALYSIS_OUTPUT_DIR.parent / f"{job_id}_extraction.json"
    with open(extraction_file, "w", encoding="utf-8") as f:
        json.dump(extraction_data, f, indent=2, ensure_ascii=False)

    return {
        "job_id": job_id,
        "page_count": len(heuristic_pages),
        "pages": heuristic_pages,
    }


def fix_incomplete_json(json_str: str) -> str:
    """Try to fix incomplete JSON by closing brackets and quotes."""
    if not json_str or not json_str.strip():
        return "{}"
    
    # Ensure it starts with {
    if not json_str.strip().startswith('{'):
        json_str = '{' + json_str.lstrip()
    
    # Count open/close braces and brackets
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    
    # Add missing closing brackets first (inner structures)
    json_str += ']' * (open_brackets - close_brackets)
    # Then add missing closing braces
    json_str += '}' * (open_braces - close_braces)
    
    # Fix unclosed strings
    json_str = json_str.rstrip()
    if json_str and not json_str[-1] in '}]':
        # Check if we're in the middle of a string
        quote_count = json_str.count('"')
        # Count escaped quotes
        escaped_quotes = json_str.count('\\"')
        # Actual unescaped quotes
        unescaped_quotes = quote_count - escaped_quotes
        
        if unescaped_quotes % 2 != 0:
            # Odd number of unescaped quotes, close the string
            json_str += '"'
        
        # If we're in the middle of a value, try to close it properly
        if not json_str.rstrip().endswith(('}', ']', '"')):
            # Remove trailing comma if present
            if json_str.rstrip().endswith(','):
                json_str = json_str.rstrip()[:-1]
            # Try to determine if we need to close a string or object
            if json_str.rstrip()[-1] not in '}]':
                # Might be in the middle of a string value, try to close it
                if '"' in json_str:
                    json_str += '"'
                json_str += '}'
    
    # Remove trailing commas before closing brackets/braces
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)
    
    return json_str


def extract_partial_json(json_str: str, page_number: int) -> Dict[str, Any]:
    """Extract what we can from a partial JSON string."""
    result = {
        "page_number": page_number,
        "skip_analysis": False,
        "page_type": "Unknown",
        "feedback": "",
        "error": "JSON was truncated, extracted partial data"
    }
    
    # Try to extract key fields using regex
    page_type_match = re.search(r'"page_type"\s*:\s*"([^"]*)"', json_str)
    if page_type_match:
        result["page_type"] = page_type_match.group(1)
    
    feedback_match = re.search(r'"feedback"\s*:\s*"([^"]*)"', json_str, re.DOTALL)
    if feedback_match:
        result["feedback"] = feedback_match.group(1)[:1000]  # Limit length
    
    skip_match = re.search(r'"skip_analysis"\s*:\s*(true|false)', json_str)
    if skip_match:
        result["skip_analysis"] = skip_match.group(1) == "true"
    
    # Try to extract score_breakdown fields individually
    score_breakdown = {}
    score_fields = [
        "coverage", "violation_quality", "screenshots", "severity_analysis",
        "structure_navigation", "professional_quality", "writing_quality", "group_integration"
    ]
    
    # Default max points for each field (defined once outside loop for efficiency)
    max_points = {
        "coverage": 15, "violation_quality": 20, "screenshots": 10,
        "severity_analysis": 10, "structure_navigation": 10,
        "professional_quality": 10, "writing_quality": 10, "group_integration": 15
    }
    
    for field in score_fields:
        # Try to extract points and comment for each field
        pattern = rf'"{field}"\s*:\s*\{{"points"\s*:\s*(\d+),\s*"max"\s*:\s*(\d+)(?:,\s*"comment"\s*:\s*"([^"]*)")?'
        match = re.search(pattern, json_str)
        if match:
            score_breakdown[field] = {
                "points": int(match.group(1)),
                "max": int(match.group(2)),
                "comment": match.group(3) if match.group(3) else ""
            }
        else:
            # Default if not found
            score_breakdown[field] = {
                "points": 0,
                "max": max_points.get(field, 10),
                "comment": "Partial analysis - JSON truncated"
            }
    
    if score_breakdown:
        result["score_breakdown"] = score_breakdown
    
    # Try to extract bonus_scores
    bonus_scores = {}
    bonus_fields = ["bonus_ai_opportunities", "bonus_exceptional_quality"]
    # Default max points for bonus fields (defined once outside loop for efficiency)
    bonus_max_points = {"bonus_ai_opportunities": 3, "bonus_exceptional_quality": 1}
    
    for field in bonus_fields:
        pattern = rf'"{field}"\s*:\s*\{{"points"\s*:\s*(\d+),\s*"max"\s*:\s*(\d+)(?:,\s*"comment"\s*:\s*"([^"]*)")?'
        match = re.search(pattern, json_str)
        if match:
            bonus_scores[field] = {
                "points": int(match.group(1)),
                "max": int(match.group(2)),
                "comment": match.group(3) if match.group(3) else ""
            }
        else:
            bonus_scores[field] = {
                "points": 0,
                "max": bonus_max_points.get(field, 0),
                "comment": ""
            }
    
    if bonus_scores:
        result["bonus_scores"] = bonus_scores
    
    return result


def build_analysis_prompt(page_content: str, page_number: int, rubric_data: Optional[Dict] = None, has_image: bool = False) -> str:
    """Build a prompt for Gemini to analyze a PDF page. Optimized per LLM recommendations."""
    # Truncate page content to first 2500 chars (reduced from 3000)
    page_content = page_content[:2500] + ("..." if len(page_content) > 2500 else "")
    word_count = len(page_content.split())
    
    # Summarize rubric instead of full text
    rubric_summary = ""
    if rubric_data and "rubric" in rubric_data:
        rubric = rubric_data["rubric"]
        criteria_list = [f"{c.get('title', 'N/A')} ({c.get('points', 0)} pts)" for c in rubric.get("criteria", [])]
        bonus_list = [f"{b.get('title', 'N/A')} ({b.get('points', 0)} pts)" for b in rubric.get("bonusCriteria", [])]
        rubric_summary = f"Rubric: {', '.join(criteria_list)}"
        if bonus_list:
            rubric_summary += f" | Bonus: {', '.join(bonus_list)}"
    
    # Include heuristics list for reference
    heuristics_list = ""
    if rubric_data and "heuristics" in rubric_data:
        heuristics = rubric_data["heuristics"]
        heuristics_list = "\n\nNIELSEN HEURISTICS REFERENCE:\n"
        for h in heuristics:
            heuristics_list += f"  {h.get('number', '?')}. {h.get('name', 'N/A')}: {h.get('description', 'N/A')}\n"

    prompt = f"""You are evaluating a student's heuristic evaluation assignment for a UX/HCI course.

{rubric_summary}
{heuristics_list}

CRITICAL GRADING PRINCIPLES:
1. Do NOT add new categories to score_breakdown. Only use the existing categories defined in the rubric above.
2. When grading, you must consider evaluations from ALL pages of the submission and synthesize them comprehensively for final scoring. Do not evaluate pages in complete isolation - consider how the work across all pages demonstrates the student's understanding and coverage.
3. CROSS-PAGE CONTENT DISTRIBUTION: Some students may spread a single violation or heuristic analysis across multiple pages. If this page does not contain certain key concepts (e.g., severity analysis, detailed violation descriptions, or heuristic explanations), do NOT immediately deduct points. After all pages are processed, the system will check if missing concepts appear on adjacent or related pages. For now, evaluate what is present on THIS page, but note in your feedback if key elements seem incomplete or missing - the final comprehensive evaluation will consider content across all pages.

STUDENT SUBMISSION - PAGE {page_number}:
Content: {word_count} words, Has image: {has_image}
{page_content}

═══ STEP 1: CLASSIFICATION ═══
Determine page type by analyzing the FULL PAGE CONTENT (text, structure, visual elements), not just word count:

CRITICAL: Identify the page type accurately. Use these specific page_type values:
- "introduction page" or "introduction" - Contains project overview, team members, methodology introduction, or assignment context
- "conclusion page" or "conclusion" - Contains final summary, takeaways, or closing remarks
- "severity summary page" or "severity summary" - Contains severity rating tables, overview of all violations by severity, or aggregated severity analysis
- "heuristic violation analysis" - Contains detailed analysis of specific heuristic violations with descriptions, screenshots, and user impact
- "heuristic title page" - Contains only a heuristic number/title (e.g., "Heuristic 1", "Heuristic 2") with minimal content
- "table of contents" - Contains document structure/navigation
- "cover page" or "title page" - Contains title, course info, student names only

- Skip analysis (skip_analysis: true) if:
  * Title page, cover page, table of contents
  * Page contains only a heuristic number/title (e.g., "Heuristic 1", "Heuristic 2") with minimal content
  * Page is clearly a section divider or subtitle page
  * Page has very little substantive content (mostly titles, headers, or decorative elements)

- Analyze (skip_analysis: false) if:
  * Page contains heuristic violation analysis with detailed descriptions (page_type: "heuristic violation analysis")
  * Page is an introduction page with project context, team info, or methodology (page_type: "introduction page" or "introduction")
  * Page is a conclusion page with final summary (page_type: "conclusion page" or "conclusion")
  * Page is a severity summary page with aggregated severity ratings (page_type: "severity summary page" or "severity summary")
  * Page follows a heuristic title page and contains the actual analysis content
  * Page has images with annotations explaining violations

Note: Heuristic title pages (showing just "Heuristic X" or similar) should be skipped, but the NEXT page usually contains the analysis for that heuristic and should be analyzed.

═══ STEP 2: EXTRACTION (if skip_analysis: false) ═══
IMPORTANT: Only extract violations for pages with page_type "heuristic violation analysis".
For introduction pages, conclusion pages, or severity summary pages, set extracted_violations to an empty array [].

Extract all violations found on this page into extracted_violations array by READING THE STUDENT'S TEXT CAREFULLY.
ONLY extract violations if page_type is "heuristic violation analysis" or similar violation analysis pages.

CROSS-PAGE VIOLATION HANDLING: Some students may spread a single violation analysis across multiple pages (e.g., violation description on one page, severity rating on another, or heuristic explanation split across pages). Extract what is explicitly present on THIS page. If a violation seems incomplete (e.g., has description but no severity, or mentions heuristic number but no name), extract what is available. The system will check adjacent pages during final comprehensive evaluation to see if missing elements appear elsewhere.

For each violation mentioned by the student, you MUST extract from the text:
- heuristic_num (1-10): The Nielsen heuristic number mentioned by the student (look for "Heuristic 1", "H1", "Heuristic #1", etc.)
- heuristic_name: The FULL NAME of the heuristic as written by the student. Look for phrases like:
  * "Visibility of System Status" or "System Status"
  * "Match Between System and the Real World" or "Match System Real World"
  * "User Control and Freedom" or "User Control"
  * "Consistency and Standards" or "Consistency"
  * "Error Prevention"
  * "Recognition Rather Than Recall" or "Recognition vs Recall"
  * "Flexibility and Efficiency" or "Flexibility"
  * "Aesthetic and Minimalist Design" or "Aesthetic Design"
  * "Help Users Recognize, Diagnose, and Recover from Errors" or "Error Recovery" or "Error Messages"
  * "Help and Documentation" or "Documentation"
  Extract the name EXACTLY as written by the student, or match to the closest standard name from the reference list above.
- description: A brief description of the violation as described by the student (max 30 words). If the description spans multiple pages, extract what is on THIS page.
- severity: The severity rating mentioned by the student on THIS page. Look for:
  * Words: "Cosmetic", "Minor", "Major", "Critical", "Low", "Medium", "High"
  * Numbers: "1", "2", "3", "4" (may be in a scale like "Severity: 3" or "Rating: 2")
  Extract this EXACTLY as written by the student (preserve the format: word or number).
  If severity is not mentioned on this page but the violation description is present, leave severity as empty string "" - it may appear on an adjacent page.

IMPORTANT: 
- Read the student's text word-by-word to find heuristic names and severity ratings
- Don't infer or guess - only extract what is explicitly written on THIS page
- If a heuristic is mentioned by number only (e.g., "Heuristic 5"), look for the name nearby on THIS page or use the standard name from the reference
- If severity is not explicitly mentioned on this page, leave it as empty string "" (it may be on another page)
- If a violation description seems incomplete, extract what is present - the final evaluation will check if related content appears on adjacent pages

═══ STEP 3: SCORING (if skip_analysis: false) ═══
Score each criterion using point deduction checklists. Start from max points, subtract for violations.

IMPORTANT: When scoring, consider the student's work across ALL pages of the submission. While you are evaluating this specific page, your scoring should reflect how well the student demonstrates understanding across the entire assignment. For example:
- Coverage should consider heuristics mentioned across all pages, not just this page
- Violation quality should consider the overall quality of analysis across all pages
- Professional quality and writing quality should consider consistency across the entire document
- Do NOT add new categories to score_breakdown - only use the existing categories defined in the rubric.

**Violation Quality (max 20):**
Start: 20 points

Each violation description should:
- Connect the problem to a specific user goal or task
- Explain the user impact (e.g., slower task, more errors, task failure)
- Link the issue to a UX or cognitive principle (e.g., cognitive load, recognition vs. recall, error prevention, feedback, error tolerance)

Deduct points when:
□ -2: Student only says things like "confusing" or "frustrating" without explaining why in terms of user goals or cognition (emotional phrasing used >2 times)
□ -3: Reasoning does not mention how the issue affects perception, memory, decision-making, or action (missing cognitive/UX principle connection)
□ -3: Severity mismatch (marked Major/Critical but impact is cosmetic, OR marked Minor but should be Major)
□ -2: A clearly cosmetic issue (e.g., small spacing change) is treated as a serious heuristic violation
□ -1: Missing "what/why/user impact" structure per violation
□ -2: Severity looks inflated (many problems marked "major/4" even when the impact is mild or users can easily recover)

Final = 20 - [deductions]

**Severity Analysis (max 10):**
Start: 10 points

Ideally, the student should:
- Briefly explain how they use the 1–4 scale (for example: based on impact × frequency × persistence)
- Give a short reason for each rating, mentioning how often it occurs and how serious the impact is

IMPORTANT: Some students may distribute severity analysis across multiple pages. If this page does not contain a severity summary or scale explanation, do NOT immediately deduct all points. Check if:
- This page is part of a multi-page severity analysis (e.g., page shows individual severity ratings, while summary appears on another page)
- The severity summary or scale explanation might appear on adjacent pages (previous or next pages)
- The content on this page references or connects to severity information on other pages

Deduct points when:
□ -3: No severity summary section found on THIS page AND you are certain it does not exist elsewhere (check for "Severity Summary", tables, or overview sections on other pages if this seems incomplete)
□ -2: Missing explanation of how 1-4 scale was applied on THIS page (but note if it might be on another page - final evaluation will check all pages)
□ -1 to -2: There is no clear explanation of how the scale is applied on this page (take off about 1–2 points, but note if explanation might be on adjacent pages)
□ -1: Individual severity ratings on this page have no rationale beyond "this is confusing" (no mention of frequency or impact severity)

Note: If severity analysis appears incomplete on this page, mention in your feedback that the final evaluation will check adjacent pages for completeness.

Final = 10 - [deductions]

**Screenshots & Evidence (max 10):**
Start: 10 points

Good work should have:
- Readable screenshots and notes (clear text, reasonable font size)
- Annotations that clearly show what the problem is (arrows, labels, short notes)

Deduct points when:
□ -1: Images blurry/unreadable at 100% zoom
□ -2: Notes are hard to read or inconsistent in size (font sizes vary >50%)
□ -2: The screenshot + note look like a personal sketch that only the author understands (annotations appear as personal sketches, not clear communication tools)
□ -1: There is minimal annotation, so the violation is not obvious to a new reader (missing annotations/labels for violations)

Final = 10 - [deductions]

**Professional Quality (max 10):**
Start: 10 points

Deduct points when:
□ -2: Background colors, patterns, or icons are visually distracting and do not help communication
□ -2: Layout is messy: poor spacing, weak alignment, or inconsistent grid (spacing inconsistent, varies >50% between sections; elements misaligned, grid structure not followed)
□ -1: Layout disorganized (making the document harder to scan)

Final = 10 - [deductions]

**Writing Quality (max 10):**
Start: 10 points

Deduct points when:
□ -2: There are frequent grammar errors spread across more than ~2 pages (multiple grammatical errors >3)
□ -1: Sentences are unclear and make it hard to understand the violation, impact, or heuristic (unclear sentences >2)

Final = 10 - [deductions]

**Structure & Navigation (max 10):**
Start: 10 points
□ -2: Poor document structure, difficult to navigate
□ -1: Could benefit from better section organization
Final = 10 - [deductions]

**Group Integration (max 15):**
CRITICAL: Only evaluate Group Integration for introduction pages or pages that explicitly discuss group collaboration, team members, or group work integration.
For other page types (heuristic violation analysis, conclusion, severity summary), set points to 0 and leave comment empty.

Start: 15 points (only for introduction/group collaboration pages)
□ -5: No evidence of group collaboration (no mention of team members, collaboration process, or group work)
□ -3: Limited integration of group members' work (mentions group but doesn't show how individual contributions were integrated)
□ -2: Missing clear indication of how group members contributed to the evaluation
Final = 15 - [deductions]

For non-introduction pages: Set points to 0, comment to "".

**Bonus - AI Opportunities (max 3):**
0 points: Default (meets requirements; AI opportunities are missing or very generic).
1 point: Student proposes at least one clear AI opportunity beyond the minimum requirement.
2 points: Student discusses AI opportunities in a detailed and thoughtful way, showing good understanding of the system and realistic AI capabilities.
3 points: Student’s AI opportunities are extremely strong, creative, and well-argued, showing an exceptional level of insight.

**Bonus - Exceptional Quality (max 2):**
0 points: Default (meets requirements; work is solid but does not especially stand out).
1 point: Work is clearly above average in one or more aspects (e.g., clarity, organization, depth of analysis, or visual polish).
2 points: Work is outstanding overall: very clear, well-organized, and polished, with analysis and presentation that go significantly beyond what is required.

**Coverage:** Leave points at 0. System calculates based on total heuristics (need 10) and violations (need 12) across all pages.

═══ STEP 4: FEEDBACK DRAFTING ═══
- List heuristics discussed and violation counts (be concise)
- Point out 2-3 key issues if problems exist (one sentence each)
- 1-2 sentence overall summary
- MAXIMUM 200 words for feedback field

COMMENT FIELD RULES:
- ONLY explain why points were deducted
- If full points, leave comment empty or omit
- Format: "Deducted X points: [specific issue]" (one sentence, max 50 words)
- NO positive comments in comment fields
- Keep ALL comments under 50 words to prevent truncation

═══ STEP 5: JSON GENERATION ═══

CRITICAL: The entire response MUST be a single, valid JSON object. DO NOT include ANY text, Markdown fences (```json, ```), or explanations outside of the JSON object itself.

IMPORTANT: Keep ALL text fields SHORT to prevent JSON truncation:
- feedback: max 200 words
- comment fields: max 50 words each
- page_type: max 20 words
- skip_reason: max 30 words

{{
  "page_number": {page_number},
  "skip_analysis": true/false,
  "page_type": "description",
  "skip_reason": "reason if skip_analysis is true",
  "extracted_violations": [{{"heuristic_num": 1, "heuristic_name": "Visibility of System Status", "description": "...", "severity": "Major"}}],
  "feedback": "Brief: heuristics, violations, 2-3 issues, summary.",
  "compelling": true/false,
  "score_breakdown": {{
    "coverage": {{"points": 0, "max": 15, "comment": ""}},
    "violation_quality": {{"points": X, "max": 20, "comment": ""}},
    "screenshots": {{"points": X, "max": 10, "comment": ""}},
    "severity_analysis": {{"points": X, "max": 10, "comment": ""}},
    "structure_navigation": {{"points": X, "max": 10, "comment": ""}},
    "professional_quality": {{"points": X, "max": 10, "comment": ""}},
    "writing_quality": {{"points": X, "max": 10, "comment": ""}},
    "group_integration": {{"points": X, "max": 15, "comment": ""}}
  }},
  "bonus_scores": {{
    "bonus_ai_opportunities": {{"points": X, "max": 3, "comment": ""}},
    "bonus_exceptional_quality": {{"points": X, "max": 1, "comment": ""}}
  }}
}}"""
    
    return prompt


# Directory to save analysis results
ANALYSIS_OUTPUT_DIR = Path(__file__).parent.parent / "output_static" / "student_analyses"
ANALYSIS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Directory to store pages and issues JSON files
PAGES_ISSUES_DIR = Path(__file__).parent.parent / "output_static" / "pages_issues"
PAGES_ISSUES_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# JSON File Operation Helpers (to reduce code duplication)
# ============================================================================

def load_json_file(file_path: Path, default: Any = None) -> Any:
    """Load JSON file with error handling. Returns default if file doesn't exist or fails to load."""
    if not file_path.exists():
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON file {file_path}: {e}")
        return default


def save_json_file(file_path: Path, data: Any, create_dirs: bool = True) -> bool:
    """Save data to JSON file with error handling. Returns True if successful."""
    try:
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving JSON file {file_path}: {e}")
        return False


def get_job_file_path(job_id: str, filename: str, base_dir: Path = PAGES_ISSUES_DIR) -> Path:
    """Get file path for a job-specific file."""
    return base_dir / f"{job_id}_{filename}"

@app.post("/api/analyze-single-page")
async def analyze_single_page(request: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a single PDF page using Gemini."""
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY not configured. Please set it in your environment."
        )
    
    if not MODEL:
        raise HTTPException(
            status_code=500,
            detail="Gemini model not initialized."
        )
    
    page_data = request.get("page")
    if not page_data:
        raise HTTPException(status_code=400, detail="No page provided for analysis.")
    
    page_number = page_data.get("pageNumber")
    snippet = page_data.get("snippet", "")
    image_base64 = page_data.get("imageBase64")
    has_image = bool(image_base64)
    job_id = request.get("jobId", f"job-{int(time.time() * 1000)}")
    
    # Get previous pages context for heuristic hint
    previous_pages_context = request.get("previousPages", [])
    
    try:
        # Use new structured page analysis prompt
        truncated_content = snippet[:2500] + ("..." if len(snippet) > 2500 else "")
        prompt = get_page_analysis_prompt(page_number, truncated_content, has_image, previous_pages_context)
        
        # Prepare content for Gemini
        content_parts = [prompt]
        
        # If we have an image, include it
        if image_base64:
            # Remove data URL prefix if present
            if image_base64.startswith("data:image"):
                image_base64 = image_base64.split(",")[1]
            
            image_bytes = base64.b64decode(image_base64)
            pil_image = Image.open(io.BytesIO(image_bytes))
            
            # Compress image to speed up processing (max width 1200px, maintain aspect ratio)
            max_width = 1200
            if pil_image.width > max_width:
                ratio = max_width / pil_image.width
                new_height = int(pil_image.height * ratio)
                pil_image = pil_image.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            content_parts.append(pil_image)
        
        # Call Gemini with optimized config per LLM recommendations
        generation_config = {
            "temperature": 0.2,  # Reduced from 0.7 for deterministic scoring
            "max_output_tokens": 8192,  # Maximum supported by Gemini 2.5 Flash to prevent JSON truncation
            "response_mime_type": "application/json",  # Force JSON output format
        }
        
        try:
            response = MODEL.generate_content(
                content_parts,
                generation_config=generation_config
            )
            
            # Get response text - try multiple methods to extract text
            response_text = None
            error_details = []
            
            # Check for safety filters or blocked content first
            if hasattr(response, 'prompt_feedback'):
                if response.prompt_feedback:
                    if hasattr(response.prompt_feedback, 'block_reason'):
                        if response.prompt_feedback.block_reason:
                            error_details.append(f"Prompt blocked: {response.prompt_feedback.block_reason}")
            
            # Check candidates for finish reasons
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    if candidate.finish_reason and candidate.finish_reason != 1:  # 1 = STOP (normal)
                        finish_reason_map = {
                            0: "FINISH_REASON_UNSPECIFIED",
                            2: "MAX_TOKENS",
                            3: "SAFETY",
                            4: "RECITATION",
                            5: "OTHER"
                        }
                        reason = finish_reason_map.get(candidate.finish_reason, f"Unknown ({candidate.finish_reason})")
                        error_details.append(f"Finish reason: {reason}")
                
                # Check safety ratings
                if hasattr(candidate, 'safety_ratings'):
                    if candidate.safety_ratings:
                        blocked_categories = []
                        for rating in candidate.safety_ratings:
                            if hasattr(rating, 'blocked') and rating.blocked:
                                category = getattr(rating, 'category', 'UNKNOWN')
                                blocked_categories.append(str(category))
                        if blocked_categories:
                            error_details.append(f"Content blocked by safety filters: {', '.join(blocked_categories)}")
            
            # Method 1: Try response.text (standard method)
            try:
                response_text = response.text
            except (ValueError, AttributeError) as e:
                error_details.append(f"Method 1 (response.text) failed: {type(e).__name__}: {str(e)}")
            
            # Method 2: If that fails, try to extract from candidates directly
            if not response_text and response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                try:
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            parts_text = []
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    parts_text.append(part.text)
                            if parts_text:
                                response_text = "".join(parts_text)
                except Exception as e:
                    error_details.append(f"Method 2 (candidates.parts) failed: {type(e).__name__}: {str(e)}")
            
            # Method 3: Try to get any text from the response object
            if not response_text:
                try:
                    # Try accessing the response as a string
                    response_text = str(response)
                    # If it's just the object representation, try candidates again
                    if response_text.startswith('<') or 'object at' in response_text:
                        response_text = None  # Reset if it's just object representation
                        if response.candidates:
                            for candidate in response.candidates:
                                try:
                                    if hasattr(candidate, 'content'):
                                        content_str = str(candidate.content)
                                        if content_str and len(content_str) > 50 and not content_str.startswith('<'):
                                            response_text = content_str
                                            break
                                except Exception:
                                    continue
                except Exception as e:
                    error_details.append(f"Method 3 (str conversion) failed: {type(e).__name__}: {str(e)}")
            
            # If we still don't have text, create a meaningful error response
            if not response_text or len(response_text.strip()) < 10:
                error_msg = "Could not extract text from Gemini response"
                if error_details:
                    error_msg += f". Details: {'; '.join(error_details)}"
                else:
                    error_msg += ". Response structure may have changed or content was filtered."
                
                print(f"[ERROR] Page {page_number}: {error_msg}")
                print(f"[DEBUG] Response object type: {type(response)}")
                print(f"[DEBUG] Response has candidates: {hasattr(response, 'candidates') and response.candidates}")
                if hasattr(response, 'candidates') and response.candidates:
                    print(f"[DEBUG] First candidate type: {type(response.candidates[0])}")
                    print(f"[DEBUG] First candidate finish_reason: {getattr(response.candidates[0], 'finish_reason', 'N/A')}")
                
                # Return a structured response indicating the issue
                return {
                    "status": "completed",
                    "result": {
                        "page_number": page_number,
                        "skip_analysis": False,
                        "page_type": "Analysis Error",
                        "feedback": f"Unable to extract response from Gemini API for page {page_number}. {error_msg}",
                        "error": error_msg,
                        "error_details": error_details if error_details else None,
                        "score_breakdown": {
                            "coverage": {"points": 0, "max": 15, "comment": "Unable to analyze - API response issue"},
                            "violation_quality": {"points": 0, "max": 20, "comment": "Unable to analyze - API response issue"},
                            "screenshots": {"points": 0, "max": 10, "comment": "Unable to analyze - API response issue"},
                            "severity_analysis": {"points": 0, "max": 10, "comment": "Unable to analyze - API response issue"},
                            "structure_navigation": {"points": 0, "max": 10, "comment": "Unable to analyze - API response issue"},
                            "professional_quality": {"points": 0, "max": 10, "comment": "Unable to analyze - API response issue"},
                            "writing_quality": {"points": 0, "max": 10, "comment": "Unable to analyze - API response issue"},
                            "group_integration": {"points": 0, "max": 15, "comment": "Unable to analyze - API response issue"},
                        }
                    }
                }
            
            # Try to extract JSON from response - prioritize direct parsing per LLM recommendations
            analysis_json = None
            used_fallback = False
            
            # Primary method: Direct JSON parsing (response_mime_type should ensure clean JSON)
            try:
                analysis_json = json.loads(response_text)
            except json.JSONDecodeError:
                # Fallback 1: Try to find JSON in markdown code blocks
                json_block_match = re.search(r'```(?:json)?\s*(\{.*?)\s*```', response_text, re.DOTALL)
                if json_block_match:
                    json_str = json_block_match.group(1)
                    json_str = fix_incomplete_json(json_str)
                    try:
                        analysis_json = json.loads(json_str)
                        used_fallback = True
                    except json.JSONDecodeError:
                        pass
                
                # Fallback 2: Find JSON object directly (from start of first {)
                if not analysis_json:
                    json_start = response_text.find('{')
                    if json_start != -1:
                        json_str = response_text[json_start:]
                        json_str = fix_incomplete_json(json_str)
                        try:
                            analysis_json = json.loads(json_str)
                            used_fallback = True
                        except json.JSONDecodeError:
                            # Fix trailing commas and try again
                            json_str = re.sub(r',\s*}', '}', json_str)
                            json_str = re.sub(r',\s*]', ']', json_str)
                            json_str = fix_incomplete_json(json_str)
                            try:
                                analysis_json = json.loads(json_str)
                                used_fallback = True
                            except json.JSONDecodeError:
                                # Last resort: extract partial data
                                analysis_json = extract_partial_json(json_str, page_number)
                                used_fallback = True
            
            # Log if fallback was used (per LLM recommendation)
            if used_fallback:
                print(f"Warning: Used fallback JSON parsing for page {page_number}")
            
            # If still no valid JSON, create a fallback response
            if not analysis_json:
                analysis_json = {
                    "page_number": page_number,
                    "skip_analysis": False,
                    "page_type": "Unknown",
                    "feedback": response_text[:1000] if response_text else "No response generated",
                    "error": "Could not parse structured JSON from response"
                }
                used_fallback = True
            
            # Ensure page_number is always set correctly (LLM might return wrong or missing page_number)
            if "page_number" not in analysis_json or analysis_json.get("page_number") != page_number:
                analysis_json["page_number"] = page_number
            
            # Create a copy of structured analysis before converting
            structured_analysis = dict(analysis_json)  # Keep new format
            
            # Convert new PageAnalysis format to legacy PageAnalysisResult format for backward compatibility
            legacy_result = convert_page_analysis_to_legacy(analysis_json, page_number)
            
            # Include both formats in response
            final_result = dict(legacy_result)  # Start with legacy format
            final_result["structured_analysis"] = structured_analysis  # Add new format
            analysis_json = final_result
            
            # Save analysis result to JSON file
            try:
                output_file = ANALYSIS_OUTPUT_DIR / f"{job_id}_page_{page_number}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(analysis_json, f, indent=2, ensure_ascii=False)
            except Exception as save_err:
                # Don't fail the request if saving fails, just log it
                print(f"Warning: Failed to save analysis to {output_file}: {save_err}")
            
        except Exception as e:
            error_result = {
                "page_number": page_number,
                "skip_analysis": True,
                "page_type": "Unknown (error)",
                "skip_reason": f"Error during analysis: {str(e)}",
                "error": str(e)
            }
            
            # Save error result to JSON file
            try:
                output_file = ANALYSIS_OUTPUT_DIR / f"{job_id}_page_{page_number}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(error_result, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            
            return {
                "status": "error",
                "page_number": page_number,
                "error": str(e),
                "result": error_result
            }
        
        return {
            "status": "completed",
            "result": analysis_json
        }
        
    except Exception as e:
        return {
            "status": "error",
            "page_number": page_number,
            "error": str(e),
            "result": {
                "page_number": page_number,
                "error": str(e),
                "feedback": f"Error analyzing page {page_number}: {e}"
            }
        }


# ============================================================================
# Reviewer Mode (HITL) API Endpoints
# ============================================================================

# Directory to store override records
OVERRIDES_DIR = Path(__file__).parent.parent / "output_static" / "overrides"
OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)

# Directory to store AI error corrections
CORRECTIONS_DIR = Path(__file__).parent.parent / "output_static" / "corrections"
CORRECTIONS_DIR.mkdir(parents=True, exist_ok=True)
CORRECTIONS_FILE = CORRECTIONS_DIR / "corrections.json"

# Directory to store manual risk flags (user-marked pages)
RISK_FLAGS_DIR = Path(__file__).parent.parent / "output_static" / "risk_flags"
RISK_FLAGS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/get-extraction-result")
async def get_extraction_result(jobId: str) -> Dict[str, Any]:
    """Get extraction result for a job ID."""
    # Try to load from stored results
    extraction_file = ANALYSIS_OUTPUT_DIR.parent / f"{jobId}_extraction.json"
    
    data = load_json_file(extraction_file)
    if data:
            # Normalize field names: convert image_base64 to imageBase64 and page_number to pageNumber
            pages = data.get("pages", [])
            normalized_pages = []
            for page in pages:
                normalized_page = dict(page)
                # Convert image_base64 to imageBase64 for frontend compatibility
                if "image_base64" in normalized_page and "imageBase64" not in normalized_page:
                    normalized_page["imageBase64"] = normalized_page["image_base64"]
                # Convert page_number to pageNumber for frontend compatibility
                if "page_number" in normalized_page and "pageNumber" not in normalized_page:
                    normalized_page["pageNumber"] = normalized_page["page_number"]
                normalized_pages.append(normalized_page)
            
            return {
                "jobId": jobId,
                "fileName": data.get("fileName"),
                "createdAt": data.get("createdAt"),
                "pages": normalized_pages,
            }
    
    # Fallback: return empty result
    return {
        "jobId": jobId,
        "fileName": None,
        "createdAt": None,
        "pages": [],
    }


@app.get("/api/get-analysis-results")
async def get_analysis_results(jobId: str) -> Dict[str, Any]:
    """Get all analysis results for a job ID."""
    results = []
    
    # Load all analysis files for this job
    for analysis_file in ANALYSIS_OUTPUT_DIR.glob(f"{jobId}_page_*.json"):
        try:
            with open(analysis_file, "r", encoding="utf-8") as f:
                result = json.load(f)
                results.append(result)
        except Exception as e:
            print(f"Error loading {analysis_file}: {e}")
    
    # Sort by page number
    results.sort(key=lambda x: x.get("page_number", 0))
    
    # Save pages.json after loading all results
    try:
        pages_data = []
        for result in results:
            structured = result.get("structured_analysis")
            if structured:
                pages_data.append(structured)
        
        if pages_data:
            pages_file = get_job_file_path(jobId, "pages.json")
            save_json_file(pages_file, pages_data)
            
            # Aggregate issues and save
            issues = aggregate_issues(pages_data)
            issues_file = PAGES_ISSUES_DIR / f"{jobId}_issues.json"
            
            # Load existing issues to preserve TA reviews
            existing_issues_data = load_json_file(issues_file, {})
            existing_issues = existing_issues_data.get("issues", []) if isinstance(existing_issues_data, dict) else []
            
            # Merge TA reviews from existing issues
            existing_issues_dict = {issue.get("issue_id"): issue for issue in existing_issues}
            for issue in issues:
                existing_issue = existing_issues_dict.get(issue["issue_id"])
                if existing_issue and existing_issue.get("ta_review"):
                    issue["ta_review"] = existing_issue["ta_review"]
            
            save_json_file(issues_file, {"issues": issues})
    except Exception as e:
        print(f"Warning: Failed to save pages/issues JSON: {e}")
    
    return {"jobId": jobId, "results": results}


@app.get("/api/get-overrides")
async def get_overrides(jobId: str) -> Dict[str, Any]:
    """Get all override records for a job ID."""
    overrides_file = OVERRIDES_DIR / f"{jobId}_overrides.json"
    data = load_json_file(overrides_file, {})
    overrides = data.get("overrides", []) if isinstance(data, dict) else []
    return {"jobId": jobId, "overrides": overrides}


@app.get("/api/get-issues")
async def get_issues(jobId: str = Query(..., description="Job ID to get issues for")) -> Dict[str, Any]:
    """Get all issues for a job ID (after aggregation)."""
    print(f"[DEBUG] get_issues called with jobId: {jobId}")
    issues_file = PAGES_ISSUES_DIR / f"{jobId}_issues.json"
    
    if issues_file.exists():
        try:
            with open(issues_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"jobId": jobId, "issues": data.get("issues", [])}
        except Exception as e:
            print(f"Error loading issues: {e}")
    
    # If no issues file exists, try to generate from pages
    pages_file = get_job_file_path(jobId, "pages.json")
    pages_data = load_json_file(pages_file)
    if pages_data:
        issues = aggregate_issues(pages_data)
        # Save the generated issues
        issues_file = get_job_file_path(jobId, "issues.json")
        if save_json_file(issues_file, {"issues": issues}):
            return {"jobId": jobId, "issues": issues}
    
    return {"jobId": jobId, "issues": []}


@app.patch("/api/update-issue-review")
async def update_issue_review(request: Dict[str, Any]) -> Dict[str, Any]:
    """Update TA review for a specific issue."""
    job_id = request.get("jobId")
    issue_id = request.get("issueId")
    ta_review = request.get("ta_review")
    
    if not job_id or not issue_id:
        raise HTTPException(status_code=400, detail="jobId and issueId are required")
    
    issues_file = get_job_file_path(job_id, "issues.json")
    data = load_json_file(issues_file)
    
    if not data:
        raise HTTPException(status_code=404, detail="Issues file not found. Please run analysis first.")
    
    issues = data.get("issues", []) if isinstance(data, dict) else []
    
    # Find and update the issue
    issue_found = False
    for issue in issues:
        if issue.get("issue_id") == issue_id:
            issue["ta_review"] = ta_review
            issue_found = True
            break
    
    if not issue_found:
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
    
    # Save back
    if not save_json_file(issues_file, {"issues": issues}):
        raise HTTPException(status_code=500, detail="Failed to save updated issues")
    
    return {
        "status": "success",
        "jobId": job_id,
        "issueId": issue_id,
        "ta_review": ta_review,
    }


def calculate_grading_scores(pages: List[Dict[str, Any]], issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate grading scores based on pages and issues metadata.
    Returns a dictionary with scores for each rubric criterion.
    """
    scores = {
        "coverage": {"points": 0, "max": 15, "comment": ""},
        "violation_quality": {"points": 0, "max": 20, "comment": ""},
        "screenshots": {"points": 0, "max": 10, "comment": ""},
        "severity_analysis": {"points": 0, "max": 10, "comment": ""},
        "structure_navigation": {"points": 0, "max": 10, "comment": ""},
        "professional_quality": {"points": 0, "max": 10, "comment": ""},
        "writing_quality": {"points": 0, "max": 10, "comment": ""},
        "group_integration": {"points": 0, "max": 15, "comment": ""},
        "bonus_ai_opportunities": {"points": 0, "max": 3, "comment": ""},
        "bonus_exceptional_quality": {"points": 0, "max": 1, "comment": ""},
    }
    
    if not pages or not issues:
        return scores
    
    # Coverage: Count unique heuristics and violations
    unique_heuristics = set()
    for issue in issues:
        if issue.get("heuristic_id") and not issue.get("heuristic_id", "").startswith("Hx"):
            unique_heuristics.add(issue.get("heuristic_id"))
    
    coverage_score = 15
    if len(unique_heuristics) < 10:
        coverage_score -= 5
    if len(issues) < 12:
        coverage_score -= 5
    if len(unique_heuristics) < 8:
        coverage_score -= 2
    if len(issues) < 10:
        coverage_score -= 2
    scores["coverage"]["points"] = max(0, coverage_score)
    scores["coverage"]["comment"] = f"Found {len(unique_heuristics)}/10 heuristics, {len(issues)} issues"
    
    # Violation Quality: Based on rubric_relevance from violation_detail pages
    violation_pages = [p for p in pages if p.get("page_role") == "violation_detail"]
    if violation_pages:
        violation_quality_levels = [p.get("rubric_relevance", {}).get("violation_quality", "none") for p in violation_pages]
        level_scores = {"high": 20, "med": 15, "low": 10, "none": 0}
        avg_score = sum(level_scores.get(level, 0) for level in violation_quality_levels) / len(violation_quality_levels) if violation_quality_levels else 0
        scores["violation_quality"]["points"] = round(avg_score)
        scores["violation_quality"]["comment"] = f"Average relevance: {sum(1 for l in violation_quality_levels if l == 'high')} high, {sum(1 for l in violation_quality_levels if l == 'med')} med"
    
    # Screenshots & Evidence: Based on has_annotations from violation_detail pages
    if violation_pages:
        annotation_levels = [p.get("has_annotations", "none") for p in violation_pages]
        annotation_scores = {"high": 10, "medium": 8, "low": 5, "none": 2}
        avg_score = sum(annotation_scores.get(level, 0) for level in annotation_levels) / len(annotation_levels) if annotation_levels else 0
        scores["screenshots"]["points"] = round(avg_score)
        scores["screenshots"]["comment"] = f"Annotation levels: {sum(1 for l in annotation_levels if l == 'high')} high, {sum(1 for l in annotation_levels if l == 'medium')} medium"
    
    # Severity Analysis: Check for severity_summary pages and rubric_relevance
    severity_pages = [p for p in pages if p.get("page_role") == "severity_summary"]
    if severity_pages:
        severity_levels = [p.get("rubric_relevance", {}).get("severity_analysis", "none") for p in severity_pages]
        level_scores = {"high": 10, "med": 7, "low": 4, "none": 0}
        avg_score = sum(level_scores.get(level, 0) for level in severity_levels) / len(severity_levels) if severity_levels else 0
        scores["severity_analysis"]["points"] = round(avg_score)
        scores["severity_analysis"]["comment"] = f"Found {len(severity_pages)} severity summary page(s)"
    else:
        scores["severity_analysis"]["points"] = 5
        scores["severity_analysis"]["comment"] = "No severity summary page found"
    
    # Structure & Navigation: Based on rubric_relevance
    structure_levels = [p.get("rubric_relevance", {}).get("structure_navigation", "none") for p in pages]
    if structure_levels:
        level_scores = {"high": 10, "med": 7, "low": 4, "none": 2}
        avg_score = sum(level_scores.get(level, 0) for level in structure_levels) / len(structure_levels)
        scores["structure_navigation"]["points"] = round(avg_score)
        scores["structure_navigation"]["comment"] = f"Average structure relevance: {sum(1 for l in structure_levels if l == 'high')} high"
    
    # Professional Quality: Based on rubric_relevance
    professional_levels = [p.get("rubric_relevance", {}).get("professional_quality", "none") for p in pages]
    if professional_levels:
        level_scores = {"high": 10, "med": 7, "low": 4, "none": 2}
        avg_score = sum(level_scores.get(level, 0) for level in professional_levels) / len(professional_levels)
        scores["professional_quality"]["points"] = round(avg_score)
        scores["professional_quality"]["comment"] = f"Average professional quality: {sum(1 for l in professional_levels if l == 'high')} high"
    
    # Writing Quality: Based on rubric_relevance
    writing_levels = [p.get("rubric_relevance", {}).get("writing_quality", "none") for p in pages]
    if writing_levels:
        level_scores = {"high": 10, "med": 7, "low": 4, "none": 2}
        avg_score = sum(level_scores.get(level, 0) for level in writing_levels) / len(writing_levels)
        scores["writing_quality"]["points"] = round(avg_score)
        scores["writing_quality"]["comment"] = f"Average writing quality: {sum(1 for l in writing_levels if l == 'high')} high"
    
    # Group Integration: Based on rubric_relevance from intro/group_collab pages
    group_pages = [p for p in pages if p.get("page_role") in ["intro", "group_collab"]]
    if group_pages:
        group_levels = [p.get("rubric_relevance", {}).get("group_integration", "none") for p in group_pages]
        level_scores = {"high": 15, "med": 10, "low": 5, "none": 0}
        avg_score = sum(level_scores.get(level, 0) for level in group_levels) / len(group_levels) if group_levels else 0
        scores["group_integration"]["points"] = round(avg_score)
        scores["group_integration"]["comment"] = f"Found {len(group_pages)} group-related page(s)"
    else:
        scores["group_integration"]["points"] = 5
        scores["group_integration"]["comment"] = "No group integration pages found"
    
    return scores


@app.get("/api/calculate-grading-scores")
async def calculate_grading_scores_endpoint(jobId: str) -> Dict[str, Any]:
    """Calculate grading scores based on pages and issues metadata."""
    pages_file = get_job_file_path(jobId, "pages.json")
    issues_file = get_job_file_path(jobId, "issues.json")
    
    pages_data = load_json_file(pages_file, {})
    issues_data = load_json_file(issues_file, {})
    
    pages = pages_data.get("pages", []) if isinstance(pages_data, dict) else (pages_data if isinstance(pages_data, list) else [])
    issues = issues_data.get("issues", []) if isinstance(issues_data, dict) else (issues_data if isinstance(issues_data, list) else [])
    
    scores = calculate_grading_scores(pages, issues)
    
    # Load saved TA scores if they exist
    scores_file = PAGES_ISSUES_DIR / f"{jobId}_scores.json"
    if scores_file.exists():
        try:
            with open(scores_file, "r", encoding="utf-8") as f:
                saved_scores = json.load(f)
                # Merge saved TA scores with calculated scores
                for key in scores:
                    if key in saved_scores and "ta_points" in saved_scores[key]:
                        scores[key]["ta_points"] = saved_scores[key]["ta_points"]
                        scores[key]["ta_comment"] = saved_scores[key].get("ta_comment", "")
        except Exception as e:
            print(f"Error loading saved scores: {e}")
    
    return {"jobId": jobId, "scores": scores}


# ============================================================================
# LLM-based Final Scoring System
# ============================================================================

def get_rubric_brief() -> str:
    """Return a brief description of the rubric components with max points from rubric."""
    return """Rubric components with maximum points:
- Coverage (max 15 points): Count-based evaluation. Full marks for 10 heuristics AND 12+ distinct violations. Deduct points if fewer heuristics or violations.
- Violation Quality (max 20 points): Evaluated on heuristic violation pages. Clarity and depth of problem descriptions and user impact analysis.
- Severity Analysis (max 10 points): Evaluated on heuristic violation pages. How well they justify severity levels (minor/major/critical) and provide clear reasoning.
- Screenshots & Evidence (max 10 points): Evaluated on heuristic violation pages. How clearly screenshots/annotations support their claims. Annotations should be clear and informative.
- Structure & Navigation (max 10 points): Evaluated on heuristic violation pages. How well they analyze structural/navigation issues in the interface.
- Professional Quality (max 10 points): Evaluated on intro/group pages AND overall. Visual organization, slide layout, use of headings, color, spacing, overall presentation quality.
- Writing Quality (max 10 points): Evaluated on intro/group pages AND overall. Clarity, grammar, and structure of explanations. Text should be clear and well-organized.
- Group Integration (max 15 points): Evaluated ONLY on intro/group collaboration pages. Explanation of group collaboration, how work fits together, and division of responsibilities.

Bonus criteria (optional, evaluated based on overall quality):
- Bonus AI Opportunities (max 3 points): Thoughtful discussion of how AI could improve UX.
- Bonus Exceptional Quality (max 2 points): Work significantly exceeds expectations."""


def load_pages_for_job(job_id: str) -> List[Dict[str, Any]]:
    """Load pages.json for a given job."""
    pages_file = get_job_file_path(job_id, "pages.json")
    data = load_json_file(pages_file, {})
    # Handle both formats: {"pages": [...]} and [...]
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get("pages", [])
    return []


def load_issues_for_job(job_id: str) -> List[Dict[str, Any]]:
    """Load issues.json for a given job."""
    issues_file = get_job_file_path(job_id, "issues.json")
    data = load_json_file(issues_file, {})
    # Handle both formats: {"issues": [...]} and [...]
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get("issues", [])
    return []


def build_scoring_input(job_id: str, pages: List[Dict[str, Any]], issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build ScoringInput object from pages and issues."""
    scoring_issues = []
    for issue in issues:
        scoring_issue = {
            "issue_id": issue.get("issue_id", ""),
            "heuristic_id": issue.get("heuristic_id", ""),
            "title": issue.get("title", ""),
            "combined_description": issue.get("combined_description", ""),
            "pages_involved": issue.get("pages_involved", []),
            "ai_proposed_severity": issue.get("ai_proposed_severity", "major"),
            "ai_rubric_scores": issue.get("ai_rubric_scores"),  # Optional
        }
        # Add TA review if present
        if issue.get("ta_review"):
            ta_review = issue["ta_review"]
            scoring_issue["ta_review"] = {
                "final_severity": ta_review.get("final_severity", "major"),
                "final_issue_score_0_4": ta_review.get("final_score_0_4", 2),
                "rubric_overrides": ta_review.get("rubric_overrides"),  # Optional
                "override_reason": ta_review.get("override_reason", ""),
                "ta_comment": ta_review.get("ta_comment", ""),
            }
        scoring_issues.append(scoring_issue)
    
    # Count pages by role for metadata
    page_roles = {}
    for page in pages:
        role = page.get("page_role", "other")
        page_roles[role] = page_roles.get(role, 0) + 1
    
    # Count unique heuristics for coverage calculation
    unique_heuristics = set()
    for issue in issues:
        heuristic_id = issue.get("heuristic_id", "")
        if heuristic_id and not heuristic_id.startswith("Hx"):
            unique_heuristics.add(heuristic_id)
    
    # Collect AI opportunities pages
    ai_opportunities_pages = []
    for page in pages:
        if page.get("page_role") == "ai_opportunities" and page.get("ai_opportunities_info"):
            ai_info = page["ai_opportunities_info"]
            if ai_info.get("present") is True:
                ai_opportunities_pages.append({
                    "page_id": page.get("page_id", ""),
                    "llm_summary": ai_info.get("llm_summary", ""),
                    "raw_text_excerpt": ai_info.get("raw_text_excerpt", ""),
                    "relevance_to_violations": ai_info.get("relevance_to_violations", "low"),
                    "specificity": ai_info.get("specificity", "generic"),
                })
    
    # Collect pages with rubric_relevance for scoring guidance
    pages_for_scoring = []
    for page in pages:
        page_data = {
            "page_id": page.get("page_id", ""),
            "page_number": page.get("page_number", 0),
            "page_role": page.get("page_role", "other"),
            "has_annotations": page.get("has_annotations", "none"),  # CRITICAL for Screenshots & Evidence scoring
            "rubric_relevance": page.get("rubric_relevance", {}),
        }
        # Include main_heading if present
        if page.get("main_heading"):
            page_data["main_heading"] = page.get("main_heading")
        # Include text content for Professional Quality and Writing Quality evaluation
        if page.get("page_role") in ["intro", "group_collab"]:
            page_data["llm_summary"] = page.get("llm_summary", "")
            page_data["raw_text_excerpt"] = page.get("raw_text_excerpt", "")
        pages_for_scoring.append(page_data)
    
    result = {
        "job_id": job_id,
        "rubric_brief": get_rubric_brief(),
        "submission_meta": {
            "num_pages": len(pages),
            "num_issues": len(issues),
            "num_heuristics": len(unique_heuristics),
            "page_roles": page_roles,  # e.g., {"violation_detail": 8, "intro": 1, "group_collab": 1}
        },
        "issues": scoring_issues,
        "pages": pages_for_scoring,  # Include pages with rubric_relevance for scoring guidance
    }
    
    # Only include ai_opportunities_pages if there are any
    if ai_opportunities_pages:
        result["ai_opportunities_pages"] = ai_opportunities_pages
    
    return result


async def call_grading_llm(scoring_input: Dict[str, Any], job_id: str = None) -> str:
    """Call LLM with grading prompt and return JSON response."""
    if not MODEL:
        raise HTTPException(status_code=500, detail="Gemini model not initialized. Please set GEMINI_API_KEY.")
    
    # Load rubric component comments if job_id is provided
    rubric_comments_text = ""
    if job_id:
        rubric_comments_file = PAGES_ISSUES_DIR / f"{job_id}_rubric_comments.json"
        if rubric_comments_file.exists():
            try:
                with open(rubric_comments_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    rubric_comments = data.get("comments", {})
                    if rubric_comments:
                        rubric_comments_text = "\n\n**TA RUBRIC COMPONENT COMMENTS:**\n"
                        for component, comment in rubric_comments.items():
                            if comment and comment.strip():
                                # Only include comments that are detailed enough (60+ chars)
                                if len(comment.strip()) >= 60:
                                    rubric_comments_text += f"- **{component}**: {comment.strip()}\n"
                                elif len(comment.strip()) >= 25:
                                    rubric_comments_text += f"- **{component}**: {comment.strip()} (Note: Consider elaborating for better clarity)\n"
            except Exception as e:
                print(f"[WARN] Could not load rubric comments: {e}")
    
    # Load the modularized grading prompt from file
    grading_prompt_content = get_current_prompt()
    
    # Replace the placeholder for ScoringInput JSON
    if "{json.dumps(scoring_input, indent=2)}" in grading_prompt_content:
        # Inject rubric comments before ScoringInput if present
        if rubric_comments_text:
            # Find the position where ScoringInput JSON should be inserted
            placeholder = "{json.dumps(scoring_input, indent=2)}"
            prompt = grading_prompt_content.replace(
                placeholder,
                rubric_comments_text + "\n\n" + json.dumps(scoring_input, indent=2)
            )
        else:
            prompt = grading_prompt_content.replace(
                "{json.dumps(scoring_input, indent=2)}",
                json.dumps(scoring_input, indent=2)
            )
    else:
        # Fallback to old prompt structure if file doesn't have the new format
        # Use the old prompt structure as fallback
        prompt = f"""You are grading a heuristic evaluation assignment for a UX/HCI course.

{get_rubric_brief()}

IMPORTANT EVALUATION RULES:
1. Coverage: Use submission_meta.num_heuristics and submission_meta.num_issues to score:
   - 10 heuristics AND 12+ issues → 15 points
   - 9-10 heuristics AND 10-11 issues → 12 points
   - 8-9 heuristics OR 8-9 issues → 8 points
   - Less than 8 heuristics OR less than 8 issues → 5 points or less

**CRITICAL: AGGREGATION STRATEGY FOR COMPONENT SCORES**

For components evaluated across multiple issues/pages (Violation Quality, Severity Analysis, Screenshots & Evidence, Structure & Navigation), you must use the **MINIMUM RULE** to combine scores:

- **Final component score = minimum score observed across all issues/pages (bounded by max)**
- If all issues/pages have max score → give max
- Otherwise, final score = min(individual scores) from all issues/pages
- This ensures that one weak issue/page cannot be compensated by strong ones

**Example:**
- Issue 1: Violation Quality = 18/20
- Issue 2: Violation Quality = 15/20
- Issue 3: Violation Quality = 20/20
- **Final Violation Quality = 15/20** (minimum of 18, 15, 20)

This aggregation strategy applies to:
- Violation Quality (max 20)
- Severity Analysis (max 10)
- Screenshots & Evidence (max 10)
- Structure & Navigation (max 10)

2. Heuristic Pages (violation_detail pages): Evaluate these components:
   
   **Violation Quality (max 20 points):** Evaluate based on clarity, depth, and cognitive reasoning in problem descriptions.
   
   CRITICAL EVALUATION CRITERIA:
   - **Explicit connection to user impacts**: Descriptions should explicitly connect problems to measurable user impacts or contextual user goals. Deduct points if descriptions are vague or lack concrete impact statements.
   - **Cognitive mechanism analysis**: This is VERY IMPORTANT. Analysis must elaborate on cognitive mechanisms behind frustration or confusion (e.g., cognitive load, error tolerance, memory constraints, perception issues). Deduct significantly if analysis only uses surface-level descriptions like "confusing" or "frustrating" without connecting to core UX principles or cognitive mechanisms.
   - **Breakdown analysis**: Must discuss why issues cause breakdowns in perception, memory, or action. Deduct points if this is missing.
   - **Severity rating accuracy**: Some severity ratings may be inflated (many marked "major" even when impact = mild). Evaluate whether severity ratings are justified based on actual impact.
   - **Depth vs. surface-level**: Deduct points if analysis leans on surface-level description without deeper articulation of cognitive cost or UX principles.
   - **Cosmetic vs. heuristic issues**: Distinguish between cosmetic issues (e.g., card spacing) and true heuristic mismatches. Minor cosmetic issues should not be treated as major violations.
   
   Scoring guidance:
   - 18-20: Excellent cognitive reasoning, explicit user impact connections, accurate severity ratings, deep UX principle analysis
   - 15-17: Good analysis with cognitive reasoning present, may have minor gaps in explicit impact connections or slight severity inflation. This is a strong score for solid work.
   - 12-14: Adequate descriptions with some cognitive mechanisms mentioned, may lack explicit impact connections but shows understanding of UX principles
   - 10-11: Basic descriptions with minimal cognitive reasoning, some surface-level analysis but demonstrates understanding
   - 8-9: Surface-level descriptions without much cognitive reasoning, but still identifies valid issues
   - 0-7: Poor quality, minimal analysis, no cognitive reasoning, mostly cosmetic issues
   
   **Severity Analysis (max 10 points):** Evaluate based on justification of severity levels and transparency of severity weighting.
   
   CRITICAL EVALUATION CRITERIA:
   - **Severity scale explanation**: It would be helpful to include a one-sentence explanation of how the 1–4 scale (or minor/major/critical scale) was applied (e.g., impact × frequency × persistence) to make severity weighting more transparent. If this explanation is missing, consider it a minor gap but don't deduct heavily (maybe 0.5-1 point).
   - **Rationale for severity**: Should include a short rationale connecting frequency of occurrence or user impact to severity to demonstrate nuanced prioritization. If severity is assigned with basic justification (even if not detailed), that's acceptable.
   - **Beyond "confusing" or "frustrating"**: Severity reasoning should go beyond just saying "confusing" or "frustrating" - should explain WHY it's confusing/frustrating and how that relates to severity. However, if there's some reasoning even if not fully detailed, that's acceptable.
   
   Scoring guidance:
   - 10: Clear severity scale explanation, detailed rationale connecting impact/frequency to severity
   - 9: Good rationale provided, may be missing scale explanation but has clear impact connection
   - 8: Basic severity assignment with some rationale, may lack detailed explanation but shows understanding
   - 7-8: Severity assigned with basic justification, demonstrates understanding of severity concepts
   - 6-7: Minimal severity reasoning but still attempts to justify severity levels
   - 0-5: No clear severity reasoning or missing severity analysis
   
   **Screenshots & Evidence (max 10 points):** Evaluate based on annotation quality, readability, and effectiveness as communication tools.
   
   CRITICAL EVALUATION CRITERIA:
   - **Readability**: Some notes may be barely readable. Deduct points for poor readability (small font, low contrast, unclear handwriting).
   - **Consistency**: Inconsistent font size across annotations reduces professionalism. Deduct points for inconsistency.
   - **Communication tool vs. personal sketch**: Notes should be used as communication tools, not personal sketches. Deduct points if annotations are too informal or unclear for others to understand.
   - **Minimal annotation**: Minimal notes and annotations to communicate the problem reduce effectiveness. Deduct points if annotations are too sparse or don't clearly indicate the problem.
   - **Clear problem indication**: Annotations should clearly point to and explain the problem. Deduct points if annotations are vague or don't connect to the described issue.
   
   Scoring guidance:
   - 10: Clear, readable, consistent annotations that effectively communicate problems
   - 9: Good annotations but may have minor readability or consistency issues
   - 8-9: Adequate annotations but readability or consistency problems, or minimal annotation
   - 7: Poor readability, inconsistent, or annotations used more as personal sketches
   - 6: Barely readable, minimal annotation, or annotations don't communicate problems effectively
   
   **Structure & Navigation (max 10 points):** Based on analysis of structural issues in the interface.

3. Intro/Group Pages: Evaluate these components:
   
   **Professional Quality (max 10 points):** Visual organization, presentation, and layout quality.
   
   CRITICAL EVALUATION CRITERIA:
   - **Background distraction**: Background could be distracting sometimes (not contributing to information and communication). Deduct points if background has:
     * High color contrast that interferes with readability
     * Meaningless icon decorations that don't support content
     * Patterns or images that compete with text for attention
   - **Layout organization**: Layout could be more organized. Deduct points for:
     * Poor spacing between elements
     * Lack of clear grid structure
     * Misaligned elements
     * Inconsistent margins or padding
   - **Visual hierarchy**: Should use headings, color, spacing to create clear information hierarchy. Deduct points if hierarchy is unclear.
   
   Scoring guidance:
   - 10: Well-organized layout, clear hierarchy, non-distracting background, consistent spacing and alignment
   - 10: Good organization with minor spacing or alignment issues
   - 8-9: Adequate layout but some organization problems or slightly distracting background
   - 7: Poor spacing, misalignment, or distracting background elements
   - 6: Very disorganized layout, highly distracting background, or major visual problems
   
   **Writing Quality (max 10 points):** Clarity, grammar, and structure of explanations.
   
   CRITICAL EVALUATION CRITERIA:
   - **Grammar errors**: Deduct points for grammar errors, spelling mistakes, or unclear sentence structure.
   - **Clarity**: Text should be clear and well-organized. Deduct points if explanations are confusing or poorly structured.
   - **Professional tone**: Writing should be professional and appropriate for academic work. Deduct points for overly casual or unprofessional language.
   
   Scoring guidance:
   - 10: Clear, well-written, no grammar errors, professional tone
   - 9: Good writing with minor grammar issues or occasional unclear sentences
   - 7-8: Adequate writing but some grammar errors or clarity issues
   - 5-6: Multiple grammar errors, unclear explanations, or unprofessional tone
   - 5: Many grammar errors, very unclear writing, or highly unprofessional
   
   **Group Integration (max 15 points):** ONLY evaluated here, not on heuristic pages. Explanation of group collaboration, how work fits together, and division of responsibilities.
   
   IMPORTANT: When evaluating Group Integration, consider using the rubric_relevance information from pages. If a page contains group integration content (page_role is "intro" or "group_collab"), check the rubric_relevance.group_integration field to help guide your scoring:
   - If ANY page has rubric_relevance.group_integration = "high" → award full points (15)
   - "med": Page mentions group collaboration but may lack detail → award moderate points (14)
   - "low": Page has minimal group integration content → award lower points (13)
   - "none": Page doesn't address group integration → award minimal or no points (12)
   
   Use the rubric_relevance.group_integration values from intro/group_collab pages to inform your scoring decision. If any page shows "high" relevance, give full marks (15 points).

4. Overall Evaluation: Professional Quality and Writing Quality should also consider the entire submission holistically.

5. Bonus Scores:
   - Bonus AI Opportunities (max 3): Evaluate based on ai_opportunities_pages if provided. See detailed criteria below.
   - Bonus Exceptional Quality (max 2): If work significantly exceeds expectations (typically only if overall_score_0_100 is high, 97+)

You will receive a JSON object called "ScoringInput" describing all issues found in a student's submission. For each issue, you can see:
- heuristic_id, title, combined_description
- AI proposed severity and AI rubric scores (if present)
- TA review overrides (final severity, per-component scores, comments), when available

The ScoringInput may also include an optional "ai_opportunities_pages" array. This contains pages where students discuss how AI could help address the usability issues they found.

Use the TA review when present as the primary truth.
Use AI scores only to fill gaps when the TA did not review an issue.

BONUS - AI OPPORTUNITIES (0-3 points):
This is an optional bonus component. Some students include an "AI Opportunities" page describing how AI could help fix the problems they found on the Julian site.

Scoring criteria:
- 0 points: No meaningful AI discussion OR AI ideas are generic/unrelated to the actual usability issues. If no ai_opportunities_pages are provided, set to 0.
- 1 point: Mentions AI in a somewhat relevant way, but ideas are shallow or only loosely tied to specific violations. Low relevance_to_violations or generic specificity.
- 2 points: Reasonable, specific AI ideas clearly tied to some violations and user experience improvements. Medium to high relevance_to_violations, somewhat_specific to very_specific.
- 3 points: Outstanding, well-motivated AI proposals tightly linked to the violations, realistic in terms of what AI can do, and clearly improve the user experience. High relevance_to_violations and very_specific specificity. Ideas should be concrete and plausible (e.g., "AI-driven skeleton screens for slow loading product pages", "AI-powered form validation", "adaptive filters based on user preferences").

Use the ai_opportunities_pages array (if provided) to evaluate:
- relevance_to_violations: How well the AI ideas connect to specific violations found
- specificity: How concrete and plausible the AI proposals are
- llm_summary and raw_text_excerpt: The actual content of the AI opportunities discussion

If ai_opportunities_pages is not provided or is empty, set bonus_ai_opportunities to 0 points and explain that no bonus content was provided.
Based on ALL issues and their scores, compute:

- A final overall_score_0_100 (integer, 0-100, including bonus if applicable).
- For each rubric component, return points (0 to max), max value, and explanation:
  - coverage: {{"points": <0-15>, "max": 15, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
  - violation_quality: {{"points": <0-20>, "max": 20, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
  - severity_analysis: {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
  - screenshots_evidence: {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
  - structure_navigation: {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
  - professional_quality: {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
  - writing_quality: {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
  - group_integration: {{"points": <0-15>, "max": 15, "explanation": "<1-2 sentences explaining why points were deducted or awarded>"}}
- Optional bonus_scores (only if applicable):
  - bonus_ai_opportunities: {{"points": <0-3>, "max": 3, "explanation": "<optional explanation>"}}
  - bonus_exceptional_quality: {{"points": <0-1>, "max": 1, "explanation": "<optional explanation>"}}
- A short summary_comment (2–4 sentences).

IMPORTANT: For each rubric component, the explanation should clearly state:
- If points were deducted, explain WHY (e.g., "Missing annotations on screenshots", "Insufficient coverage of heuristics", "Poor severity justification")
- If full points were awarded, briefly explain WHY (e.g., "All 10 heuristics covered with detailed analysis", "Clear annotations on all screenshots")
- Be specific and reference the actual issues/pages when explaining deductions.

Return **ONLY** a valid JSON object matching this structure:
{{
  "overall_score_0_100": <integer 0-100>,
  "rubric_scores": {{
    "coverage": {{"points": <0-15>, "max": 15, "explanation": "<1-2 sentences>"}},
    "violation_quality": {{"points": <0-20>, "max": 20, "explanation": "<1-2 sentences>"}},
    "severity_analysis": {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences>"}},
    "screenshots_evidence": {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences>"}},
    "structure_navigation": {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences>"}},
    "professional_quality": {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences>"}},
    "writing_quality": {{"points": <0-10>, "max": 10, "explanation": "<1-2 sentences>"}},
    "group_integration": {{"points": <0-15>, "max": 15, "explanation": "<1-2 sentences>"}}
  }},
  "bonus_scores": {{
    "bonus_ai_opportunities": {{"points": <0-3>, "max": 3, "explanation": "<optional>"}},
    "bonus_exceptional_quality": {{"points": <0-2>, "max": 2, "explanation": "<optional>"}}
  }},
  "summary_comment": "<2-4 sentences>",
  "ai_vs_ta_notes": "<optional notes about differences>"
}}

Do not include any extra text or explanation outside the JSON object.

The ScoringInput JSON contains:
1. **Issues array**: Issue-level aggregated data (heuristic_id, title, combined_description, pages_involved, ai_proposed_severity, and optional TA review overrides)
2. **Submission metadata**: Overall statistics (num_pages, num_issues, num_heuristics, page_roles distribution)
3. **AI opportunities pages** (optional): Pages where students discuss how AI could help address UX issues

{rubric_comments_text if rubric_comments_text else ""}

Now here is the ScoringInput JSON:

```json
{json.dumps(scoring_input, indent=2)}
```
"""
    
    try:
        # Use minimal temperature for maximum consistency
        # Note: Gemini may round very low temperatures to 0, which is fine for deterministic scoring
        generation_config = {
            "temperature": 0.0,  # Set to 0 for maximum determinism and consistency - same input should produce same output
            "max_output_tokens": 16384,  # Increased significantly for detailed grading responses with explanations (prompt is ~6800 tokens)
            "response_mime_type": "application/json",
        }
        
        # Add top_p if supported (helps reduce randomness further)
        try:
            generation_config["top_p"] = 0.95
        except:
            pass  # Ignore if not supported
        
        response = MODEL.generate_content(prompt, generation_config=generation_config)
        
        # Extract response text with detailed error diagnostics
        response_text = None
        error_details = []
        
        # Check for safety filters or blocked content first
        if hasattr(response, 'prompt_feedback'):
            if response.prompt_feedback:
                if hasattr(response.prompt_feedback, 'block_reason'):
                    if response.prompt_feedback.block_reason:
                        error_details.append(f"Prompt blocked: {response.prompt_feedback.block_reason}")
        
        # Check candidates for finish reasons and safety ratings
        max_tokens_detected = False
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'finish_reason'):
                finish_reason = candidate.finish_reason
                if finish_reason and finish_reason != 1:  # 1 = STOP (normal)
                    finish_reason_map = {
                        0: "FINISH_REASON_UNSPECIFIED",
                        2: "MAX_TOKENS",
                        3: "SAFETY",
                        4: "RECITATION",
                        5: "OTHER"
                    }
                    reason = finish_reason_map.get(finish_reason, f"Unknown ({finish_reason})")
                    error_details.append(f"Finish reason: {reason}")
                    
                    # Track MAX_TOKENS for special handling
                    if finish_reason == 2:  # MAX_TOKENS
                        max_tokens_detected = True
            
            # Check safety ratings
            if hasattr(candidate, 'safety_ratings'):
                if candidate.safety_ratings:
                    blocked_categories = []
                    for rating in candidate.safety_ratings:
                        if hasattr(rating, 'blocked') and rating.blocked:
                            category = getattr(rating, 'category', 'UNKNOWN')
                            blocked_categories.append(str(category))
                    if blocked_categories:
                        error_details.append(f"Content blocked by safety filters: {', '.join(blocked_categories)}")
        
        # Method 1: Try response.text (standard method)
        try:
            response_text = response.text
            # Even if MAX_TOKENS, we might have partial response
            if max_tokens_detected and response_text and len(response_text.strip()) > 50:
                print(f"[WARNING] Got partial response due to MAX_TOKENS (length: {len(response_text)})")
        except (ValueError, AttributeError) as e:
            error_details.append(f"Method 1 (response.text) failed: {type(e).__name__}: {str(e)}")
        
        # Method 2: If that fails, try to extract from candidates directly
        if not response_text and response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            try:
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts') and candidate.content.parts:
                        parts_text = []
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                parts_text.append(part.text)
                        if parts_text:
                            response_text = "".join(parts_text)
                            if max_tokens_detected and response_text and len(response_text.strip()) > 50:
                                print(f"[WARNING] Got partial response from candidates due to MAX_TOKENS (length: {len(response_text)})")
            except Exception as e:
                error_details.append(f"Method 2 (candidates.parts) failed: {type(e).__name__}: {str(e)}")
        
        # Method 3: Try to get any text from the response object
        if not response_text:
            try:
                # Try accessing the response as a string
                response_text = str(response)
                # If it's just the object representation, try candidates again
                if response_text.startswith('<') or 'object at' in response_text:
                    response_text = None  # Reset if it's just object representation
                    if response.candidates:
                        for candidate in response.candidates:
                            try:
                                if hasattr(candidate, 'content'):
                                    content_str = str(candidate.content)
                                    if content_str and len(content_str) > 50 and not content_str.startswith('<'):
                                        response_text = content_str
                                        break
                            except Exception:
                                continue
            except Exception as e:
                error_details.append(f"Method 3 (str conversion) failed: {type(e).__name__}: {str(e)}")
        
        # If we still don't have text, create a meaningful error response
        if not response_text or len(response_text.strip()) < 10:
            error_msg = "Could not extract text from Gemini response"
            if error_details:
                error_msg += f". Details: {'; '.join(error_details)}"
            else:
                error_msg += ". Response structure may have changed or content was filtered."
            
            # Check if it's a MAX_TOKENS issue
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'finish_reason'):
                    finish_reason = candidate.finish_reason
                    if finish_reason == 2:  # MAX_TOKENS
                        error_msg = "Response was truncated due to MAX_TOKENS limit. The grading response exceeded 16384 tokens."
                        # Try to get usage metadata if available
                        if hasattr(response, 'usage_metadata'):
                            usage = response.usage_metadata
                            prompt_tokens = getattr(usage, 'prompt_token_count', None)
                            total_tokens = getattr(usage, 'total_token_count', None)
                            if prompt_tokens:
                                error_msg += f" Prompt tokens: {prompt_tokens}"
                            if total_tokens:
                                error_msg += f" Total tokens: {total_tokens}"
                        error_msg += " The response may be too complex. Consider reducing the number of issues or simplifying the prompt."
            
            print(f"[ERROR] Grading LLM: {error_msg}")
            print(f"[DEBUG] Response object type: {type(response)}")
            print(f"[DEBUG] Response has candidates: {hasattr(response, 'candidates') and response.candidates}")
            if hasattr(response, 'candidates') and response.candidates:
                print(f"[DEBUG] First candidate type: {type(response.candidates[0])}")
                print(f"[DEBUG] First candidate finish_reason: {getattr(response.candidates[0], 'finish_reason', 'N/A')}")
                if hasattr(response, 'usage_metadata'):
                    usage = response.usage_metadata
                    print(f"[DEBUG] Usage metadata: {usage}")
            
            raise ValueError(error_msg)
        
        return response_text
    except ValueError as e:
        # Re-raise ValueError with detailed message
        print(f"[ERROR] Grading LLM ValueError: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to call LLM for grading: {str(e)}")
    except Exception as e:
        print(f"[ERROR] Error calling grading LLM: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to call LLM for grading: {str(e)}")


def parse_scoring_output(raw: str) -> Dict[str, Any]:
    """Parse LLM JSON response into ScoringOutput and normalize structure."""
    try:
        # Clean up the response text - remove markdown code fences if present
        cleaned_raw = raw.strip()
        if cleaned_raw.startswith("```json"):
            cleaned_raw = cleaned_raw[7:].strip()
        if cleaned_raw.startswith("```"):
            cleaned_raw = cleaned_raw[3:].strip()
        if cleaned_raw.endswith("```"):
            cleaned_raw = cleaned_raw[:-3].strip()
        
        # Try direct JSON parsing
        output = json.loads(cleaned_raw)
        
        # Validate structure with detailed error messages
        # Accept both 'overall_score_0_100' and 'total_score' as valid field names
        if "overall_score_0_100" not in output and "total_score" not in output:
            available_keys = list(output.keys()) if isinstance(output, dict) else "Not a dict"
            error_msg = f"Missing 'overall_score_0_100' or 'total_score' in response. Available keys: {available_keys}"
            print(f"[ERROR] Parse scoring output: {error_msg}")
            print(f"[DEBUG] Response preview (first 500 chars): {cleaned_raw[:500]}")
            raise ValueError(error_msg)
        
        # Normalize field name: if 'total_score' exists but 'overall_score_0_100' doesn't, use 'total_score'
        if "overall_score_0_100" not in output and "total_score" in output:
            output["overall_score_0_100"] = output["total_score"]
            print(f"[INFO] Using 'total_score' ({output['total_score']}) as 'overall_score_0_100'")
        if "rubric_scores" not in output:
            available_keys = list(output.keys()) if isinstance(output, dict) else "Not a dict"
            error_msg = f"Missing 'rubric_scores' in response. Available keys: {available_keys}"
            print(f"[ERROR] Parse scoring output: {error_msg}")
            print(f"[DEBUG] Response preview (first 500 chars): {cleaned_raw[:500]}")
            raise ValueError(error_msg)
        
        # Normalize rubric_scores structure - ensure each has {points, max, explanation}
        rubric_scores = output.get("rubric_scores", {})
        max_points = {
            "coverage": 15,
            "violation_quality": 20,
            "severity_analysis": 10,
            "screenshots_evidence": 10,
            "structure_navigation": 10,
            "professional_quality": 10,
            "writing_quality": 10,
            "group_integration": 15,
        }
        
        normalized_rubric = {}
        for key, max_val in max_points.items():
            if key in rubric_scores:
                value = rubric_scores[key]
                if isinstance(value, dict) and "points" in value:
                    normalized_rubric[key] = {
                        "points": value.get("points", 0),
                        "max": value.get("max", max_val),
                        "explanation": value.get("explanation", "No explanation provided.")
                    }
                elif isinstance(value, (int, float)):
                    # Legacy format: just a number, convert to {points, max, explanation}
                    normalized_rubric[key] = {
                        "points": int(value),
                        "max": max_val,
                        "explanation": "No explanation provided."
                    }
                else:
                    normalized_rubric[key] = {"points": 0, "max": max_val, "explanation": "No explanation provided."}
            else:
                normalized_rubric[key] = {"points": 0, "max": max_val, "explanation": "No explanation provided."}

        # Enforce integer scores for all components except Screenshots & Evidence
        # Only Screenshots & Evidence is allowed to have 0.5-style granular deductions.
        for key, score in normalized_rubric.items():
            if key != "screenshots_evidence":
                try:
                    score_points = float(score.get("points", 0))
                    score["points"] = int(round(score_points))
                except (TypeError, ValueError):
                    # If parsing fails, fall back to 0 to avoid breaking the pipeline
                    score["points"] = int(score.get("points", 0) or 0)

        output["rubric_scores"] = normalized_rubric
        
        # Normalize bonus_scores if present
        if "bonus_scores" in output:
            bonus_scores = output["bonus_scores"]
            bonus_max = {
                "bonus_ai_opportunities": 3,
                "bonus_exceptional_quality": 2,
            }
            normalized_bonus = {}
            for key, max_val in bonus_max.items():
                if key in bonus_scores:
                    value = bonus_scores[key]
                    if isinstance(value, dict) and "points" in value:
                        normalized_bonus[key] = {
                            "points": value.get("points", 0),
                            "max": value.get("max", max_val),
                            "explanation": value.get("explanation", "")
                        }
                    elif isinstance(value, (int, float)):
                        normalized_bonus[key] = {
                            "points": int(value),
                            "max": max_val,
                            "explanation": ""
                        }
                    else:
                        normalized_bonus[key] = {"points": 0, "max": max_val, "explanation": ""}
                else:
                    normalized_bonus[key] = {"points": 0, "max": max_val, "explanation": ""}
            output["bonus_scores"] = normalized_bonus
        
        return output
    except json.JSONDecodeError as e:
        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if json_match:
            try:
                output = json.loads(json_match.group(1))
                # Re-validate after extraction
                if "overall_score_0_100" not in output:
                    raise ValueError(f"Missing 'overall_score_0_100' in extracted JSON. Available keys: {list(output.keys()) if isinstance(output, dict) else 'Not a dict'}")
                if "rubric_scores" not in output:
                    raise ValueError(f"Missing 'rubric_scores' in extracted JSON. Available keys: {list(output.keys()) if isinstance(output, dict) else 'Not a dict'}")
                # Continue with normalization if extraction succeeded
                # (normalization code continues below)
            except (json.JSONDecodeError, ValueError) as e2:
                print(f"[ERROR] Failed to parse JSON even after extracting from code block: {e2}")
                print(f"[DEBUG] Raw response (first 1000 chars): {raw[:1000]}")
                raise ValueError(f"Could not parse JSON from LLM response: {str(e2)}")
        else:
            print(f"[ERROR] JSON decode error: {e}")
            print(f"[DEBUG] Raw response (first 1000 chars): {raw[:1000]}")
            raise ValueError(f"Could not parse JSON from LLM response: {str(e)}")
        # Try to extract JSON from markdown code blocks
        json_block_match = re.search(r'```(?:json)?\s*(\{.*?)\s*```', raw, re.DOTALL)
        if json_block_match:
            json_str = json_block_match.group(1)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object directly
        json_start = raw.find('{')
        if json_start != -1:
            json_str = raw[json_start:]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Provide detailed error information
        error_msg = f"Could not parse JSON from LLM response: {str(e)}"
        
        # Include first 500 chars of raw response for debugging
        raw_preview = raw[:500] if raw else "(empty response)"
        error_msg += f"\n\nRaw response preview (first 500 chars):\n{raw_preview}"
        
        # Check if response is empty
        if not raw or len(raw.strip()) == 0:
            error_msg += "\n\nERROR: Response is completely empty. This may indicate the LLM did not generate any output."
        
        # Check if response looks like HTML or error message
        if raw and ("<html" in raw.lower() or "<!doctype" in raw.lower()):
            error_msg += "\n\nERROR: Response appears to be HTML instead of JSON. This may indicate an API error."
        
        # Log the full response for debugging (truncated to 2000 chars)
        print(f"[ERROR] Full LLM response (truncated to 2000 chars):\n{raw[:2000]}")
        
        raise ValueError(error_msg)


def save_job_scoring(job_id: str, scoring_output: Dict[str, Any]) -> None:
    """Save scoring output to disk."""
    scoring_file = get_job_file_path(job_id, "scoring.json")
    data = {
        "job_id": job_id,
        "scoring": scoring_output,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }
    save_json_file(scoring_file, data)


def compare_scoring_changes(old_scoring: Dict[str, Any], new_scoring: Dict[str, Any]) -> Dict[str, Any]:
    """Compare old and new scoring outputs and generate a summary of changes."""
    changes = {
        "overall_score_change": None,
        "component_changes": [],
        "bonus_changes": [],
    }
    
    # Compare overall score
    old_overall = old_scoring.get("overall_score_0_100", 0)
    new_overall = new_scoring.get("overall_score_0_100", 0)
    if old_overall != new_overall:
        changes["overall_score_change"] = {
            "old": old_overall,
            "new": new_overall,
            "delta": new_overall - old_overall,
        }
    
    # Compare rubric scores
    old_rubric = old_scoring.get("rubric_scores", {})
    new_rubric = new_scoring.get("rubric_scores", {})
    
    for key in set(list(old_rubric.keys()) + list(new_rubric.keys())):
        old_score = old_rubric.get(key, {})
        new_score = new_rubric.get(key, {})
        
        old_points = old_score.get("points", 0) if isinstance(old_score, dict) else old_score
        new_points = new_score.get("points", 0) if isinstance(new_score, dict) else new_score
        
        if old_points != new_points:
            changes["component_changes"].append({
                "component": key,
                "old": old_points,
                "new": new_points,
                "delta": new_points - old_points,
            })
    
    # Compare bonus scores
    old_bonus = old_scoring.get("bonus_scores", {})
    new_bonus = new_scoring.get("bonus_scores", {})
    
    for key in set(list(old_bonus.keys()) + list(new_bonus.keys())):
        old_score = old_bonus.get(key, {})
        new_score = new_bonus.get(key, {})
        
        old_points = old_score.get("points", 0) if isinstance(old_score, dict) else old_score
        new_points = new_score.get("points", 0) if isinstance(new_score, dict) else new_score
        
        if old_points != new_points:
            changes["bonus_changes"].append({
                "component": key,
                "old": old_points,
                "new": new_points,
                "delta": new_points - old_points,
            })
    
    return changes


async def generate_improved_prompt_from_reviews(
    job_id: str,
    old_scoring: Dict[str, Any],
    new_scoring: Dict[str, Any],
    issues: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Analyze TA feedback and generate small, targeted improvements to the grading prompt."""
    if not MODEL:
        return None
    
    # Collect TA review comments from issues
    ta_feedback = []
    for issue in issues:
        if issue.get("ta_review"):
            ta_review = issue["ta_review"]
            feedback_item = {
                "issue_id": issue.get("issue_id", ""),
                "heuristic_id": issue.get("heuristic_id", ""),
                "title": issue.get("title", ""),
            }
            if ta_review.get("override_reason"):
                feedback_item["override_reason"] = ta_review["override_reason"]
            if ta_review.get("ta_comment"):
                feedback_item["ta_comment"] = ta_review["ta_comment"]
            if feedback_item.get("override_reason") or feedback_item.get("ta_comment"):
                ta_feedback.append(feedback_item)
    
    # Load rubric component comments
    rubric_comments = {}
    rubric_comments_file = PAGES_ISSUES_DIR / f"{job_id}_rubric_comments.json"
    if rubric_comments_file.exists():
        try:
            with open(rubric_comments_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                rubric_comments = data.get("comments", {})
        except Exception as e:
            print(f"[WARN] Could not load rubric comments: {e}")
    
    # Calculate changes
    overall_change = new_scoring.get('overall_score_0_100', 0) - old_scoring.get('overall_score_0_100', 0)
    
    # Build prompt for LLM to analyze issues and suggest small improvements
    ta_feedback_text = ""
    if ta_feedback:
        ta_feedback_text = "\n\nTA REVIEW FEEDBACK FROM ISSUES:\n"
        for i, feedback in enumerate(ta_feedback, 1):
            ta_feedback_text += f"\n{i}. {feedback.get('heuristic_id')} - {feedback.get('title', 'N/A')}:\n"
            if feedback.get("override_reason"):
                ta_feedback_text += f"   Override Reason: {feedback['override_reason']}\n"
            if feedback.get("ta_comment"):
                ta_feedback_text += f"   TA Comment: {feedback['ta_comment']}\n"
    else:
        ta_feedback_text = "\n\nTA REVIEW FEEDBACK: No TA reviews found on individual issues.\n"
    
    rubric_comments_text = ""
    if rubric_comments:
        rubric_comments_text = "\n\nTA RUBRIC COMPONENT COMMENTS:\n"
        for component, comment in rubric_comments.items():
            if comment and comment.strip():
                rubric_comments_text += f"- {component}: {comment}\n"
    else:
        rubric_comments_text = "\n\nTA RUBRIC COMPONENT COMMENTS: No rubric component comments found.\n"
    
    # Load current grading prompt
    # Use the same path as defined in the file
    grading_prompt_path = Path(__file__).parent.parent / "output_static" / "grading_prompt.txt"
    current_prompt = ""
    if grading_prompt_path.exists():
        try:
            with open(grading_prompt_path, "r", encoding="utf-8") as f:
                current_prompt = f.read().strip()
        except Exception as e:
            print(f"[WARNING] Failed to load grading_prompt.txt: {e}")
            current_prompt = ""
    
    prompt = f"""You are analyzing TA feedback to identify what needs to be improved in the grading prompt.

CONTEXT:
- Old score (with TA reviews): {old_scoring.get('overall_score_0_100', 0)}/100
- New score (after clearing TA reviews): {new_scoring.get('overall_score_0_100', 0)}/100
- Score change: {overall_change:+d} points
{ta_feedback_text}
{rubric_comments_text}

OLD SCORING DETAILS:
{json.dumps(old_scoring, indent=2)}

NEW SCORING DETAILS:
{json.dumps(new_scoring, indent=2)}

CURRENT GRADING PROMPT:
{current_prompt}

Your task:
1. Analyze the TA feedback (override reasons, TA comments, and rubric component comments) to understand what the TA found wrong or missing in the AI's grading.
2. Summarize the key problems: What patterns do you see in how the AI's grading differs from TA expectations based on their actual feedback?
3. Suggest MINOR, targeted improvements: Provide 2-4 small, specific changes to the grading prompt that would better align AI grading with TA expectations, based on the actual TA feedback provided above.
4. DO NOT rewrite the entire prompt. Only suggest small, focused modifications to specific sections.
5. Focus on the specific issues mentioned in the TA feedback.
6. After providing suggestions, APPLY these improvements to the current prompt and return the FULL MODIFIED PROMPT.

Return a JSON object with this structure:
{{
  "problems_summary": "1-2 sentences summarizing the main issues based on TA feedback",
  "suggested_improvements": [
    {{
      "section": "Which section of the prompt (e.g., 'Section 3.2 Violation Quality', 'Section 3.3 Severity Analysis')",
      "current_text": "The exact current text that needs modification (quote 2-4 lines from the prompt)",
      "suggested_change": "The exact replacement text (1-3 sentences, minimal change)",
      "rationale": "Why this change would help based on TA feedback (1 sentence)"
    }}
  ],
  "modified_prompt": "The FULL grading prompt with all suggested improvements applied. This must be the complete, valid prompt that can be saved directly to grading_prompt.txt. Make MINIMAL changes - only modify the specific sections mentioned in suggested_improvements, keeping everything else exactly the same."
}}

CRITICAL REQUIREMENTS FOR modified_prompt:
- Keep ALL sections intact (Section 0, 1, 2, 3, 3B, 4, 5, 6)
- Only modify the specific wording in the sections mentioned in suggested_improvements
- Do NOT change the structure, format, or any other content
- Do NOT change ScoringInput or ScoringOutput logic
- The modified_prompt must be ready to save directly to grading_prompt.txt

Return ONLY valid JSON, no markdown, no explanation outside the JSON.
"""
    
    try:
        response = MODEL.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up markdown if present
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.startswith("```"):
            response_text = response_text[3:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()
        
        analysis = json.loads(response_text)
        
        # Save analysis to a file
        analysis_file = PAGES_ISSUES_DIR / f"{job_id}_prompt_improvement_analysis.json"
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        
        return analysis
    except Exception as e:
        print(f"[ERROR] Failed to generate prompt improvement analysis: {e}")
        return None


async def generate_prompt_from_comments(job_id: str) -> Dict[str, Any]:
    """Generate descriptive analysis and prompt draft from TA rubric component comments."""
    if not MODEL:
        raise HTTPException(status_code=500, detail="LLM model not available")

    rubric_comments_file = PAGES_ISSUES_DIR / f"{job_id}_rubric_comments.json"
    if not rubric_comments_file.exists():
        raise HTTPException(status_code=404, detail="No rubric component comments found for this job.")

    try:
        with open(rubric_comments_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            rubric_comments = data.get("comments", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load rubric comments: {str(e)}")

    if not rubric_comments:
        raise HTTPException(status_code=404, detail="Rubric component comments file is empty.")

    grading_prompt_path = Path(__file__).parent.parent / "output_static" / "grading_prompt.txt"
    current_prompt = ""
    if grading_prompt_path.exists():
        try:
            with open(grading_prompt_path, "r", encoding="utf-8") as f:
                current_prompt = f.read().strip()
        except Exception as e:
            print(f"[WARNING] Failed to load grading_prompt.txt: {e}")
            current_prompt = ""

    summary_prompt = f"""You are assisting a TA in refining an autograder prompt.

CURRENT PROMPT:
\"\"\"PROMPT_START
{current_prompt}
PROMPT_END\"\"\"

TA RUBRIC COMMENTS (JSON):
{json.dumps(rubric_comments, indent=2)}

TASK:
1. Summarize, in 2–3 sentences, what these TA comments are asking for (focus on rubric components and tone/expectations).

2. **DECIDE whether modifications are needed:**
   - If TA comments are empty, unclear, too vague → Set recommendations to [] (empty array) and keep modified_prompt IDENTICAL to current_prompt
   - If the requested changes are too repetitive or already addressed in the current prompt → Set recommendations to [] and keep modified_prompt IDENTICAL to current_prompt
   - If the requested changes would significantly alter the prompt structure or JSON schemas (which must stay fixed) → Set recommendations to [] and keep modified_prompt IDENTICAL to current_prompt
   - Only if TA comments provide clear, actionable, non-repetitive feedback that would improve the prompt → Provide 2–4 actionable recommendations

3. **ONLY if you provided recommendations (recommendations array is NOT empty):**
   - Apply those recommendations to the CURRENT PROMPT and return the FULL REVISED PROMPT in the "modified_prompt" field
   - Read the CURRENT PROMPT carefully (between PROMPT_START and PROMPT_END)
   - For EACH recommendation, identify the specific section(s) in the prompt that need to be modified
   - Make the MINIMAL changes needed to address each recommendation
   - Return the COMPLETE modified prompt in "modified_prompt" - it MUST be different from the current prompt

4. **If you did NOT provide recommendations (recommendations array IS empty):**
   - Set "modified_prompt" to be IDENTICAL to the current prompt (copy it exactly, no changes)
   - In your analysis_summary, explain why no modifications were needed (e.g., "TA comments were too vague", "Changes already addressed in current prompt", "Would break JSON schema requirements", "Comments are too repetitive", etc.)

5. Do NOT change the ScoringInput or ScoringOutput JSON schemas, and do NOT add/remove/rename ANY keys. Treat all JSON field names and structures in the prompt as a fixed API contract that must stay exactly the same.

6. Keep the overall section structure, headings, and numbering identical. Prefer local wording tweaks, clarification sentences, or short insertions rather than large rewrites. Preserve the majority of the existing text and organization.

**CRITICAL RULES:**
- If recommendations array is empty → modified_prompt MUST be IDENTICAL to current_prompt (copy it exactly)
- If recommendations array is not empty → modified_prompt MUST be DIFFERENT from current_prompt and include the changes
- DO NOT make changes if TA comments are unclear, too vague, too short, or would break the prompt structure
- DO NOT make changes if the requested modifications are already present in the current prompt
- DO NOT make changes if the comments are repetitive or don't add value

OUTPUT (valid JSON only):
{{
  "analysis_summary": "Descriptive overview in plain English",
  "recommendations": ["Short recommendation bullet", "..."],
  "modified_prompt": "FULL prompt text after applying the minimal changes"
}}
"""

    try:
        generation_config = {
            "temperature": 0.3,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        response = MODEL.generate_content(summary_prompt, generation_config=generation_config)
        response_text = response.text.strip()

        # Clean up potential markdown fences
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.startswith("```"):
            response_text = response_text[3:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()

        try:
            # 首先嚴格嘗試解析整個回應
            analysis = json.loads(response_text)
        except json.JSONDecodeError:
            # 第二層：從回應中抽出第一個 JSON 物件片段再嘗試解析
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_fragment = response_text[start : end + 1]
                try:
                    analysis = json.loads(json_fragment)
                except json.JSONDecodeError:
                    # 仍然失敗時，嘗試手動提取 analysis_summary / recommendations
                    preview = response_text[:2000]
                    # 尝试直接从文本中提取 analysis_summary 和 recommendations 段落
                    summary_match = re.search(r'"analysis_summary"\s*:\s*"([^"]*)"', response_text, re.DOTALL)
                    rec_block_match = re.search(r'"recommendations"\s*:\s*\[(.*?)\]', response_text, re.DOTALL)
                    summary_text = summary_match.group(1).strip() if summary_match else None
                    recs: List[str] = []
                    if rec_block_match:
                        rec_block = rec_block_match.group(1)
                        for m in re.finditer(r'"([^"]+)"', rec_block):
                            rec = m.group(1).strip()
                            if rec:
                                recs.append(rec)
                    # Try to extract modified_prompt from response text
                    modified_prompt_extracted = current_prompt
                    prompt_start_marker = "PROMPT_START"
                    prompt_end_marker = "PROMPT_END"
                    start_idx = response_text.find(prompt_start_marker)
                    end_idx = response_text.find(prompt_end_marker)
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        extracted = response_text[start_idx + len(prompt_start_marker):end_idx].strip()
                        extracted = extracted.replace('\\n', '\n').replace('\\"', '"')
                        if extracted and extracted != current_prompt.strip():
                            modified_prompt_extracted = extracted
                    
                    if summary_text or recs:
                        return {
                            "analysis_summary": (summary_text or "LLM returned non-strict JSON. Showing raw text instead:\n\n" + preview) + 
                                ("\n\n⚠️ WARNING: Could not parse full JSON response. Please verify the modified_prompt contains actual changes." if modified_prompt_extracted == current_prompt else ""),
                            "recommendations": recs,
                            "modified_prompt": modified_prompt_extracted,
                        }
                    return {
                        "analysis_summary": "LLM returned non-strict JSON. Showing raw text instead:\n\n" + preview + 
                            "\n\n⚠️ WARNING: Could not parse JSON response. The modified_prompt may not contain actual changes.",
                        "recommendations": [],
                        "modified_prompt": modified_prompt_extracted,
                    }
            # 完全找不到 JSON 結構，只能回傳原文
            preview = response_text[:2000]
            # Try to extract modified_prompt from response text even if JSON parsing failed
            modified_prompt_extracted = current_prompt
            prompt_start_marker = "PROMPT_START"
            prompt_end_marker = "PROMPT_END"
            start_idx = response_text.find(prompt_start_marker)
            end_idx = response_text.find(prompt_end_marker)
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                extracted = response_text[start_idx + len(prompt_start_marker):end_idx].strip()
                extracted = extracted.replace('\\n', '\n').replace('\\"', '"')
                if extracted and extracted != current_prompt.strip():
                    modified_prompt_extracted = extracted
            
            return {
                "analysis_summary": "LLM returned non-strict JSON. Showing raw text instead:\n\n" + preview + 
                    ("\n\n⚠️ WARNING: Could not parse JSON response. The modified_prompt may not contain actual changes." if modified_prompt_extracted == current_prompt else ""),
                "recommendations": [],
                "modified_prompt": modified_prompt_extracted,
            }

        analysis.setdefault("analysis_summary", "No summary provided.")
        analysis.setdefault("recommendations", [])
        analysis.setdefault("modified_prompt", current_prompt)
        
        # CRITICAL: Verify that modified_prompt matches the recommendations
        modified_prompt = analysis.get("modified_prompt", current_prompt)
        recommendations = analysis.get("recommendations", [])
        
        # Check if modified_prompt is the same as current_prompt
        is_unchanged = modified_prompt.strip() == current_prompt.strip()
        
        if is_unchanged:
            # Try to extract modified_prompt from the response if it exists
            # Look for text between PROMPT_START and PROMPT_END markers
            prompt_start_marker = "PROMPT_START"
            prompt_end_marker = "PROMPT_END"
            start_idx = response_text.find(prompt_start_marker)
            end_idx = response_text.find(prompt_end_marker)
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                extracted_prompt = response_text[start_idx + len(prompt_start_marker):end_idx].strip()
                # Remove any JSON escaping
                extracted_prompt = extracted_prompt.replace('\\n', '\n').replace('\\"', '"')
                if extracted_prompt and extracted_prompt != current_prompt.strip():
                    print(f"[INFO] Extracted modified_prompt from response text")
                    analysis["modified_prompt"] = extracted_prompt
                    modified_prompt = extracted_prompt
                    is_unchanged = False
        
        # Validation logic based on recommendations
        if recommendations and len(recommendations) > 0:
            # If we have recommendations, the prompt MUST be different
            if is_unchanged:
                analysis["analysis_summary"] = (
                    analysis.get("analysis_summary", "") + 
                    "\n\n⚠️ WARNING: The LLM provided recommendations but did not apply them to the prompt. "
                    "The modified_prompt is identical to the current prompt. Please review the recommendations manually and apply changes yourself."
                )
                print(f"[WARNING] Recommendations provided but not applied to prompt. Recommendations: {recommendations[:2]}")
        else:
            # If no recommendations, the prompt should be unchanged (this is expected and correct)
            if not is_unchanged:
                # This is unexpected - no recommendations but prompt changed
                # Force it back to current_prompt since LLM shouldn't have made changes
                print(f"[INFO] No recommendations provided, but modified_prompt differs from current_prompt. Setting modified_prompt to current_prompt.")
                analysis["modified_prompt"] = current_prompt
                modified_prompt = current_prompt
            else:
                # This is correct - no recommendations and no changes
                print(f"[INFO] No recommendations provided, and modified_prompt matches current_prompt (as expected).")
        
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate prompt analysis: {str(e)}")


async def recompute_job_scores(job_id: str, clear_reviews: bool = True) -> Dict[str, Any]:
    """Recompute final scores using LLM based on pages and issues."""
    # 1. Load pages.json and issues.json
    pages = load_pages_for_job(job_id)
    issues = load_issues_for_job(job_id)
    
    print(f"[DEBUG] Loading data for job {job_id}: {len(pages)} pages, {len(issues)} issues")
    
    if not pages:
        error_msg = f"No pages found for job {job_id}. Please run analysis first."
        print(f"[ERROR] {error_msg}")
        raise HTTPException(status_code=404, detail=error_msg)
    if not issues:
        error_msg = f"No issues found for job {job_id}. Please run analysis first."
        print(f"[ERROR] {error_msg}")
        raise HTTPException(status_code=404, detail=error_msg)
    
    # Load old scoring output for comparison
    old_scoring = None
    scoring_file = PAGES_ISSUES_DIR / f"{job_id}_scoring.json"
    if scoring_file.exists():
        try:
            with open(scoring_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                old_scoring = data.get("scoring", {})
        except Exception as e:
            print(f"[WARNING] Could not load old scoring for comparison: {e}")
    
    # Clear TA reviews if requested
    if clear_reviews:
        print(f"[DEBUG] Clearing TA reviews for job {job_id}")
        issues_file = PAGES_ISSUES_DIR / f"{job_id}_issues.json"
        issues_file = get_job_file_path(job_id, "issues.json")
        data = load_json_file(issues_file)
        if data:
            issues_data = data.get("issues", []) if isinstance(data, dict) else []
            
            # Clear ta_review from all issues
            for issue in issues_data:
                if "ta_review" in issue:
                    del issue["ta_review"]
            
            # Save back
            if save_json_file(issues_file, {"issues": issues_data}):
                # Reload issues after clearing
                issues = load_issues_for_job(job_id)
                print(f"[DEBUG] Cleared TA reviews from {len(issues_data)} issues")
    
    # 2. Build ScoringInput
    scoring_input = build_scoring_input(job_id, pages, issues)
    
    # 3. Call LLM (pass job_id to load rubric comments)
    llm_response = await call_grading_llm(scoring_input, job_id=job_id)
    
    # 4. Parse response
    scoring_output = parse_scoring_output(llm_response)
    
    # 5. Compare with old scoring and generate change summary
    changes_summary = compare_scoring_changes(old_scoring, scoring_output) if old_scoring else None
    
    # 6. Analyze TA feedback and generate improvement suggestions (if any were cleared)
    improvement_analysis = None
    if clear_reviews and old_scoring:
        try:
            improvement_analysis = await generate_improved_prompt_from_reviews(job_id, old_scoring, scoring_output, issues)
        except Exception as e:
            print(f"[WARNING] Could not generate improvement analysis: {e}")
    
    # 7. Save to disk
    save_job_scoring(job_id, scoring_output)
    
    return {
        "scoring": scoring_output,
        "changes": changes_summary,
        "improvement_analysis": improvement_analysis,
    }


@app.post("/api/jobs/{jobId}/review/recompute")
async def recompute_scores_endpoint(jobId: str, request: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Recompute final scores using LLM."""
    print(f"[DEBUG] Received recompute request for jobId: {jobId}")
    clear_reviews = request.get("clear_reviews", True)  # Default to clearing reviews
    
    try:
        result = await recompute_job_scores(jobId, clear_reviews=clear_reviews)
        print(f"[DEBUG] Successfully computed scores for jobId: {jobId}")
        return {
            "ok": True,
            "scoring": result["scoring"],
            "changes": result.get("changes"),
            "improvement_analysis": result.get("improvement_analysis"),
        }
    except HTTPException as e:
        print(f"[ERROR] HTTPException in recompute: {e.status_code} - {e.detail}")
        raise
    except Exception as err:
        print(f"[ERROR] Error recomputing scores: {type(err).__name__}: {str(err)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to recompute scores: {str(err)}")


@app.post("/api/jobs/{jobId}/comment-prompt-analysis")
async def comment_prompt_analysis(jobId: str) -> Dict[str, Any]:
    """Combine TA rubric comments with the current prompt to produce an annotated draft before re-running grading."""
    analysis = await generate_prompt_from_comments(jobId)
    return {
        "ok": True,
        "analysis": analysis,
    }


@app.post("/api/apply-prompt-improvements")
async def apply_prompt_improvements(request: Dict[str, Any]) -> Dict[str, Any]:
    """Apply suggested improvements to the grading prompt."""
    improvements = request.get("improvements", [])
    if not improvements:
        raise HTTPException(status_code=400, detail="No improvements provided")
    
    try:
        # Load current prompt
        current_prompt = get_current_prompt()
        
        # Apply improvements (for now, just save the current prompt with a note)
        # In the future, we could implement automatic text replacement
        # For now, we'll just save the improvements analysis and let the user manually update
        
        # Save improvements to a file for reference
        improvements_file = PAGES_ISSUES_DIR / "prompt_improvements_log.json"
        improvements_data = []
        if improvements_file.exists():
            try:
                with open(improvements_file, "r", encoding="utf-8") as f:
                    improvements_data = json.load(f)
            except:
                pass
        
        improvements_data.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "improvements": improvements,
        })
        
        with open(improvements_file, "w", encoding="utf-8") as f:
            json.dump(improvements_data, f, indent=2, ensure_ascii=False)
        
        improvements_file_path = str(improvements_file.relative_to(Path(__file__).parent.parent))
        
        return {
            "ok": True,
            "message": "Improvements logged. Please manually update grading_prompt.txt based on the suggestions.",
            "saved_to": improvements_file_path,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply improvements: {str(e)}")


@app.post("/api/update-grading-prompt")
async def update_grading_prompt(request: Dict[str, Any]) -> Dict[str, Any]:
    """Update the grading prompt file with a new version."""
    new_prompt = request.get("prompt", "")
    if not new_prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    
    try:
        success = save_prompt_to_backend(new_prompt)
        if success:
            return {"ok": True, "message": "Grading prompt updated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to save prompt")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update prompt: {str(e)}")


@app.post("/api/backup-grading-prompt")
async def backup_grading_prompt() -> Dict[str, Any]:
    """Backup the current grading prompt as the original prompt. Only creates backup if it doesn't exist."""
    try:
        if not GRADING_PROMPT_FILE.exists():
            raise HTTPException(status_code=404, detail="Current grading prompt file does not exist")
        
        # Check if backup already exists
        if GRADING_PROMPT_BACKUP_FILE.exists():
            raise HTTPException(
                status_code=400, 
                detail=f"Backup already exists at {GRADING_PROMPT_BACKUP_FILE.name}. The original prompt backup cannot be overwritten. If you need to create a new backup, please manually delete the existing backup file first."
            )
        
        # Read current prompt (this is the original prompt to be backed up)
        with open(GRADING_PROMPT_FILE, "r", encoding="utf-8") as f:
            original_prompt = f.read()
        
        # Save to backup file (this is the original prompt, never modified by code)
        GRADING_PROMPT_BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GRADING_PROMPT_BACKUP_FILE, "w", encoding="utf-8") as f:
            f.write(original_prompt)
        
        return {
            "ok": True,
            "message": f"Original prompt backed up successfully to {GRADING_PROMPT_BACKUP_FILE.name}. This backup will never be modified automatically.",
            "backup_path": str(GRADING_PROMPT_BACKUP_FILE.relative_to(Path(__file__).parent.parent))
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to backup prompt: {str(e)}")


@app.post("/api/restore-grading-prompt")
async def restore_grading_prompt() -> Dict[str, Any]:
    """Restore the grading prompt from the original backup file."""
    try:
        if not GRADING_PROMPT_BACKUP_FILE.exists():
            raise HTTPException(status_code=404, detail="Backup file does not exist. Please create a backup of the original prompt first.")
        
        # Read original prompt from backup
        with open(GRADING_PROMPT_BACKUP_FILE, "r", encoding="utf-8") as f:
            original_prompt = f.read()
        
        # Restore original prompt to main file
        success = save_prompt_to_backend(original_prompt)
        if success:
            return {
                "ok": True,
                "message": "Prompt restored successfully from original backup"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to restore prompt")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore prompt: {str(e)}")


@app.get("/api/check-backup-exists")
async def check_backup_exists() -> Dict[str, Any]:
    """Check if a backup file exists."""
    backup_exists = GRADING_PROMPT_BACKUP_FILE.exists()
    return {
        "ok": True,
        "backup_exists": backup_exists,
        "backup_path": str(GRADING_PROMPT_BACKUP_FILE.relative_to(Path(__file__).parent.parent)) if backup_exists else None
    }


@app.get("/api/jobs/{jobId}/scoring")
async def get_scoring_output(jobId: str) -> Dict[str, Any]:
    """Get saved scoring output for a job."""
    scoring_file = get_job_file_path(jobId, "scoring.json")
    data = load_json_file(scoring_file)
    if data:
        scoring = data.get("scoring", {}) if isinstance(data, dict) else {}
        return {"ok": True, "scoring": scoring}
    else:
        raise HTTPException(status_code=404, detail="Scoring output not found. Please run recompute first.")


@app.get("/api/jobs/{jobId}/rubric-comments")
async def get_rubric_comments(jobId: str) -> Dict[str, Any]:
    """Get saved rubric component comments for a job."""
    comments_file = get_job_file_path(jobId, "rubric_comments.json")
    data = load_json_file(comments_file)
    if data:
        comments = data.get("comments", {}) if isinstance(data, dict) else {}
        return {"ok": True, "comments": comments}
    else:
        raise HTTPException(status_code=404, detail="Rubric comments not found.")


@app.delete("/api/jobs/{jobId}/scoring/summary-comment")
async def delete_summary_comment(jobId: str) -> Dict[str, Any]:
    """Delete the summary comment from scoring output."""
    scoring_file = get_job_file_path(jobId, "scoring.json")
    data = load_json_file(scoring_file)
    
    if not data:
        raise HTTPException(status_code=404, detail="Scoring output not found.")
    
    # Clear summary_comment
    if isinstance(data, dict) and "scoring" in data:
        data["scoring"]["summary_comment"] = ""
    
    if save_json_file(scoring_file, data):
        return {"ok": True, "message": "Summary comment deleted successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete summary comment")


@app.post("/api/jobs/{jobId}/rubric-comments")
async def save_rubric_comments(jobId: str, request: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Save rubric component comments for a job."""
    comments = request.get("comments", {})
    comments_file = get_job_file_path(jobId, "rubric_comments.json")
    
    if save_json_file(comments_file, {"job_id": jobId, "comments": comments}):
        return {"ok": True, "message": "Rubric comments saved successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save rubric comments")


@app.post("/api/save-issue-scores")
async def save_issue_scores(request: Dict[str, Any]) -> Dict[str, Any]:
    """Save TA-modified scores for a specific issue."""
    job_id = request.get("jobId")
    issue_id = request.get("issueId")
    scores = request.get("scores")
    
    if not job_id or not issue_id or not scores:
        raise HTTPException(status_code=400, detail="jobId, issueId, and scores are required")
    
    issue_scores_file = get_job_file_path(job_id, "issue_scores.json")
    
    # Load existing issue scores
    issue_scores_data = load_json_file(issue_scores_file, {})
    if not isinstance(issue_scores_data, dict):
        issue_scores_data = {}
    
    # Update scores for this issue
    if "issues" not in issue_scores_data:
        issue_scores_data["issues"] = {}
    issue_scores_data["issues"][issue_id] = scores
    issue_scores_data["lastUpdated"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    
    if save_json_file(issue_scores_file, issue_scores_data):
        
        return {
            "status": "success",
            "jobId": job_id,
            "issueId": issue_id,
            "scores": scores,
        }
    else:
        raise HTTPException(status_code=500, detail="Error saving issue scores")


@app.get("/api/jobs/{jobId}/issue-scores")
async def get_issue_scores(jobId: str) -> Dict[str, Any]:
    """Get saved issue scores for a job."""
    issue_scores_file = get_job_file_path(jobId, "issue_scores.json")
    data = load_json_file(issue_scores_file, {})
    issues = data.get("issues", {}) if isinstance(data, dict) else {}
    return {"ok": True, "issues": issues}


@app.post("/api/save-grading-scores")
async def save_grading_scores(request: Dict[str, Any]) -> Dict[str, Any]:
    """Save TA-modified grading scores."""
    job_id = request.get("jobId")
    scores = request.get("scores")
    
    if not job_id or not scores:
        raise HTTPException(status_code=400, detail="jobId and scores are required")
    
    scores_file = get_job_file_path(job_id, "scores.json")
    data = {"scores": scores, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())}
    
    if save_json_file(scores_file, data):
        return {
            "status": "success",
            "jobId": job_id,
            "scores": scores,
        }
    else:
        raise HTTPException(status_code=500, detail="Error saving scores")


@app.get("/api/get-final-grade")
async def get_final_grade(jobId: str = Query(...)) -> Dict[str, Any]:
    """Get final grade for a job. Returns 404 if no final grade exists."""
    final_grade_file = get_job_file_path(jobId, "final_grade.json")
    data = load_json_file(final_grade_file)
    
    if not data:
        raise HTTPException(status_code=404, detail="Final grade not found")
    
    return {
        "finalGrade": data.get("finalGrade"),
        "overallFeedback": data.get("overallFeedback"),
        "timestamp": data.get("timestamp"),
    }


@app.post("/api/save-final-grade")
async def save_final_grade(request: Dict[str, Any]) -> Dict[str, Any]:
    """Save final grade for a job."""
    job_id = request.get("jobId")
    final_grade = request.get("finalGrade")
    overall_feedback = request.get("overallFeedback", "")
    
    if not job_id or final_grade is None:
        raise HTTPException(status_code=400, detail="jobId and finalGrade are required")
    
    final_grade_file = get_job_file_path(job_id, "final_grade.json")
    data = {
        "finalGrade": final_grade,
        "overallFeedback": overall_feedback,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }
    
    if save_json_file(final_grade_file, data):
        return {
            "status": "success",
            "jobId": job_id,
            "finalGrade": final_grade,
        }
    else:
        raise HTTPException(status_code=500, detail="Error saving final grade")


@app.patch("/api/update-page-review")
async def update_page_review(jobId: str, pageId: str, request: Dict[str, Any]) -> Dict[str, Any]:
    """Update TA review for a specific page."""
    if not jobId or not pageId:
        raise HTTPException(status_code=400, detail="jobId and pageId are required")
    
    ta_review = {
        "override_reason": request.get("override_reason"),
        "ta_comment": request.get("ta_comment"),
    }
    
    pages_file = PAGES_ISSUES_DIR / f"{jobId}_pages.json"
    
    if not pages_file.exists():
        raise HTTPException(status_code=404, detail="Pages file not found. Please run analysis first.")
    
    try:
        with open(pages_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Handle both formats: {"pages": [...]} and [...]
            if isinstance(data, list):
                pages = data
            elif isinstance(data, dict):
                pages = data.get("pages", [])
            else:
                pages = []
        
        if not pages:
            raise HTTPException(status_code=404, detail="No pages found in pages.json")
        
        # Find and update the page
        page_found = False
        for page in pages:
            if page.get("page_id") == pageId:
                page["ta_review"] = ta_review
                page_found = True
                break
        
        if not page_found:
            # Log available page_ids for debugging
            available_page_ids = [p.get("page_id", "N/A") for p in pages[:5]]
            print(f"[DEBUG] Page {pageId} not found. Available page_ids (first 5): {available_page_ids}")
            raise HTTPException(status_code=404, detail=f"Page {pageId} not found. Available pages: {len(pages)}")
        
        # Save back - use the same format as get_pages (direct array)
        with open(pages_file, "w", encoding="utf-8") as f:
            json.dump(pages, f, indent=2, ensure_ascii=False)
        
        return {
            "status": "success",
            "jobId": jobId,
            "pageId": pageId,
            "ta_review": ta_review,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error updating page review: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating page review: {str(e)}")


@app.patch("/api/update-page-metadata")
async def update_page_metadata(request: Dict[str, Any]) -> Dict[str, Any]:
    """Update page metadata (main_heading, has_annotations, rubric_relevance) for a specific page."""
    job_id = request.get("jobId")
    page_id = request.get("pageId")
    main_heading = request.get("main_heading")
    has_annotations = request.get("has_annotations")
    rubric_relevance = request.get("rubric_relevance")
    
    if not job_id or not page_id:
        raise HTTPException(status_code=400, detail="jobId and pageId are required")
    
    pages_file = PAGES_ISSUES_DIR / f"{job_id}_pages.json"
    
    if not pages_file.exists():
        raise HTTPException(status_code=404, detail="Pages file not found. Please run analysis first.")
    
    try:
        with open(pages_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Handle both formats: {"pages": [...]} and [...]
            if isinstance(data, list):
                pages = data
            elif isinstance(data, dict):
                pages = data.get("pages", [])
            else:
                pages = []
        
        if not pages:
            raise HTTPException(status_code=404, detail="No pages found in pages.json")
        
        # Find and update the page
        page_found = False
        for page in pages:
            if page.get("page_id") == page_id:
                if main_heading is not None:
                    page["main_heading"] = main_heading if main_heading else None
                if has_annotations is not None:
                    page["has_annotations"] = has_annotations
                if rubric_relevance is not None:
                    # Merge with existing rubric_relevance to preserve fields not being updated
                    if "rubric_relevance" not in page:
                        page["rubric_relevance"] = {}
                    page["rubric_relevance"].update(rubric_relevance)
                page_found = True
                break
        
        if not page_found:
            available_page_ids = [p.get("page_id", "N/A") for p in pages[:5]]
            print(f"[DEBUG] Page {page_id} not found. Available page_ids (first 5): {available_page_ids}")
            raise HTTPException(status_code=404, detail=f"Page {page_id} not found. Available pages: {len(pages)}")
        
        # Save back - use the same format as get_pages (direct array)
        with open(pages_file, "w", encoding="utf-8") as f:
            json.dump(pages, f, indent=2, ensure_ascii=False)
        
        return {
            "status": "success",
            "jobId": job_id,
            "pageId": page_id,
            "message": "Page metadata updated successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error updating page metadata: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating page metadata: {str(e)}")


@app.post("/api/reanalyze-page-with-role")
async def reanalyze_page_with_role(request: Dict[str, Any]) -> Dict[str, Any]:
    """Update page_role for a page and reanalyze it with the new role."""
    job_id = request.get("jobId")
    page_id = request.get("pageId")
    new_page_role = request.get("page_role")
    heuristic_id = request.get("heuristic_id")  # Optional: for heuristic_explainer pages
    
    if not job_id or not page_id or not new_page_role:
        raise HTTPException(status_code=400, detail="jobId, pageId, and page_role are required")
    
    # Valid page roles
    valid_roles = ["intro", "group_collab", "heuristic_explainer", "violation_detail", 
                   "severity_summary", "conclusion", "ai_opportunities", "other"]
    if new_page_role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid page_role. Must be one of: {valid_roles}")
    
    # If switching to heuristic_explainer, heuristic_id is required
    if new_page_role == "heuristic_explainer" and not heuristic_id:
        raise HTTPException(status_code=400, detail="heuristic_id is required when page_role is 'heuristic_explainer'")
    
    # Validate heuristic_id format (H1-H10)
    if heuristic_id:
        if not (heuristic_id.startswith("H") and len(heuristic_id) >= 2):
            raise HTTPException(status_code=400, detail="Invalid heuristic_id format. Must be H1-H10")
        try:
            heuristic_num = int(heuristic_id[1:].split("_")[0])
            if heuristic_num < 1 or heuristic_num > 10:
                raise HTTPException(status_code=400, detail="heuristic_id must be H1-H10")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid heuristic_id format. Must be H1-H10")
    
    try:
        # Load pages to find the page
        pages_file = PAGES_ISSUES_DIR / f"{job_id}_pages.json"
        if not pages_file.exists():
            raise HTTPException(status_code=404, detail="Pages file not found. Please run analysis first.")
        
        with open(pages_file, "r", encoding="utf-8") as f:
            pages_data = json.load(f)
            if isinstance(pages_data, list):
                pages = pages_data
            elif isinstance(pages_data, dict):
                pages = pages_data.get("pages", [])
            else:
                pages = []
        
        # Find the page
        page_to_update = None
        for page in pages:
            if page.get("page_id") == page_id:
                page_to_update = page
                break
        
        if not page_to_update:
            raise HTTPException(status_code=404, detail=f"Page {page_id} not found")
        
        page_number = page_to_update.get("page_number")
        
        # Load extraction data to get original page content
        extraction_file = ANALYSIS_OUTPUT_DIR.parent / f"{job_id}_extraction.json"
        if not extraction_file.exists():
            raise HTTPException(status_code=404, detail="Extraction file not found. Cannot reanalyze without original page data.")
        
        with open(extraction_file, "r", encoding="utf-8") as f:
            extraction_data = json.load(f)
            extraction_pages = extraction_data.get("pages", [])
        
        # Find the original page data
        original_page = None
        for ep in extraction_pages:
            if ep.get("page_number") == page_number:
                original_page = ep
                break
        
        if not original_page:
            raise HTTPException(status_code=404, detail=f"Original page {page_number} not found in extraction data")
        
        # Get previous pages context for heuristic hint
        previous_pages_context = []
        for p in pages:
            if p.get("page_number", 0) < page_number:
                prev_page_data = {
                    "page_number": p.get("page_number"),
                    "page_role": p.get("page_role"),
                    "main_heading": p.get("main_heading", ""),
                    "fragments": p.get("fragments", []),
                    "page_content": "",  # We'll get this from extraction if needed
                }
                # Try to get page content from extraction
                for ep in extraction_pages:
                    if ep.get("page_number") == p.get("page_number"):
                        prev_page_data["page_content"] = ep.get("snippet", "")
                        break
                # Only include heuristic_explainer pages
                if prev_page_data["page_role"] == "heuristic_explainer":
                    previous_pages_context.append(prev_page_data)
        
        # Prepare page data for analysis
        page_data = {
            "pageNumber": page_number,
            "snippet": original_page.get("snippet", ""),
            "imageBase64": original_page.get("image_base64"),
        }
        
        # Call analyze-single-page logic
        if not GEMINI_API_KEY:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
        
        if not MODEL:
            raise HTTPException(status_code=500, detail="Gemini model not initialized")
        
        snippet = page_data.get("snippet", "")
        image_base64 = page_data.get("imageBase64")
        has_image = bool(image_base64)
        
        # Use new structured page analysis prompt
        truncated_content = snippet[:2500] + ("..." if len(snippet) > 2500 else "")
        prompt = get_page_analysis_prompt(page_number, truncated_content, has_image, previous_pages_context)
        
        # Prepare content for Gemini
        content_parts = [prompt]
        
        # If we have an image, include it
        if image_base64:
            # Remove data URL prefix if present
            if image_base64.startswith("data:image"):
                image_base64 = image_base64.split(",")[1]
            
            image_bytes = base64.b64decode(image_base64)
            pil_image = Image.open(io.BytesIO(image_bytes))
            
            # Compress image
            max_width = 1200
            if pil_image.width > max_width:
                ratio = max_width / pil_image.width
                new_height = int(pil_image.height * ratio)
                pil_image = pil_image.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            content_parts.append(pil_image)
        
        # Call Gemini
        generation_config = {
            "temperature": 0.2,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        
        response = MODEL.generate_content(content_parts, generation_config=generation_config)
        
        # Parse response
        if not response.candidates or len(response.candidates) == 0:
            raise HTTPException(status_code=500, detail="No response from Gemini API")
        
        candidate = response.candidates[0]
        if hasattr(candidate, 'finish_reason') and candidate.finish_reason != 1:
            raise HTTPException(status_code=500, detail=f"Gemini API error: finish_reason={candidate.finish_reason}")
        
        response_text = response.text
        
        # Parse JSON response
        try:
            structured_analysis = json.loads(response_text)
        except json.JSONDecodeError as e:
            # Try to extract JSON from markdown
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                structured_analysis = json.loads(json_match.group())
            else:
                raise HTTPException(status_code=500, detail=f"Failed to parse JSON response: {str(e)}")
        
        # Override page_role with the new one
        structured_analysis["page_role"] = new_page_role
        
        # If switching to heuristic_explainer and heuristic_id is provided, add a fragment with that heuristic
        if new_page_role == "heuristic_explainer" and heuristic_id:
            # Create a fragment for the heuristic explainer page
            fragment = {
                "heuristic_id": heuristic_id,
                "issue_key": f"heuristic_{heuristic_id.lower()}_explanation",
                "fragment_role": ["design_rationale"],
                "text_summary": f"This page explains {heuristic_id} (Nielsen's Heuristic {heuristic_id[1:]}).",
                "rubric_tags": ["coverage"]
            }
            # Set fragments to contain this single fragment
            structured_analysis["fragments"] = [fragment]
        
        # Save the analysis result
        analysis_file = ANALYSIS_OUTPUT_DIR / f"{job_id}_page_{page_number}.json"
        analysis_result = {
            "page_number": page_number,
            "structured_analysis": structured_analysis,
        }
        with open(analysis_file, "w", encoding="utf-8") as f:
            json.dump(analysis_result, f, indent=2, ensure_ascii=False)
        
        # Update pages.json
        for page in pages:
            if page.get("page_id") == page_id:
                # Update with new analysis
                page.update(structured_analysis)
                page["page_id"] = page_id  # Preserve page_id
                break
        
        with open(pages_file, "w", encoding="utf-8") as f:
            json.dump(pages, f, indent=2, ensure_ascii=False)
        
        # Regenerate issues.json
        issues = aggregate_issues(pages)
        issues_file = PAGES_ISSUES_DIR / f"{job_id}_issues.json"
        
        # Preserve TA reviews from existing issues
        existing_issues = []
        if issues_file.exists():
            try:
                with open(issues_file, "r", encoding="utf-8") as f:
                    existing_issues_data = json.load(f)
                    existing_issues = existing_issues_data.get("issues", [])
            except Exception:
                pass
        
        existing_issues_dict = {issue.get("issue_id"): issue for issue in existing_issues}
        for issue in issues:
            existing_issue = existing_issues_dict.get(issue["issue_id"])
            if existing_issue and existing_issue.get("ta_review"):
                issue["ta_review"] = existing_issue["ta_review"]
        
        with open(issues_file, "w", encoding="utf-8") as f:
            json.dump({"issues": issues}, f, indent=2, ensure_ascii=False)
        
        return {
            "status": "success",
            "jobId": job_id,
            "pageId": page_id,
            "page": structured_analysis,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Error reanalyzing page: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error reanalyzing page: {str(e)}")


@app.get("/api/get-pages")
async def get_pages(jobId: str = Query(..., description="Job ID to get pages for")) -> Dict[str, Any]:
    """Get all PageAnalysis objects for a job ID."""
    print(f"[DEBUG] get_pages called with jobId: {jobId}")
    pages_file = PAGES_ISSUES_DIR / f"{jobId}_pages.json"
    
    if pages_file.exists():
        try:
            with open(pages_file, "r", encoding="utf-8") as f:
                pages_data = json.load(f)
                # Handle both list and dict formats
                if isinstance(pages_data, list):
                    return {"jobId": jobId, "pages": pages_data}
                elif isinstance(pages_data, dict):
                    return {"jobId": jobId, "pages": pages_data.get("pages", [])}
                return {"jobId": jobId, "pages": pages_data}
        except Exception as e:
            print(f"Error loading pages: {e}")
    
    # If pages.json doesn't exist, try to generate it from analysis results
    # This handles the case where user jumps to reviewer mode before get-analysis-results is called
    try:
        results = []
        # Load all analysis files for this job
        for analysis_file in ANALYSIS_OUTPUT_DIR.glob(f"{jobId}_page_*.json"):
            try:
                with open(analysis_file, "r", encoding="utf-8") as f:
                    result = json.load(f)
                    results.append(result)
            except Exception as e:
                print(f"Error loading {analysis_file}: {e}")
        
        if results:
            # Sort by page number
            results.sort(key=lambda x: x.get("page_number", 0))
            
            # Extract structured_analysis from results
            pages_data = []
            for result in results:
                structured = result.get("structured_analysis")
                if structured:
                    pages_data.append(structured)
            
            if pages_data:
                # Save pages.json
                pages_file = PAGES_ISSUES_DIR / f"{jobId}_pages.json"
                with open(pages_file, "w", encoding="utf-8") as f:
                    json.dump(pages_data, f, indent=2, ensure_ascii=False)
                
                # Also generate and save issues.json
                issues = aggregate_issues(pages_data)
                issues_file = PAGES_ISSUES_DIR / f"{jobId}_issues.json"
                
                # Load existing issues to preserve TA reviews
                existing_issues = []
                if issues_file.exists():
                    try:
                        with open(issues_file, "r", encoding="utf-8") as f:
                            existing_issues_data = json.load(f)
                            existing_issues = existing_issues_data.get("issues", [])
                    except Exception:
                        pass
                
                # Merge TA reviews from existing issues
                existing_issues_dict = {issue.get("issue_id"): issue for issue in existing_issues}
                for issue in issues:
                    existing_issue = existing_issues_dict.get(issue["issue_id"])
                    if existing_issue and existing_issue.get("ta_review"):
                        issue["ta_review"] = existing_issue["ta_review"]
                
                with open(issues_file, "w", encoding="utf-8") as f:
                    json.dump({"issues": issues}, f, indent=2, ensure_ascii=False)
                
                return {"jobId": jobId, "pages": pages_data}
    except Exception as e:
        print(f"Error generating pages from analysis results: {e}")
    
    return {"jobId": jobId, "pages": []}


@app.get("/api/list-jobs")
async def list_jobs() -> Dict[str, Any]:
    """List all available job IDs from extraction results."""
    jobs = []
    extraction_dir = ANALYSIS_OUTPUT_DIR.parent
    
    # Find all extraction files
    for extraction_file in extraction_dir.glob("*_extraction.json"):
        try:
            with open(extraction_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                job_id = data.get("jobId") or extraction_file.stem.replace("_extraction", "")
                jobs.append({
                    "jobId": job_id,
                    "fileName": data.get("fileName"),
                    "createdAt": data.get("createdAt"),
                })
        except Exception as e:
            print(f"Error loading {extraction_file}: {e}")
    
    # Sort by creation date (newest first)
    jobs.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    
    return {"jobs": jobs}


@app.post("/api/save-override")
async def save_override(request: Dict[str, Any]) -> Dict[str, Any]:
    """Save an override record and automatically create a correction entry."""
    job_id = request.get("jobId")
    if not job_id:
        raise HTTPException(status_code=400, detail="jobId is required")
    
    # Generate override ID
    override_id = f"override_{int(time.time() * 1000)}_{len(str(time.time()))}"
    
    page_number = request.get("pageNumber")
    field = request.get("field")
    original_value = request.get("originalValue")
    override_value = request.get("overrideValue")
    reviewer_notes = request.get("reviewerNotes", "")
    
    override_record: Dict[str, Any] = {
        "id": override_id,
        "jobId": job_id,
        "pageNumber": page_number,
        "field": field,
        "originalValue": original_value,
        "overrideValue": override_value,
        "reviewerName": request.get("reviewerName", "Anonymous"),
        "reviewerNotes": reviewer_notes,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }
    
    # Load existing overrides
    overrides_file = OVERRIDES_DIR / f"{job_id}_overrides.json"
    overrides_data = {"overrides": []}
    
    if overrides_file.exists():
        with open(overrides_file, "r", encoding="utf-8") as f:
            overrides_data = json.load(f)
    
    # Check if this exact override already exists (same page, field, and values)
    existing_override = None
    for existing in overrides_data["overrides"]:
        if (existing.get("pageNumber") == page_number and 
            existing.get("field") == field and
            existing.get("originalValue") == original_value and
            existing.get("overrideValue") == override_value):
            existing_override = existing
            break
    
    # Only add if it's a new override (different values)
    if not existing_override:
        overrides_data["overrides"].append(override_record)
    else:
        # Update existing override with new notes if provided
        if reviewer_notes and reviewer_notes.strip():
            existing_override["reviewerNotes"] = reviewer_notes
            existing_override["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        override_record = existing_override
    
    # Save back
    with open(overrides_file, "w", encoding="utf-8") as f:
        json.dump(overrides_data, f, indent=2, ensure_ascii=False)
    
    # Automatically create a risk flag if user added notes/comment (but not for auto-set notes)
    # Exclude auto-generated notes like "Auto-set: All 10 heuristics covered"
    auto_set_notes = ["Auto-set:", "auto-set:", "Auto-generated", "auto-generated"]
    is_auto_note = any(auto_note in reviewer_notes for auto_note in auto_set_notes) if reviewer_notes else False
    
    if reviewer_notes and reviewer_notes.strip() and not is_auto_note:
        risk_flags_file = RISK_FLAGS_DIR / f"{job_id}_risk_flags.json"
        risk_flags_data = {"riskPages": []}
        
        if risk_flags_file.exists():
            try:
                with open(risk_flags_file, "r", encoding="utf-8") as f:
                    risk_flags_data = json.load(f)
            except Exception as e:
                print(f"Error loading risk flags: {e}")
        
        # Check if page is already flagged
        existing_index = None
        for i, page in enumerate(risk_flags_data["riskPages"]):
            if page.get("pageNumber") == page_number:
                existing_index = i
                break
        
        if existing_index is None:
            # Add flag (only if not already flagged)
            risk_flags_data["riskPages"].append({
                "pageNumber": page_number,
                "notes": reviewer_notes,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            })
            
            # Save risk flags
            with open(risk_flags_file, "w", encoding="utf-8") as f:
                json.dump(risk_flags_data, f, indent=2, ensure_ascii=False)
    
    # Automatically create a correction entry for prompt improvement (only if it's a new override)
    if not existing_override:
        # Extract component name from field (e.g., "score_breakdown.violation_quality.points" -> "violation_quality")
        component = field
        if "." in field:
            # Extract the component name from nested field paths
            parts = field.split(".")
            if len(parts) >= 2:
                component = parts[1]  # e.g., "violation_quality" from "score_breakdown.violation_quality.points"
            else:
                component = parts[0]
        
        # Generate reason based on the change
        reason = f"TA override: Changed {field} from {original_value} to {override_value}"
        if reviewer_notes:
            reason += f". Notes: {reviewer_notes}"
        
        # Check if correction already exists for this override (more strict check)
        corrections = load_corrections()
        correction_exists = False
        for corr in corrections:
            # Check if same override already has a correction (same job, page, component, and values)
            if (corr.get("jobId") == job_id and
                corr.get("pageNumber") == page_number and
                corr.get("component") == component and
                str(corr.get("originalValue")) == str(original_value) and
                str(corr.get("correctedValue")) == str(override_value)):
                correction_exists = True
                break
        
        # Only create new correction if it doesn't exist
        if not correction_exists:
            correction = {
                "id": f"correction_{int(time.time() * 1000)}",
                "jobId": job_id,
                "pageNumber": page_number,
                "component": component,
                "reason": reason,
                "originalValue": original_value,
                "correctedValue": override_value,
                "reviewerNotes": reviewer_notes or "Auto-generated from override",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                "source": "auto_from_override",  # Mark as auto-generated
            }
            
            # Save correction
            save_correction(correction)
    
    return {
        "status": "success",
        "override": override_record,
        "correction": correction,  # Return the auto-generated correction
    }


@app.delete("/api/delete-submission")
async def delete_submission(jobId: str) -> Dict[str, Any]:
    """Delete a submission and all associated files."""
    if not jobId:
        raise HTTPException(status_code=400, detail="jobId is required")
    
    base_dir = ANALYSIS_OUTPUT_DIR.parent
    deleted_files = []
    
    # Delete extraction result
    extraction_file = base_dir / f"{jobId}_extraction.json"
    if extraction_file.exists():
        extraction_file.unlink()
        deleted_files.append("extraction")
    
    # Delete analysis results (page analysis JSON files)
    analysis_files = list(ANALYSIS_OUTPUT_DIR.glob(f"{jobId}_page_*.json"))
    for analysis_file in analysis_files:
        analysis_file.unlink()
        deleted_files.append(f"analysis_{analysis_file.name}")
    
    # Delete overrides
    overrides_file = OVERRIDES_DIR / f"{jobId}_overrides.json"
    if overrides_file.exists():
        overrides_file.unlink()
        deleted_files.append("overrides")
    
    # Delete pages and issues JSON files (from issue reviewer)
    pages_file = PAGES_ISSUES_DIR / f"{jobId}_pages.json"
    if pages_file.exists():
        pages_file.unlink()
        deleted_files.append("pages")
    
    issues_file = PAGES_ISSUES_DIR / f"{jobId}_issues.json"
    if issues_file.exists():
        issues_file.unlink()
        deleted_files.append("issues")
    
    # Delete scores JSON file
    scores_file = PAGES_ISSUES_DIR / f"{jobId}_scores.json"
    if scores_file.exists():
        scores_file.unlink()
        deleted_files.append("scores")
    
    # Delete scoring output JSON file
    scoring_file = PAGES_ISSUES_DIR / f"{jobId}_scoring.json"
    if scoring_file.exists():
        scoring_file.unlink()
        deleted_files.append("scoring")
    
    # Delete rubric comments JSON file
    rubric_comments_file = PAGES_ISSUES_DIR / f"{jobId}_rubric_comments.json"
    if rubric_comments_file.exists():
        rubric_comments_file.unlink()
        deleted_files.append("rubric_comments")
    
    # Delete prompt improvement analysis JSON file (if exists)
    prompt_analysis_file = PAGES_ISSUES_DIR / f"{jobId}_prompt_improvement_analysis.json"
    if prompt_analysis_file.exists():
        prompt_analysis_file.unlink()
        deleted_files.append("prompt_improvement_analysis")
    
    return {
        "status": "success",
        "jobId": jobId,
        "deletedFiles": deleted_files,
        "message": f"Deleted {len(deleted_files)} file(s) for job {jobId}",
    }


# ============================================================================
# Prompt Refinement Pipeline (AI-to-AI Critique)
# ============================================================================

PROMPT_REFINEMENT_DIR = Path(__file__).parent.parent / "output_static" / "prompt_refinement"
PROMPT_REFINEMENT_DIR.mkdir(parents=True, exist_ok=True)

# Store for active refinement sessions
refinement_sessions: Dict[str, Dict[str, Any]] = {}


# Path to grading prompt file (primary prompt for grading)
GRADING_PROMPT_FILE = Path(__file__).parent.parent / "output_static" / "grading_prompt.txt"
# Backup path for prompt (never modified by code, only by user manually)
GRADING_PROMPT_BACKUP_FILE = Path(__file__).parent.parent / "output_static" / "grading_prompt_backup.txt"
# Legacy path for backward compatibility
SAVED_PROMPT_FILE = Path(__file__).parent.parent / "output_static" / "saved_prompt.txt"

# Default refined prompt template (from saved_prompt.txt)
DEFAULT_REFINED_PROMPT = """You are an expert grading assistant specializing in UX/HCI heuristic evaluations. Your task is to evaluate a student's assignment, processing it page by page and contributing to a comprehensive document-level assessment.

Rubric: Coverage (15 pts), Violation Quality (20 pts), Screenshots & Evidence (10 pts), Severity Analysis (10 pts), Structure & Navigation (10 pts), Professional Quality (10 pts), Writing Quality (10 pts), Group Integration (15 pts) | Bonus: Optional AI Opportunities Section (3 pts), Bonus: Exceptional Quality (2 pts)

NIELSEN HEURISTICS REFERENCE:
  1. Visibility of System Status: Keep users informed about what's happening through timely feedback
  2. Match Between System and the Real World: Use familiar language, concepts, and conventions that users understand
  3. User Control and Freedom: Provide ways to undo/redo actions and exit unwanted states easily
  4. Consistency and Standards: Follow platform conventions and be consistent within your interface
  5. Error Prevention: Prevent problems before they occur through good design
  6. Recognition Rather Than Recall: Make objects, actions, and options visible; don't make users remember
  7. Flexibility and Efficiency of Use: Provide shortcuts and ways to customize for experienced users
  8. Aesthetic and Minimalist Design: Remove irrelevant or rarely needed information; keep it clean
  9. Help Users Recognize, Diagnose, and Recover from Errors: Error messages should be clear, indicate the problem, and suggest solutions
  10. Help and Documentation: Provide help documentation that is easy to find, searchable, and focused on user tasks

STUDENT SUBMISSION INPUT FORMAT:
```json
{
  "current_page": {
    "page_number": {page_number},
    "is_final_page": false,
    "content": "Content: {word_count} words, Has image: {has_image}\n{page_content}"
  },
  "previous_document_state": {
    "total_unique_heuristics_found": [],
    "total_violations_found": 0,
    "severity_scale_explained": false,
    "group_collaboration_discussed": false,
    "accumulated_page_scores_violation_quality": [],
    "accumulated_page_scores_screenshots": [],
    "accumulated_page_scores_professional_quality": [],
    "accumulated_page_scores_writing_quality": [],
    "accumulated_page_scores_structure_navigation": [],
    "accumulated_page_scores_severity_analysis": [],
    "accumulated_bonus_ai_opportunities_points": 0,
    "accumulated_bonus_exceptional_quality_points": 0
  }
}
```

You must first process current_page.content using previous_document_state for context.

═══ STEP 1: CLASSIFICATION ═══
Determine page type by analyzing the FULL PAGE CONTENT (`current_page.content`, text, structure, visual elements), not just word count:

CRITICAL: Identify the page type accurately. Use these specific page_type values:
- "introduction page" or "introduction" - Contains project overview, team members, methodology introduction, or assignment context
- "conclusion page" or "conclusion" - Contains final summary, takeaways, or closing remarks
- "severity summary page" or "severity summary" - Contains severity rating tables, overview of all violations by severity, or aggregated severity analysis
- "heuristic violation analysis" - Contains detailed analysis of specific heuristic violations with descriptions, screenshots, and user impact
- "heuristic title page" - Contains only a heuristic number/title (e.g., "Heuristic 1", "Heuristic 2") with minimal content
- "table of contents" - Contains document structure/navigation
- "cover page" or "title page" - Contains title, course info, student names only

- Skip analysis (skip_analysis: true) if:
  * Title page, cover page, table of contents
  * Page contains only a heuristic number/title (e.g., "Heuristic 1", "Heuristic 2") with minimal content
  * Page is clearly a section divider or subtitle page
  * Page has very little substantive content (mostly titles, headers, or decorative elements)

- Analyze (skip_analysis: false) if:
  * Page contains heuristic violation analysis with detailed descriptions (page_type: "heuristic violation analysis")
  * Page is an introduction page with project context, team info, or methodology (page_type: "introduction page" or "introduction")
  * Page is a conclusion page with final summary (page_type: "conclusion page" or "conclusion")
  * Page is a severity summary page with aggregated severity ratings (page_type: "severity summary page" or "severity summary")
  * Page follows a heuristic title page and contains the actual analysis content
  * Page has images with annotations explaining violations

Note: Heuristic title pages (showing just "Heuristic X" or similar) should be skipped, but the NEXT page usually contains the analysis for that heuristic and should be analyzed.

═══ STEP 2: EXTRACTION & DOCUMENT STATE UPDATE (if skip_analysis: false) ═══
Initialize `current_document_state` as a copy of `previous_document_state`.

IMPORTANT: Only extract violations for pages with page_type "heuristic violation analysis".
For introduction pages, conclusion pages, or severity summary pages, set extracted_violations to an empty array [].

Extract all violations found on this page into `extracted_violations` array by READING THE STUDENT'S TEXT CAREFULLY.
ONLY extract violations if page_type is "heuristic violation analysis" or similar violation analysis pages.

After extraction, update `current_document_state`:
- For each unique `heuristic_num` extracted on this page, add it to `current_document_state.total_unique_heuristics_found` if not already present.
- Increment `current_document_state.total_violations_found` by the count of `extracted_violations` on this page.
- If `page_type` is "severity summary page" and the page contains an explanation of the 1-4 severity scale, set `current_document_state.severity_scale_explained` to `true`.
- If `page_type` is "introduction page" or contains explicit discussion of group collaboration/team members, set `current_document_state.group_collaboration_discussed` to `true`.

For each violation mentioned by the student, you MUST extract from the text:
- heuristic_num (1-10): The Nielsen heuristic number mentioned by the student (look for "Heuristic 1", "H1", "Heuristic #1", etc.)
- heuristic_name: The FULL NAME of the heuristic as written by the student. Look for phrases like:
  * "Visibility of System Status" or "System Status"
  * "Match Between System and the Real World" or "Match System Real World"
  * "User Control and Freedom" or "User Control"
  * "Consistency and Standards" or "Consistency"
  * "Error Prevention"
  * "Recognition Rather Than Recall" or "Recognition vs Recall"
  * "Flexibility and Efficiency" or "Flexibility"
  * "Aesthetic and Minimalist Design" or "Aesthetic Design"
  * "Help Users Recognize, Diagnose, and Recover from Errors" or "Error Recovery" or "Error Messages"
  * "Help and Documentation" or "Documentation"
  Extract the name EXACTLY as written by the student, or match to the closest standard name from the reference list above.
- description: A brief description of the violation as described by the student (max 30 words). If the description spans multiple pages, extract what is on THIS page.
- severity: The severity rating mentioned by the student on THIS page. Look for:
  * Words: "Cosmetic", "Minor", "Major", "Critical", "Low", "Medium", "High"
  * Numbers: "1", "2", "3", "4" (may be in a scale like "Severity: 3" or "Rating: 2")
  Extract this EXACTLY as written by the student (preserve the format: word or number).
  If severity is not mentioned on this page but the violation description is present, leave severity as empty string "" - it may appear on an adjacent page.

IMPORTANT:
- Read the student's text word-by-word to find heuristic names and severity ratings
- Don't infer or guess - only extract what is explicitly written on THIS page
- If a heuristic is mentioned by number only (e.g., "Heuristic 5"), look for the name nearby on THIS page or use the standard name from the reference
- If severity is not explicitly mentioned on this page, leave it as empty string "" (it may be on another page)
- If a violation description seems incomplete, extract what is present - the `updated_document_state` and final evaluation will track completeness.

═══ STEP 3: SCORING ═══
All scoring involves point deduction checklists. Start from max points, subtract for violations.

**Intermediate Page Scoring (if skip_analysis is false AND current_page.is_final_page is false):**
For the following categories, calculate page_score based *only* on current_page.content using the deduction checklists. Then, add this page_score to the respective accumulated_page_scores_CRITERION_NAME list in current_document_state. Set points in score_breakdown to 0 with a deferral comment.

**Violation Quality (max 20):**
Start: 20 points
Deduct points when evaluating current_page.content only:
□ -2: Student only says things like "confusing" or "frustrating" without explaining why in terms of user goals or cognition (emotional phrasing used >2 times on this page)
□ -3: Reasoning on this page does not mention how the issue affects perception, memory, decision-making, or action (missing cognitive/UX principle connection on this page)
□ -3: Severity mismatch on this page (marked Major/Critical but impact is cosmetic, OR marked Minor but should be Major, based on the description on this page)
□ -2: A clearly cosmetic issue (e.g., small spacing change) is treated as a serious heuristic violation on this page
□ -1: Missing "what/why/user impact" structure per violation on this page
□ -2: Severity looks inflated on this page (many problems marked "major/4" even when the impact is mild or users can easily recover, based on descriptions on this page)
page_score_violation_quality = 20 - [deductions]
current_document_state.accumulated_page_scores_violation_quality.append(page_score_violation_quality)

**Severity Analysis (max 10):**
IMPORTANT: Only evaluate Severity Analysis if page_type is "heuristic violation analysis" or "severity summary page". For all other page types (introduction, conclusion, etc.), set page_score_severity_analysis = 10 (full points) and do NOT add deductions.

If page_type is "heuristic violation analysis" or "severity summary page":
Start: 10 points
Deduct points for issues on current_page only:
□ -3: If current_page is a 'severity summary page' but lacks comprehensive summary tables or overview sections.
□ -2: Missing explanation of how the 1-4 scale was applied on THIS page, particularly if this page is an introduction or dedicated methodology section.
□ -1: Individual severity ratings on this page have no rationale beyond "this is confusing" (no mention of frequency or impact severity).
page_score_severity_analysis = 10 - [deductions]
Else:
page_score_severity_analysis = 10 # Full points for non-heuristic/non-severity pages
current_document_state.accumulated_page_scores_severity_analysis.append(page_score_severity_analysis)

**Screenshots & Evidence (max 10):**
Start: 10 points
Deduct points when evaluating current_page.content only:
□ -2: Screenshots on this page have NO annotations at all (completely unannotated screenshots with no labels, arrows, or notes explaining violations)
□ -1: Images blurry/unreadable at 100% zoom on this page
□ -2: Notes on this page are hard to read or inconsistent in size (font sizes vary >50%)
□ -2: The screenshot + note on this page look like a personal sketch that only the author understands (annotations appear as personal sketches, not clear communication tools)
□ -1: There is minimal annotation on this page, so the violation is not obvious to a new reader (missing annotations/labels for violations)
page_score_screenshots = 10 - [deductions]
current_document_state.accumulated_page_scores_screenshots.append(page_score_screenshots)

**Professional Quality (max 10):**
Start: 10 points
Deduct points when evaluating current_page.content only:
□ -2: Background colors, patterns, or icons on THIS page are visually distracting and do not help communication
□ -2: Layout on THIS page is messy: poor spacing, weak alignment, or inconsistent grid (spacing inconsistent, varies >50% between elements on this page; elements misaligned, grid structure not followed on this page)
□ -1: Layout on THIS page disorganized (making the content harder to scan)
page_score_professional_quality = 10 - [deductions]
current_document_state.accumulated_page_scores_professional_quality.append(page_score_professional_quality)

**Writing Quality (max 10):**
Start: 10 points
Deduct points when evaluating current_page.content only:
□ -2: There are frequent grammar errors on THIS page (multiple grammatical errors >3)
□ -1: Sentences on THIS page are unclear and make it hard to understand the violation, impact, or heuristic (unclear sentences >2)
page_score_writing_quality = 10 - [deductions]
current_document_state.accumulated_page_scores_writing_quality.append(page_score_writing_quality)

**Structure & Navigation (max 10):**
Start: 10 points
Deduct points when evaluating current_page.content only:
□ -2: Poor internal page structure or difficult to navigate THIS page's content (e.g., illogical flow, missing headings, poor hierarchy).
□ -1: THIS page could benefit from better internal organization or flow.
page_score_structure_navigation = 10 - [deductions]
current_document_state.accumulated_page_scores_structure_navigation.append(page_score_structure_navigation)

**Group Integration (max 15):**
If current_page.is_final_page is false:
Set points to 0. Comment: "Group Integration assessed based on introduction/group discussion pages. Final score calculated on final page."

**Bonus - AI Opportunities (max 3):**
Calculate points earned on current_page.content only:
0 points: Default (meets requirements; AI opportunities are missing or very generic).
1 point: Student proposes at least one clear AI opportunity beyond the minimum requirement on this page.
2 points: Student discusses AI opportunities on this page in a detailed and thoughtful way, showing good understanding of the system and realistic AI capabilities.
3 points: Student's AI opportunities on this page are extremely strong, creative, and well-argued, showing an exceptional level of insight.
current_document_state.accumulated_bonus_ai_opportunities_points += [points earned on this page]
If current_page.is_final_page is false:
Final = 0 // Score deferred

**Bonus - Exceptional Quality (max 2):**
Calculate points earned on current_page.content only:
0 points: Default (meets requirements; work is solid but does not especially stand out).
1 point: Work on this page is TRULY exceptional and clearly above average in MULTIPLE aspects (e.g., exceptional clarity, outstanding organization, exceptional depth of analysis, AND exceptional visual polish). Only award if work significantly exceeds typical high-quality submissions.
2 points: Work on this page is EXTREMELY outstanding: exceptionally clear, exceptionally well-organized, and exceptionally polished, with analysis and presentation that go FAR beyond what is required. This should be RARE - only award for truly exceptional work that stands out even among high-quality submissions.
CRITICAL: Only award points for work that is genuinely exceptional, not just good or above average.
current_document_state.accumulated_bonus_exceptional_quality_points += [points earned on this page]
If current_page.is_final_page is false:
Final = 0 // Score deferred

**Final Page Scoring (if skip_analysis is false AND current_page.is_final_page is true):**
For all categories in score_breakdown and bonus_scores, calculate the *final document-level score* based on the comprehensive information aggregated in current_document_state from all processed pages.
expected_analysis_content_in_document = (current_document_state.total_violations_found > 0)

MINIMUM RULE for criteria using accumulated_page_scores_*:
For any criterion that uses accumulated_page_scores_* lists, the final document-level score = the minimum page score observed in that criterion (bounded by max).
- If all pages have max, give max.
- Otherwise, final score = min(page_scores) from accumulated_page_scores_*.

This is simple and direct: take the minimum of all page scores for that criterion.

**Coverage (max 15):**
Start: 15 points
If len(current_document_state.total_unique_heuristics_found) < 10:
  -5
If current_document_state.total_violations_found < 12:
  -5
If len(current_document_state.total_unique_heuristics_found) < 8:
  -2
If current_document_state.total_violations_found < 10:
  -2
Final_coverage = 15 - [deductions]

**Violation Quality (max 20):**
If len(current_document_state.accumulated_page_scores_violation_quality) > 0:
  # Use minimum rule: final score = minimum page score observed (bounded by max)
  # If all pages have max, give max. Otherwise, final = min(page_scores)
  min_page_score = min(current_document_state.accumulated_page_scores_violation_quality)
  if all(score == 20 for score in current_document_state.accumulated_page_scores_violation_quality):
    Final_violation_quality = 20
  else:
    Final_violation_quality = min_page_score
Else:
  Final_violation_quality = 0 # If no violations analyzed across document, cannot score this criterion.

**Severity Analysis (max 10):**
Final_severity_analysis = 10
# Deduct for missing global explanation:
if current_document_state.severity_scale_explained is false:
  Final_severity_analysis -= 5
# If there are page-level severity analysis scores, use minimum rule.
# The final score is the MINIMUM of the globally-deducted score and the minimum page score.
if len(current_document_state.accumulated_page_scores_severity_analysis) > 0:
  min_page_score = min(current_document_state.accumulated_page_scores_severity_analysis)
  # Take the minimum of global deduction and minimum page score
  Final_severity_analysis = min(Final_severity_analysis, min_page_score)
# If no page-level scores were accumulated but a global explanation was provided, the score remains 10 or 5.
# If no page-level scores AND no global explanation, it defaults to 5 points (only global deduction applies).

**Screenshots & Evidence (max 10):**
if len(current_document_state.accumulated_page_scores_screenshots) > 0:
  # Use minimum rule: final score = minimum page score observed (bounded by max)
  # If all pages have max, give max. Otherwise, final = min(page_scores)
  min_page_score = min(current_document_state.accumulated_page_scores_screenshots)
  if all(score == 10 for score in current_document_state.accumulated_page_scores_screenshots):
    Final_screenshots = 10
  else:
    Final_screenshots = min_page_score
elif expected_analysis_content_in_document:
  Final_screenshots = 0 # Penalize if screenshots were expected in violation analysis but none were provided.
else:
  Final_screenshots = 10 # Full points if no violations were analyzed, hence no screenshots expected.

**Professional Quality (max 10):**
if len(current_document_state.accumulated_page_scores_professional_quality) > 0:
  # Use minimum rule: final score = minimum page score observed (bounded by max)
  # If all pages have max, give max. Otherwise, final = min(page_scores)
  min_page_score = min(current_document_state.accumulated_page_scores_professional_quality)
  if all(score == 10 for score in current_document_state.accumulated_page_scores_professional_quality):
    Final_professional_quality = 10
  else:
    Final_professional_quality = min_page_score
elif expected_analysis_content_in_document:
  Final_professional_quality = 0 # Penalize if content was expected but showed no professional quality across pages.
else:
  Final_professional_quality = 10 # Full points if no relevant content was analyzed.

**Writing Quality (max 10):**
if len(current_document_state.accumulated_page_scores_writing_quality) > 0:
  # Use minimum rule: final score = minimum page score observed (bounded by max)
  # If all pages have max, give max. Otherwise, final = min(page_scores)
  min_page_score = min(current_document_state.accumulated_page_scores_writing_quality)
  if all(score == 10 for score in current_document_state.accumulated_page_scores_writing_quality):
    Final_writing_quality = 10
  else:
    Final_writing_quality = min_page_score
elif expected_analysis_content_in_document:
  Final_writing_quality = 0 # Penalize if content was expected but showed no writing quality across pages.
else:
  Final_writing_quality = 10 # Full points if no relevant content was analyzed.

**Structure & Navigation (max 10):**
if len(current_document_state.accumulated_page_scores_structure_navigation) > 0:
  # Use minimum rule: final score = minimum page score observed (bounded by max)
  # If all pages have max, give max. Otherwise, final = min(page_scores)
  min_page_score = min(current_document_state.accumulated_page_scores_structure_navigation)
  if all(score == 10 for score in current_document_state.accumulated_page_scores_structure_navigation):
    Final_structure_navigation = 10
  else:
    Final_structure_navigation = min_page_score
elif expected_analysis_content_in_document:
  Final_structure_navigation = 0 # Penalize if structure/navigation was expected but none was evident.
else:
  Final_structure_navigation = 10 # Full points if no relevant content was analyzed.

**Group Integration (max 15):**
Start: 15 points
If current_document_state.group_collaboration_discussed is false:
  □ -10: No evidence of mentioning group or team member contributions was found anywhere in the document.
Final_group_integration = 15 - [deductions]

**Bonus - AI Opportunities (max 3):**
Final_bonus_ai_opportunities = current_document_state.accumulated_bonus_ai_opportunities_points

**Bonus - Exceptional Quality (max 2):**
Final_bonus_exceptional_quality = current_document_state.accumulated_bonus_exceptional_quality_points

═══ STEP 4: FEEDBACK DRAFTING ═══
- List heuristics discussed and violation counts found on THIS page (be concise)
- Point out 2-3 key issues *on this page* if problems exist (one sentence each)
- 1-2 sentence overall summary *of this page's content and its contribution to the assignment*
- If current_page.is_final_page is true, add a brief 1-2 sentence statement about the overall document quality based on updated_document_state and the aggregated scores.
- MAXIMUM 200 words for feedback field

COMMENT FIELD RULES:
- ONLY explain why points were deducted for the specific criterion based on content on THIS page (for non-final pages) or for the overall document (for final page).
- If full points, leave comment empty or omit
- Format: "Deducted X points: [specific issue]" (one sentence, max 50 words)
- For deferred scores on non-final pages: "Score deferred to final page for document aggregation."
- NO positive comments in comment fields
- Keep ALL comments under 50 words to prevent truncation

═══ STEP 5: JSON GENERATION ═══

CRITICAL: The entire response MUST be a single, valid JSON object. DO NOT include ANY text, Markdown fences (```json, ```), or explanations outside of the JSON object itself.

IMPORTANT: Keep ALL text fields SHORT to prevent JSON truncation:
- feedback: max 200 words
- comment fields: max 50 words each
- page_type: max 20 words
- skip_reason: max 30 words

{
  "page_number": <current_page.page_number>,
  "skip_analysis": true/false,
  "page_type": "description",
  "skip_reason": "reason if skip_analysis is true",
  "extracted_violations": [{"heuristic_num": 1, "heuristic_name": "Visibility of System Status", "description": "...", "severity": "Major"}],
  "feedback": "Brief: heuristics, violations, 2-3 issues, summary.",
  "compelling": true/false,
  "score_breakdown": {
    "coverage": {"points": X, "max": 15, "comment": ""},
    "violation_quality": {"points": X, "max": 20, "comment": ""},
    "screenshots": {"points": X, "max": 10, "comment": ""},
    "severity_analysis": {"points": X, "max": 10, "comment": ""},
    "structure_navigation": {"points": X, "max": 10, "comment": ""},
    "professional_quality": {"points": X, "max": 10, "comment": ""},
    "writing_quality": {"points": X, "max": 10, "comment": ""},
    "group_integration": {"points": X, "max": 15, "comment": ""}
  },
  "bonus_scores": {
    "bonus_ai_opportunities": {"points": X, "max": 3, "comment": ""},
    "bonus_exceptional_quality": {"points": X, "max": 2, "comment": ""}
  },
  "updated_document_state": {
    "total_unique_heuristics_found": [],
    "total_violations_found": 0,
    "severity_scale_explained": false,
    "group_collaboration_discussed": false,
    "accumulated_page_scores_violation_quality": [],
    "accumulated_page_scores_screenshots": [],
    "accumulated_page_scores_professional_quality": [],
    "accumulated_page_scores_writing_quality": [],
    "accumulated_page_scores_structure_navigation": [],
    "accumulated_page_scores_severity_analysis": [],
    "accumulated_bonus_ai_opportunities_points": 0,
    "accumulated_bonus_exceptional_quality_points": 0
  }
}
}"""


def convert_page_analysis_to_legacy(page_analysis: Dict[str, Any], page_number: int) -> Dict[str, Any]:
    """Convert new PageAnalysis format to legacy PageAnalysisResult format for backward compatibility."""
    legacy = {
        "page_number": page_number,
        "skip_analysis": False,
        "page_type": page_analysis.get("page_role", "other"),
        "extracted_violations": [],
        "feedback": "",
        "compelling": None,
    }
    
    # Convert page_role to page_type
    role_to_type = {
        "intro": "introduction page",
        "group_collab": "group collaboration page",
        "heuristic_explainer": "heuristic explainer page",
        "violation_detail": "heuristic violation analysis",
        "severity_summary": "severity summary page",
        "conclusion": "conclusion page",
        "other": "other",
    }
    legacy["page_type"] = role_to_type.get(page_analysis.get("page_role", "other"), "other")
    
    # Convert fragments to extracted_violations
    fragments = page_analysis.get("fragments", [])
    for frag in fragments:
        heuristic_id = frag.get("heuristic_id", "")
        # Extract heuristic number from "H1", "H2", etc.
        heuristic_num = None
        if heuristic_id.startswith("H") and len(heuristic_id) > 1:
            try:
                num_str = heuristic_id[1:].split("_")[0]  # Handle "H1", "Hx_unknown"
                if num_str.isdigit():
                    heuristic_num = int(num_str)
            except:
                pass
        
        if heuristic_num and 1 <= heuristic_num <= 10:
            violation = {
                "heuristic_num": heuristic_num,
                "heuristic_number": heuristic_num,
                "heuristic_name": f"Heuristic {heuristic_num}",
                "description": frag.get("text_summary", ""),
                "severity": frag.get("severity_hint", ""),
            }
            legacy["extracted_violations"].append(violation)
    
    # Generate feedback from fragments and page info
    feedback_parts = []
    if page_analysis.get("main_heading"):
        feedback_parts.append(f"Page Title: {page_analysis['main_heading']}")
    
    if fragments:
        feedback_parts.append(f"Found {len(fragments)} heuristic issue(s):")
        for frag in fragments:
            feedback_parts.append(f"- {frag.get('heuristic_id', 'Unknown')}: {frag.get('text_summary', '')}")
    else:
        feedback_parts.append("No specific heuristic violations identified on this page.")
    
    # Add severity summary info if present
    if page_analysis.get("severity_summary"):
        summary = page_analysis["severity_summary"]
        feedback_parts.append(f"Severity Summary: {summary.get('visualization', 'unknown')} visualization, "
                            f"coverage: {summary.get('coverage_scope', 'unclear')}, "
                            f"clarity: {summary.get('mapping_clarity', 'unclear')}")
        if summary.get("llm_note"):
            feedback_parts.append(f"Note: {summary['llm_note']}")
    
    legacy["feedback"] = "\n".join(feedback_parts)
    
    # Set compelling based on rubric relevance
    relevance = page_analysis.get("rubric_relevance", {})
    high_relevance_count = sum(1 for v in relevance.values() if v == "high")
    legacy["compelling"] = high_relevance_count >= 2
    
    return legacy


def aggregate_issues(pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate fragments from multiple PageAnalysis objects into Issue objects.
    
    Args:
        pages: List of PageAnalysis dictionaries (from structured_analysis field)
    
    Returns:
        List of Issue dictionaries
    """
    # Group fragments by heuristic_id + issue_key
    # Only include fragments from violation_detail pages (exclude intro, conclusion, severity_summary, etc.)
    fragment_groups: Dict[str, List[Dict[str, Any]]] = {}
    
    for page in pages:
        page_role = page.get("page_role", "other")
        page_id = page.get("page_id", f"p{page.get('page_number', 0):02d}")
        fragments = page.get("fragments", [])
        screenshot_cluster_id = page.get("screenshot_cluster_id")
        
        # Filter logic:
        # - Skip if page_role is conclusion/intro/severity_summary/group_collab/heuristic_explainer/other AND has no fragments
        # - Include if page_role is violation_detail (always has fragments)
        # - Include if page has fragments (even if page_role is conclusion/intro/etc, it means the page contains heuristic detail)
        if page_role not in ["violation_detail"] and len(fragments) == 0:
            # This is a pure non-violation page with no heuristic content, skip it
            continue
        
        # If we reach here, either:
        # 1. page_role is violation_detail, OR
        # 2. page has fragments (even if page_role is conclusion/intro/etc)
        
        for frag in fragments:
            heuristic_id = frag.get("heuristic_id", "")
            issue_key = frag.get("issue_key", "")
            
            # Skip fragments with unknown or invalid heuristic_id
            # Only process H1-H10 (valid Nielsen heuristics)
            if not heuristic_id or heuristic_id.startswith("Hx") or heuristic_id == "Hx_unknown":
                continue
            
            # Validate heuristic_id format (H1-H10)
            heuristic_num_str = heuristic_id.replace("H", "").replace("h", "").split("_")[0]
            try:
                heuristic_num = int(heuristic_num_str)
                if heuristic_num < 1 or heuristic_num > 10:
                    continue  # Skip invalid heuristic numbers
            except (ValueError, TypeError):
                continue  # Skip if cannot parse as number
            
            # Create a unique key for grouping
            group_key = f"{heuristic_id}::{issue_key}"
            
            if group_key not in fragment_groups:
                fragment_groups[group_key] = []
            
            # Store fragment with page context
            fragment_groups[group_key].append({
                "fragment": frag,
                "page_id": page_id,
                "screenshot_cluster_id": screenshot_cluster_id,
            })
    
    # Convert groups to Issues
    issues = []
    issue_counter = 1
    
    for group_key, group_fragments in fragment_groups.items():
        if not group_fragments:
            continue
        
        # Extract heuristic_id and issue_key from group_key
        parts = group_key.split("::", 1)
        heuristic_id = parts[0] if len(parts) > 0 else "Hx_unknown"
        issue_key = parts[1] if len(parts) > 1 else f"issue_{issue_counter}"
        
        # Collect unique page_ids and screenshot_cluster_ids
        # Double-check: verify all pages in this group are actually violation_detail pages
        page_ids = set()
        screenshot_cluster_ids = set()
        all_fragments = []
        
        for item in group_fragments:
            # Find the original page to verify it has fragments (defensive check)
            page_id = item["page_id"]
            original_page = next((p for p in pages if p.get("page_id") == page_id or f"p{p.get('page_number', 0):02d}" == page_id), None)
            
            # Skip if page has no fragments (defensive check - should not happen if first filter worked)
            if original_page and len(original_page.get("fragments", [])) == 0:
                continue
            
            page_ids.add(page_id)
            if item.get("screenshot_cluster_id"):
                screenshot_cluster_ids.add(item["screenshot_cluster_id"])
            all_fragments.append(item["fragment"])
        
        # Skip this issue if no valid fragments remain after filtering
        if not all_fragments:
            continue
        
        # Generate title from first fragment's text_summary
        first_fragment = all_fragments[0]
        title_text = first_fragment.get("text_summary", "").strip()
        # Take first sentence or first 60 chars, whichever is shorter
        # Try to extract first sentence
        first_sentence = title_text.split('.')[0].strip()
        if first_sentence and len(first_sentence) <= 60:
            title = first_sentence
        elif len(title_text) > 60:
            # Take first 60 chars and try to break at word boundary
            truncated = title_text[:60]
            last_space = truncated.rfind(' ')
            if last_space > 40:  # Only break at word if we have enough content
                title = truncated[:last_space] + "..."
            else:
                title = truncated + "..."
        else:
            title = title_text or f"{heuristic_id} Issue"
        
        # Combine descriptions
        descriptions = [f.get("text_summary", "") for f in all_fragments if f.get("text_summary")]
        combined_description = " ".join(descriptions)
        
        # Determine AI proposed severity
        severity_hints = [f.get("severity_hint") for f in all_fragments if f.get("severity_hint")]
        severity_map = {"minor": 1, "major": 2, "critical": 3}
        max_severity = "major"  # default
        if severity_hints:
            max_severity_value = max([severity_map.get(s, 0) for s in severity_hints])
            max_severity = [k for k, v in severity_map.items() if v == max_severity_value][0] if max_severity_value > 0 else "major"
        
        # Generate AI severity rationale
        ai_severity_rationale = f"Based on {len(all_fragments)} fragment(s) across {len(page_ids)} page(s). "
        if severity_hints:
            ai_severity_rationale += f"Severity hints: {', '.join(set(severity_hints))}. "
        ai_severity_rationale += f"Description: {combined_description[:200]}"
        
        # Create Issue object
        issue = {
            "issue_id": f"issue_{issue_counter:03d}",
            "heuristic_id": heuristic_id,
            "issue_key": issue_key,
            "title": title,
            "combined_description": combined_description,
            "pages_involved": sorted(list(page_ids)),
            "screenshot_cluster_ids": sorted(list(screenshot_cluster_ids)),
            "ai_proposed_severity": max_severity,
            "ai_severity_rationale": ai_severity_rationale,
            "ta_review": None,  # Will be filled by TA in reviewer mode
        }
        
        issues.append(issue)
        issue_counter += 1
    
    return issues


def get_page_analysis_prompt(page_number: int, page_content: str, has_image: bool, previous_pages_context: Optional[List[Dict[str, Any]]] = None) -> str:
    """Generate prompt for structured page analysis (PageAnalysis format).
    
    Args:
        page_number: Current page number
        page_content: Content of current page
        has_image: Whether page has an image
        previous_pages_context: List of previous pages' analysis results, each containing:
            - page_number: Page number
            - page_role: Role of the page (e.g., "heuristic_explainer", "violation_detail")
            - main_heading: Main heading of the page (if available)
            - fragments: List of fragments (for heuristic_explainer pages, this may contain heuristic info)
    """
    word_count = len(page_content.split())
    image_note = "with screenshot/image" if has_image else "text only"
    
    # Build context hint from previous pages
    heuristic_hint = ""
    if previous_pages_context:
        # Find the most recent heuristic_explainer page (closest to current page)
        for prev_page in reversed(previous_pages_context):
            if prev_page.get("page_role") == "heuristic_explainer":
                prev_page_num = prev_page.get("page_number", "?")
                prev_heading = prev_page.get("main_heading", "")
                prev_content = prev_page.get("page_content", "")  # Original page content
                
                import re
                heuristic_id_from_heading = None
                heuristic_id_from_content = None
                heuristic_from_fragments = None
                
                # Method 1: Try to extract heuristic from main_heading (most reliable if available)
                if prev_heading:
                    patterns = [
                        r'[Hh]euristic\s*#?\s*(\d+)',  # "Heuristic 1", "Heuristic #1", "Heuristic: 1"
                        r'^[Hh](\d+)\s*[:\-]',  # "H1:", "H1 -"
                        r'^[Hh](\d+)\s*$',  # Just "H1"
                        r'[Hh]euristic\s+(\d+)',  # "Heuristic 1" with space
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, prev_heading)
                        if match:
                            heuristic_num = match.group(1)
                            if heuristic_num.isdigit() and 1 <= int(heuristic_num) <= 10:
                                heuristic_id_from_heading = f"H{heuristic_num}"
                                break
                
                # Method 2: Try to extract from page content (more reliable than fragments)
                # Search in the first 500 characters of the page content
                if prev_content and not heuristic_id_from_heading:
                    content_snippet = prev_content[:500]  # First 500 chars should contain heuristic info
                    patterns = [
                        r'[Hh]euristic\s*#?\s*(\d+)',  # "Heuristic 1", "Heuristic #1"
                        r'\b[Hh](\d+)\b',  # "H1" as word boundary
                        r'[Hh]euristic\s+(\d+)',  # "Heuristic 1" with space
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, content_snippet)
                        if match:
                            heuristic_num = match.group(1)
                            if heuristic_num.isdigit() and 1 <= int(heuristic_num) <= 10:
                                heuristic_id_from_content = f"H{heuristic_num}"
                                break
                
                # Method 3: Try fragments as fallback (less reliable for explainer pages)
                fragments = prev_page.get("fragments", [])
                if fragments:
                    for frag in fragments:
                        heuristic_id = frag.get("heuristic_id", "")
                        if heuristic_id and heuristic_id.startswith("H") and len(heuristic_id) >= 2:
                            # Check if it's a valid heuristic (H1-H10)
                            num_str = heuristic_id[1:].split("_")[0]
                            if num_str.isdigit() and 1 <= int(num_str) <= 10:
                                heuristic_from_fragments = heuristic_id
                                break
                
                # Priority: heading > content > fragments
                final_heuristic_id = heuristic_id_from_heading or heuristic_id_from_content or heuristic_from_fragments
                
                if final_heuristic_id:
                    heuristic_hint = f"""

**CONTEXT HINT FOR HEURISTIC IDENTIFICATION (OPTIONAL - ONLY IF APPLICABLE):**
The previous page (Page {prev_page_num}) is a "heuristic_explainer" page that introduces {final_heuristic_id}. 

**IMPORTANT RULES FOR USING THIS HINT:**
1. This hint is OPTIONAL and should ONLY be used if:
   - The current page (Page {page_number}) is classified as "violation_detail" AND
   - The current page does NOT have a clear title, subtitle, or heading that explicitly identifies a heuristic (e.g., "Heuristic 1", "H1", "Visibility of System Status") AND
   - The current page's content does NOT clearly mention a specific heuristic

2. DO NOT use this hint if:
   - The current page explicitly mentions a DIFFERENT heuristic in its title/heading/subtitle/content
   - The current page's content clearly discusses a different heuristic than {final_heuristic_id}
   - The current page is NOT a "violation_detail" page
   - The current page has ANY explicit heuristic identification (even if different from the hint)

3. When the hint applies:
   - Use {final_heuristic_id} as the heuristic_id for fragments on this page
   - This hint continues to apply to subsequent violation_detail pages UNTIL a new heuristic_explainer page appears

4. CRITICAL: Always verify the page content first. If the page content clearly indicates ANY heuristic (even if different from the hint), use that instead of the hint.

**SPECIAL CASE: Pages with only screenshots and minimal text:**
- If the current page has a screenshot/image but very little or no explanatory text describing the heuristic or violation, check adjacent pages (previous or next) for heuristic context.
- If the previous page (Page {prev_page_num}) is a "heuristic_explainer" or "violation_detail" page that discusses a specific heuristic, that heuristic likely applies to the current screenshot page as well.
- Similarly, if the next page (not yet analyzed) appears to contain explanation text for the screenshot, the heuristic from the previous context or the next page's context may apply.
- **IMPORTANT: If the current page only has a screenshot with minimal text, and the explanation is on the next page, you should still use the hint from the previous heuristic_explainer page if available. The screenshot page and its explanation page often belong to the same heuristic context.**
- In such cases, use the hint from the previous heuristic_explainer page if available, as screenshots are often placed on separate pages from their explanations.

**NOTE: If no hint is provided above, or if the hint does not apply, you must determine the heuristic_id from the current page's own content using the steps below.**"""
                break
    
    # Add note if no hint was found
    if not heuristic_hint:
        heuristic_hint = """

**NOTE: No heuristic_explainer page was found before this page. You must determine the heuristic_id entirely from the current page's own content using the steps below.**"""
    
    prompt = f"""You are analyzing a single page from a student's heuristic evaluation assignment. Your task is to extract structured information about what this page contains and how it relates to the grading rubric.

PAGE CONTENT:
Page {page_number} ({word_count} words, {image_note})
---
{page_content[:2500]}
---{heuristic_hint}

NIELSEN HEURISTICS REFERENCE:
1. Visibility of System Status
2. Match Between System and the Real World
3. User Control and Freedom
4. Consistency and Standards
5. Error Prevention
6. Recognition Rather Than Recall
7. Flexibility and Efficiency of Use
8. Aesthetic and Minimalist Design
9. Help Users Recognize, Diagnose, and Recover from Errors
10. Help and Documentation

TASK: Generate a compact JSON object describing this page's role, relevance to rubric dimensions, and any heuristic/issue fragments it discusses.

OUTPUT FORMAT (JSON):
{{
  "page_id": "p{page_number:02d}",
  "page_number": {page_number},
  "page_role": "<one of: intro, group_collab, heuristic_explainer, violation_detail, severity_summary, conclusion, ai_opportunities, other>",
  "main_heading": "<main title/heading on the page, if any, max 50 chars>",
  "has_annotations": "<none|low|medium|high>",
  "rubric_relevance": {{
    "coverage": "<none|low|med|high>",
    "violation_quality": "<none|low|med|high>",
    "severity_analysis": "<none|low|med|high>",
    "screenshots_evidence": "<none|low|med|high>",
    "group_integration": "<none|low|med|high>",
    "professional_quality": "<none|low|med|high>",
    "writing_quality": "<none|low|med|high>"
  }},
  "screenshot_cluster_id": "<optional: e.g., 'ss_1' if this page shares screenshot with other pages>",
  "fragments": [
    {{
      "heuristic_id": "<H1-H10 or Hx_unknown>",
      "issue_key": "<2-6 words, snake_case, e.g., 'navbar_low_contrast'>",
      "fragment_role": ["<problem_description|impact|evidence|design_rationale|fix_idea>", "<add up to 2 more roles>"],
      "text_summary": "<1-2 sentences, paraphrase what page says about this issue>",
      "severity_hint": "<optional: minor|major|critical>",
      "rubric_tags": ["<optional: coverage|violation_quality|severity_analysis|screenshots_evidence>", "<add more tags if relevant>"]
    }}
  ],
  "severity_summary": {{
    "is_summary": true,
    "visualization": "<table|plot|mixed|text_only>",
    "coverage_scope": "<all_issues|major_issues_only|unclear>",
    "mapping_clarity": "<clear|somewhat_clear|unclear>",
    "llm_note": "<1-2 sentences describing the visualization>"
  }},
  "ai_opportunities_info": {{
    "present": true,
    "raw_text_excerpt": "<3-6 sentences, concise extract/paraphrase of AI ideas>",
    "llm_summary": "<2-3 sentence summary of what AI is supposed to do>",
    "relevance_to_violations": "<low|med|high>",
    "specificity": "<generic|somewhat_specific|very_specific>"
  }}
}}
NOTE: 
- Only include "severity_summary" field if page_role === "severity_summary". Otherwise omit this field entirely.
- Only include "ai_opportunities_info" field if page_role === "ai_opportunities". Otherwise omit this field entirely.

RULES:
1. page_role: Pick ONE dominant role:
   - "intro": Introduces project/site/overall structure
   - "group_collab": Talks about team roles, collaboration, division of work
   - "heuristic_explainer": Defines Nielsen's heuristics generically (not site-specific)
   - "violation_detail": Analyzes specific problems on target website (with screenshots/bullets)
   - "severity_summary": Summarizes severity across issues (tables/plots)
     **IMPORTANT: If a page contains a table that mentions multiple heuristics (e.g., a table listing Heuristic 1, Heuristic 2, Heuristic 3, etc. with their severity ratings or summaries), it should be classified as "severity_summary". Pages with tables summarizing multiple heuristics are typically summary pages, not detailed violation analysis pages.**
     **EXCEPTION: If a page is a title/subtitle page (contains only 1-7 words total, typically just a heading like "Findings by Heuristic" or "Introduction" with minimal or no other content), it should be classified as "other" (title/subtitle page). Count ALL words on the page - if the total word count is 1-7 words, classify as "other" regardless of whether it contains a table or other visual elements.**
   - "conclusion": Conclusions, reflections, limitations, learnings, next steps
   - "ai_opportunities": Page mainly discusses how AI, machine learning, chatbots, recommendation systems, etc. could be used to address the problems found on the Julian site. The page should propose concrete AI solutions tied to specific violations or usability issues.
   - "other": Doesn't fit above

   **Important disambiguation between "conclusion" and "violation_detail":**
   - If the main heading clearly contains words like "Conclusion", "Conclusions", "Summary & Reflection", "Final Thoughts", or similar wrap‑up language, and the page is primarily summarizing takeaways or reflecting on the work, you MUST set `page_role = "conclusion"` (even if it briefly mentions heuristics or issues).
   - Only use `page_role = "violation_detail"` when the page's main purpose is to introduce or deeply analyze specific problems (often with focused screenshots and detailed bullets), not when it is mainly a course/project conclusion slide.
   - For true conclusion pages, do NOT treat summary bullets as new violation analysis; those pages should be classified as "conclusion" and handled as such in later scoring.

2. rubric_relevance: Rate how much this page matters for each dimension:
   - "none": Page doesn't address this dimension at all
   - "low": Page mentions it briefly
   - "med": Page has some content relevant to this dimension
   - "high": Page is primarily about this dimension
   
   Specific guidance:
   - coverage: Does this page help demonstrate how many heuristics/issues the student covered?
   - violation_quality: Does this page include detailed, thoughtful analysis of specific problems?
   - severity_analysis: Does this page reason about severity levels (major/minor/critical)?
   - screenshots_evidence: Does this page provide clear evidence (screenshots, annotations)?
   - group_integration: Does this page talk about group collaboration or how parts fit together?
   - professional_quality: Layout, visual design, information hierarchy, overall slide professionalism.
     Examples: Well-organized layout with color/alignment emphasizing structure → "high".
     Text blends into background, high saturation colors, irrelevant patterns affecting readability → "low".
     Very disorganized or distracting layout → "none".
   - writing_quality: Is text clear, logical, with grammar/spelling that doesn't hinder understanding?
     Examples: Long analysis written clearly → "high"; grammar errors, simple sentences → "med"; pure bullets, incomplete sentences → "low".

3. fragments: List 0-5 HeuristicFragment objects:
   - CRITICAL: Only include fragments if page_role === "violation_detail"
   - For intro, conclusion, severity_summary, group_collab, heuristic_explainer, or other pages, set fragments to [] (empty array)
   - Even if a conclusion or intro page mentions heuristics or issues, do NOT create fragments for them
   - One fragment = "this page says something substantive about one heuristic + one issue"
   - heuristic_id: "H1" to "H10" (or "Hx_unknown" if unclear)
   
   **CRITICAL: Determining heuristic_id for violation_detail pages (READ CAREFULLY):**
   
   **IMPORTANT: The following steps apply REGARDLESS of whether a CONTEXT HINT is provided above. Always follow this priority order.**
   
   **Step 1: Check the current page itself FIRST (HIGHEST PRIORITY - ALWAYS DO THIS FIRST)**
   - Look for explicit heuristic identification in:
     * Page title/heading (e.g., "Heuristic 1", "H1", "Visibility of System Status", "Heuristic #1")
     * Subtitle or section header
     * First paragraph that mentions "Heuristic X" or a heuristic name
     * Any clear mention of heuristic numbers (1-10) or heuristic names in the page content
   - If found, use that heuristic_id. DO NOT use any hint if the page explicitly identifies a heuristic.
   - This step takes ABSOLUTE PRIORITY over any hint.
   
   **Step 2: Check page content thoroughly for heuristic mentions (SECOND PRIORITY)**
   - Read the ENTIRE page content carefully for any mention of:
     * Heuristic numbers (1-10) in any format ("Heuristic 1", "H1", "Heuristic #1", etc.)
     * Heuristic names (e.g., "Visibility of System Status", "Error Prevention", etc.)
     * References to specific Nielsen heuristics
   - If the content clearly discusses a specific heuristic, use that heuristic_id
   - If the content mentions multiple heuristics, assign each fragment to the appropriate heuristic based on context
   - Search for patterns like "Heuristic X", "HX", "Heuristic #X" where X is 1-10
   
   **Step 3: Use CONTEXT HINT only if Steps 1-2 found NOTHING (LOWEST PRIORITY - OPTIONAL)**
   - ONLY use the hint if:
     * The current page has NO explicit heuristic identification in title/heading/subtitle AND
     * The page content does NOT clearly mention any specific heuristic (no numbers 1-10, no heuristic names) AND
     * A CONTEXT HINT is provided above (if no hint is provided, skip to Step 4)
   - If all conditions are met, use the heuristic from the hint
   - REMEMBER: The hint applies to this page and subsequent violation_detail pages until a new heuristic_explainer appears
   - If ANY of the conditions are not met, DO NOT use the hint
   
   **Step 4: Last resort (ONLY if Steps 1-3 found nothing)**
   - If no explicit identification, no content mention, and no applicable hint: use "Hx_unknown"
   - This should be RARE - most pages will have some heuristic identification
   
   **VERIFICATION RULE (CRITICAL - APPLY BEFORE EVERY heuristic_id ASSIGNMENT):**
   - Before assigning heuristic_id, ask: "Does this page's content clearly indicate ANY heuristic (even if different from the hint)?"
   - If YES → use the heuristic indicated by the content (ignore the hint completely)
   - If NO → check if hint is available and applicable, then use hint
   - If NO hint or hint not applicable → use "Hx_unknown"
   - NEVER blindly use the hint if the page content contradicts it or provides any heuristic information
   
   **SCENARIOS TO HANDLE:**
   - Scenario A: Page has explicit heuristic in title → Use that heuristic (ignore hint)
   - Scenario B: Page has no title but content mentions "Heuristic 3" → Use H3 (ignore hint)
   - Scenario C: Page has no title, no content mention, but hint says H2 → Use H2 from hint
   - Scenario D: Page has no title, no content mention, no hint → Use "Hx_unknown"
   - Scenario E: Page has title "Heuristic 1" but hint says H2 → Use H1 from title (ignore hint)
   
   - issue_key: 2-6 words, lowercase, snake_case (e.g., "search_bar_mobile_hidden")
   - fragment_role: 1-3 roles from [problem_description, impact, evidence, design_rationale, fix_idea]
   - text_summary: 1-2 sentences, paraphrase (NO copy-paste)
   - severity_hint: Optional, only if page clearly suggests severity
   - rubric_tags: Optional, which rubric dimensions this fragment contributes to

4. severity_summary: Only include if page_role === "severity_summary"
   - visualization: "table" | "plot" | "mixed" | "text_only"
   - coverage_scope: "all_issues" | "major_issues_only" | "unclear"
   - mapping_clarity: "clear" | "somewhat_clear" | "unclear"
   - llm_note: 1-2 sentences describing the visualization

5. ai_opportunities_info: Only include if page_role === "ai_opportunities"
   - present: Always true when this field is included
   - raw_text_excerpt: 3-6 sentences, concise extract/paraphrase of the student's AI ideas (not the whole page, but enough for later scoring)
   - llm_summary: 2-3 sentence summary of what AI is supposed to do
   - relevance_to_violations:
     * "high": AI ideas clearly reference specific problems or heuristics discussed earlier
     * "med": Partially connected to violations
     * "low": Mostly generic, not tied to specific violations
   - specificity:
     * "very_specific": Ideas are concrete and plausible (e.g., "AI-driven skeleton screens for slow loading product pages")
     * "somewhat_specific": Some details but also generic statements
     * "generic": Mostly "AI can improve everything" without concrete mechanisms

6. has_annotations: Only evaluate for pages with page_role === "violation_detail" and has_image === true. For other pages, set to "none".
   **IMPORTANT: Annotations are SHORT TEXT MARKINGS or VISUAL MARKINGS that point to problems ON or IMMEDIATELY ADJACENT to the screenshot. Do NOT confuse annotations with the detailed analysis text below the screenshot.**
   
   Annotations are SHORT markers that directly point to problems on the screenshot:
   - Visual markings ON the screenshot: red boxes, squares, rectangles, borders, arrows, lines, circles, highlights, underlines drawn directly on the image
   - Short text labels ON or IMMEDIATELY ADJACENT to the screenshot: brief labels, numbers, short notes (e.g., "Issue 1", "Problem here", "Missing button") placed on the image or right next to it
   
   **CRITICAL: What does NOT count as annotation:**
   - Detailed analysis paragraphs below the screenshot (these are part of the violation description, not annotations)
   - Long explanatory text that analyzes the screenshot content
   - Any text that is part of the main body content describing the violation
   
   **What DOES count as annotation:**
   - Short text labels/notes drawn ON the screenshot itself
   - Short text labels placed immediately next to or adjacent to the screenshot (e.g., "Issue 1", "Problem", "Missing")
   - Visual markings (boxes, arrows, circles) on the screenshot
   - Brief callouts or pointers that directly reference specific elements in the screenshot
   
   Rating levels (BE GENEROUS AND LENIENT):
    - "high": Screenshots show clear visual markings OR multiple short text labels that point to problems
      (e.g., multiple boxes/arrows/circles with short labels like "Issue 1", "Problem here", or clear callouts)
      **BE GENEROUS: If there are 2+ visual markings OR 2+ text labels, consider "high"**
    - "medium": There are visible markings OR some short text labels on the screenshot or immediately adjacent
      (e.g., one or a few boxes/arrows/highlights, or a few short labels like "Issue 1", "Missing button")
      **BE GENEROUS: If there is ANY visual marking OR ANY text label, strongly consider "medium"**
    - "low": There is at least one simple marking OR one brief text label OR any indication that the student attempted to mark the screenshot
      (e.g., a single box/arrow/circle, one short label like "Problem" or "Issue", or even a subtle highlight or underline)
      **BE GENEROUS: If there is ANY visible attempt to mark or label the screenshot, use "low" instead of "none"**
    - "none": ONLY use this when screenshots are completely unmarked with NO visual markings AND NO text labels anywhere near the screenshot
      **BE STRICT: Only use "none" if you are absolutely certain there are NO markings, labels, highlights, or any form of annotation attempt**
 
   Key guidelines (BE GENEROUS):
    - Visual markings (boxes, arrows, circles, borders, frames, highlights, underlines) drawn ON the screenshot → count as annotation
    - Short text labels ON the screenshot (e.g., "Issue 1", "Problem") → count as annotation
    - Short text labels immediately adjacent to the screenshot (e.g., "Issue 1" right next to the image) → count as annotation
    - Even subtle markings (light highlights, faint boxes, small arrows) → count as annotation
    - Text that appears near the screenshot (even if not directly on it) that references specific elements → consider as annotation
    - Long explanatory text describing the problem → do NOT count as annotation (but be generous with shorter text near the image)
    - **GENEROUS RULE: If you can see ANY box, border, frame, highlight, underline, or any visual marking ON the screenshot → at least "low", prefer "medium"**
    - **GENEROUS RULE: If you can see ANY arrow, line, circle, or highlight ON the screenshot → prefer "medium" or "high"**
    - **GENEROUS RULE: If you can see ANY short text labels, numbers, or brief notes ON or immediately adjacent to the screenshot → prefer "medium" or "high"**
    - **GENEROUS RULE: When unsure between two levels, ALWAYS choose the more generous one (e.g., prefer "low" over "none", "medium" over "low", "high" over "medium")**
    - **GENEROUS RULE: Only use "none" when you are absolutely certain screenshots are completely unmarked (no visual markings AND no short text labels on or adjacent to the screenshot)**
    - **GENEROUS RULE: If there is ANY indication that the student tried to annotate (even if minimal or subtle), use "low" at minimum**

7. Keep it compact:
   - text_summary ≤ 2 sentences
   - llm_note ≤ 2 sentences
   - At most 5 fragments per page
   - Paraphrase, don't copy long quotes
   - main_heading max 50 characters

CRITICAL: Output ONLY valid JSON. No markdown, no explanations, just the JSON object."""
    
    return prompt


def get_current_prompt() -> str:
    """Get the current grading prompt. First try grading_prompt.txt, then saved_prompt.txt (legacy), then use default."""
    # Try to load grading_prompt.txt first (primary prompt file)
    if GRADING_PROMPT_FILE.exists():
        try:
            with open(GRADING_PROMPT_FILE, "r", encoding="utf-8") as f:
                prompt = f.read().strip()
                # Remove markdown code fences if present
                if prompt.startswith("```"):
                    prompt = prompt.split("```", 2)[-1].strip()
                if prompt.endswith("```"):
                    prompt = prompt.rsplit("```", 1)[0].strip()
                if prompt.endswith("---"):
                    prompt = prompt.rsplit("---", 1)[0].strip()
                if prompt:
                    return prompt
        except Exception as e:
            print(f"[WARNING] Failed to load grading_prompt.txt: {e}")
    
    # Fallback to legacy saved_prompt.txt
    if SAVED_PROMPT_FILE.exists():
        try:
            with open(SAVED_PROMPT_FILE, "r", encoding="utf-8") as f:
                saved_prompt = f.read().strip()
                # Remove markdown code fences if present
                if saved_prompt.startswith("```"):
                    saved_prompt = saved_prompt.split("```", 2)[-1].strip()
                if saved_prompt.endswith("```"):
                    saved_prompt = saved_prompt.rsplit("```", 1)[0].strip()
                if saved_prompt.endswith("---"):
                    saved_prompt = saved_prompt.rsplit("---", 1)[0].strip()
                if saved_prompt:
                    return saved_prompt
        except Exception as e:
            print(f"[WARNING] Failed to load saved_prompt.txt: {e}")
    
    # Fallback: Use default refined prompt template
    return DEFAULT_REFINED_PROMPT

def save_prompt_to_backend(prompt: str) -> bool:
    """Save prompt to backend permanently. Saves to grading_prompt.txt (primary) and optionally to saved_prompt.txt (legacy)."""
    try:
        # Save to primary grading_prompt.txt
        GRADING_PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GRADING_PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[INFO] Prompt saved to {GRADING_PROMPT_FILE}")
        
        # Also save to legacy saved_prompt.txt for backward compatibility
        SAVED_PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SAVED_PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"[INFO] Prompt also saved to legacy {SAVED_PROMPT_FILE}")
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save prompt: {e}")
        return False


def call_openai_api(prompt: str, system_prompt: str = "") -> str:
    """Call OpenAI API for critique/refinement. Falls back to Gemini if OpenAI not available."""
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    
    if not openai_api_key:
        # Fallback: Use Gemini as AI B if OpenAI not configured
        if MODEL:
            try:
                full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
                response = MODEL.generate_content(full_prompt)
                return response.text
            except Exception as e:
                return f"Error calling Gemini: {str(e)}"
        return "OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."
    
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o-mini",  # Use cost-effective model
            "messages": [
                {"role": "system", "content": system_prompt} if system_prompt else None,
                {"role": "user", "content": prompt}
            ]
        }
        # Remove None values
        data["messages"] = [msg for msg in data["messages"] if msg is not None]
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except ImportError:
        # If requests not available, fallback to Gemini
        if MODEL:
            try:
                full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
                response = MODEL.generate_content(full_prompt)
                return response.text
            except Exception as e:
                return f"Error: {str(e)}"
        return "OpenAI API not available. Please install 'requests' package or configure OpenAI API key."
    except Exception as e:
        return f"Error calling OpenAI API: {str(e)}"


@app.get("/api/get-current-prompt")
async def get_current_prompt_endpoint() -> Dict[str, Any]:
    """Get the current grading prompt."""
    try:
        prompt = get_current_prompt()
        return {"prompt": prompt}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get current prompt: {str(e)}")


@app.post("/api/start-prompt-refinement")
async def start_prompt_refinement(request: Dict[str, Any]) -> Dict[str, Any]:
    """Start a new prompt refinement session."""
    original_prompt = request.get("originalPrompt", "")
    iterations = request.get("iterations", 2)
    
    if not original_prompt:
        raise HTTPException(status_code=400, detail="Original prompt is required")
    
    session_id = f"refinement-{int(time.time() * 1000)}"
    
    session = {
        "id": session_id,
        "originalPrompt": original_prompt,
        "versions": [],
        "currentVersion": 0,
        "status": "idle",
        "iterations": iterations,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }
    
    refinement_sessions[session_id] = session
    
    # Save session to file
    session_file = PROMPT_REFINEMENT_DIR / f"{session_id}.json"
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)
    
    return {"session": session}


@app.post("/api/critique-prompt")
async def critique_prompt(request: Dict[str, Any]) -> Dict[str, Any]:
    """Round 1: Critic B critiques P0 and generates P1 with problem analysis."""
    session_id = request.get("sessionId")
    round_num = request.get("round", 1)
    step = request.get("step")  # "critic_b_round1" or "critic_b_round3"
    
    if not session_id or session_id not in refinement_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = refinement_sessions[session_id]
    
    # Get P0 (original) or P2 (for round 3)
    if step == "critic_b_round1":
        # Round 1: Critique original prompt P0
        prompt_to_critique = session["originalPrompt"]
        prompt_label = "P0"
    elif step == "critic_b_round3":
        # Round 3: Critique P2
        p2_versions = [v for v in session["versions"] if v.get("type") == "designed" and v.get("label") == "P2"]
        if not p2_versions:
            raise HTTPException(status_code=400, detail="P2 not found for round 3 critique")
        prompt_to_critique = p2_versions[-1]["prompt"]
        prompt_label = "P2"
    else:
        raise HTTPException(status_code=400, detail="Invalid step. Use 'critic_b_round1' or 'critic_b_round3'")
    
    # Load rubric for context
    rubric_context = ""
    if RUBRIC_DATA:
        criteria_list = [f"{c.get('title', 'N/A')} ({c.get('points', 0)} pts)" for c in RUBRIC_DATA.get("rubric", {}).get("criteria", [])]
        rubric_context = f"\n\nCOURSE RUBRIC CONTEXT:\n- Criteria: {', '.join(criteria_list[:5])}...\n"
    
    # Critic B's prompt (focusing on fairness, consistency, hallucination prevention, operability)
    critic_b_prompt = f"""You are now playing the role of Prompt Critic B. Your task is to critically evaluate the following grading prompt from the perspectives of:
1. Scoring fairness - Will this prompt lead to fair and consistent scoring?
2. Consistency - Are the evaluation criteria clear and consistently applicable?
3. Hallucination prevention - Does this prompt reduce the risk of AI making up violations or scores?
4. Operability - Is this prompt specific and actionable for both AI and human reviewers?
5. LLM capability constraints - Does this prompt account for LLM limitations, especially JSON/array handling?

CRITICAL REQUIREMENTS TO CHECK:
- The prompt must NOT add new categories to score_breakdown. It should only use the existing categories defined in the rubric.
- The prompt must ensure that grading considers evaluations from ALL pages and synthesizes them comprehensively for final scoring, not just evaluating pages in isolation.
-- The prompt must NOT change the ScoringInput or ScoringOutput JSON schemas, and must NOT add/remove/rename ANY keys in those structures. Treat those JSON field names and structures as a fixed API contract.
-- The overall section structure, headings, and numbering of the grading prompt should remain stable. Recommend incremental, local edits (clarifications, wording tweaks) instead of large-scale rewrites.

CRITICAL: LLM CAPABILITY CONSTRAINTS - You MUST evaluate whether the prompt accounts for these limitations:

**CORE PRINCIPLE: The prompt must be ACCURATE, CONCISE, EFFECTIVE, and LLM-UNDERSTANDABLE.**

When critiquing the prompt, you MUST ensure it:
1. **Accuracy**: Preserves all essential grading criteria and requirements
2. **Conciseness**: Uses the most minimal language possible while maintaining clarity
3. **Effectiveness**: Achieves the grading goals with maximum efficiency
4. **LLM-Understandability**: Written in language that LLMs can reliably parse and execute

**Specific LLM Limitations to Consider:**
   - LLMs are prone to JSON formatting errors, especially with arrays and nested structures
   - Array handling is particularly fragile: LLMs may truncate arrays, omit closing brackets, or create malformed JSON
   - Debugging JSON parsing errors is time-consuming and costly
   - Complex instructions increase the risk of misinterpretation or partial execution
   - When critiquing the prompt, check if it:
     * Minimizes complex nested JSON structures (especially arrays within arrays)
     * Prefers flat structures over deeply nested ones
     * Keeps array elements simple and well-defined
     * Provides clear, explicit examples of expected JSON array formats
     * Avoids requiring LLMs to generate large arrays (if possible, uses simpler data structures)
     * Explicitly instructs the LLM to properly close all brackets and arrays
     * Uses string-based formats or simpler structures instead of complex nested arrays when possible
     * Uses direct, unambiguous language that LLMs can easily understand
     * Avoids ambiguous phrasing or complex conditional logic
   - If the prompt has complex array structures or unclear instructions, suggest simplifications to reduce JSON parsing failure risk and improve LLM comprehension

GRADING PROMPT TO CRITIQUE ({prompt_label}):
---
{prompt_to_critique}
---{rubric_context}

Please provide:
1. A detailed problem analysis - Identify specific issues in the prompt from the four perspectives above, and check if it violates the critical requirements
2. An improved version of the prompt (P1 or P3) that addresses these issues and ensures:
   - No new categories are added to score_breakdown
   - Grading synthesizes evaluations from all pages comprehensively

Format your response as follows:
---
IMPROVED PROMPT (P1/P3):
[Your improved prompt here]
---

PROBLEM ANALYSIS:
[Detailed analysis of issues found, organized by the four perspectives. This will be shown to the professor.]
---"""

    try:
        # Use OpenAI/Gemini fallback for Critic B
        response_text = call_openai_api(
            critic_b_prompt,
            system_prompt="You are Prompt Critic B, an expert in educational assessment and grading prompt design. Focus on fairness, consistency, hallucination prevention, and operability."
        )
        
        # Parse response
        if "IMPROVED PROMPT" in response_text and "PROBLEM ANALYSIS:" in response_text:
            parts = response_text.split("PROBLEM ANALYSIS:")
            improved_prompt = parts[0].replace("IMPROVED PROMPT", "").replace("(P1/P3):", "").strip("---").strip()
            problem_analysis = parts[1].strip("---").strip()
        elif "IMPROVED PROMPT" in response_text:
            improved_prompt = response_text.split("IMPROVED PROMPT")[1].split("---")[1].strip() if "---" in response_text else response_text
            problem_analysis = "Critique completed, but detailed analysis not provided."
        else:
            improved_prompt = response_text
            problem_analysis = "Critique completed."
        
        # Determine label (P1 for round 1, P3 for round 3)
        prompt_label_new = "P1" if step == "critic_b_round1" else "P3"
        
        version = {
            "id": f"{session_id}-critic-b-{step}",
            "version": len(session["versions"]) + 1,
            "prompt": improved_prompt,
            "aiModel": "openai",
            "critique": problem_analysis,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "round": round_num,
            "type": "critic",
            "label": prompt_label_new,
            "problemAnalysis": problem_analysis,
        }
        
    except Exception as e:
        improved_prompt = f"Error: {str(e)}\n\n{prompt_to_critique}"
        problem_analysis = f"Error occurred: {str(e)}"
        prompt_label_new = "P1" if step == "critic_b_round1" else "P3"
        version = {
            "id": f"{session_id}-critic-b-{step}",
            "version": len(session["versions"]) + 1,
            "prompt": improved_prompt,
            "aiModel": "openai",
            "critique": problem_analysis,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "round": round_num,
            "type": "critic",
            "label": prompt_label_new,
            "problemAnalysis": problem_analysis,
        }
    
    session["versions"].append(version)
    session["currentVersion"] = round_num
    
    # Save session
    session_file = PROMPT_REFINEMENT_DIR / f"{session_id}.json"
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)
    
    refinement_sessions[session_id] = session
    
    return {"session": session}


@app.post("/api/refine-prompt")
async def refine_prompt(request: Dict[str, Any]) -> Dict[str, Any]:
    """Round 2: Designer A compares P0 and P1, synthesizes P2. Or Round 4: Designer A synthesizes P2 and P3."""
    session_id = request.get("sessionId")
    round_num = request.get("round", 1)
    step = request.get("step", "designer_a_round2")  # "designer_a_round2" or "designer_a_round4"
    
    if not session_id or session_id not in refinement_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = refinement_sessions[session_id]
    
    # Get P0 (original)
    p0 = session["originalPrompt"]
    
    if step == "designer_a_round2":
        # Round 2: Compare P0 and P1, synthesize P2
        p1_versions = [v for v in session["versions"] if v.get("type") == "critic" and v.get("label") == "P1"]
        if not p1_versions:
            raise HTTPException(status_code=400, detail="P1 not found for synthesis")
        p1 = p1_versions[-1]["prompt"]
        p1_analysis = p1_versions[-1].get("problemAnalysis", "")
        output_label = "P2"
    elif step == "designer_a_round4":
        # Round 4: Synthesize P2 and P3
        p2_versions = [v for v in session["versions"] if v.get("type") == "designed" and v.get("label") == "P2"]
        p3_versions = [v for v in session["versions"] if v.get("type") == "critic" and v.get("label") == "P3"]
        if not p2_versions or not p3_versions:
            raise HTTPException(status_code=400, detail="P2 or P3 not found for synthesis")
        p1 = p2_versions[-1]["prompt"]
        p1_analysis = p3_versions[-1].get("problemAnalysis", "")
        output_label = "P4"
    else:
        raise HTTPException(status_code=400, detail="Invalid step")
    
    # Load rubric for alignment
    rubric_context = ""
    if RUBRIC_DATA:
        criteria_list = [f"{c.get('title', 'N/A')} ({c.get('points', 0)} pts)" for c in RUBRIC_DATA.get("rubric", {}).get("criteria", [])]
        rubric_context = f"\n\nCOURSE RUBRIC CONTEXT:\n- Criteria: {', '.join(criteria_list)}\n"
    
    # Designer A's prompt
    designer_a_prompt = f"""You are now playing the role of Prompt Designer A. You are given the original prompt P0 and Critic B's improved version P1 (with problem analysis).

Your task:
1. Summarize the strengths of P0 and P1 respectively
2. Synthesize a better prompt P2 that:
   - Combines the best elements from both P0 and P1
   - Ensures specificity and operability
   - Aligns with the course rubric
   - Is clear for both AI and human reviewers
   - MUST NOT add new categories to score_breakdown (only use existing rubric categories)
   - MUST ensure grading synthesizes evaluations from ALL pages comprehensively, not just evaluating pages in isolation
   - MUST NOT change the ScoringInput or ScoringOutput JSON schemas, and MUST NOT add/remove/rename ANY keys in those structures. Treat all JSON field names and structures as a fixed API contract.
   - SHOULD keep the existing top-level sections, headings, and numbering. Make conservative, local edits rather than rewriting the entire prompt.
   
CRITICAL: LLM CAPABILITY CONSTRAINTS - You MUST consider these limitations when refining the prompt:

**CORE PRINCIPLE: The refined prompt must be ACCURATE, CONCISE, EFFECTIVE, and LLM-UNDERSTANDABLE.**

When designing the prompt, you MUST:
1. **Accuracy**: Preserve all essential grading criteria and requirements
2. **Conciseness**: Use the most minimal language possible while maintaining clarity - every word should serve a purpose
3. **Effectiveness**: Achieve grading goals with maximum efficiency - avoid redundancy
4. **LLM-Understandability**: Write in language that LLMs can reliably parse and execute - use direct, unambiguous instructions

**Specific LLM Limitations to Address:**
   - LLMs are prone to JSON formatting errors, especially with arrays and nested structures
   - Array handling is particularly fragile: LLMs may truncate arrays, omit closing brackets, or create malformed JSON
   - Debugging JSON parsing errors is time-consuming and costly
   - Complex instructions increase the risk of misinterpretation or partial execution
   - When designing the prompt, you MUST:
     * Minimize complex nested JSON structures (especially arrays within arrays)
     * Prefer flat structures over deeply nested ones
     * Keep array elements simple and well-defined
     * Provide clear, explicit examples of expected JSON array formats
     * Avoid requiring LLMs to generate large arrays (if possible, use simpler data structures)
     * Ensure the prompt explicitly instructs the LLM to properly close all brackets and arrays
     * Consider using string-based formats or simpler structures instead of complex nested arrays when possible
     * Use direct, unambiguous language that LLMs can easily understand
     * Avoid ambiguous phrasing or complex conditional logic
   - The refined prompt should be designed to minimize the risk of JSON parsing failures, array corruption, and LLM misinterpretation

ORIGINAL PROMPT (P0):
---
{p0}
---

CRITIC B'S IMPROVED PROMPT (P1):
---
{p1}
---

CRITIC B'S PROBLEM ANALYSIS:
---
{p1_analysis}
---{rubric_context}

Please provide:
1. A summary of strengths of P0 and P1
2. A synthesized prompt P2 that combines the best of both

Format your response as follows:
---
STRENGTHS SUMMARY:
P0 Strengths: [List key strengths of original prompt]
P1 Strengths: [List key strengths of Critic B's improved version]
---

SYNTHESIZED PROMPT (P2):
[Your synthesized prompt here, combining best elements from P0 and P1]
---

DESIGN SUMMARY:
[Brief 2-3 sentence summary of how you synthesized P2 and what makes it better]
---"""

    try:
        if MODEL:
            response = MODEL.generate_content(designer_a_prompt)
            response_text = response.text
            
            # Parse response
            strengths_summary = ""
            synthesized_prompt = ""
            design_summary = ""
            
            if "STRENGTHS SUMMARY:" in response_text and "SYNTHESIZED PROMPT" in response_text:
                parts = response_text.split("SYNTHESIZED PROMPT")
                strengths_summary = parts[0].replace("STRENGTHS SUMMARY:", "").strip("---").strip()
                remaining = parts[1] if len(parts) > 1 else ""
                
                if "DESIGN SUMMARY:" in remaining:
                    prompt_parts = remaining.split("DESIGN SUMMARY:")
                    synthesized_prompt = prompt_parts[0].replace("(P2):", "").strip("---").strip()
                    design_summary = prompt_parts[1].strip("---").strip()
                else:
                    synthesized_prompt = remaining.replace("(P2):", "").strip("---").strip()
                    design_summary = "Synthesized from P0 and P1."
            elif "SYNTHESIZED PROMPT" in response_text:
                synthesized_prompt = response_text.split("SYNTHESIZED PROMPT")[1].split("---")[1].strip() if "---" in response_text else response_text
                design_summary = "Synthesized from P0 and P1."
            else:
                synthesized_prompt = response_text
                design_summary = "Synthesized from P0 and P1."
        else:
            synthesized_prompt = p1  # Fallback to P1
            design_summary = "Model not available - using P1"
            strengths_summary = "Model not available"
    except Exception as e:
        synthesized_prompt = f"Error: {str(e)}\n\n{p1}"
        design_summary = f"Error occurred: {str(e)}"
        strengths_summary = f"Error occurred: {str(e)}"
    
    version = {
        "id": f"{session_id}-designer-a-{step}",
        "version": len(session["versions"]) + 1,
        "prompt": synthesized_prompt,
        "aiModel": "gemini",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "round": round_num,
        "type": "designed",
        "label": output_label,
        "refinementSummary": design_summary,
        "strengthsSummary": strengths_summary,
    }
    session["versions"].append(version)
    session["currentVersion"] = round_num
    
    # Save session
    session_file = PROMPT_REFINEMENT_DIR / f"{session_id}.json"
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)
    
    refinement_sessions[session_id] = session
    
    return {"session": session}


@app.post("/api/generate-final-prompt")
async def generate_final_prompt(request: Dict[str, Any]) -> Dict[str, Any]:
    """Final Review: Judge selects Best Prompt from P0, P1, P2, P3 (and P4 if exists)."""
    session_id = request.get("sessionId")
    
    if not session_id or session_id not in refinement_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = refinement_sessions[session_id]
    
    # Collect all prompt versions (P0, P1, P2, P3, P4)
    p0 = session["originalPrompt"]
    p1_versions = [v for v in session["versions"] if v.get("label") == "P1"]
    p2_versions = [v for v in session["versions"] if v.get("label") == "P2"]
    p3_versions = [v for v in session["versions"] if v.get("label") == "P3"]
    p4_versions = [v for v in session["versions"] if v.get("label") == "P4"]
    
    # Build candidate prompts list
    candidates = [{"label": "P0", "prompt": p0, "source": "Original"}]
    if p1_versions:
        candidates.append({"label": "P1", "prompt": p1_versions[-1]["prompt"], "source": "Critic B Round 1"})
    if p2_versions:
        candidates.append({"label": "P2", "prompt": p2_versions[-1]["prompt"], "source": "Designer A Round 2"})
    if p3_versions:
        candidates.append({"label": "P3", "prompt": p3_versions[-1]["prompt"], "source": "Critic B Round 3"})
    if p4_versions:
        candidates.append({"label": "P4", "prompt": p4_versions[-1]["prompt"], "source": "Designer A Round 4"})
    
    if len(candidates) < 2:
        raise HTTPException(status_code=400, detail="Not enough prompt versions for final judgment")
    
    # Build candidates text
    candidates_text = "\n\n---\n\n".join([
        f"{c['label']} ({c['source']}):\n{c['prompt']}"
        for c in candidates
    ])
    
    # Load rubric for alignment check
    rubric_context = ""
    if RUBRIC_DATA:
        criteria_list = [f"{c.get('title', 'N/A')} ({c.get('points', 0)} pts)" for c in RUBRIC_DATA.get("rubric", {}).get("criteria", [])]
        rubric_context = f"\n\nCOURSE RUBRIC:\n- Criteria: {', '.join(criteria_list)}\n"
    
    # Judge's prompt
    judge_prompt = f"""You are now playing the role of Prompt Judge. Your task is to evaluate {len(candidates)} grading prompt candidates and select the best one.

CANDIDATE PROMPTS:
---
{candidates_text}
---{rubric_context}

Please evaluate each prompt (0-10 points) based on:
1. Alignment with course rubric - How well does the prompt align with the course rubric requirements?
2. Clarity for students/TAs - How clear and understandable is the prompt for both students and teaching assistants?
3. Reduction of hallucinations and arbitrary scoring - How well does the prompt prevent AI from making up violations or arbitrary scores?
4. Ease of incorporating HITL corrections - How easy is it to incorporate Human-in-the-Loop corrections into the grading process?
5. Adherence to critical requirements:
   - Does the prompt avoid adding new categories to score_breakdown (only uses existing rubric categories)?
   - Does the prompt ensure grading synthesizes evaluations from ALL pages comprehensively, not just evaluating pages in isolation?
6. LLM capability constraints - **CRITICAL PRINCIPLE: The prompt must be ACCURATE, CONCISE, EFFECTIVE, and LLM-UNDERSTANDABLE.**
   
   **Core Evaluation Criteria:**
   - **Accuracy**: Does the prompt preserve all essential grading criteria and requirements?
   - **Conciseness**: Does it use the most minimal language possible while maintaining clarity? (Every word should serve a purpose)
   - **Effectiveness**: Does it achieve grading goals with maximum efficiency? (Avoids redundancy)
   - **LLM-Understandability**: Is it written in language that LLMs can reliably parse and execute? (Uses direct, unambiguous instructions)
   
   **Specific Technical Checks:**
   - Does it minimize complex nested JSON structures (especially arrays within arrays)?
   - Does it prefer flat structures over deeply nested ones?
   - Does it keep array elements simple and well-defined?
   - Does it provide clear, explicit examples of expected JSON array formats?
   - Does it avoid requiring LLMs to generate large arrays (uses simpler data structures when possible)?
   - Does it explicitly instruct the LLM to properly close all brackets and arrays?
   - Does it use string-based formats or simpler structures instead of complex nested arrays when possible?
   - Does it avoid ambiguous phrasing or complex conditional logic?
   - **CRITICAL: Prompts that minimize JSON parsing failure risk, array corruption, and LLM misinterpretation should be strongly preferred, as debugging JSON errors and fixing misunderstandings is time-consuming and costly**

Then:
1. Provide a scoring table for all candidates
2. Select one as the "Best Prompt"
3. Provide a slightly polished final version

Format your response as follows:
---
SCORING TABLE:
P0: [score]/10 - [brief reason]
P1: [score]/10 - [brief reason]
P2: [score]/10 - [brief reason]
[P3/P4 if exists]
---

BEST PROMPT SELECTED:
[Label of best prompt, e.g., P2]
---

REASONING:
[2-3 sentences explaining why this prompt was selected]
---

FINAL POLISHED PROMPT:
[Your slightly polished version of the best prompt]
---

REFINEMENT REPORT:
[3-5 sentence report explaining what was refined and improved compared to the original P0]
---"""

    refinement_report = ""
    scoring_table = ""
    best_prompt_label = ""
    reasoning = ""
    
    try:
        if MODEL:
            response = MODEL.generate_content(judge_prompt)
            response_text = response.text
            
            # Parse response
            if "SCORING TABLE:" in response_text:
                scoring_table = response_text.split("SCORING TABLE:")[1].split("---")[0].strip() if "---" in response_text.split("SCORING TABLE:")[1] else ""
            
            if "BEST PROMPT SELECTED:" in response_text:
                best_prompt_label = response_text.split("BEST PROMPT SELECTED:")[1].split("---")[0].strip() if "---" in response_text.split("BEST PROMPT SELECTED:")[1] else ""
            
            if "REASONING:" in response_text:
                reasoning = response_text.split("REASONING:")[1].split("---")[0].strip() if "---" in response_text.split("REASONING:")[1] else ""
            
            if "FINAL POLISHED PROMPT:" in response_text:
                parts = response_text.split("FINAL POLISHED PROMPT:")
                if "REFINEMENT REPORT:" in parts[1]:
                    final_parts = parts[1].split("REFINEMENT REPORT:")
                    final_prompt = final_parts[0].strip("---").strip()
                    refinement_report = final_parts[1].strip("---").strip()
                else:
                    final_prompt = parts[1].strip("---").strip()
                    refinement_report = "Final prompt polished by Judge."
            elif "FINAL PROMPT:" in response_text:
                final_prompt = response_text.split("FINAL PROMPT:")[1].strip("---").strip()
                refinement_report = "Final prompt selected by Judge."
            else:
                # Fallback: use the best candidate
                best_candidate = next((c for c in candidates if c["label"] == best_prompt_label), candidates[-1])
                final_prompt = best_candidate["prompt"]
                refinement_report = f"Selected {best_candidate['label']} as best prompt."
        else:
            # Fallback: use P2 or latest
            best_candidate = p2_versions[-1] if p2_versions else candidates[-1]
            final_prompt = best_candidate["prompt"] if isinstance(best_candidate, dict) else best_candidate
            refinement_report = "Model not available - using latest version"
    except Exception as e:
        best_candidate = candidates[-1]
        final_prompt = best_candidate["prompt"]
        refinement_report = f"Error occurred: {str(e)}"
    
    session["status"] = "completed"
    session["finalPrompt"] = final_prompt
    session["refinementReport"] = refinement_report
    session["scoringTable"] = scoring_table
    session["bestPromptLabel"] = best_prompt_label
    session["judgeReasoning"] = reasoning
    
    # Save final version
    final_version = {
        "id": f"{session_id}-final",
        "version": len(session["versions"]) + 1,
        "prompt": final_prompt,
        "aiModel": "judge",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "type": "final",
        "label": "Best Prompt",
        "refinementReport": refinement_report,
        "scoringTable": scoring_table,
        "bestPromptLabel": best_prompt_label,
        "reasoning": reasoning,
    }
    session["versions"].append(final_version)
    
    # Save session
    session_file = PROMPT_REFINEMENT_DIR / f"{session_id}.json"
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)
    
    refinement_sessions[session_id] = session
    
    return {
        "session": session,
        "finalPrompt": final_prompt,
        "refinementReport": refinement_report,
        "scoringTable": scoring_table,
        "bestPromptLabel": best_prompt_label,
        "judgeReasoning": reasoning,
    }


@app.post("/api/save-prompt")
async def save_prompt(request: Dict[str, Any]) -> Dict[str, Any]:
    """Save prompt to backend permanently."""
    prompt = request.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    
    success = save_prompt_to_backend(prompt)
    if success:
        return {
            "status": "success",
            "message": "Prompt saved to backend successfully",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save prompt")


# ============================================================================
# Ruthless Multi-panel Audit System
# ============================================================================

RUTHLESS_AUDIT_DIR = Path(__file__).parent.parent / "output_static" / "ruthless_audits"
RUTHLESS_AUDIT_DIR.mkdir(parents=True, exist_ok=True)


async def run_ruthless_audit(prompt: str, system_context: str = "") -> Dict[str, Any]:
    """
    Run a ruthless multi-panel audit on the grading prompt/system.
    This is a comprehensive architectural review, governance check, rot analysis,
    system critique, and recommendation generation.
    
    Returns a detailed audit report with:
    - Architectural issues
    - Governance violations
    - Technical debt / rot
    - System weaknesses
    - Recommendations
    """
    audit_prompt = f"""You are conducting a RUTHLESS MULTI-PANEL AUDIT of an autograder system's grading prompt and architecture.

This is a comprehensive quality gate review that should be thorough, critical, and constructive.

SYSTEM CONTEXT:
{system_context if system_context else "Autograder for UX/HCI heuristic evaluation assignments. System uses LLM (Gemini) to grade student submissions page-by-page, then aggregates into issues and final scores."}

CURRENT GRADING PROMPT:
```
{prompt}
```

CONDUCT A COMPREHENSIVE AUDIT ACROSS THESE DIMENSIONS:

1. **ARCHITECTURAL REVIEW**
   - Is the prompt structure logical and maintainable?
   - Are there clear separation of concerns?
   - Is the prompt too monolithic or appropriately modular?
   - Are there missing abstractions or over-engineering?

2. **GOVERNANCE CHECK**
   - Does the prompt follow best practices for LLM prompt engineering?
   - Are there safety concerns (bias, fairness, accuracy)?
   - Are evaluation criteria clear and unambiguous?
   - Is there proper error handling guidance?

3. **ROT ANALYSIS**
   - Are there outdated instructions or deprecated patterns?
   - Is there technical debt in the prompt structure?
   - Are there inconsistencies or contradictions?
   - Is the prompt becoming too complex or bloated?

4. **SYSTEM CRITIQUE**
   - What are the fundamental weaknesses in the current approach?
   - Are there edge cases not handled?
   - Is the prompt too rigid or too flexible?
   - Are there scalability concerns?

5. **RECOMMENDATION GENERATION**
   - What specific improvements should be made?
   - What should be prioritized (P0, P1, P2)?
   - What are the risks of NOT making these changes?
   - What are quick wins vs. long-term improvements?

OUTPUT FORMAT (JSON):
{{
  "audit_id": "audit-<timestamp>",
  "timestamp": "<ISO timestamp>",
  "summary": "1-2 sentence executive summary",
  "architectural_issues": [
    {{
      "severity": "critical|high|medium|low",
      "category": "structure|modularity|abstraction|maintainability",
      "issue": "Description of the issue",
      "impact": "What this means for the system",
      "recommendation": "What should be done"
    }}
  ],
  "governance_violations": [
    {{
      "severity": "critical|high|medium|low",
      "category": "bias|fairness|accuracy|safety|clarity",
      "issue": "Description of the violation",
      "impact": "What this means for grading quality",
      "recommendation": "What should be done"
    }}
  ],
  "rot_analysis": [
    {{
      "severity": "critical|high|medium|low",
      "category": "outdated|debt|inconsistency|complexity",
      "issue": "Description of the rot",
      "impact": "What this means long-term",
      "recommendation": "What should be done"
    }}
  ],
  "system_critique": [
    {{
      "severity": "critical|high|medium|low",
      "category": "weakness|edge_case|rigidity|scalability",
      "issue": "Description of the critique",
      "impact": "What this means for the system",
      "recommendation": "What should be done"
    }}
  ],
  "prioritized_recommendations": [
    {{
      "priority": "P0|P1|P2",
      "category": "architectural|governance|rot|system",
      "title": "Short title",
      "description": "Detailed description",
      "effort": "low|medium|high",
      "impact": "low|medium|high",
      "risk_if_not_done": "What happens if we don't fix this"
    }}
  ],
  "quick_wins": [
    "List of easy improvements that can be made immediately"
  ],
  "long_term_improvements": [
    "List of strategic improvements for future iterations"
  ],
  "overall_assessment": "Overall health score and assessment (1-2 paragraphs)"
}}

Be RUTHLESS but CONSTRUCTIVE. This is a quality gate - find real problems, not just minor suggestions.
The prompt will be long. The answer even longer. This is normal and expected for a comprehensive audit.
"""
    
    try:
        generation_config = {
            "temperature": 0.3,  # Lower temperature for more consistent, critical analysis
            "max_output_tokens": 16384,  # Long response expected
            "response_mime_type": "application/json",
        }
        
        response = MODEL.generate_content(audit_prompt, generation_config=generation_config)
        
        # Extract JSON from response
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.startswith("```"):
            response_text = response_text[3:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()
        
        audit_result = json.loads(response_text)
        
        # Add timestamp if not present
        if "timestamp" not in audit_result:
            audit_result["timestamp"] = datetime.now().isoformat()
        if "audit_id" not in audit_result:
            audit_result["audit_id"] = f"audit-{int(time.time() * 1000)}"
        
        # Save audit to file
        audit_file = RUTHLESS_AUDIT_DIR / f"{audit_result['audit_id']}.json"
        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump({
                "audit_result": audit_result,
                "prompt_audited": prompt,
                "system_context": system_context,
            }, f, indent=2, ensure_ascii=False)
        
        return audit_result
    except Exception as e:
        print(f"[ERROR] Ruthless audit failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run ruthless audit: {str(e)}")


@app.post("/api/ruthless-audit")
async def ruthless_audit_endpoint(request: Dict[str, Any]) -> Dict[str, Any]:
    """Run a ruthless multi-panel audit on the current grading prompt."""
    prompt = request.get("prompt", "")
    system_context = request.get("systemContext", "")
    
    if not prompt:
        # Load current prompt if not provided
        prompt = get_current_prompt()
    
    audit_result = await run_ruthless_audit(prompt, system_context)
    
    return {
        "status": "success",
        "audit": audit_result,
    }


# ============================================================================
# Enhanced Prompt Refinement Pipeline (Multi-Plan Generation & Comparison)
# ============================================================================

async def generate_multiple_plans(original_prompt: str, num_plans: int = 3) -> List[Dict[str, Any]]:
    """
    Generate 2-3 different grading strategy/evaluation plans.
    Each plan should propose a different approach to improving the prompt.
    """
    plans_prompt = f"""You are an expert prompt engineer tasked with improving a grading prompt for an autograder system.

CURRENT PROMPT:
```
{original_prompt}
```

Generate {num_plans} DIFFERENT and DISTINCT improvement plans. Each plan should propose a different strategic approach to improving this prompt, but **all plans must respect the existing JSON API contract**:
- Do NOT change the ScoringInput or ScoringOutput JSON schemas.
- Do NOT add, remove, or rename ANY keys or fields.
- Do NOT propose restructuring the JSON sections; focus on wording, clarification, and rubric guidance.

**CRITICAL PRINCIPLE: All improvements must prioritize making the prompt ACCURATE, CONCISE, EFFECTIVE, and LLM-UNDERSTANDABLE.**
- **Accuracy**: Preserve all essential grading criteria
- **Conciseness**: Use minimal language while maintaining clarity
- **Effectiveness**: Achieve goals with maximum efficiency
- **LLM-Understandability**: Use direct, unambiguous language that LLMs can reliably parse and execute

Each plan should include:
1. A clear strategy/approach (what's the main idea?)
2. Specific improvements to make (prioritizing LLM-friendly structures and clear instructions)
3. Rationale for why this approach would help (especially how it improves LLM comprehension and reduces parsing errors)
4. Expected benefits (including reduced JSON parsing failures and improved LLM execution reliability) - **REQUIRED: Must provide at least 2-3 specific benefits**
5. Potential risks or trade-offs

OUTPUT FORMAT (JSON):
{{
  "plans": [
    {{
      "plan_id": "plan_1",
      "strategy_name": "Short descriptive name",
      "strategy_description": "1-2 sentences describing the overall approach",
      "improvements": [
        {{
          "area": "What part of the prompt to improve",
          "current_state": "What it currently does",
          "proposed_change": "What to change it to",
          "rationale": "Why this change helps"
        }}
      ],
      "expected_benefits": [
        "Benefit 1: Specific improvement this plan will achieve",
        "Benefit 2: Another concrete benefit",
        "Benefit 3: Additional advantage"
      ],
      "potential_risks": [
        "List of potential risks or trade-offs"
      ],
      "complexity": "low|medium|high",
      "estimated_impact": "low|medium|high"
    }}
  ]
}}

**CRITICAL: Each plan MUST include a non-empty "expected_benefits" array with at least 2-3 specific, concrete benefits. Do NOT leave this field empty or use placeholder text.**

Make sure the plans are DISTINCTLY different - not just variations of the same idea.
Consider different angles: structural changes, clarity improvements, evaluation criteria refinement, error handling, etc.
"""
    
    try:
        generation_config = {
            "temperature": 0.7,  # Higher temperature for more creative/diverse plans
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        
        response = MODEL.generate_content(plans_prompt, generation_config=generation_config)
        response_text = response.text.strip()
        
        # Clean up potential markdown fences
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.startswith("```"):
            response_text = response_text[3:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()
        
        # Robust JSON parsing with multiple fallback layers
        plans_data = None
        try:
            # First attempt: Direct JSON parsing
            plans_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"[WARN] Direct JSON parse failed: {e}")
            error_msg = str(e)
            
            # Check if error is about unterminated string
            if "Unterminated string" in error_msg or "Expecting" in error_msg:
                print(f"[INFO] Detected unterminated string or malformed JSON, attempting fixes...")
            
            # Fallback 1: Extract JSON fragment from response and fix it
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_fragment = response_text[start : end + 1]
                try:
                    # Try to fix common JSON issues (unterminated strings, missing brackets, etc.)
                    json_fragment = fix_incomplete_json(json_fragment)
                    plans_data = json.loads(json_fragment)
                    print(f"[INFO] Successfully parsed JSON fragment after fixing")
                except json.JSONDecodeError as e2:
                    print(f"[WARN] JSON fragment parse also failed: {e2}")
                    # Fallback 2: More aggressive string termination fix
                    try:
                        # Try to fix unterminated strings more aggressively
                        # Find lines with unterminated strings and close them
                        lines = json_fragment.split('\n')
                        fixed_lines = []
                        for i, line in enumerate(lines):
                            # Count unescaped quotes in this line
                            unescaped_quotes = len(re.findall(r'(?<!\\)"', line))
                            if unescaped_quotes % 2 == 1:
                                # Odd number of quotes - likely unterminated
                                # Try to close the string at a reasonable position
                                if ':' in line and not line.rstrip().endswith('"'):
                                    # Find the value part after ':'
                                    colon_pos = line.find(':')
                                    value_part = line[colon_pos + 1:].strip()
                                    if value_part.startswith('"') and not value_part.endswith('"'):
                                        # Unterminated string value, try to close it
                                        # Find the last non-whitespace character before potential comma/brace
                                        last_char_pos = len(value_part) - 1
                                        while last_char_pos >= 0 and value_part[last_char_pos] in ' \t':
                                            last_char_pos -= 1
                                        if last_char_pos >= 0 and value_part[last_char_pos] != '"':
                                            # Add closing quote
                                            line = line[:colon_pos + 1] + value_part[:last_char_pos + 1] + '"' + line[colon_pos + 1 + last_char_pos + 1:]
                            fixed_lines.append(line)
                        
                        json_fragment = '\n'.join(fixed_lines)
                        json_fragment = fix_incomplete_json(json_fragment)
                        plans_data = json.loads(json_fragment)
                        print(f"[INFO] Successfully parsed after aggressive string fixing")
                    except json.JSONDecodeError as e3:
                        print(f"[WARN] Aggressive fixing also failed: {e3}")
                        # Fallback 3: Try to extract plans array using regex (last resort)
                        try:
                            # Try to find the plans array even if JSON is malformed
                            plans_match = re.search(r'"plans"\s*:\s*\[', response_text, re.DOTALL)
                            if plans_match:
                                # Try to extract the array content
                                start_pos = plans_match.end()
                                # Find matching closing bracket
                                bracket_count = 1
                                end_pos = start_pos
                                for i in range(start_pos, len(response_text)):
                                    if response_text[i] == '[':
                                        bracket_count += 1
                                    elif response_text[i] == ']':
                                        bracket_count -= 1
                                        if bracket_count == 0:
                                            end_pos = i
                                            break
                                
                                if end_pos > start_pos:
                                    plans_array_text = response_text[start_pos:end_pos]
                                    # Try to extract individual plan objects using regex
                                    plan_objects = []
                                    # Look for plan objects (simplified pattern)
                                    plan_pattern = r'\{\s*"plan_id"[^}]*\}'
                                    for plan_match in re.finditer(plan_pattern, plans_array_text, re.DOTALL):
                                        try:
                                            plan_text = plan_match.group(0)
                                            # Try to fix the plan object
                                            plan_text = fix_incomplete_json(plan_text)
                                            plan_obj = json.loads(plan_text)
                                            plan_objects.append(plan_obj)
                                        except:
                                            continue
                                    if plan_objects:
                                        plans_data = {"plans": plan_objects}
                                        print(f"[INFO] Extracted {len(plan_objects)} plans using regex fallback")
                        except Exception as e4:
                            print(f"[WARN] Regex extraction also failed: {e4}")
            
            # If all parsing attempts failed, raise a more informative error
            if not plans_data:
                error_preview = response_text[:1000] if len(response_text) > 1000 else response_text
                print(f"[ERROR] All JSON parsing attempts failed.")
                print(f"[ERROR] Original error: {error_msg}")
                print(f"[ERROR] Response preview (first 1000 chars): {error_preview}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to parse LLM response as JSON. The response may contain unterminated strings or malformed JSON. Original error: {error_msg}"
                )
        
        plans = plans_data.get("plans", [])
        # Validate and ensure expected_benefits exists for each plan
        for i, plan in enumerate(plans):
            if "expected_benefits" not in plan or not plan.get("expected_benefits"):
                print(f"[WARN] Plan {i+1} ({plan.get('plan_id', 'unknown')}) missing expected_benefits field")
                plan["expected_benefits"] = []
            # Ensure it's a list
            if not isinstance(plan.get("expected_benefits"), list):
                print(f"[WARN] Plan {i+1} expected_benefits is not a list, converting...")
                plan["expected_benefits"] = []
            # Log if empty
            if not plan.get("expected_benefits"):
                print(f"[WARN] Plan {i+1} ({plan.get('strategy_name', 'unknown')}) has empty expected_benefits")
            else:
                print(f"[INFO] Plan {i+1} has {len(plan.get('expected_benefits', []))} expected benefits")
        return plans
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to generate multiple plans: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate improvement plans: {str(e)}")


async def compare_plans(plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare multiple plans, analyzing strengths and weaknesses of each.
    """
    plans_json = json.dumps(plans, indent=2)
    
    comparison_prompt = f"""You are an expert evaluator comparing multiple prompt improvement plans.

PLANS TO COMPARE:
{plans_json}

**CRITICAL PRINCIPLE: Evaluate each plan based on whether it makes the prompt ACCURATE, CONCISE, EFFECTIVE, and LLM-UNDERSTANDABLE.**

For each plan, analyze:
1. **Strengths**: What does this plan do well? (Especially regarding LLM comprehension and execution reliability)
2. **Weaknesses**: What are the limitations or concerns? (Especially regarding JSON parsing risks or LLM misinterpretation)
3. **Feasibility**: How easy is it to implement? (Consider LLM's ability to execute the changes)
4. **Impact**: How much would this improve the prompt? (Prioritize improvements that reduce parsing errors and improve LLM understanding)
5. **Risk**: What could go wrong? (Especially JSON formatting errors, array corruption, or LLM confusion)
6. **LLM-Friendliness**: Does this plan improve or worsen LLM's ability to understand and execute the prompt correctly?

Then provide:
- A comparison matrix showing how plans compare on key dimensions
- Which plan is best for different scenarios
- What elements from each plan could be combined

OUTPUT FORMAT (JSON):
{{
  "comparison": [
    {{
      "plan_id": "plan_1",
      "strengths": ["List of strengths"],
      "weaknesses": ["List of weaknesses"],
      "feasibility_score": 1-10,
      "impact_score": 1-10,
      "risk_score": 1-10,
      "overall_assessment": "Overall assessment of this plan"
    }}
  ],
  "comparison_matrix": {{
    "dimensions": ["feasibility", "impact", "risk", "clarity", "maintainability"],
    "scores": {{
      "plan_1": [8, 7, 3, 9, 8],
      "plan_2": [6, 9, 5, 7, 6],
      "plan_3": [9, 6, 2, 8, 9]
    }}
  }},
  "best_for_scenarios": {{
    "quick_improvements": "plan_X",
    "long_term_quality": "plan_Y",
    "risk_minimization": "plan_Z"
  }},
  "combine_recommendation": "Which elements from which plans should be combined and why"
}}
"""
    
    try:
        generation_config = {
            "temperature": 0.4,  # Lower temperature for more analytical comparison
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        
        response = MODEL.generate_content(comparison_prompt, generation_config=generation_config)
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.startswith("```"):
            response_text = response_text[3:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()
        
        # Robust JSON parsing with fallback
        try:
            comparison_result = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"[WARN] Direct JSON parse failed for comparison: {e}")
            # Try to extract and fix JSON fragment
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_fragment = response_text[start : end + 1]
                json_fragment = fix_incomplete_json(json_fragment)
                try:
                    comparison_result = json.loads(json_fragment)
                    print(f"[INFO] Successfully parsed comparison JSON after fixing")
                except json.JSONDecodeError as e2:
                    print(f"[ERROR] Failed to parse comparison JSON even after fixing: {e2}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to parse comparison result as JSON. The response may contain unterminated strings or malformed JSON. Error: {str(e2)}"
                    )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to parse comparison result as JSON. No valid JSON structure found. Error: {str(e)}"
                )
        
        return comparison_result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to compare plans: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to compare plans: {str(e)}")


async def synthesize_best_plan(original_prompt: str, plans: List[Dict[str, Any]], comparison: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synthesize a "Best Combined Plan" by taking the best elements from each plan.
    """
    plans_json = json.dumps(plans, indent=2)
    comparison_json = json.dumps(comparison, indent=2)
    
    synthesis_prompt = f"""You are synthesizing the BEST COMBINED PLAN from multiple improvement plans.

ORIGINAL PROMPT:
```
{original_prompt}
```

AVAILABLE PLANS:
{plans_json}

COMPARISON ANALYSIS:
{comparison_json}

**CRITICAL PRINCIPLE: The improved prompt must be ACCURATE, CONCISE, EFFECTIVE, and LLM-UNDERSTANDABLE.**
- **Accuracy**: Preserve all essential grading criteria and requirements
- **Conciseness**: Use the most minimal language possible while maintaining clarity (every word should serve a purpose)
- **Effectiveness**: Achieve grading goals with maximum efficiency (avoid redundancy)
- **LLM-Understandability**: Write in language that LLMs can reliably parse and execute (use direct, unambiguous instructions, minimize complex JSON structures, avoid ambiguous phrasing)

Create a BEST COMBINED PLAN that:
1. Takes the strongest elements from each plan (prioritizing those that improve LLM comprehension and reduce parsing errors)
2. Avoids the weaknesses identified in the comparison (especially those related to JSON complexity or LLM confusion)
3. Creates a coherent, unified improvement strategy that maximizes LLM execution reliability
4. Generates an improved prompt that incorporates the best ideas while ensuring it is LLM-friendly (minimizes JSON parsing failures, array corruption, and misinterpretation risks)
5. STRICTLY preserves the ScoringInput and ScoringOutput JSON schemas and all existing key names. Do NOT add/remove/rename any fields or restructure those JSON sections. Focus improvements on explanatory text, rubric guidance, and clarity, while keeping the API contract unchanged.

OUTPUT FORMAT (JSON):
{{
  "best_combined_plan": {{
    "strategy_name": "Name of the combined approach",
    "strategy_description": "Description of the combined strategy",
    "elements_from_plans": {{
      "plan_1": ["Which elements we're taking from plan 1"],
      "plan_2": ["Which elements we're taking from plan 2"],
      "plan_3": ["Which elements we're taking from plan 3"]
    }},
    "improved_prompt": "The full improved prompt text",
    "improvement_summary": "Summary of what was improved and why",
    "expected_benefits": ["List of expected benefits"],
    "implementation_notes": "Notes on how to implement or test this"
  }}
}}
"""
    
    try:
        generation_config = {
            "temperature": 0.5,
            "max_output_tokens": 16384,  # Long response expected for full prompt
            "response_mime_type": "application/json",
        }
        
        response = MODEL.generate_content(synthesis_prompt, generation_config=generation_config)
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:].strip()
        if response_text.startswith("```"):
            response_text = response_text[3:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()
        
        # Robust JSON parsing with fallback
        try:
            synthesis_result = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"[WARN] Direct JSON parse failed for synthesis: {e}")
            # Try to extract and fix JSON fragment
            start = response_text.find("{")
            end = response_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_fragment = response_text[start : end + 1]
                json_fragment = fix_incomplete_json(json_fragment)
                try:
                    synthesis_result = json.loads(json_fragment)
                    print(f"[INFO] Successfully parsed synthesis JSON after fixing")
                except json.JSONDecodeError as e2:
                    print(f"[ERROR] Failed to parse synthesis JSON even after fixing: {e2}")
                    # For synthesis, the improved_prompt might be in a separate section
                    # Try to extract it even if the JSON is malformed
                    improved_prompt_match = re.search(r'"improved_prompt"\s*:\s*"([^"]*)"', response_text, re.DOTALL)
                    if improved_prompt_match:
                        improved_prompt = improved_prompt_match.group(1)
                        # Create a minimal valid result
                        synthesis_result = {
                            "best_combined_plan": {
                                "improved_prompt": improved_prompt,
                                "strategy_name": "Extracted from malformed JSON",
                                "strategy_description": "Prompt was extracted despite JSON parsing errors",
                                "improvement_summary": "JSON parsing failed, but improved prompt was extracted",
                            }
                        }
                        print(f"[INFO] Extracted improved_prompt from malformed JSON")
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to parse synthesis result as JSON. The response may contain unterminated strings or malformed JSON. Error: {str(e2)}"
                        )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to parse synthesis result as JSON. No valid JSON structure found. Error: {str(e)}"
                )
        
        return synthesis_result.get("best_combined_plan", {})
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to synthesize best plan: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to synthesize best plan: {str(e)}")


@app.post("/api/enhanced-prompt-refinement")
async def enhanced_prompt_refinement(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhanced prompt refinement pipeline:
    1. Generate 2-3 different improvement plans
    2. Compare plans (strengths/weaknesses)
    3. Synthesize best combined plan
    4. Generate improved prompt
    """
    original_prompt = request.get("originalPrompt", "")
    num_plans = request.get("numPlans", 3)
    
    if not original_prompt:
        original_prompt = get_current_prompt()
    
    if num_plans < 2 or num_plans > 3:
        num_plans = 3
    
    try:
        # Step 1: Generate multiple plans
        plans = await generate_multiple_plans(original_prompt, num_plans)
        
        # Step 2: Compare plans
        comparison = await compare_plans(plans)
        
        # Step 3: Synthesize best combined plan
        best_plan = await synthesize_best_plan(original_prompt, plans, comparison)
        
        # Save refinement session
        session_id = f"enhanced-refinement-{int(time.time() * 1000)}"
        session_data = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "original_prompt": original_prompt,
            "plans": plans,
            "comparison": comparison,
            "best_combined_plan": best_plan,
        }
        
        session_file = PROMPT_REFINEMENT_DIR / f"{session_id}.json"
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        return {
            "status": "success",
            "session_id": session_id,
            "plans": plans,
            "comparison": comparison,
            "best_combined_plan": best_plan,
            "improved_prompt": best_plan.get("improved_prompt", ""),
        }
    except Exception as e:
        print(f"[ERROR] Enhanced prompt refinement failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enhanced prompt refinement failed: {str(e)}")


# ============================================================================
# HITL: AI Error Reporting & Corrections System
# ============================================================================

def load_corrections() -> List[Dict[str, Any]]:
    """Load all corrections from corrections.json."""
    if CORRECTIONS_FILE.exists():
        try:
            with open(CORRECTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("corrections", [])
        except Exception as e:
            print(f"Error loading corrections: {e}")
            return []
    return []


def save_correction(correction: Dict[str, Any]) -> None:
    """Save a correction to corrections.json."""
    corrections = load_corrections()
    corrections.append(correction)
    
    data = {
        "corrections": corrections,
        "lastUpdated": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }
    
    with open(CORRECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@app.post("/api/report-ai-error")
async def report_ai_error(request: Dict[str, Any]) -> Dict[str, Any]:
    """Report an AI error/correction made by TA."""
    job_id = request.get("jobId")
    page_number = request.get("pageNumber")
    component = request.get("component")  # e.g., "violation_quality", "coverage", "feedback", etc.
    reason = request.get("reason")  # Why the AI was wrong
    original_value = request.get("originalValue")
    corrected_value = request.get("correctedValue")
    reviewer_notes = request.get("reviewerNotes", "")
    
    if not job_id or page_number is None or not component or not reason:
        raise HTTPException(
            status_code=400,
            detail="jobId, pageNumber, component, and reason are required"
        )
    
    correction = {
        "id": f"correction_{int(time.time() * 1000)}",
        "jobId": job_id,
        "pageNumber": page_number,
        "component": component,
        "reason": reason,
        "originalValue": original_value,
        "correctedValue": corrected_value,
        "reviewerNotes": reviewer_notes,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }
    
    save_correction(correction)
    
    return {
        "status": "success",
        "correction": correction,
        "message": "AI error reported and saved",
    }


@app.get("/api/get-corrections")
async def get_corrections(jobId: Optional[str] = None) -> Dict[str, Any]:
    """Get all corrections, optionally filtered by jobId."""
    corrections = load_corrections()
    
    if jobId:
        corrections = [c for c in corrections if c.get("jobId") == jobId]
    
    return {
        "corrections": corrections,
        "total": len(corrections),
    }


@app.post("/api/generate-prompt-from-corrections")
async def generate_prompt_from_corrections(request: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an improved prompt based on accumulated corrections, including page images and score changes."""
    limit = request.get("limit", 50)
    current_prompt = request.get("currentPrompt", "")
    corrections_with_images = request.get("corrections", [])  # Frontend sends corrections with images
    score_changes = request.get("scoreChanges", [])
    
    # If frontend didn't send corrections, load from file
    if not corrections_with_images:
        corrections = load_corrections()
        if not corrections:
            raise HTTPException(status_code=400, detail="No corrections found")
        recent_corrections = corrections[-limit:]
    else:
        recent_corrections = corrections_with_images[-limit:]
    
    # Build structured feedback with score changes
    corrections_summary_parts = []
    for i, c in enumerate(recent_corrections):
        summary = f"Correction #{i+1}:\n"
        summary += f"  Page: {c.get('pageNumber', 'N/A')}\n"
        summary += f"  Component: {c.get('component')}\n"
        summary += f"  Score Change: {c.get('originalValue')} → {c.get('correctedValue')}\n"
        summary += f"  Reason: {c.get('reason', 'N/A')}\n"
        if c.get('reviewerNotes'):
            summary += f"  TA Notes: {c.get('reviewerNotes')}\n"
        corrections_summary_parts.append(summary)
    
    corrections_summary = "\n\n".join(corrections_summary_parts)
    
    # Get current prompt if not provided
    if not current_prompt:
        current_prompt = get_current_prompt()
    
    # Analyze corrections to identify patterns
    component_counts = {}
    for c in recent_corrections:
        comp = c.get("component", "unknown")
        component_counts[comp] = component_counts.get(comp, 0) + 1
    
    top_issues = sorted(component_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    pattern_analysis = "\n".join([
        f"  - {comp}: {count} correction(s)"
        for comp, count in top_issues
    ])
    
    # Build improvement prompt
    improvement_prompt_text = f"""You are improving a grading prompt based on TA corrections and overrides.

CURRENT PROMPT:
---
{current_prompt}
---

TA CORRECTIONS SUMMARY ({len(recent_corrections)} corrections analyzed):
---
{corrections_summary}
---

PATTERN ANALYSIS (most frequently corrected components):
{pattern_analysis}

Based on these corrections, generate an improved version of the prompt that:
1. Addresses the specific issues identified in the corrections
2. Reduces the types of errors that led to these corrections (especially in: {', '.join([c[0] for c in top_issues[:3]]) if top_issues else 'various components'})
3. Maintains the core structure and requirements
4. Improves clarity and specificity to prevent similar mistakes
5. Provides better guidance for evaluating the components that were most frequently corrected

IMPORTANT: You must provide TWO things:
1. The improved prompt itself
2. A brief explanation of how you modified the prompt (what changes you made and why)

Format your response as follows:
---
IMPROVED PROMPT:
[Your improved prompt here]
---

MODIFICATION NOTES:
[Explain what you changed and why, focusing on how the changes address the TA corrections]
---"""

    try:
        if MODEL:
            # If we have page images, include them in the request
            images_with_corrections = []
            for c in recent_corrections:
                if c.get('pageImage'):
                    try:
                        # Decode base64 image (handle data URL format: "data:image/png;base64,...")
                        image_b64 = c.get('pageImage')
                        if ',' in image_b64:
                            image_b64 = image_b64.split(',')[-1]
                        image_data = base64.b64decode(image_b64)
                        img = Image.open(io.BytesIO(image_data))
                        images_with_corrections.append({
                            'image': img,
                            'correction': c,
                        })
                    except Exception as e:
                        print(f"Error processing image for correction: {e}")
            
            if images_with_corrections:
                # Use multimodal prompt with images
                # For each image, create a part with the image and its correction context
                parts = [improvement_prompt_text]
                for img_data in images_with_corrections[:5]:  # Limit to 5 images to avoid token limits
                    c = img_data['correction']
                    parts.append(f"\n\nEXAMPLE PAGE (Page {c.get('pageNumber')}):")
                    parts.append(img_data['image'])
                    parts.append(f"This page had a correction: {c.get('component')} score changed from {c.get('originalValue')} to {c.get('correctedValue')}. Notes: {c.get('reviewerNotes', 'N/A')}")
                
                response = MODEL.generate_content(parts)
            else:
                # Text-only prompt
                response = MODEL.generate_content(improvement_prompt_text)
            
            response_text = response.text
            
            # Parse the response to extract improved prompt and modification notes
            improved_prompt = ""
            modification_notes = ""
            
            if "IMPROVED PROMPT:" in response_text and "MODIFICATION NOTES:" in response_text:
                # Split by the markers
                parts = response_text.split("MODIFICATION NOTES:")
                if len(parts) >= 2:
                    improved_prompt_part = parts[0].replace("IMPROVED PROMPT:", "").strip()
                    improved_prompt = improved_prompt_part.strip("---").strip()
                    modification_notes = parts[1].strip("---").strip()
                else:
                    improved_prompt = response_text
            elif "IMPROVED PROMPT:" in response_text:
                improved_prompt = response_text.split("IMPROVED PROMPT:")[1].strip("---").strip()
            else:
                # Fallback: use entire response as improved prompt
                improved_prompt = response_text
        else:
            improved_prompt = current_prompt
            modification_notes = "Model not available - using current prompt"
    except Exception as e:
        improved_prompt = f"Error generating improved prompt: {str(e)}\n\n{current_prompt}"
        modification_notes = f"Error occurred: {str(e)}"
    
    return {
        "status": "success",
        "improvedPrompt": improved_prompt,
        "modificationNotes": modification_notes,
        "currentPrompt": current_prompt,
        "correctionsUsed": len(recent_corrections),
        "totalCorrections": len(corrections_with_images) if corrections_with_images else len(load_corrections()),
    }


@app.get("/api/get-ai-flags")
async def get_ai_flags(jobId: str) -> Dict[str, Any]:
    """Get user-manually-marked risk flags for a submission."""
    if not jobId:
        raise HTTPException(status_code=400, detail="jobId is required")
    
    # Load manually marked risk flags
    risk_flags_file = RISK_FLAGS_DIR / f"{jobId}_risk_flags.json"
    risk_pages = []
    
    if risk_flags_file.exists():
        try:
            with open(risk_flags_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_risk_pages = data.get("riskPages", [])
                # Filter out auto-generated notes (same logic as save_override)
                auto_set_keywords = ["Auto-set:", "auto-set:", "Auto-generated", "auto-generated"]
                risk_pages = [
                    page for page in all_risk_pages
                    if page.get("notes") and not any(
                        keyword in page.get("notes", "") for keyword in auto_set_keywords
                    )
                ]
                # If we filtered out pages, update the file to remove them
                if len(risk_pages) < len(all_risk_pages):
                    data["riskPages"] = risk_pages
                    with open(risk_flags_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error loading risk flags: {e}")
    
    return {
        "jobId": jobId,
        "riskPages": risk_pages,
        "totalRiskPages": len(risk_pages),
    }


@app.post("/api/toggle-risk-flag")
async def toggle_risk_flag(request: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle a manual risk flag for a page (mark/unmark as risky)."""
    job_id = request.get("jobId")
    page_number = request.get("pageNumber")
    notes = request.get("notes", "")
    
    if not job_id or page_number is None:
        raise HTTPException(status_code=400, detail="jobId and pageNumber are required")
    
    # Load existing risk flags
    risk_flags_file = RISK_FLAGS_DIR / f"{job_id}_risk_flags.json"
    risk_flags_data = {"riskPages": []}
    
    if risk_flags_file.exists():
        try:
            with open(risk_flags_file, "r", encoding="utf-8") as f:
                risk_flags_data = json.load(f)
        except Exception as e:
            print(f"Error loading risk flags: {e}")
    
    # Check if page is already flagged
    existing_index = None
    for i, page in enumerate(risk_flags_data["riskPages"]):
        if page.get("pageNumber") == page_number:
            existing_index = i
            break
    
    if existing_index is not None:
        # Remove flag (unmark)
        risk_flags_data["riskPages"].pop(existing_index)
        action = "removed"
    else:
        # Add flag (mark)
        risk_flags_data["riskPages"].append({
            "pageNumber": page_number,
            "notes": notes,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        })
        action = "added"
    
    # Save back
    with open(risk_flags_file, "w", encoding="utf-8") as f:
        json.dump(risk_flags_data, f, indent=2, ensure_ascii=False)
    
    return {
        "status": "success",
        "action": action,
        "riskPages": risk_flags_data["riskPages"],
        "totalRiskPages": len(risk_flags_data["riskPages"]),
    }
