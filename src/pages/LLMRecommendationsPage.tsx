import React from "react";

const LLMRecommendationsPage: React.FC = () => {
  return (
    <main className="mx-auto max-w-4xl px-4 py-8 text-slate-800">
      {/* Header */}
      <header className="mb-8">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Autograder Design Report
        </p>
        <h1 className="mb-3 text-3xl font-bold">
          LLM Recommendations for Improving the Autograder
        </h1>
        <p className="text-sm text-slate-600">
          This page summarizes recommendations from multiple LLMs (ChatGPT, Claude, and Gemini)
          for making the grading system more consistent, reliable, and maintainable.
          These insights come from analyzing the same autograder prompt from different
          model perspectives.
        </p>
      </header>

      {/* Note box - UPDATED */}
      <section className="mb-8 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        <strong>Note.</strong> This analysis includes recommendations from{" "}
        <strong>ChatGPT</strong>, <strong>Claude</strong>, and <strong>Gemini</strong>. Where
        recommendations overlap, they are presented as unified principles. Where they differ,
        all unique perspectives are noted.
      </section>

      {/* 1. Temperature and Consistency */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          1. Lower Temperature for Deterministic Scoring
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-blue-500 bg-blue-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
            All models agree
          </p>
        </div>
        <p className="mb-2 text-sm">
          The current configuration uses temperature 0.7, which introduces significant
          randomness in scoring. This is appropriate for creative writing but problematic
          for grading, where consistency is critical.
        </p>
        <p className="mb-2 text-sm text-slate-600">
          <strong>Current issue:</strong> The same page can receive different scores
          across multiple runs, making grading unfair and unpredictable.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Reduce temperature to <strong>0.1 or 0.2</strong> for grading tasks</li>
          <li>Consider adding a fixed <strong>seed parameter</strong> if supported by your API</li>
          <li>This makes scoring more deterministic and reduces variance across students</li>
        </ul>
      </section>

      {/* 3. Reduce Prompt Length */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          3. Reduce Prompt Length and Instruction Density
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-blue-500 bg-blue-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
            All models agree
          </p>
        </div>
        <p className="mb-2 text-sm">
          The current prompt mixes the full rubric, detailed deduction rules,
          assignment-wide requirements, JSON schema, and many repeated reminders.
          When too many rules are packed together, LLMs struggle to follow all of
          them consistently.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Summarize rubric criteria instead of pasting the full text</li>
          <li>
            Move long explanations and examples into separate documentation that
            the model doesn't see on every call
          </li>
          <li>Keep instructions action-focused: what to look for and what to output</li>
          <li>Remove redundant reminders (saying the same thing multiple times doesn't help)</li>
        </ul>
      </section>

      {/* 4. Structured Scoring Process - ENHANCED */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          4. Use Step-by-Step Scoring Instructions & Mandatory Internal Process
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-orange-500 bg-orange-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-orange-700">
            Claude's & Gemini's emphasis
          </p>
        </div>
        <p className="mb-2 text-sm">
          Instead of presenting all scoring criteria in a wall of text, organize
          them into explicit steps that the LLM can follow sequentially. **Gemini**
          further stresses making this process mandatory before final output.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Define a **Mandatory Sequential Process** (Gemini's recommendation):
            <ol className="ml-4 mt-1 list-decimal space-y-1">
              <li>**Classification:** Determine `skip_analysis` and `page_type`.</li>
              <li>**Extraction:** Build the `extracted_violations` array (see point 6).</li>
              <li>**Deduction:** Score each criterion sequentially.</li>
              <li>**Feedback Drafting:** Synthesize the `feedback`.</li>
              <li>**Final JSON Generation:** Output the result.</li>
            </ol>
          </li>
          <li>Use clear visual separators: <code>═══ STEP 1 ═══</code>, <code>═══ STEP 2 ═══</code></li>
          <li>Make the decision logic explicit and linear</li>
        </ul>
        <div className="mt-3 rounded-lg bg-slate-100 p-3 text-xs">
          <p className="mb-1 font-semibold">Example structure (Step 2/Deduction):</p>
          <pre className="text-slate-700">
{`STEP 2: Score Violation Quality (start at 20)
  □ -2: Emotional words used >2 times
  □ -3: Severity mismatch
  Final score = 20 - [deductions]`}
          </pre>
        </div>
      </section>

      {/* 5. Separate JSON Schema */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          5. Separate JSON Schema From Instructional Text
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-blue-500 bg-blue-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
            All models agree
          </p>
        </div>
        <p className="mb-2 text-sm">
          The current JSON template embeds long natural-language explanations inside
          fields like <code>comment</code>. The model frequently copies these
          sentences directly into the output, making results verbose and inconsistent.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Keep the JSON schema clean: use <strong>empty strings</strong> as defaults
            for comment fields
          </li>
          <li>
            Place detailed instructions about how to write comments in the
            natural-language part of the prompt, not inside the JSON
          </li>
          <li>Provide a minimal JSON example that the model can reliably imitate</li>
        </ul>
      </section>
      
      {/* 5.5. JSON Output Constraints - NEW GEMINI EMPHASIS */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          5.5. Enforce Strict Zero-Tolerance JSON Output Constraints
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-green-500 bg-green-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-green-700">
            Gemini's emphasis
          </p>
        </div>
        <p className="mb-2 text-sm">
          LLMs often prepend or append conversational text or Markdown fences (e.g., ```json)
          even when explicitly told not to. This breaks downstream parsing.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Add a **CRITICAL WARNING** immediately preceding the JSON template:
          </li>
          <li>
            Use strong, zero-tolerance language: <strong>"The entire response MUST be a single, valid JSON object. DO NOT include ANY text, Markdown fences (```json, ```), or explanations outside of the JSON object itself."</strong>
          </li>
          <li>This forces a cleaner output, reducing the need for fragile client-side string repair.</li>
        </ul>
      </section>


      {/* 6. Page vs Assignment Level - ENHANCED */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          6. Decouple Extraction and Scoring with Structured Data
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-orange-500 bg-orange-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-orange-700">
            All models agree (Two-Stage Pipeline), Gemini emphasizes Data Decoupling
          </p>
        </div>
        <p className="mb-2 text-sm">
          Criteria like Coverage depend on the entire submission, but the model is called
          on a single page. To solve this, the LLM must **extract machine-readable data**
          for later aggregation.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Use a <strong>two-stage pipeline</strong>:
            <ol className="ml-4 mt-1 list-decimal space-y-1">
              <li>Stage 1 (per page): **Extraction** of violations, severities, local quality.</li>
              <li>Stage 2 (per assignment): Aggregate data and compute **Final Scores** globally.</li>
            </ol>
          </li>
          <li>
            **Introduce `extracted_violations` Array (Gemini's proposal):** Create a **new, mandatory JSON array field** (`extracted_violations`) to store all violations found on the current page (e.g., <code>{`{"heuristic_num": X, "description": "...", "severity": "..."}`}</code>)
          </li>
          <li>
            For page-level calls, focus on **extraction only**, not final scoring (Coverage points should be 0).
          </li>
        </ul>
      </section>

      {/* 8. Token Limits */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          8. Optimize Token Limits to Prevent Truncation
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-blue-500 bg-blue-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
            All models agree
          </p>
        </div>
        <p className="mb-2 text-sm">
          Very high <code>max_output_tokens</code> (like 8192) can encourage
          unnecessarily long responses and increase the chance of truncated JSON.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Set <code>max_output_tokens</code> to a moderate range: <strong>1500-2500</strong>
          </li>
          <li>Truncate input content to first 2000-3000 characters if needed</li>
          <li>This reduces truncation risk and makes parsing more robust</li>
        </ul>
      </section>

      {/* 10. Error Handling */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          10. Strengthen JSON Parsing and Error Handling
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-blue-500 bg-blue-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
            All models agree
          </p>
        </div>
        <p className="mb-2 text-sm">
          The current implementation uses regex-based fixes when JSON is malformed.
          While robust, this can obscure when the model actually failed and may
          silently assign incorrect scores.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Rely primarily on <code>response_mime_type="application/json"</code> and
            direct parsing
          </li>
          <li>Use fallback repair logic only when parsing fails</li>
          <li>
            <strong>Log clearly</strong> when degraded mode is used for a page
          </li>
          <li>Add validation to ensure scores don't exceed max points</li>
        </ul>
      </section>

      {/* 2. Quantify Subjective Criteria - MOVED TO BOTTOM */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          2. Replace Subjective Language With Quantifiable Rules
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-purple-500 bg-purple-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-purple-700">
            Claude's emphasis
          </p>
        </div>
        <p className="mb-2 text-sm">
          The current prompt contains many subjective phrases that LLMs interpret
          differently each time: "usually do NOT give full points," "if compelling,"
          "barely readable," "could be more organized."
        </p>
        <p className="mb-2 text-sm text-slate-600">
          <strong>Current issue:</strong> These vague terms lead to inconsistent
          interpretation. What seems "compelling" in one run may not in another.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Convert fuzzy criteria to <strong>countable rules</strong>:
            <ul className="ml-4 mt-1 list-circle space-y-1">
              <li>"Repetition" → "Uses emotional phrasing MORE THAN 2 times"</li>
              <li>"Barely readable" → "Cannot read labels/UI text at 100% zoom"</li>
              <li>"Inconsistent spacing" → "Spacing varies by more than 50%"</li>
            </ul>
          </li>
          <li>Use <strong>checklists with point deductions</strong> instead of ranges</li>
          <li>Start from max points and subtract specific amounts for each violation</li>
        </ul>
        <div className="mt-3 rounded-lg bg-slate-100 p-3 text-xs">
          <p className="mb-1 font-semibold">Example transformation:</p>
          <p className="mb-2 text-red-600">
            ❌ Before: "Deduct points if severity ratings appear inflated"
          </p>
          <p className="text-green-600">
            ✅ After: "Deduct 3 points if violation marked Major/Critical but
            describes only cosmetic issue"
          </p>
        </div>
      </section>

      {/* 7. Comment Field Guidelines - MOVED TO BOTTOM */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          7. Enforce Strict Comment Field Guidelines
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-purple-500 bg-purple-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-purple-700">
            Claude's emphasis
          </p>
        </div>
        <p className="mb-2 text-sm">
          The current prompt asks for comments explaining deductions, but models often
          include positive praise ("excellent work," "good job"), making feedback
          inconsistent and less actionable.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            <strong>Rule:</strong> Comment fields should ONLY explain why points were
            deducted
          </li>
          <li>If full points awarded, leave comment field empty or omit it entirely</li>
          <li>No positive feedback in comment fields (save that for the overall feedback)</li>
          <li>
            Format: "Deducted X points: [specific issue 1], [specific issue 2]"
          </li>
        </ul>
        <div className="mt-3 rounded-lg bg-slate-100 p-3 text-xs">
          <p className="mb-1 font-semibold">Example:</p>
          <p className="mb-2 text-red-600">
            ❌ Before: "Good analysis overall, but could improve severity ratings"
          </p>
          <p className="text-green-600">
            ✅ After: "Severity ratings inflated: 3 violations marked Major but
            describe cosmetic issues (-3)"
          </p>
        </div>
      </section>

      {/* 9. Add Few-Shot Examples - MOVED TO BOTTOM */}
      <section className="mb-8">
        <h2 className="mb-2 text-xl font-semibold">
          9. Include Few-Shot Examples for Critical Criteria
        </h2>
        <div className="mb-3 rounded-lg border-l-4 border-purple-500 bg-purple-50 px-3 py-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-purple-700">
            Claude's emphasis
          </p>
        </div>
        <p className="mb-2 text-sm">
          For criteria where scoring is most inconsistent (like Violation Quality
          or Professional Quality), concrete examples help the LLM understand the
          standard better than abstract rules.
        </p>
        <h3 className="mb-1 mt-3 text-sm font-semibold">Recommendation</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>
            Add 2-3 scoring examples at the start of the prompt showing:
            <ul className="ml-4 mt-1 list-circle space-y-1">
              <li>Student text excerpt</li>
              <li>Issues identified</li>
              <li>Point calculation</li>
              <li>Final score</li>
            </ul>
          </li>
          <li>Use realistic examples from past student work (anonymized)</li>
          <li>Show both good (high score) and problematic (low score) examples</li>
        </ul>
      </section>

      {/* Summary - UPDATED */}
      <section className="border-t border-slate-200 pt-4">
        <h2 className="mb-3 text-lg font-semibold">Summary of Key Principles</h2>
        <div className="space-y-3 text-sm text-slate-700">
          <p>
            ChatGPT, Claude, and Gemini all identified core issues with the current
            autograder design: high temperature causing randomness, vague scoring
            criteria, overly long prompts, and the challenge of page-level analysis versus
            assignment-level requirements.
          </p>
          <p>
            * <strong>Claude particularly emphasized</strong> the importance of
                converting subjective language into countable rules, using structured
                step-by-step instructions, and enforcing strict comment field guidelines.
          </p>
          <p>
            * <strong>ChatGPT particularly emphasized</strong> the architectural
                separation between extraction and scoring, reducing token limits, and
                simplifying the JSON schema.
          </p>
          <p>
            * <strong>Gemini particularly emphasized</strong> enforcing a **Mandatory Sequential Process** (point 4), **Data Decoupling** by using a new `extracted_violations` JSON array (point 6), and implementing **Zero-Tolerance JSON Constraints** (point 5.5) to ensure structural output integrity.
          </p>
          <p className="rounded-lg bg-emerald-50 border border-emerald-200 p-3 mt-4">
            <strong className="text-emerald-800">Key takeaway:</strong> The most
            impactful changes will be: (1) lowering temperature to 0.1-0.2,
            (2) converting all vague criteria to countable rules with specific
            point deductions, (3) using a two-stage extraction-then-scoring
            pipeline with **structured data extraction**, and (4) providing few-shot examples for complex criteria.
            These changes should dramatically improve grading consistency.
          </p>
        </div>
      </section>

      {/* Original Prompt Code Reference (Used for ChatGPT Analysis) */}
      <section className="border-t border-slate-300 pt-8 mt-12">
        <h2 className="mb-4 text-2xl font-bold text-slate-900">
          Original Prompt Code Reference
        </h2>
        <p className="mb-4 text-sm text-slate-600">
          Below is the original prompt code that was used when analyzing the autograder design
          with ChatGPT. This is the <code>build_analysis_prompt</code> function from <code>backend/main.py</code>
          that was provided to ChatGPT for generating the recommendations above. It is included here
          for reference and comparison with the recommendations.
        </p>
        <div className="rounded-lg border border-slate-300 bg-slate-900 overflow-hidden">
          <div className="bg-slate-800 px-4 py-2 border-b border-slate-700">
            <p className="text-xs font-mono text-slate-300">
              backend/main.py - build_analysis_prompt() (Original code provided to ChatGPT)
            </p>
          </div>
          <pre className="p-4 overflow-x-auto text-xs text-slate-100 font-mono leading-relaxed">
            <code>{`def build_analysis_prompt(page_content: str, page_number: int, rubric_data: Optional[Dict] = None, has_image: bool = False) -> str:
    """Build a prompt for Gemini to analyze a PDF page."""
    # Truncate page content to first 3000 chars to speed up processing
    page_content = page_content[:3000] + ("..." if len(page_content) > 3000 else "")
    word_count = len(page_content.split())
    
    rubric_text = ""
    if rubric_data and "rubric" in rubric_data:
        rubric = rubric_data["rubric"]
        rubric_text = f"""
RUBRIC FOR EVALUATION:
Name: {rubric.get('name', 'N/A')}
Total Points: {rubric.get('totalPoints', 0)}

CRITERIA:
"""
        for criterion in rubric.get("criteria", []):
            rubric_text += f"- {criterion.get('title', 'N/A')} ({criterion.get('points', 0)} points): {criterion.get('description', 'N/A')}\\n"
        
        if rubric.get("bonusCriteria"):
            rubric_text += "\\nBONUS CRITERIA:\\n"
            for bonus in rubric.get("bonusCriteria", []):
                rubric_text += f"- {bonus.get('title', 'N/A')} ({bonus.get('points', 0)} points): {bonus.get('description', 'N/A')}\\n"

    prompt = f"""You are evaluating a student's heuristic evaluation assignment for a UX/HCI course.

{rubric_text}

STUDENT SUBMISSION - PAGE {page_number}:
Content length: {word_count} words
Has image: {has_image}
Content preview:
{page_content}

TASK:
First, determine what type of page this is by analyzing the FULL PAGE CONTENT (text, structure, visual elements), not just word count:
- Set "skip_analysis": true if:
  * Title page, cover page, introduction page, or table of contents
  * Page contains only a heuristic number/title (e.g., "Heuristic 1", "Heuristic 2") with minimal content
  * Page is clearly a section divider or subtitle page
  * Page has very little substantive content (mostly titles, headers, or decorative elements)
- Set "skip_analysis": false if:
  * Page contains heuristic violation analysis with detailed descriptions
  * Page has substantial content discussing violations, user impact, or UX issues
  * Page is a conclusion, methodology, severity summary, or AI opportunities section
  * Page follows a heuristic title page and contains the actual analysis content
  * Page has images with annotations explaining violations

Note: Heuristic title pages (showing just "Heuristic X" or similar) should be skipped, but the NEXT page usually contains the analysis for that heuristic and should be analyzed.

For pages that should be analyzed (skip_analysis: false):
1. Identify the page type (e.g., 'heuristic violation analysis', 'Severity Table', 'conclusion', 'AI Opportunities', 'Severity Summary', etc.)
2. Evaluate how correct the student's analysis is
3. Determine if their arguments are compelling
4. If compelling, give high scores; if not, evaluate according to the rubric criteria

IMPORTANT SCORING GUIDELINES:
- **Coverage**: This criterion evaluates the ENTIRE PDF submission, not just this single page. The assignment requires:
  1. All 10 Nielsen heuristics must be addressed across the entire PDF
  2. Minimum 12 violations must be identified across the entire PDF
  For this single page analysis, simply note which heuristics are discussed on this page and how many violations are mentioned in your feedback. The final Coverage score will be calculated automatically by the system based on the total heuristics count and violations count across all pages. Do NOT try to score Coverage here - just document what heuristics and violations are on this page. The system will automatically check if the totals meet the requirements (10 heuristics, 12 violations) and assign the Coverage score accordingly.
- **Violation Quality**: Usually do NOT give full points (20/20). Deduct points for:
  1. Repetition of emotional phrasing ("annoying," "frustrating", "confused") rather than proper UX terminology
  2. Inflated severity ratings: If violations are marked as "major" or "critical" but the actual user impact is mild or cosmetic, deduct points. Each violation should have a clear "what/why/user impact" structure, and severity ratings should match the actual impact described.
  3. Understated severity: Conversely, if serious issues are marked as "minor" or "cosmetic" when they should be "major" or "critical", also deduct points.
  Look for proper use of UX/HCI concepts and terminology, and appropriate severity ratings that match the described impact. Full points should be reserved for exceptional analyses that demonstrate deep understanding and accurate severity assessment.
  **IMPORTANT**: In the comment field, ONLY explain why points were deducted. Do NOT write positive comments like "you did well" or "excellent work". If points are deducted, explain the specific reason (e.g., "Overuse of emotional phrasing ('annoying', 'frustrating') instead of proper UX terminology", "Severity ratings are inflated: violations marked as 'major' but impact is only cosmetic"). If full points (20/20), leave the comment field empty or omit it.
- **Severity Analysis**: 
  1. CAREFULLY check if there is a severity summary section. Look for:
     - Pages titled "Severity Summary", "Severity Analysis", "Summary", or similar
     - Tables or lists or graphs that summarize violations and their severity levels
     - Sections that discuss overall severity patterns or provide a severity overview
     - Do NOT confuse individual violation severity ratings with a summary section
     - If you find ANY evidence of a severity summary (even if it's on a different page or in a table format), do NOT deduct the 3 points
     - Only deduct 3 points if you are CERTAIN there is NO severity summary section anywhere in the submission
  2. If the assignment does NOT have a severity summary section (or severity summary page), deduct 3 points from the maximum (10 points). So if there's no severity summary, the maximum possible score for Severity Analysis on this page would be 7/10. If this page IS a severity summary page, do not deduct points for missing severity summary.
  3. It would be helpful to include a one-sentence explanation of how the 1–4 scale was applied (e.g., impact × frequency × persistence) to make severity weighting more transparent. If such an explanation is missing, deduct points accordingly.
  **IMPORTANT**: In the comment field, ONLY explain why points were deducted. Do NOT write positive comments. If points are deducted, explain the specific reason (e.g., "No overall severity summary section found", "Missing explanation of how the 1-4 severity scale was applied"). If full points (10/10), leave the comment field empty or omit it.
- **Screenshots & Evidence**: Deduct points if:
  1. Images are very blurry or low quality (barely readable)
  2. Annotations/notes are inconsistent (inconsistent font sizes, messy formatting)
  3. Notes appear to be personal sketches rather than clear communication tools for explaining violations
  4. Screenshots lack proper annotations or labels that help explain the issues
  **IMPORTANT**: In the comment field, ONLY explain why points were deducted. Do NOT write positive comments. If points are deducted, explain the specific reason (e.g., "Screenshots are blurry and annotations are barely readable", "Inconsistent font sizes in annotations"). If full points (10/10), leave comment empty.
- **Professional Quality**: Consider layout organization, spacing, grid alignment, and visual consistency. Deduct points if the layout could be more organized, spacing is inconsistent, or alignment is careless.
  **IMPORTANT**: In the comment field, ONLY explain why points were deducted. Do NOT write positive comments. If points are deducted, explain the specific reason (e.g., "Inconsistent spacing between sections, some elements are misaligned", "Layout could be more organized with better use of grid structure"). If full points (10/10), leave comment empty.
- **Bonus Scores (AI Opportunities & Exceptional Quality)**: These are bonus credits. Only give high scores (close to max) if the work is truly exceptional. For average or good work, give modest scores (0-1 points out of max). Reserve full bonus points for work that significantly exceeds expectations.
  **IMPORTANT**: In the comment field, ONLY explain why points were not given (if 0 points). Do NOT write positive comments. If 0 points, explain why (e.g., "No exceptional AI opportunities identified beyond basic suggestions"). If points are given, leave the comment field empty or omit it.

FEEDBACK GUIDELINES:
- Keep feedback concise and focused. For pages with issues, point out 2-3 key problems.
- End with a brief overall summary for this page (1-2 sentences).
- Be constructive and polite, but direct about areas needing improvement.
- IMPORTANT: Include in the feedback which Nielsen heuristics are discussed on this page and which violations are identified, along with counts. This helps with coverage assessment.

EXTRACT HEURISTICS AND SEVERITY:
- In your feedback, clearly list each heuristic violation mentioned on this page.
- For each violation, note which heuristic number (1-10) it relates to and the severity level mentioned by the student (if any: Cosmetic/Minor/Major/Critical or 1-4 scale).
- Format example: "This page covers Heuristic 1 (Visibility of System Status) with 2 violations: missing loading indicator (severity: Major), unclear error messages (severity: Minor). Also covers Heuristic 3 (User Control and Freedom) with 1 violation: no undo option (severity: Major)."

Provide your response in the following JSON format:
{{
  "page_number": {page_number},
  "skip_analysis": true/false,
  "page_type": "description of what type of content this page contains",
  "skip_reason": "brief reason if skip_analysis is true (e.g., 'title page with minimal text')",
  "feedback": "concise feedback: 2-3 key issues if problems exist, then 1-2 sentence overall summary. IMPORTANT: For each violation mentioned, clearly state: (1) which heuristic number (1-10), (2) the violation description, and (3) the severity level if mentioned by student (Cosmetic/Minor/Major/Critical or 1-4). Example: 'This page covers Heuristic 1 (Visibility of System Status) with 2 violations: missing loading indicator (severity: Major), unclear error messages (severity: Minor). Also covers Heuristic 3 (User Control and Freedom) with 1 violation: no undo option (severity: Major).' (only if skip_analysis is false)",
  "compelling": true/false (only if skip_analysis is false),
  "score_breakdown": {{
    "coverage": {{"points": 0, "max": 15, "comment": "Coverage will be calculated automatically based on total heuristics and violations count across all pages. Leave this as 0 points for now - the system will calculate the final score based on whether 10 heuristics and 12 violations are met."}},
    "violation_quality": {{"points": X, "max": 20, "comment": "ONLY explain why points were deducted. Do NOT write positive comments. If points deducted, explain the reason (e.g., 'Overuse of emotional phrasing instead of UX terminology', 'Severity ratings are inflated'). If full points (20/20), leave comment empty."}},
    "screenshots": {{"points": X, "max": 10, "comment": "ONLY explain why points were deducted. Do NOT write positive comments. If points deducted, explain the reason (e.g., 'Screenshots are blurry', 'Inconsistent annotation formatting'). If full points (10/10), leave comment empty."}},
    "severity_analysis": {{"points": X, "max": 10, "comment": "ONLY explain why points were deducted. Do NOT write positive comments. If points deducted, explain the reason (e.g., 'No severity summary section found', 'Missing explanation of severity scale application'). If full points (10/10), leave comment empty."}},
    "structure_navigation": {{"points": X, "max": 10, "comment": "ONLY explain why points were deducted. Do NOT write positive comments. If points deducted, explain the reason (e.g., 'Poor document structure, difficult to navigate', 'Could benefit from better section organization'). If full points (10/10), leave comment empty."}},
    "professional_quality": {{"points": X, "max": 10, "comment": "ONLY explain why points were deducted. Do NOT write positive comments. If points deducted, explain the reason (e.g., 'Inconsistent spacing and misaligned elements', 'Layout could be more organized'). If full points (10/10), leave comment empty."}},
    "writing_quality": {{"points": X, "max": 10, "comment": "ONLY explain why points were deducted. Do NOT write positive comments. If points deducted, explain the reason (e.g., 'Multiple grammatical errors and unclear sentences', 'Some awkward phrasing'). If full points (10/10), leave comment empty."}},
    "group_integration": {{"points": X, "max": 15, "comment": "ONLY explain why points were deducted. Do NOT write positive comments. If points deducted, explain the reason (e.g., 'No evidence of group collaboration', 'Limited integration of group members' work'). If full points (15/15), leave comment empty."}}
  }} (only if skip_analysis is false),
  "bonus_scores": {{
    "bonus_ai_opportunities": {{"points": X, "max": 3, "comment": "ONLY explain why 0 points were given. Do NOT write positive comments. If 0 points, explain why (e.g., 'No exceptional AI opportunities identified beyond basic suggestions'). If points are given, leave comment empty."}},
    "bonus_exceptional_quality": {{"points": X, "max": 2, "comment": "ONLY explain why 0 points were given. Do NOT write positive comments. If 0 points, explain why. If points are given, leave comment empty."}}
  }} (only if skip_analysis is false)
}}

Be fair but thorough. Remember: violation_quality rarely gets full points, professional_quality should consider layout/spacing issues, and bonus scores should be conservative unless truly exceptional."""
    
    return prompt`}</code>
          </pre>
        </div>
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <p className="font-semibold mb-1">Note:</p>
          <p>
            This is the original prompt code that was provided to ChatGPT for analysis. The complete
            implementation also includes generation configuration (temperature: 0.7, max_output_tokens: 8192)
            and JSON parsing logic. This code served as the basis for ChatGPT's recommendations above.
            See <code>backend/main.py</code> for the complete current implementation.
          </p>
        </div>
      </section>
    </main>
  );
};

export default LLMRecommendationsPage;