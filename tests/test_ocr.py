import shutil

import pytest

pdfengine = pytest.importorskip("pymupdf")
PIL = pytest.importorskip("PIL")

from PIL import Image, ImageDraw, ImageFont
from app.parser import extract_pdf


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract executable is not installed")
def test_image_only_pdf_requires_opt_in_ocr_and_recovers_heading(tmp_path):
    image = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=72)
    draw.text((80, 80), "1 Safety", fill="black", font=font)
    draw.text((80, 220), "Wear the cuff as instructed.", fill="black", font=font)
    draw.text((80, 380), "1.1 Warning", fill="black", font=font)
    draw.text((80, 520), "Do not overinflate the cuff.", fill="black", font=font)

    image_path = tmp_path / "page.png"
    image.save(image_path)
    pdf_path = tmp_path / "scan.pdf"
    doc = pdfengine.open()
    page = doc.new_page(width=600, height=400)
    page.insert_image(page.rect, filename=str(image_path))
    doc.save(pdf_path)
    doc.close()

    with pytest.raises(ValueError, match="Image-only pages require OCR"):
        extract_pdf(pdf_path)

    tree, extracted = extract_pdf(pdf_path, ocr=True)
    assert tree[0].heading.lower() == "safety"
    assert "overinflate" in extracted.lower()
