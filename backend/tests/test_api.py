import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def sse(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_health_and_ui(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["index"]["num_chunks"] > 0
    assert "Streaming Live RAG" in client.get("/").text


def test_turn_streams_events_over_sse(client):
    sid = client.post("/api/sessions").json()["session_id"]
    body = {"chunks": [{"t": 0, "text": "How many sick days"}, {"t": 0.6, "text": "do we get per year?"}],
            "end_t": 1.0, "speed": 10}
    r = client.post(f"/api/sessions/{sid}/turns", json=body)
    assert r.headers["content-type"].startswith("text/event-stream")
    events = sse(r)
    assert events[0]["type"] == "TURN_STARTED" and events[-1]["type"] == "TURN_SUMMARY"
    final = next(e for e in events if e["type"] == "FINAL_RESPONSE")
    assert any(c["document_id"] == "DOC_11" for c in final["citations"])
    tel = client.get(f"/api/sessions/{sid}/telemetry").text.strip().splitlines()
    assert len(tel) == len(events)
    state = client.get(f"/api/sessions/{sid}").json()
    assert state["versions"][0]["version"] == 1
    assert client.get(f"/api/chunks/{final['citations'][0]['chunk_id']}").json()["document_id"] == "DOC_11"
    assert client.delete(f"/api/sessions/{sid}").json()["ended"]
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_baseline_selectable_and_validation(client):
    sid = client.post("/api/sessions").json()["session_id"]
    r = client.post(f"/api/sessions/{sid}/turns", json={"chunks": [{"t": 0, "text": "sick leave"}],
                                                         "speed": 10, "system": "baseline"})
    assert any(e["type"] == "FINAL_RESPONSE" for e in sse(r))
    assert client.post(f"/api/sessions/{sid}/turns", json={"chunks": []}).status_code == 422
    assert client.post("/api/sessions/nope/turns", json={"chunks": [{"t": 0, "text": "x"}]}).status_code == 404
