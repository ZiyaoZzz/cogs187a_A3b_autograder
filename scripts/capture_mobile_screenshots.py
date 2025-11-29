from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
)

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output_static"
INDEX_PATH = OUTPUT_DIR / "pages_index.json"
MOBILE_DIR = OUTPUT_DIR / "mobile"
MOBILE_SCREENS_DIR = MOBILE_DIR / "screens"

MOBILE_SCREENS_DIR.mkdir(parents=True, exist_ok=True)


def load_index() -> List[Dict[str, Any]]:
    """Load the existing pages_index.json written by crawl_to_pdfs."""
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"pages_index.json not found at {INDEX_PATH}")
    with INDEX_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "index"
    last = path.split("/")[-1]
    return last or "index"


async def capture_mobile(
    page: Page,
    url: str,
    out_path: Path,
) -> bool:
    """
    Capture a mobile-view screenshot of the given URL.

    Viewport roughly like a modern phone (e.g., iPhone 12-ish).
    """
    print(f"[mobile] Capturing {url} → {out_path.relative_to(BASE_DIR)}")
    try:
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=120_000,
        )
    except TimeoutError as e:
        print(f"[mobile] Timeout while loading {url}: {e}")
    except Exception as e:
        print(f"[mobile] Failed to navigate to {url}: {e}")
        return False

    # Wait for a moment to let the content stabilize
    await page.wait_for_timeout(2000)

    try:
        MOBILE_SCREENS_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out_path), full_page=True)
        return True
    except Exception as e:
        print(f"[mobile] Failed to take screenshot for {url}: {e}")
        return False


async def main_async() -> None:
    index_records = load_index()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Open a new context for mobile screenshots
        mobile_context = await browser.new_context(
            viewport={"width": 430, "height": 932},  # Common phone sizes
            device_scale_factor=2.0,
            is_mobile=True,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
        )

        updated_records: List[Dict[str, Any]] = []

        for rec in index_records:
            raw_id = rec.get("id")
            url = rec.get("url")
            if raw_id is None or not url:
                print("[skip] Record missing id or url:", rec)
                updated_records.append(rec)
                continue

            rec_id_str = str(raw_id).zfill(3)
            slug = slug_from_url(url)

            mobile_name = f"{rec_id_str}__{slug}_mobile.png"
            mobile_path = MOBILE_SCREENS_DIR / mobile_name

            success = False
            if mobile_path.exists():
                print(f"[mobile] Skip existing mobile screenshot: {mobile_path}")
                success = True
            else:
                page = await mobile_context.new_page()
                try:
                    success = await capture_mobile(page, url, mobile_path)
                finally:
                    await page.close()

            # Write mobile_image_path to index (even if it fails, write the original)
            if success:
                rec["mobile_image_path"] = str(
                    Path("output_static") / "mobile" / "screens" / mobile_name
                )
                rec["mobile_overlay_path"] = str(
                    Path("output_static")
                    / "mobile"
                    / "overlays"
                    / mobile_name.replace(".png", "_overlay.png")
                )
            updated_records.append(rec)

        await mobile_context.close()
        await browser.close()

    # Write back to pages_index.json
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(updated_records, f, indent=2, ensure_ascii=False)
    print(f"[mobile] Updated pages_index.json with mobile_image_path")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
