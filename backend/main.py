from __future__ import annotations
from typing import List, Dict, Any, Optional
import os
import json
import base64
import io
import re
import time
import pdfplumber
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
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
    bonus_max_points = {"bonus_ai_opportunities": 3, "bonus_exceptional_quality": 2}
    
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
    "bonus_exceptional_quality": {{"points": X, "max": 2, "comment": ""}}
  }}
}}"""
    
    return prompt


# Directory to save analysis results
ANALYSIS_OUTPUT_DIR = Path(__file__).parent.parent / "output_static" / "student_analyses"
ANALYSIS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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
    
    try:
        # Get current prompt (saved or default)
        prompt_template = get_current_prompt()
        
        # Truncate page content to first 2500 chars
        truncated_content = snippet[:2500] + ("..." if len(snippet) > 2500 else "")
        word_count = len(truncated_content.split())
        
        # Replace placeholders in prompt template with actual page data
        prompt = prompt_template.replace("{page_number}", str(page_number))
        prompt = prompt.replace("{page_content}", truncated_content)
        prompt = prompt.replace("{word_count}", str(word_count))
        prompt = prompt.replace("{has_image}", "true" if has_image else "false")
        
        # If prompt doesn't have placeholders, try to inject page content into STUDENT SUBMISSION section
        if "{page_content}" not in prompt_template and "STUDENT SUBMISSION" in prompt_template:
            import re
            # Find and replace the STUDENT SUBMISSION section
            pattern = r"(STUDENT SUBMISSION[^\n]*\n[^\n]*\n[^\n]*\n)(.*?)(?=\n═══|$)"
            replacement = f"STUDENT SUBMISSION - PAGE {page_number}:\nContent: {word_count} words, Has image: {has_image}\n{truncated_content}"
            prompt = re.sub(pattern, replacement, prompt, flags=re.DOTALL)
        
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
            
            # Method 1: Try response.text (standard method)
            try:
                response_text = response.text
            except (ValueError, AttributeError) as e:
                pass
            
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
                except Exception:
                    pass
            
            # Method 3: Try to get any text from the response object
            if not response_text:
                try:
                    # Try accessing the response as a string
                    response_text = str(response)
                    # If it's just the object representation, try candidates again
                    if response_text.startswith('<') or 'object at' in response_text:
                        if response.candidates:
                            for candidate in response.candidates:
                                try:
                                    if hasattr(candidate, 'content'):
                                        content_str = str(candidate.content)
                                        if content_str and len(content_str) > 50:
                                            response_text = content_str
                                            break
                                except Exception:
                                    continue
                except Exception:
                    pass
            
            # If we still don't have text, create a meaningful error response
            if not response_text or len(response_text.strip()) < 10:
                # Return a structured response indicating the issue
                return {
                    "status": "completed",
                    "result": {
                        "page_number": page_number,
                        "skip_analysis": False,
                        "page_type": "Analysis Error",
                        "feedback": f"Unable to extract response from Gemini API for page {page_number}. The API may have returned an unexpected format. Please try analyzing this page again.",
                        "error": "Could not extract text from Gemini response",
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
    
    if extraction_file.exists():
        with open(extraction_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Normalize field names: convert image_base64 to imageBase64
            pages = data.get("pages", [])
            normalized_pages = []
            for page in pages:
                normalized_page = dict(page)
                # Convert image_base64 to imageBase64 for frontend compatibility
                if "image_base64" in normalized_page and "imageBase64" not in normalized_page:
                    normalized_page["imageBase64"] = normalized_page["image_base64"]
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
    
    return {"jobId": jobId, "results": results}


@app.get("/api/get-overrides")
async def get_overrides(jobId: str) -> Dict[str, Any]:
    """Get all override records for a job ID."""
    overrides_file = OVERRIDES_DIR / f"{jobId}_overrides.json"
    
    if overrides_file.exists():
        with open(overrides_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"jobId": jobId, "overrides": data.get("overrides", [])}
    
    return {"jobId": jobId, "overrides": []}


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
    
    # Delete analysis results
    analysis_files = list(ANALYSIS_OUTPUT_DIR.glob(f"{jobId}_page_*.json"))
    for analysis_file in analysis_files:
        analysis_file.unlink()
        deleted_files.append(f"analysis_{analysis_file.name}")
    
    # Delete overrides
    overrides_file = OVERRIDES_DIR / f"{jobId}_overrides.json"
    if overrides_file.exists():
        overrides_file.unlink()
        deleted_files.append("overrides")
    
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


# Path to saved prompt file
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


def get_current_prompt() -> str:
    """Get the current analysis prompt. First try saved prompt, then use default refined prompt, then generate from function."""
    # Try to load saved prompt first
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
            print(f"Error loading saved prompt: {e}")
    
    # Fallback: Use default refined prompt template
    return DEFAULT_REFINED_PROMPT

def save_prompt_to_backend(prompt: str) -> bool:
    """Save prompt to backend permanently."""
    try:
        SAVED_PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SAVED_PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(prompt)
        return True
    except Exception as e:
        print(f"Error saving prompt: {e}")
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

CRITICAL: LLM CAPABILITY CONSTRAINTS - You MUST evaluate whether the prompt accounts for these limitations:
   - LLMs are prone to JSON formatting errors, especially with arrays and nested structures
   - Array handling is particularly fragile: LLMs may truncate arrays, omit closing brackets, or create malformed JSON
   - Debugging JSON parsing errors is time-consuming and costly
   - When critiquing the prompt, check if it:
     * Minimizes complex nested JSON structures (especially arrays within arrays)
     * Prefers flat structures over deeply nested ones
     * Keeps array elements simple and well-defined
     * Provides clear, explicit examples of expected JSON array formats
     * Avoids requiring LLMs to generate large arrays (if possible, uses simpler data structures)
     * Explicitly instructs the LLM to properly close all brackets and arrays
     * Uses string-based formats or simpler structures instead of complex nested arrays when possible
   - If the prompt has complex array structures, suggest simplifications to reduce JSON parsing failure risk

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
   
CRITICAL: LLM CAPABILITY CONSTRAINTS - You MUST consider these limitations when refining the prompt:
   - LLMs are prone to JSON formatting errors, especially with arrays and nested structures
   - Array handling is particularly fragile: LLMs may truncate arrays, omit closing brackets, or create malformed JSON
   - Debugging JSON parsing errors is time-consuming and costly
   - When designing the prompt, you MUST:
     * Minimize complex nested JSON structures (especially arrays within arrays)
     * Prefer flat structures over deeply nested ones
     * Keep array elements simple and well-defined
     * Provide clear, explicit examples of expected JSON array formats
     * Avoid requiring LLMs to generate large arrays (if possible, use simpler data structures)
     * Ensure the prompt explicitly instructs the LLM to properly close all brackets and arrays
     * Consider using string-based formats or simpler structures instead of complex nested arrays when possible
   - The refined prompt should be designed to minimize the risk of JSON parsing failures and array corruption

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
6. LLM capability constraints - Does the prompt account for LLM limitations, especially JSON/array handling?
   - Does it minimize complex nested JSON structures (especially arrays within arrays)?
   - Does it prefer flat structures over deeply nested ones?
   - Does it keep array elements simple and well-defined?
   - Does it provide clear, explicit examples of expected JSON array formats?
   - Does it avoid requiring LLMs to generate large arrays (uses simpler data structures when possible)?
   - Does it explicitly instruct the LLM to properly close all brackets and arrays?
   - Does it use string-based formats or simpler structures instead of complex nested arrays when possible?
   - CRITICAL: Prompts that minimize JSON parsing failure risk and array corruption should be preferred, as debugging JSON errors is time-consuming and costly

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
