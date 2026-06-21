#!/usr/bin/env python3
"""
WeChat article fetcher using Playwright with local browser.

Features (v1.1 improvements ported from cat-xierluo/legal-skills):
- Headless mode by default with automatic fallback to headed on failure
- Auto retry up to 3 times on failure
- Anti-detection: hide navigator.webdriver, override plugins/chrome
- Image download to local _assets/ folder with smart filtering
- Configurable minimum image size filter (default 15KB)

Usage:
    python fetch_weixin.py <url> [output_filename]

Example:
    # Auto-generate filename (YYYYMMDD+Title format)
    python fetch_weixin.py "https://mp.weixin.qq.com/s/xxxxx"

    # Custom filename
    python fetch_weixin.py "https://mp.weixin.qq.com/s/xxxxx" article.md

    # Custom output directory (auto-generates filename inside)
    python fetch_weixin.py "https://mp.weixin.qq.com/s/xxxxx" "./articles/"
"""

import sys
import os
import asyncio
import re
import urllib.request
import ssl
from pathlib import Path

from playwright.async_api import async_playwright
from markdownify import markdownify as md

# ---------------------------------------------------------------------------
# Config (matches the Node.js version defaults)
# ---------------------------------------------------------------------------
IMAGE_FILTER_CONFIG = {
    "min_file_size": 15 * 1024,  # 15 KB – skip decorative icons / emoji
    "enabled": True,
}

MAX_RETRIES = 3
RETRY_DELAY = 3   # seconds between retries
PAGE_TIMEOUT = 90_000   # ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_publish_date(publish_time: str | None) -> str | None:
    """
    Parse publish time and extract date in YYYYMMDD format.

    Examples:
        "2025年12月6日 13:31" → "20251206"
        "2024年1月5日"       → "20240105"
    """
    if not publish_time:
        return None

    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", publish_time)
    if match:
        year = match.group(1)
        month = match.group(2).zfill(2)
        day = match.group(3).zfill(2)
        return f"{year}{month}{day}"

    return None


