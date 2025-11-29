from __future__ import annotations
import os
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from typing import Optional, List, Dict

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from PIL import Image, ImageStat

START_URL = "https://visitjulian.com/"
DOMAIN = "visitjulian.com"

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

OUTPUT_DIR = PROJECT_ROOT / "output_static"
DESKTOP_DIR = OUTPUT_DIR / "desktop"
DESKTOP_SCREENS_DIR = DESKTOP_DIR / "screens"
DESKTOP_HTML_DIR = DESKTOP_DIR / "html"
INDEX_PATH = OUTPUT_DIR / "pages_index.json"

DESKTOP_SCREENS_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_HTML_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

NON_HTML_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".css",
    ".js",
    ".zip",
    ".mp3",
    ".mp4",
    ".mov",
)

THIRD_PARTY_KEYWORDS = [
    "youtube.com",
    "youtu.be",
    "player.vimeo.com",
    "vimeo.com",
    "maps.google",
    "google.com/maps",
    "calendar.google",
    "openstreetmap.org",
    "snapwidget",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "tiktok.com",
    "tripadvisor",
    "eventbrite",
    "soundcloud.com",
]


def normalize_link(base: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href, _ = urldefrag(href)
    if href.startswith(("mailto:", "tel:", "javascript:")):
        return None
    abs_url = urljoin(base, href)
    parsed = urlparse(abs_url)
    if parsed.netloc != DOMAIN:
        return None

    path_lower = parsed.path.lower()
    if any(path_lower.endswith(ext) for ext in NON_HTML_EXTENSIONS):
        return None

    return abs_url


def extract_third_party_embeds(html: str) -> List[str]:
    """Heuristically detect third-party embeds (iframe/video) from HTML."""
    embeds: List[str] = []
    soup = BeautifulSoup(html, "html.parser")

    def add_embed(src: Optional[str], label: str) -> None:
        if not src:
            return
        src = src.strip()
        if not src:
            return
        src_lower = src.lower()
        for keyword in THIRD_PARTY_KEYWORDS:
            if keyword in src_lower:
                embeds.append(f"{label}: {src}")
                return
        parsed = urlparse(src)
        if parsed.netloc and DOMAIN not in parsed.netloc:
            embeds.append(f"{label}: {src}")

    for iframe in soup.find_all("iframe"):
        add_embed(iframe.get("src") or iframe.get("data-src"), "iframe")

    for embed_tag in soup.find_all("embed"):
        add_embed(embed_tag.get("src"), "embed")

    for video in soup.find_all("video"):
        add_embed(video.get("src"), "video")
        for source in video.find_all("source"):
            add_embed(source.get("src"), "video-source")

    return embeds


def collect_links(start_url: str, max_pages: int = 3) -> List[str]:
    visited = set()
    to_visit = [start_url]
    all_urls = set()

    session = requests.Session()

    while to_visit:
        if len(all_urls) >= max_pages:
            print(f"[crawl] Reached max_pages={max_pages}, stopping crawl.")
            break

        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        all_urls.add(url)

        print(f"[crawl] Fetching: {url}")
        print(f"[crawl] Progress: visited={len(visited)} queued={len(to_visit)}")

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[crawl] Failed to fetch {url}: {e}")
            continue

        content_type = resp.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            print(f"[crawl] Skipping non-HTML content at {url} (Content-Type: {content_type})")
            continue

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"[crawl] Failed to parse HTML at {url}: {e}")
            continue

        for a in soup.find_all("a"):
            href = a.get("href")
            new_url = normalize_link(url, href)
            if not new_url:
                continue
            if new_url not in visited and new_url not in to_visit and new_url not in all_urls:
                to_visit.append(new_url)

        if len(visited) % 10 == 0:
            print(f"[crawl] Summary: visited={len(visited)} total_collected={len(all_urls)} queue={len(to_visit)}")

        time.sleep(0.5)

    urls_list = sorted(all_urls)
    print(f"[crawl] Total collected HTML URLs: {len(urls_list)}")
    return urls_list


def safe_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith("/"):
        path = path[:-1]
    if not path:
        path = "index"
    name = path.replace("/", "_")
    if not name:
        name = "page"
    return name


