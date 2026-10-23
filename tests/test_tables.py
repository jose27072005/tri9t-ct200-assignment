import pytest

pymupdf = pytest.importorskip("pymupdf")

from app.parser import extract_tables


def test_grid_table_is_extracted_with_page_and_heading_context(tmp_path):
    path = tmp_path / "table.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=320, height=240)
    page.insert_text((30, 35), "1 Safety", fontname="hebo", fontsize=14)
    xs = [30, 160, 290]
    ys = [60, 95, 130, 165, 200]
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]), color=(0, 0, 0), width=0.7)
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y), color=(0, 0, 0), width=0.7)
    values = [
        ("Code", "Meaning"),
        ("E1", "Loose cuff"),
        ("E2", "Movement"),
        ("E3", "Overpressure"),
    ]
    for row, cells in enumerate(values):
        for col, value in enumerate(cells):
            page.insert_text((xs[col] + 5, ys[row] + 22), value, fontsize=9)
    doc.save(path)
    doc.close()

    tables = extract_tables(path)

    assert len(tables) == 1
    assert tables[0]["page_number"] == 1
    assert tables[0]["heading_context"] == "Safety"
    assert tables[0]["rows"][0] == ["Code", "Meaning"]
    assert tables[0]["rows"][-1] == ["E3", "Overpressure"]
