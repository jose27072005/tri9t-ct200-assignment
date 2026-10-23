from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, store
from app.models import Base
from app.parser import parse_text


def test_versioned_selection_generation_and_staleness(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", test_session)
    monkeypatch.setattr(main, "init_db", lambda: Base.metadata.create_all(engine))
    monkeypatch.setattr(store, "STORE", tmp_path / "generated.json")

    def parse_fixture(path, ocr=False):
        version_two = "v2" in Path(path).name
        body = "Deflate within two seconds." if version_two else "Deflate within three seconds."
        source = f"1 Safety\nFollow the safe-use instructions.\n1.1 Pressure limit\n{body}"
        return parse_text(source), source

    monkeypatch.setattr(main, "extract_pdf", parse_fixture)

    def generated(text, node_ids):
        from app.llm import Cases
        records = [{
            "title": f"Pressure limit case {i}",
            "preconditions": ["Monitor is powered on"],
            "steps": ["Trigger the documented pressure condition", "Observe the display and cuff"],
            "expected_result": "The monitor follows the selected pressure limit requirement.",
            "source_node_ids": [node_ids[0]], "risk": "high"
        } for i in range(3)]
        return Cases(cases=records), "test-model", 1, "test-provider"

    monkeypatch.setattr(main.llm, "generate", generated)
    (tmp_path / "ct200_v1.pdf").write_bytes(b"fixture")
    (tmp_path / "ct200_v2.pdf").write_bytes(b"fixture")

    with TestClient(main.app) as client:
        v1 = client.post("/ingest", json={"version": "v1", "path": str(tmp_path / "ct200_v1.pdf")})
        assert v1.status_code == 200
        roots = client.get("/documents/ct-200/nodes?version=v1").json()
        section = roots[0]
        requirement = section["children"][0]
        assert requirement["heading"] == "Pressure limit"

        selection = client.post("/selections", json={
            "name": "Pressure safety", "document_key": "ct-200", "version": "v1",
            "node_ids": [section["id"]]
        })
        assert selection.status_code == 200
        pinned = client.get(f"/selections/{selection.json()['id']}").json()
        assert pinned["version"] == "v1"
        assert "Deflate within three seconds" in pinned["items"][0]["text"]
        generation = client.post("/generations", json={"selection_id": selection.json()["id"]})
        assert generation.status_code == 200
        generation_body = generation.json()
        assert generation_body["stale"] is False
        assert generation_body["provider"] == "test-provider"

        v2 = client.post("/ingest", json={"version": "v2", "path": str(tmp_path / "ct200_v2.pdf")})
        assert v2.status_code == 200
        roots_v2 = client.get("/documents/ct-200/nodes").json()
        assert roots_v2[0]["logical_id"] == section["logical_id"]
        assert roots_v2[0]["changed"] is False
        diff = client.get(f"/nodes/{requirement['id']}/diff").json()
        assert diff["versions"][-1]["changed"] is True
        assert any("three seconds" in line for line in diff["diff"])

        prior = client.get(f"/generations/{generation_body['id']}").json()
        assert prior["stale"] is True
        assert prior["impacted_sources"][0]["heading"] == "Safety"
        assert any(x["heading"] == "Pressure limit" for x in prior["impacted_sources"])
        assert "three seconds" in prior["sources"][0]["text"]
        assert "two seconds" in client.get(f"/nodes/{diff['versions'][-1]['node_id']}").json()["text"]
        by_descendant = client.get(f"/generations?node_id={requirement['id']}").json()
        assert len(by_descendant) == 1
        assert by_descendant[0]["stale"] is True
        pinned_after_v2 = client.get(f"/selections/{selection.json()['id']}").json()
        assert pinned_after_v2["version"] == "v1"
        assert "Deflate within three seconds" in pinned_after_v2["items"][0]["text"]

    engine.dispose()


def test_duplicate_headings_have_distinct_persisted_ids_and_parents(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", test_session)
    monkeypatch.setattr(main, "init_db", lambda: Base.metadata.create_all(engine))
    monkeypatch.setattr(store, "STORE", tmp_path / "generated.json")
    source = "1 Safety\nCaution.\n1.1 Warning\nSafety warning.\n2 Operation\n2.1 Warning\nOperation warning."
    monkeypatch.setattr(main, "extract_pdf", lambda path, ocr=False: (parse_text(source), source))
    pdf = tmp_path / "duplicate-headings.pdf"
    pdf.write_bytes(b"fixture")

    with TestClient(main.app) as client:
        assert client.post("/ingest", json={"document_key":"dupes","version":"v1","path":str(pdf)}).status_code == 200
        roots = client.get("/documents/dupes/nodes?version=v1").json()
        first, second = roots[0]["children"][0], roots[1]["children"][0]
        assert first["heading"] == second["heading"] == "Warning"
        assert first["id"] != second["id"]
        assert first["parent_id"] == roots[0]["id"]
        assert second["parent_id"] == roots[1]["id"]

    engine.dispose()


def test_semantic_sibling_match_preserves_identity_when_heading_is_renamed(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", test_session)
    monkeypatch.setattr(main, "init_db", lambda: Base.metadata.create_all(engine))
    monkeypatch.setattr(store, "STORE", tmp_path / "generated.json")
    pdf_v1 = tmp_path / "manual_v1.pdf"
    pdf_v2 = tmp_path / "manual_v2.pdf"
    pdf_v1.write_bytes(b"fixture")
    pdf_v2.write_bytes(b"fixture")

    def parse_fixture(path, ocr=False):
        if "v2" in Path(path).name:
            source = "1 Safety\n1.1 Maximum cuff pressure\nMaximum cuff pressure is capped at 299 mmHg."
        else:
            source = "1 Safety\n1.1 Cuff pressure limit\nMaximum cuff pressure is 299 mmHg."
        return parse_text(source), source

    monkeypatch.setattr(main, "extract_pdf", parse_fixture)
    with TestClient(main.app) as client:
        assert client.post("/ingest", json={"document_key":"semantic","version":"v1","path":str(pdf_v1)}).status_code == 200
        old = client.get("/documents/semantic/search", params={"q":"Cuff pressure","version":"v1"}).json()[0]
        assert client.post("/ingest", json={"document_key":"semantic","version":"v2","path":str(pdf_v2)}).status_code == 200
        new = client.get("/documents/semantic/search", params={"q":"Maximum cuff pressure","version":"v2"}).json()[0]
        assert new["logical_id"] == old["logical_id"]
        assert new["changed"] is True

    engine.dispose()