def sanitize_filename(filename: str) -> str:
    """Remove / replace invalid characters in filename."""
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)
    filename = re.sub(r"\s+", " ", filename)
    filename = filename.strip(". ")
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def sanitize_dirname(name: str) -> str:
    """Same as sanitize_filename but shorter limit for dir names."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(". ")
    if len(name) > 80:
        name = name[:80]
    return name


def short_hash(url: str, length: int = 8) -> str:
    """Short hex digest of a URL to avoid filename collisions."""
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:length]


# ---------------------------------------------------------------------------
# Anti-detection script (injected into every page)
# ---------------------------------------------------------------------------
ANTI_DETECTION_JS = """
() => {
    // Hide automation-controlled flag
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    // Fake Chrome runtime
    window.chrome = { runtime: {} };
    // Fake plugins array (mimics normal Chrome)
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    // Override permissions API
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({state: Notification.permission}) :
            origQuery(parameters)
    );
}
"""


# ---------------------------------------------------------------------------
# Lazy-image fix
# ---------------------------------------------------------------------------
LAZY_IMAGE_JS = """
() => {
    const images = document.querySelectorAll('#js_content img');
    images.forEach(img => {
        const dataSrc = img.getAttribute('data-src') ||
                      img.getAttribute('data-original') ||
                      img.getAttribute('data-actualsrc');
        if (dataSrc) {
            img.src = dataSrc;
        }
    });
}
"""


# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------
async def download_images(page, img_urls: list[str], assets_dir: str) -> dict[str, str]:
    """
    Download images to a local assets directory.

    Returns a dict mapping original URL → local relative path (or original
    URL if download failed / filtered out).
    """
    os.makedirs(assets_dir, exist_ok=True)
    mapping = {}

    # Build cookie header from page context so WeChat CDN doesn't block us
    cookies = await page.context.cookies()
    cookie_header = "; ".join(
        [f"{c['name']}={c['value']}" for c in cookies]
    )
    referer = page.url

    ssl_ctx = ssl.create_default_context()

    for i, url in enumerate(img_urls):
        # Generate a stable local filename
        ext = ".jpg"
        url_lower = url.lower()
        if ".png" in url_lower:
            ext = ".png"
        elif ".gif" in url_lower:
            ext = ".gif"
        elif ".webp" in url_lower:
            ext = ".webp"
        local_name = f"image_{short_hash(url)}_{i}{ext}"
        local_path = os.path.join(assets_dir, local_name)

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Linux; Android 12; SM-S906N) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Mobile Safari/537.36"
                    ),
                    "Referer": referer,
                    "Cookie": cookie_header,
                },
            )
            with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
                data = resp.read()

            # Filter tiny decorative images
            if IMAGE_FILTER_CONFIG["enabled"] and len(data) < IMAGE_FILTER_CONFIG["min_file_size"]:
                print(f"    ⊘ Skipped (too small, {len(data)} bytes): {local_name}")
                mapping[url] = url   # keep original remote URL
                continue

            with open(local_path, "wb") as f:
                f.write(data)

            rel_path = os.path.join(
                os.path.basename(assets_dir), local_name
            )
            mapping[url] = rel_path
            print(f"    ✓ Downloaded ({len(data):,} bytes): {local_name}")

        except Exception as e:
            print(f"    ⚠ Failed: {url[:80]}… → {e}")
            mapping[url] = url   # fall back to remote URL

    return mapping


# ---------------------------------------------------------------------------
# Replace image URLs in Markdown content
# ---------------------------------------------------------------------------
def replace_image_urls(md_content: str, mapping: dict[str, str]) -> str:
    """Replace remote image URLs in Markdown with local paths."""
    for remote_url, local_path in mapping.items():
        md_content = md_content.replace(remote_url, local_path)
    return md_content


# ---------------------------------------------------------------------------
# Core fetch logic
# ---------------------------------------------------------------------------
async def _do_fetch(page, url: str):
    """Single fetch attempt. Returns (title, author, publish_time, markdown, img_urls)."""
    print(f"[LOAD] Loading page...")
    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)

    # Anti-detection
    await page.evaluate(ANTI_DETECTION_JS)

    print(f"[WAIT] Waiting for content to appear...")
    try:
        await page.wait_for_selector("#js_content", timeout=60_000)
    except Exception:
        print(f"[WAIT] Content not found, waiting additional time...")
        await asyncio.sleep(5)

        # Debug screenshot
        try:
            screenshot_path = "debug_page.png"
            await page.screenshot(path=screenshot_path)
            print(f"[DEBUG] Screenshot saved to: {screenshot_path}")
        except Exception:
            pass

        page_title = await page.title()
        print(f"[DEBUG] Page title: {page_title}")

        await page.wait_for_selector("#js_content", timeout=30_000)

    # Additional wait for lazy-loaded content
    print(f"[WAIT] Waiting for images to load...")
    await asyncio.sleep(3)

    # --- Extract metadata ---
    title = await page.locator("#activity-name").text_content()
    title = title.strip() if title else "Untitled"
    print(f"[INFO] Title: {title}")

    try:
        author = await page.locator("#js_name").text_content()
        author = author.strip() if author else None
    except Exception:
        author = None

    try:
        publish_time = await page.locator("#publish_time").text_content()
        publish_time = publish_time.strip() if publish_time else None
    except Exception:
        publish_time = None

    # --- Fix lazy-loaded images ---
    await page.evaluate(LAZY_IMAGE_JS)

    # Collect image URLs BEFORE converting to Markdown
    img_elements = page.locator("#js_content img")
    img_count = await img_elements.count()
    img_urls = []
    for i in range(img_count):
        try:
            src = await img_elements.nth(i).get_attribute("src")
            if src and src.startswith("http"):
                img_urls.append(src)
        except Exception:
            pass
    print(f"[INFO] Found {len(img_urls)} downloadable images")

    # --- Convert to Markdown ---
    content_html = await page.locator("#js_content").inner_html()
    content_md = md(content_html, heading_style="ATX", bullets="-")

    # Clean excessive whitespace
    lines = content_md.split("\n")
    cleaned_lines = []
    prev_empty = False
    for line in lines:
        line = line.rstrip()
        is_empty = len(line.strip()) == 0
        if is_empty and prev_empty:
            continue
        cleaned_lines.append(line)
        prev_empty = is_empty
    content_md = "\n".join(cleaned_lines).strip()

    return title, author, publish_time, content_md, img_urls


async def fetch_weixin_article(url: str, output_file: str | None = None):
    """Fetch WeChat article with headless-first, retry, anti-detection, and image download."""
    print(f"[FETCH] Fetching WeChat article: {url}")

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        # Headless on all attempts except the last one
        headless = attempt < MAX_RETRIES

        if attempt > 1:
            print(f"\n[RETRY] Attempt {attempt}/{MAX_RETRIES} "
                  f"({'headless' if headless else 'headed'})…")
            await asyncio.sleep(RETRY_DELAY)
        else:
            print(f"[INFO] Launching browser "
                  f"({'headless' if headless else 'headed'})…")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )

                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Linux; Android 12; SM-S906N) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Mobile Safari/537.36"
                    ),
                    viewport={"width": 414, "height": 896},
                    locale="zh-CN",
                )

                page = await context.new_page()

                try:
                    title, author, publish_time, content_md, img_urls = (
                        await _do_fetch(page, url)
                    )

                    # --- Build final Markdown ---
                    markdown_parts = [f"# {title}\n"]

                    if author or publish_time:
                        meta_parts = []
                        if author:
                            meta_parts.append(f"**作者**: {author}")
                        if publish_time:
                            meta_parts.append(f"**发布时间**: {publish_time}")
                        markdown_parts.append(" | ".join(meta_parts) + "\n")

                    markdown_parts.append("---\n")

                    # --- Download images ---
                    if img_urls:
                        # Determine assets directory
                        clean_title = sanitize_dirname(title)
                        date_str = parse_publish_date(publish_time)
                        if date_str:
                            assets_folder = f"{date_str}{clean_title}_assets"
                        else:
                            assets_folder = f"{clean_title}_assets"

                        print(f"[IMG] Downloading {len(img_urls)} images "
                              f"to {assets_folder}/…")
                        mapping = await download_images(
                            page, img_urls, assets_folder
                        )
                        content_md = replace_image_urls(content_md, mapping)

                        local_count = sum(
                            1 for v in mapping.values()
                            if not v.startswith("http")
                        )
                        print(f"[IMG] {local_count}/{len(img_urls)} "
                              f"downloaded locally")

                    markdown_parts.append(content_md)
                    final_markdown = "\n".join(markdown_parts)

                    # --- Determine output filename ---
                    if output_file is None:
                        date_str = parse_publish_date(publish_time)
                        clean_title = sanitize_filename(title)

                        if date_str:
                            output_file = f"{date_str}{clean_title}.md"
                        else:
                            output_file = f"{clean_title}.md"
                        print(
                            f"[INFO] Auto-generated filename: {output_file}"
                        )

                    # If output_file is a directory, auto-name inside it
                    output_path = Path(output_file)
                    if output_path.is_dir() or output_file.endswith(os.sep):
                        date_str = parse_publish_date(publish_time)
                        clean_title = sanitize_filename(title)
                        if date_str:
                            fname = f"{date_str}{clean_title}.md"
                        else:
                            fname = f"{clean_title}.md"
                        output_path = output_path / fname
                    else:
                        output_path = Path(output_file)

                    # Write
                    output_path.write_text(final_markdown, encoding="utf-8")

                    # Stats
                    char_count = len(final_markdown)
                    word_count = len(final_markdown.split())
                    md_image_count = final_markdown.count("![")

                    print(f"✓ Content saved to: {output_path}")
                    print(f"✓ Statistics:")
                    print(f"  • Characters: {char_count:,}")
                    print(f"  • Words: {word_count:,}")
                    print(f"  • Images: {md_image_count}")
                    print(f"\n✓ WeChat article fetched successfully!")

                    return  # success – exit retry loop

                finally:
                    await browser.close()

        except Exception as e:
            last_error = e
            print(f"✗ Attempt {attempt} failed: {e}")

    # All retries exhausted
    print(f"\n✗ All {MAX_RETRIES} attempts failed.")
    print(f"  Last error: {last_error}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_weixin.py <url> [output_filename]")
        print("\nExamples:")
        print("  # Auto-generate filename (YYYYMMDD+Title format)")
        print("  python fetch_weixin.py 'https://mp.weixin.qq.com/s/xxxxx'")
        print("\n  # Custom filename")
        print("  python fetch_weixin.py 'https://mp.weixin.qq.com/s/xxxxx' article.md")
        print("\n  # Output to directory (auto-names inside)")
        print("  python fetch_weixin.py 'https://mp.weixin.qq.com/s/xxxxx' ./articles/")
        sys.exit(1)

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) >= 3 else None

    if "mp.weixin.qq.com" not in url:
        print("⚠ Warning: URL does not appear to be a WeChat article")
        print("  Expected: https://mp.weixin.qq.com/s/...")

    if output_file and not output_file.endswith(".md") and not output_file.endswith(os.sep):
        output_file += ".md"

    asyncio.run(fetch_weixin_article(url, output_file))


if __name__ == "__main__":
    main()