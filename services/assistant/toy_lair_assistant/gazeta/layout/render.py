"""HTML to A4 PDF with Playwright Chromium, with overflow trimming and a page cap."""

from __future__ import annotations

import io
import time
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
    ("Bodoni Moda", "normal", 700, "bodoni-moda-latin-700-normal.woff2"),
    ("Bodoni Moda", "normal", 900, "bodoni-moda-latin-900-normal.woff2"),
    ("Bodoni Moda", "italic", 400, "bodoni-moda-latin-400-italic.woff2"),
]
OVERFLOW_JS = """() => {
  const f = document.querySelector('#front');
  const cols = f.querySelector('.front');
  const room = cols.clientHeight;
  const used = (el) => el.lastElementChild ? el.lastElementChild.getBoundingClientRect().bottom - el.getBoundingClientRect().top : 0;
  const p = document.querySelector('#puzzles');
  return {
    front: f.scrollHeight - f.clientHeight,
    lead: used(cols.querySelector('.lead')) - room,
    side: used(cols.querySelector('.side')) - room,
    puzzles: p ? p.scrollHeight - p.clientHeight : 0,
  };
}"""

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


def render(view: dict, max_pages: int = 6, attempts: int = 4) -> tuple[bytes, dict]:
    """Chromium sometimes dies on a heavy page, so a crashed driver gets a fresh start."""
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return _render_once(view, max_pages)
        except Exception as exc:
            if "playwright" not in type(exc).__module__ and "Connection closed" not in str(exc) and "Target" not in str(exc):
                raise
            last = exc
            time.sleep(1.5)
    raise last  # type: ignore[misc]


def _render_once(view: dict, max_pages: int = 6) -> tuple[bytes, dict]:
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
                if over["lead"] > 1 or over["side"] > 1 or over["front"] > 1:
                    if over["lead"] > 1:
                        step = V.shrink_lead(view)
                    elif over["side"] > 1:
                        step = V.shrink_side(view)
                    else:
                        step = False
                    step = step or V.shrink_front(view)
                    if step:
                        info["trims"].append("front")
                        continue
                if over["puzzles"] > 1:
                    if V.shrink_puzzles(view):
                        info["trims"].append("puzzles")
                        continue
                if page_count(pdf) > max_pages:
                    if V.cap_flow(view):
                        info["trims"].append("flow")
                        continue
                break
            # second pass: fill page numbers for teasers and the puzzles page
            texts = page_texts(pdf)
            body_pages = texts[1:-1] if view.get("puzzles") else texts[1:]
            for t in view["teasers"]:
                key = V.norm(t["headline"])[:24]
                for i, text in enumerate(body_pages, start=2):
                    if key and key in text:
                        t["page"] = i
                        break
            view["teasers"] = [t for t in view["teasers"] if t["page"]]
            if view.get("puzzles"):
                view["puzzles_page"] = page_count(pdf)
            pdf, _ = _print(page, view)
        finally:
            browser.close()
    info["pages"] = page_count(pdf)
    return pdf, info
