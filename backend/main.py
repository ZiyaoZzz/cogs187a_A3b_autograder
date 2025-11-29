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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

    return {
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
            max_points = {
                "coverage": 15, "violation_quality": 20, "screenshots": 10,
                "severity_analysis": 10, "structure_navigation": 10,
                "professional_quality": 10, "writing_quality": 10, "group_integration": 15
            }
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
            max_points = {"bonus_ai_opportunities": 3, "bonus_exceptional_quality": 2}
            bonus_scores[field] = {
                "points": 0,
                "max": max_points.get(field, 0),
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

STUDENT SUBMISSION - PAGE {page_number}:
Content: {word_count} words, Has image: {has_image}
{page_content}

═══ STEP 1: CLASSIFICATION ═══
Determine page type by analyzing the FULL PAGE CONTENT (text, structure, visual elements), not just word count:
- Skip analysis (skip_analysis: true) if:
  * Title page, cover page, introduction page, or table of contents
  * Page contains only a heuristic number/title (e.g., "Heuristic 1", "Heuristic 2") with minimal content
  * Page is clearly a section divider or subtitle page
  * Page has very little substantive content (mostly titles, headers, or decorative elements)
- Analyze (skip_analysis: false) if:
  * Page contains heuristic violation analysis with detailed descriptions
  * Page has substantial content discussing violations, user impact, or UX issues
  * Page is a conclusion, methodology, severity summary, or AI opportunities section
  * Page follows a heuristic title page and contains the actual analysis content
  * Page has images with annotations explaining violations

Note: Heuristic title pages (showing just "Heuristic X" or similar) should be skipped, but the NEXT page usually contains the analysis for that heuristic and should be analyzed.

═══ STEP 2: EXTRACTION (if skip_analysis: false) ═══
Extract all violations found on this page into extracted_violations array by READING THE STUDENT'S TEXT CAREFULLY.

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
- description: A brief description of the violation as described by the student (max 30 words)
- severity: The severity rating mentioned by the student. Look for:
  * Words: "Cosmetic", "Minor", "Major", "Critical", "Low", "Medium", "High"
  * Numbers: "1", "2", "3", "4" (may be in a scale like "Severity: 3" or "Rating: 2")
  Extract this EXACTLY as written by the student (preserve the format: word or number).

IMPORTANT: 
- Read the student's text word-by-word to find heuristic names and severity ratings
- Don't infer or guess - only extract what is explicitly written
- If a heuristic is mentioned by number only (e.g., "Heuristic 5"), look for the name nearby or use the standard name from the reference
- If severity is not explicitly mentioned, leave it as empty string ""

═══ STEP 3: SCORING (if skip_analysis: false) ═══
Score each criterion using point deduction checklists. Start from max points, subtract for violations.

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

Deduct points when:
□ -3: No severity summary section found (check for "Severity Summary", tables, or overview sections)
□ -2: Missing explanation of how 1-4 scale was applied (e.g., impact × frequency × persistence), similar structure accepted
□ -1 to -2: There is no clear explanation of how the scale is applied at all (take off about 1–2 points)
□ -1: Individual severity ratings have no rationale beyond "this is confusing" (no mention of frequency or impact severity)

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
Start: 15 points
□ -5: No evidence of group collaboration
□ -3: Limited integration of group members' work
Final = 15 - [deductions]

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
        prompt = build_analysis_prompt(snippet, page_number, RUBRIC_DATA, has_image=has_image)
        
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
            "max_output_tokens": 4096,  # Increased to 4096 to prevent JSON truncation (Gemini 2.5 Flash supports up to 8192)
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
