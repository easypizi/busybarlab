import pytest

from toy_lair_assistant.gazeta.layout import render, sample
from toy_lair_assistant.gazeta.layout import view as V


def test_first_render_is_not_trimmed_and_steps_cut_whole_sentences():
    v = sample.sample_view(1, 6)
    full = sum(len(p.split()) for p in v["lead"]["body"])
    V.apply_body_limit(v)
    assert sum(len(p.split()) for p in v["lead"]["body"]) == full
    assert V.shrink_front(v)
    body = v["lead"]["body"]
    assert 0 < sum(len(p.split()) for p in body) <= V.BODY_LIMITS[1]
    assert all(p.rstrip().endswith((".", "?", "!")) and "…" not in p for p in body)


def test_shrink_front_runs_out():
    v = sample.sample_view(1, 1)
    for _ in range(30):
        if not V.shrink_front(v):
            break
    else:
        pytest.fail("shrink_front never finished")
    assert v["lead"]["graphic"]["kind"] != "illustration"


def test_shrink_day_order():
    v = sample.sample_view(1, 1)
    assert len(v["day"]["tasks"]) == 5
    V.shrink_day(v)
    V.shrink_day(v)
    assert len(v["day"]["tasks"]) == 3
    V.shrink_day(v)
    assert v["day"]["idea"]["text"].split().__len__() <= 23
    while V.shrink_day(v):
        pass
    assert v["day"]["tasks"] == [] and v["day"]["idea"] is None


def test_cap_flow_drops_from_longest():
    v = sample.sample_view(3, 1)
    v["sections"][0]["stories"] += v["sections"][0]["stories"]
    before = len(v["sections"][0]["stories"])
    V.cap_flow(v)
    assert len(v["sections"][0]["stories"]) < before


def test_html_has_no_unfilled_placeholders():
    html = render.render_html(sample.sample_view())
    assert "{{" not in html and "{%" not in html
    assert "IVANencial Times" in html and "Bay Area Incidents" in html


def test_missing_lead_and_graphic_do_not_break_template():
    v = sample.sample_view()
    v["lead"] = None
    v["f1"] = None
    v["launches"] = []
    html = render.render_html(v)
    assert "Threat desk" in html


@pytest.fixture(scope="module")
def chromium():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch(args=["--no-sandbox"]).close()
    except Exception:
        pytest.skip("Playwright Chromium is not installed")


def test_render_pdf_within_cap_and_page_numbers(chromium):
    v = sample.sample_view(12, 6)
    pdf, info = render.render(v, max_pages=5)
    assert pdf.startswith(b"%PDF")
    assert 3 <= info["pages"] <= 5
    assert any(t["page"] for t in v["teasers"])


def test_render_overflow_trims_front(chromium):
    v = sample.sample_view(1, 1)
    v["lead"]["body"] = [sample.LOREM * 6 for _ in range(6)]
    v["lead"]["headline"] = "A very long headline " * 6
    pdf, info = render.render(v, max_pages=6)
    assert info["pages"] >= 3
    from pypdf import PdfReader
    import io

    assert len(PdfReader(io.BytesIO(pdf)).pages[0].extract_text()) > 200