def extract_title_from_url(url: str) -> str:
    """Extract a readable title from URL path."""
    parsed = urlparse(url)
    path = parsed.path.replace("/", "").replace("-", " ").strip()
    if not path:
        return "Home"
    words = path.split()
    title = " ".join(word.capitalize() for word in words)
    return title


def is_potentially_dynamic(html: str, url: str) -> bool:
    """
    Heuristic: check if page likely has dynamic visual content
    (video/iframe/lazy/webcam/background-image slider/map).
    """
    lower = html.lower()
    patterns = [
        "<video",
        "<iframe",
        "data-src",
        "lazyload",
        'loading="lazy"',
        "loading='lazy'",
        "swiper-container",
        "carousel",
        "webcam",
        "livecam",
        "background-image:",      
        "timely-slider-event-image",
        "google.com/maps",           # map iframe
    ]
    if any(p in lower for p in patterns):
        return True

    if "visit-julian-webcam" in url or "julian-events" in url:
        return True

    return False



def try_activate_media(page, url: str) -> None:
    """
    For dynamic pages:
    - Scroll through the page to trigger lazy loading
    - Try clicking 'play' buttons
    - Try clicking iframe centers
    - If there is a Google Maps iframe, wait extra time for tiles
    """
    print(f"[dyn] Activating dynamic content on {url}")

    # 1) Scroll through page
    try:
        page.evaluate(
            """
            () => {
              return new Promise(resolve => {
                let totalHeight = 0;
                const distance = 400;
                const timer = setInterval(() => {
                  const scrollHeight = document.body.scrollHeight || document.documentElement.scrollHeight;
                  window.scrollBy(0, distance);
                  totalHeight += distance;
                  if (totalHeight >= scrollHeight) {
                    clearInterval(timer);
                    window.scrollTo(0, 0);
                    resolve();
                  }
                }, 250);
              });
            }
            """
        )
    except Exception as e:
        print(f"[dyn] Failed while scrolling {url}: {e}")

    # 2) Click common play buttons
    try:
        play_texts = ["Play", "Watch", "View", "Live", "▶"]
        for text in play_texts:
            locator = page.get_by_text(text, exact=False)
            count = locator.count()
            for i in range(count):
                el = locator.nth(i)
                if el.is_visible():
                    print(f"[dyn] Clicking text button '{text}' on {url}")
                    el.click()
                    page.wait_for_timeout(500)
                    break

        try:
            play_buttons = page.get_by_role("button", name="Play")
            if play_buttons.count() > 0:
                print(f"[dyn] Clicking role=button 'Play' on {url}")
                play_buttons.first.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

        css_selectors = [
            ".vjs-big-play-button",
            ".mejs-overlay-play",
            ".play-button",
            ".wp-video-shortcode .wp-play-pause",
        ]
        for sel in css_selectors:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                print(f"[dyn] Clicking CSS selector '{sel}' on {url}")
                loc.first.click()
                page.wait_for_timeout(500)
                break
    except Exception as e:
        print(f"[dyn] Error while clicking play buttons on {url}: {e}")

    # 3) Click iframe centers
    has_google_maps = False
    try:
        frames = page.locator("iframe")
        count = frames.count()
        for i in range(count):
            iframe_el = frames.nth(i)
            if not iframe_el.is_visible():
                continue

            # Check if this iframe has google maps
            try:
                src = iframe_el.get_attribute("src") or ""
                if "google.com/maps" in (src.lower()):
                    has_google_maps = True
            except Exception:
                pass

            box = iframe_el.bounding_box()
            if not box:
                continue
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            print(f"[dyn] Clicking iframe center #{i} on {url}")
            page.mouse.click(x, y)
            page.wait_for_timeout(500)
    except Exception as e:
        print(f"[dyn] Error while clicking iframe centers on {url}: {e}")

    if has_google_maps:
        print(f"[dyn] Detected Google Maps iframe on {url}, waiting extra for tiles...")
        page.wait_for_timeout(5000)
    else:
        page.wait_for_timeout(3000)



def looks_mostly_uniform(img_path: Path, threshold: float = 5.0) -> bool:
    """
    Rough check: if grayscale standard deviation is very small, the image is
    almost one flat color (e.g., fully white / black / grey).
    """
    try:
        img = Image.open(img_path).convert("L")
        stat = ImageStat.Stat(img)
        std = stat.stddev[0]
        return std < threshold
    except Exception as e:
        print(f"[img] Warning: failed to analyze image {img_path}: {e}")
        return False


