from __future__ import annotations
import subprocess
import sys
import shutil
from pathlib import Path


def main() -> None:
    # Project root directory: .../cogs187a_A3b_autograder/
    base_dir = Path(__file__).resolve().parent.parent

    output_dir = base_dir / "output_static"
    desktop_dir = output_dir / "desktop"
    mobile_dir = output_dir / "mobile"
    legacy_analysis_dir = output_dir / "analysis"
    legacy_overlays_dir = output_dir / "overlays"
    pages_index = output_dir / "pages_index.json"

    print("=== [1] Cleaning previous analysis and overlays ===")

    # Remove new desktop / mobile directories
    if desktop_dir.exists():
        print(f"  - Removing desktop dir: {desktop_dir}")
        shutil.rmtree(desktop_dir)
    if mobile_dir.exists():
        print(f"  - Removing mobile dir: {mobile_dir}")
        shutil.rmtree(mobile_dir)

    # Clean up legacy directories
    if legacy_analysis_dir.exists():
        print(f"  - Removing legacy analysis dir: {legacy_analysis_dir}")
        shutil.rmtree(legacy_analysis_dir)
    if legacy_overlays_dir.exists():
        print(f"  - Removing legacy overlays dir: {legacy_overlays_dir}")
        shutil.rmtree(legacy_overlays_dir)

    # Optional: Remove old pages_index.json to let crawl_to_pdfs rewrite it
    if pages_index.exists():
        print(f"  - Removing old pages_index: {pages_index}")
        pages_index.unlink()

    print("=== [2] Running crawl_to_pdfs.py (crawl + desktop screenshots + pages_index) ===")
    crawl_script = base_dir / "scripts" / "crawl_to_pdfs.py"
    subprocess.run(
        [sys.executable, str(crawl_script)],
        cwd=str(base_dir),
        check=True,
    )

    print("=== [3] Running capture_mobile_screenshots.py (mobile screenshots + index update) ===")
    capture_mobile_script = base_dir / "scripts" / "capture_mobile_screenshots.py"
    subprocess.run(
        [sys.executable, str(capture_mobile_script)],
        cwd=str(base_dir),
        check=True,
    )

    print("=== [4] Running analyze_with_gemini.py (LLM heuristic analysis) ===")
    analyze_script = base_dir / "scripts" / "analyze_with_gemini.py"
    subprocess.run(
        [sys.executable, str(analyze_script)],
        cwd=str(base_dir),
        check=True,
    )

    print("=== [5] Running generate_overlays.py (draw bounding boxes + labels) ===")
    overlays_script = base_dir / "scripts" / "generate_overlays.py"
    subprocess.run(
        [sys.executable, str(overlays_script)],
        cwd=str(base_dir),
        check=True,
    )

    print("\n✅ All done!")
    print(" - Desktop screenshots: output_static/desktop/screens/")
    print(" - Desktop HTML:        output_static/desktop/html/")
    print(" - Desktop analyses:    output_static/desktop/analysis/")
    print(" - Desktop overlays:    output_static/desktop/overlays/")
    print(" - Mobile screenshots:  output_static/mobile/screens/")
    print(" - Mobile overlays:     output_static/mobile/overlays/")
    print(" - Mobile analyses:     output_static/mobile/analysis/")
    print(" - pages_index.json:    output_static/pages_index.json")


if __name__ == "__main__":
    main()
