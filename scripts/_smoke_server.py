"""Start the backend on a free port, check /api/health, the dashboard and one SSE turn, then stop it.
Used by scripts/reproduce.py (clean-copy replay)."""
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
                             "--port", str(port)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(180):
            try:
                health = json.loads(urllib.request.urlopen(f"{base}/api/health", timeout=2).read())
                break
            except Exception:
                time.sleep(1)
        else:
            raise SystemExit("backend did not start within 180 s")
        page = urllib.request.urlopen(f"{base}/", timeout=10).read().decode()
        assert "Streaming Live RAG" in page, "dashboard not served"
        sid = json.loads(urllib.request.urlopen(urllib.request.Request(f"{base}/api/sessions", method="POST")).read())["session_id"]
        body = json.dumps({"chunks": [{"t": 0, "text": "How many sick days"}, {"t": 0.6, "text": "do we get?"}],
                           "end_t": 1.0, "speed": 5}).encode()
        req = urllib.request.Request(f"{base}/api/sessions/{sid}/turns", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        events = [json.loads(l[6:]) for l in urllib.request.urlopen(req, timeout=120).read().decode().splitlines()
                  if l.startswith("data: ")]
        assert events[-1]["type"] == "TURN_SUMMARY", "SSE turn incomplete"
        print(f"ok: health {health['status']}, {health['index']['num_chunks']} chunks, reranker {health['reranker']}, "
              f"dashboard served, SSE turn with {len(events)} events")
    finally:
        proc.terminate()
        proc.wait(timeout=30)


if __name__ == "__main__":
    main()