def render_urls_to_images(urls: List[str]) -> List[Dict]:
    index_records: List[Dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.0,
        )
        page = context.new_page()
        page.set_default_navigation_timeout(30000)  # 30s timeout

        total = len(urls)

        for i, url in enumerate(urls, start=1):
            print(f"\n[img] ({i}/{total}) Rendering: {url}")
            try:
                # 1) navigate
                try:
                    page.goto(url, wait_until="load", timeout=20000)
                except PlaywrightTimeoutError:
                    print(f"[img] Load timeout, using domcontentloaded for {url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)

                # 2) HTML content & save
                html = page.content()
                base_name = safe_filename_from_url(url)
                id_str = f"{i:03d}"
                html_name = f"{id_str}_{base_name}.html"
                html_path = DESKTOP_HTML_DIR / html_name
                html_path.write_text(html, encoding="utf-8")
                print(f"[html] Saved {html_path}")
                third_party_embeds = extract_third_party_embeds(html)

                # 3) Is it a dynamic page?
                dynamic = is_potentially_dynamic(html, url)
                if dynamic:
                    print(f"[dyn] Page detected as dynamic: {url}")
                    try_activate_media(page, url)
                else:
                    # Original logic to wait for images to load (very friendly to static pages)
                    print(f"[img] Waiting for images to load on static page...")
                    try:
                        page.evaluate(
                            """
                            () => Promise.race([
                                Promise.all(
                                    Array.from(document.images)
                                      .filter(img => !img.complete && img.src)
                                      .map(img => new Promise((resolve) => {
                                          if (img.complete) {
                                              resolve();
                                              return;
                                          }
                                          img.onload = resolve;
                                          img.onerror = resolve;
                                          setTimeout(resolve, 3000);
                                      }))
                                ),
                                new Promise(resolve => setTimeout(resolve, 5000))
                            ])
                            """
                        )
                    except Exception as e:
                        print(f"[img] Warning: error waiting for images: {e}")
                    page.wait_for_timeout(1000)

                # 4) Screenshot (first time)
                numbered = f"{id_str}_{base_name}.png"
                img_path = DESKTOP_SCREENS_DIR / numbered
                page.screenshot(path=str(img_path), full_page=True)
                print(f"[img] Saved screenshot {img_path}")

                # 5) If it's a dynamic page but the image is almost completely blank, retry once
                if dynamic and looks_mostly_uniform(img_path):
                    print(f"[dyn] Screenshot looks very uniform; retrying capture for {url}")
                    try_activate_media(page, url)
                    page.screenshot(path=str(img_path), full_page=True)
                    print(f"[dyn] Overwrote screenshot after retry: {img_path}")

                # metadata
                title = extract_title_from_url(url)
                image_path = str(img_path.relative_to(PROJECT_ROOT))
                overlay_rel = (
                    image_path.replace("/screens/", "/overlays/")
                    .replace("\\screens\\", "\\overlays\\")
                    .replace(".png", "_overlay.png")
                )
                html_rel = str(html_path.relative_to(PROJECT_ROOT))

                index_records.append(
                    {
                        "id": id_str,
                        "title": title,
                        "url": url,
                        "screenshot": numbered,
                        "image_path": image_path,
                        "overlay_path": overlay_rel,
                        "html_path": html_rel,
                        "third_party_embeds": third_party_embeds,
                        "has_third_party_embeds": bool(third_party_embeds),
                    }
                )
            except Exception as e:
                print(f"[img] Failed to render {url}: {e}")

        browser.close()

    return index_records


def main():
    urls = collect_links(START_URL, max_pages=3)
    index_records = render_urls_to_images(urls)

    with INDEX_PATH.open("w", encoding="utf-8") as f:
        json.dump(index_records, f, indent=2, ensure_ascii=False)

    print(f"\n[done] Saved {len(index_records)} screenshots into {DESKTOP_SCREENS_DIR}")
    print(f"[done] Index file written to {INDEX_PATH}")


if __name__ == "__main__":
    main()
