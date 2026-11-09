"""HTML to A4 PDF with Playwright Chromium, with overflow trimming and a page cap."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import view as V

HERE = Path(__file__).parent
FONT_DIR = HERE / "fonts"
FONTS = [
    ("Playfair Display", "normal", 700, "playfair-display-latin-700-normal.woff2"),
    ("Playfair Display", "normal", 900, "playfair-display-latin-900-normal.woff2"),
    ("Playfair Display", "italic", 700, "playfair-display-latin-700-italic.woff2"),
    ("Literata", "normal", 400, "literata-latin-400-normal.woff2"),
    ("Literata", "italic", 400, "literata-latin-400-italic.woff2"),
    ("Literata", "normal", 600, "literata-latin-600-normal.woff2"),
    ("Unbounded", "normal", 400, "unbounded-latin-400-normal.woff2"),
    ("Unbounded", "normal", 700, "unbounded-latin-700-normal.woff2"),
    ("Unbounded", "normal", 900, "unbounded-latin-900-normal.woff2"),
    ("Neucha", "normal", 400, "neucha-latin-400-normal.woff2"),
]
OVERFLOW_JS = """() => ({
  front: document.querySelector('#front').scrollHeight - document.querySelector('#front').clientHeight,
  day: document.querySelector('#day').scrollHeight - document.querySelector('#day').clientHeight,
  sideFront: (() => { const f = document.querySelector('#front .front'); return f.scrollHeight - f.clientHeight; })(),
})"""

_env = Environment(loader=FileSystemLoader(HERE), autoescape=select_autoescape(["html"]))


def render_html(view: dict) -> str:
    fonts = [{"family": f, "style": s, "weight": w, "url": (FONT_DIR / name).as_uri()} for f, s, w, name in FONTS]
    return _env.get_template("paper.html").render(v=view, fonts=fonts)


def page_count(pdf: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(pdf)).pages)


def page_texts(pdf: bytes) -> list[str]:
    from pypdf import PdfReader

    return [V.norm(p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages]


def _print(page: Any, view: dict) -> tuple[bytes, dict]:
    html_path = HERE / "_issue.html"
    html_path.write_text(render_html(view), encoding="utf-8")
    page.goto(html_path.as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(150)
    over = page.evaluate(OVERFLOW_JS)
    pdf = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
    return pdf, over


def render(view: dict, max_pages: int = 6) -> tuple[bytes, dict]:
    """Returns (pdf, info). View is trimmed in place. Info has pages and trims."""
    from playwright.sync_api import sync_playwright

    info: dict = {"trims": [], "pages": 0}
    V.apply_body_limit(view)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            for _ in range(80):
                pdf, over = _print(page, view)
                if over["front"] > 1 or over["sideFront"] > 1:
                    if V.shrink_front(view):
                        info["trims"].append("front")
                        continue
                if over["day"] > 1:
                    if V.shrink_day(view):
                        info["trims"].append("day")
                        continue
                if page_count(pdf) > max_pages:
                    if V.cap_flow(view):
                        info["trims"].append("flow")
                        continue
                break
            # second pass: fill page numbers for teasers
            texts = page_texts(pdf)
            for t in view["teasers"]:
                key = V.norm(t["headline"])[:24]
                for i, text in enumerate(texts[2:], start=3):
                    if key and key in text:
                        t["page"] = i
                        break
            before = len(view["teasers"])
            view["teasers"] = [t for t in view["teasers"] if t["page"]]
            if any(t["page"] for t in view["teasers"]) or len(view["teasers"]) != before:
                pdf, _ = _print(page, view)
        finally:
            browser.close()
    info["pages"] = page_count(pdf)
    return pdf, info
