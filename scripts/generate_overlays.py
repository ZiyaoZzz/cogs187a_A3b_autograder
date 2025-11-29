from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont

# Project root (e.g., COGS187_A3_Autograder/)
BASE_DIR = Path(__file__).resolve().parent.parent
DESKTOP_DIR = BASE_DIR / "output_static" / "desktop"
MOBILE_DIR = BASE_DIR / "output_static" / "mobile"


def load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON issue file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def wrap_text(text: str, max_chars: int = 50) -> str:
    """
    Basic text wrapping by word count.
    Ensures annotation text does not exceed a reasonable width.
    """
    words = text.split()
    lines: List[str] = []
    current: List[str] = []

    for w in words:
        current.append(w)
        if len(" ".join(current)) > max_chars:
            last = current.pop()
            lines.append(" ".join(current))
            current = [last]

    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def clamp_box(x: int, y: int, bw: int, bh: int, w: int, h: int) -> tuple[int, int, int, int]:
    """
    Clamp the bounding box to stay fully within the image.
    Also enforces a small minimum size.
    """
    MIN_SIZE = 8

    if x < 0:
        bw += x  # reduce width accordingly
        x = 0
    if y < 0:
        bh += y
        y = 0

    if x + bw > w:
        bw = w - x
    if y + bh > h:
        bh = h - y

    bw = max(MIN_SIZE, bw)
    bh = max(MIN_SIZE, bh)

    return x, y, bw, bh


def draw_overlay(
    image_path: Path,
    issues: List[Dict[str, Any]],
    output_path: Path,
) -> None:
    """
    Draw red bounding boxes + English annotation labels
    (including description) on a screenshot image.
    """
    if not image_path.exists():
        print(f"[WARN] Screenshot not found: {image_path}")
        return

    img = Image.open(image_path).convert("RGBA")
    w, h = img.size

    overlay = img.copy()
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    for issue in issues:
        bbox = issue.get("bbox", {})
        x_rel = float(bbox.get("x", 0.0))
        y_rel = float(bbox.get("y", 0.0))
        w_rel = float(bbox.get("width", 0.0))
        h_rel = float(bbox.get("height", 0.0))

        # Convert relative coordinates → actual pixel coordinates
        x = int(x_rel * w)
        y = int(y_rel * h)
        bw = int(w_rel * w)
        bh = int(h_rel * h)

        # Make sure the box stays inside the image and isn't degenerate
        x, y, bw, bh = clamp_box(x, y, bw, bh, w, h)
        rect = [x, y, x + bw, y + bh]

        # --- 1. Draw bounding box ---
        draw.rectangle(rect, outline="red", width=4)

        # --- 2. Construct annotation text (include description) ---
        heuristic_number = issue.get("heuristic_number")
        severity_label = issue.get("severity_label", "")
        title = issue.get("title", "")
        description = issue.get("description", "")

        # Optionally truncate description so it fits visually on the image.
        # You can tweak these numbers depending on how much text you want.
        max_desc_len = 240
        short_desc = description
        if len(short_desc) > max_desc_len:
            short_desc = short_desc[: max_desc_len - 3] + "..."

        label_text = (
            f"Heuristic {heuristic_number} ({severity_label})\n"
            f"{title}\n"
            f"Description: {short_desc}"
        )

        # Wrap text so it doesn’t create a super-wide label.
        label_text = wrap_text(label_text, max_chars=70)

        # --- 3. Measure text box size ---
        padding = 4
        text_bbox = draw.multiline_textbbox((0, 0), label_text, font=font, spacing=2)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        # Default position: above the box
        label_x = x
        label_y = y - text_h - 2 * padding

        # If there is not enough space above, place below the box
        if label_y < 0:
            label_y = y + bh + 4

        # If it overflows to the right, shift it left
        if label_x + text_w + 2 * padding > w:
            label_x = max(0, w - text_w - 2 * padding)

        # If it still overflows bottom, clamp it
        if label_y + text_h + 2 * padding > h:
            label_y = max(0, h - text_h - 2 * padding)

        # --- 4. Draw white background for readability ---
        bg_rect = [
            label_x,
            label_y,
            label_x + text_w + 2 * padding,
            label_y + text_h + 2 * padding,
        ]
        draw.rectangle(bg_rect, fill=(255, 255, 255, 235), outline="red")

        # --- 5. Draw annotation text ---
        draw.multiline_text(
            (label_x + padding, label_y + padding),
            label_text,
            font=font,
            fill="black",
            spacing=2,
        )

    # Save result
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path)
    print(f"[OK] Overlay saved: {output_path.relative_to(BASE_DIR)}")


def resolve_screenshot_path(
    entry: Dict[str, Any], screens_dir: Path
) -> Optional[Path]:
    raw_path = entry.get("image_path")
    if isinstance(raw_path, str) and raw_path.strip():
        path = Path(raw_path)
        if not path.is_absolute():
            path = BASE_DIR / raw_path
        if path.exists():
            return path

    rec_id = entry.get("id")
    if rec_id is not None:
        rec_id_str = str(rec_id).zfill(3)
        candidates = sorted(screens_dir.glob(f"{rec_id_str}*.png"))
        if candidates:
            return candidates[0]

    return None


def generate_for_view(
    view_name: str,
    analysis_dir: Path,
    screens_dir: Path,
    overlays_dir: Path,
) -> None:
    if not analysis_dir.exists():
        print(f"[WARN] Analysis dir missing for {view_name}: {analysis_dir}")
        return

    overlays_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Generating overlays for {view_name} ===")
    for json_path in sorted(analysis_dir.glob("*.json")):
        if json_path.name == "pages_index.json":
            continue

        data = load_json(json_path)

        if "issues" in data and isinstance(data["issues"], list):
            issues = data["issues"]
        else:
            issues = [data]

        if not issues:
            print(f"[INFO] {json_path.name} contains no issues — skipped.")
            continue

        screenshot_path = resolve_screenshot_path(data, screens_dir)
        if not screenshot_path or not screenshot_path.exists():
            print(
                f"[WARN] Screenshot not found for {json_path.stem} in view {view_name}"
            )
            continue

        overlay_name = screenshot_path.stem + "_overlay.png"
        overlay_path = overlays_dir / overlay_name
        draw_overlay(screenshot_path, issues, overlay_path)


def main():
    configs = [
        (
            "desktop",
            DESKTOP_DIR / "analysis",
            DESKTOP_DIR / "screens",
            DESKTOP_DIR / "overlays",
        ),
        (
            "mobile",
            MOBILE_DIR / "analysis",
            MOBILE_DIR / "screens",
            MOBILE_DIR / "overlays",
        ),
    ]

    for view_name, analysis_dir, screens_dir, overlays_dir in configs:
        generate_for_view(view_name, analysis_dir, screens_dir, overlays_dir)


if __name__ == "__main__":
    main()
