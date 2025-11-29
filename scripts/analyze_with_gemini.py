from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

import google.generativeai as genai
from PIL import Image

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("Please set GEMINI_API_KEY in your environment.")

genai.configure(api_key=API_KEY)

MODEL_NAME = "models/gemini-2.5-flash"

BASE_PROMPT_TEXT = """
You are an HCI and usability expert performing a heuristic evaluation
of a web page for a usability class assignment.

You are given a screenshot image of a single page from a tourism website.
Using Nielsen's 10 heuristics:

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

Your task:

1. Scan the screenshot and identify the most important usability issues.
   Focus on issues that would actually affect a typical user trying to
   navigate, read, or perform simple tasks (e.g., finding information,
   booking, contacting, etc.).

2. Avoid over-reporting template chrome:
   - Many pages on this site share a common header, sidebar, and footer.
   - Only report issues in these shared regions if they are clearly
     Major or Critical, OR if they directly interfere with the main
     goals of the page (e.g., finding or booking lodging).
   - Do NOT create multiple issues that all describe essentially the
     same generic problem (e.g., "footer text is small" or "global nav
     labels are vague"). Prefer to focus on issues that are specific to
     the page content or that strongly impact real user tasks.

3. For each distinct issue, decide:
   - which single heuristic it most clearly violates
   - a severity rating from 1 to 4:
       1 = Cosmetic
       2 = Minor
       3 = Major
       4 = Critical / Catastrophic
   - a short title
   - a few sentences describing:
       * what the issue is
       * why it matters for users
       * how it might affect common tasks
   - an approximate bounding box indicating where the issue appears
     on the screenshot, using relative coordinates in [0, 1]:
       bbox.x      = left position
       bbox.y      = top position
       bbox.width  = width
       bbox.height = height

   Bounding box guidelines (very important):
   - Make the box as tight as is reasonable around the element(s)
     involved in the issue (for example, a specific card, button,
     navigation bar, or content block).
   - Do NOT cover an entire column or the whole page unless the issue
     truly involves most of the layout or content.
   - As a rule of thumb, most issues should have width and height
     less than or equal to about 0.6. Use very large boxes
     (width/height > 0.8) only when the entire page is the problem
     (for example, overly dense content everywhere).

4. Also compute an overall score for the page from 1 to 4, where:
   1 = Mostly cosmetic issues
   2 = Some minor issues, page is generally usable
   3 = Several major issues, users will often struggle
   4 = Serious problems, page fails for common tasks

Important:
- Do NOT invent dynamic behavior; base your evaluation only on what is visible
  in the static screenshot.
- Limit yourself to 3–8 of the most important issues to avoid noise.
- Be strict about JSON formatting.
"""


def build_prompt(
    third_party_embeds: Optional[List[str]] = None,
    view_label: str = "desktop",
) -> str:
    """
    Build the final prompt, optionally adding guidance about third-party embeds
    (e.g., Google Maps, webcams, external calendars) and about the viewport
    (desktop vs mobile).
    """
    extra_parts: List[str] = []

    # Viewport-specific hint
    if view_label == "mobile":
        extra_parts.append(
            """
5. Viewport context (mobile):

   The screenshot you see represents a MOBILE / narrow-viewport layout
   (e.g., a phone). When evaluating this view, you may pay special attention
   to:

   - tap target size and spacing,
   - readability on small screens,
   - whether important actions are hidden behind menus,
   - how well the layout supports one-handed use and scrolling.

   Still, apply the same Nielsen heuristics as usual.
"""
        )
    else:
        extra_parts.append(
            """
5. Viewport context (desktop):

   The screenshot you see represents a DESKTOP / wide-viewport layout.
   You may pay special attention to:

   - information hierarchy and use of whitespace,
   - scanability of lists and cards,
   - clarity of navigation on larger screens,
   - how well the layout uses available space without overwhelming users.
"""
        )

    # Third-party embeds
    embeds = third_party_embeds or []
    if embeds:
        embeds_str = ", ".join(embeds)
        extra_parts.append(
            f"""
6. Third-party embedded content (very important):

   Based on the page's HTML, this page includes one or more third-party
   embedded widgets or dynamic components. Examples may include:
   {embeds_str}.

   These embedded widgets sometimes do NOT render correctly in automated
   screenshots (for example, they may appear blank, show only a loading
   spinner, or show a static placeholder).

   When evaluating this page:

   - Do NOT treat a blank or partially missing embedded widget area as a
     usability problem by itself.
   - You may comment on how the page *integrates* such widgets (for example,
     unlabeled map section, unclear purpose of a webcam panel, or missing
     explanation of what a calendar controls), but you should NOT penalize
     the page only because the live external content is not visible in
     the screenshot.
   - Focus your issues on layout, labeling, navigation, and interaction
     that are under the website's control, rather than on whether the
     third-party service successfully rendered inside the frame.
"""
        )

    extra = "\n".join(extra_parts)

    return BASE_PROMPT_TEXT + extra + """

Output your answer as a single valid JSON object with this structure:

{
  "overall_score": 2.0,
  "issues": [
    {
      "id": "iss_001",
      "heuristic_number": 1,
      "heuristic_name": "Visibility of System Status",
      "severity": 3,
      "severity_label": "Major",
      "title": "Short title here",
      "description": "A few sentences explaining the issue and its impact.",
      "bbox": {
        "x": 0.10,
        "y": 0.05,
        "width": 0.80,
        "height": 0.15
      }
    }
  ]
}
"""


def analyze_screenshot(
    image_path: Path,
    url: Optional[str] = None,
    third_party_embeds: Optional[List[str]] = None,
    view_label: str = "desktop",
) -> Dict[str, Any]:
    print(f"[ai] Analyzing {image_path} (view={view_label})")

    img = Image.open(image_path)

    model = genai.GenerativeModel(MODEL_NAME)

    prompt_text = build_prompt(third_party_embeds, view_label=view_label)

    response = model.generate_content(
        [prompt_text, img],
        generation_config={"response_mime_type": "application/json"},
    )

    text_out = response.text

    try:
        data = json.loads(text_out)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "Model did not return valid JSON: {}\nRaw output:\n{}".format(e, text_out)
        )

    if url is not None:
        data["url"] = url
    data["image_path"] = str(image_path)
    data["view"] = view_label

    # Carry through embed metadata for downstream use
    if third_party_embeds is not None:
        data["third_party_embeds"] = third_party_embeds
        data["has_third_party_embeds"] = bool(third_party_embeds)

    return data


def load_index(project_root: Path) -> List[Dict[str, Any]]:
    index_path = project_root / "output_static" / "pages_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Index file not found: {index_path}")
    with index_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    project_root = Path(__file__).parent.parent
    desktop_analysis_dir = project_root / "output_static" / "desktop" / "analysis"
    mobile_analysis_dir = project_root / "output_static" / "mobile" / "analysis"
    desktop_analysis_dir.mkdir(parents=True, exist_ok=True)
    mobile_analysis_dir.mkdir(parents=True, exist_ok=True)

    index_records = load_index(project_root)

    for rec in index_records:
        # id may be "001" or 1; normalize to "001"
        raw_id = rec.get("id")
        if raw_id is None:
            print("[skip] Record has no id; skipping:", rec)
            continue
        rec_id_str = str(raw_id).zfill(3)

        url = rec.get("url")
        third_party_embeds = rec.get("third_party_embeds") or []

        # === 1) Desktop analysis ===
        image_rel = rec.get("image_path") or rec.get("screenshot")
        if image_rel:
            img_path = project_root / image_rel
            out_path = desktop_analysis_dir / f"{rec_id_str}.json"

            if not img_path.exists():
                print(f"[skip] Desktop image not found for record {rec_id_str}: {img_path}")
            elif out_path.exists():
                print(f"[skip] Desktop analysis already exists: {out_path}")
            else:
                try:
                    result = analyze_screenshot(
                        img_path,
                        url=url,
                        third_party_embeds=third_party_embeds,
                        view_label="desktop",
                    )
                except Exception as e:
                    print(f"[error] Failed to analyze desktop {img_path}: {e}")
                else:
                    out_path.write_text(
                        json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(f"[ai] Saved desktop analysis to {out_path}")
        else:
            print(f"[skip] Record {rec_id_str} has no image_path/screenshot; skipping desktop.")

        # === 2) Mobile analysis (if available) ===
        mobile_rel = rec.get("mobile_image_path")
        if not mobile_rel:
            continue  # no mobile screenshot for this page

        mobile_img_path = project_root / mobile_rel
        mobile_out_path = mobile_analysis_dir / f"{rec_id_str}_mobile.json"

        if not mobile_img_path.exists():
            print(f"[skip] Mobile image not found for record {rec_id_str}: {mobile_img_path}")
            continue

        if mobile_out_path.exists():
            print(f"[skip] Mobile analysis already exists: {mobile_out_path}")
            continue

        try:
            mobile_result = analyze_screenshot(
                mobile_img_path,
                url=url,
                third_party_embeds=third_party_embeds,
                view_label="mobile",
            )
        except Exception as e:
            print(f"[error] Failed to analyze mobile {mobile_img_path}: {e}")
            continue

        mobile_out_path.write_text(
            json.dumps(mobile_result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[ai] Saved mobile analysis to {mobile_out_path}")


if __name__ == "__main__":
    main()
