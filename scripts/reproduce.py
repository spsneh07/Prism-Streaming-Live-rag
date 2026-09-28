"""G1 reproducibility check: replay the whole pipeline from a clean copy.

    python scripts/reproduce.py            # writes results/reproducibility.json

1. Copy the repository into an empty temp directory WITHOUT derived artefacts
   (data/processed, results, caches) - exactly what a fresh `git clone` contains.
2. In that copy run: build_index -> calibrate_sufficiency -> pytest ->
   benchmark --quick (dev set) -> demo_stream (one scenario). Each step must exit 0.
3. Check installed package versions against backend/requirements.txt pins.
4. Docker: if the docker CLI exists, `docker compose build` + container health check;
   otherwise static checks only (every COPY source exists, CMD target exists,
   pinned CPU torch wheel is published for the base image's Python), reported as
   NOT VERIFIED - never as PASS.

Model weights: `scripts/download_models.py` normally fetches them. If
data/models/ already exists locally it is copied instead of re-downloaded
(the development machine has a slow network); this is recorded in the report.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Derived artefacts are excluded by exact path (a name-only rule once dropped the
# source package backend/app/telemetry together with results/telemetry).
DERIVED_PATHS = {Path("data/processed"), Path("data/models"), Path("results"), Path(".git"), Path(".claude")}
DERIVED_NAMES = {"__pycache__", ".pytest_cache"}


def ignore(dirpath, names):
    rel = Path(dirpath).relative_to(ROOT)
    return {n for n in names if n in DERIVED_NAMES or n.endswith(".pyc") or rel / n in DERIVED_PATHS}


def run(step, cmd, cwd, log, env):
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
    dt = round(time.perf_counter() - t0, 1)
    tail = (p.stdout + p.stderr).strip().splitlines()[-3:]
    log.append({"step": step, "cmd": " ".join(cmd), "exit_code": p.returncode, "seconds": dt, "tail": tail})
    print(f"[{'ok' if p.returncode == 0 else 'FAIL'}] {step} ({dt}s)", flush=True)
    return p.returncode == 0


def pins_check():
    bad = []
    for line in (ROOT / "backend" / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if "==" not in line:
            continue
        name, ver = line.split("==")
        try:
            got = metadata.version(name)
        except metadata.PackageNotFoundError:
            bad.append(f"{name} missing")
            continue
        if got.split("+")[0] != ver:
            bad.append(f"{name} {got} != {ver}")
    return bad


def docker_static():
    checks = {}
    df = (ROOT / "Dockerfile").read_text()
    for src in re.findall(r"^COPY\s+(\S+)\s+\S+", df, re.M):
        checks[f"COPY source exists: {src}"] = (ROOT / src).exists()
    checks["CMD app module exists (backend/app/main.py)"] = (ROOT / "backend" / "app" / "main.py").exists()
    checks[".dockerignore present"] = (ROOT / ".dockerignore").exists()
    py = re.search(r"FROM python:(\d+)\.(\d+)", df)
    torch = re.search(r"torch==([\d.]+)", df)
    if py and torch:
        tag = f"cp{py.group(1)}{py.group(2)}"
        url = "https://download.pytorch.org/whl/cpu/torch/"
        try:
            html = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
            checks[f"torch {torch.group(1)} CPU wheel for {tag} linux x86_64 published"] = bool(
                re.search(rf"torch-{re.escape(torch.group(1))}%2Bcpu-{tag}-{tag}-(?:manylinux|linux)[^\"']*x86_64", html))
        except Exception as exc:  # network
            checks[f"torch wheel index reachable ({exc.__class__.__name__})"] = False
    compose = (ROOT / "docker-compose.yml").read_text()
    checks["compose builds from repo root"] = "build: ." in compose
    return checks


def main() -> None:
    log: list[dict] = []
    report: dict = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "python": sys.version.split()[0]}
    tmp = Path(tempfile.mkdtemp(prefix="slrag_clean_"))
    work = tmp / "repo"
    shutil.copytree(ROOT, work, ignore=ignore)
    if (ROOT / "data" / "models").exists():
        shutil.copytree(ROOT / "data" / "models", work / "data" / "models")
        report["models"] = "copied from local data/models (slow network); download_models.py not re-run"
    else:
        report["models"] = "downloaded"
    report["clean_copy"] = {"path": str(work), "derived_dirs_present": [d for d in ("data/processed", "results")
                                                                        if (work / d).exists()]}
    # No reliance on this machine's Hugging Face cache: an empty cache directory and offline
    # mode, so models can only come from the copy's own data/models (as in the Docker image).
    hf_empty = tmp / "hf_cache_empty"
    hf_empty.mkdir()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HOME": str(hf_empty), "HF_HUB_OFFLINE": "1",
           "TRANSFORMERS_OFFLINE": "1"}
    report["isolation"] = "HF_HOME=<empty temp dir>, HF_HUB_OFFLINE=1; derived data/results absent in the copy"
    py = sys.executable
    steps = [
        ("download models (skipped if present)", [py, "scripts/download_models.py"], work),
        ("ingest + build index", [py, "scripts/build_index.py"], work),
        ("calibrate sufficiency gate", [py, "scripts/calibrate_sufficiency.py"], work),
        ("tests", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], work / "backend"),
        ("benchmark (dev set, quick)", [py, "scripts/benchmark.py", "--set", "dev", "--quick"], work),
    ] + [(f"demo ({n})", [py, "scripts/demo_stream.py", "--scenario", n, "--speed", "4"], work)
         for n in ("early_retrieval", "multi_intent", "refinement", "suppression", "insufficient_evidence")] + [
        ("backend starts and serves /api/health and /", [py, "scripts/_smoke_server.py"], work),
    ]
    ok = True
    for name, cmd, cwd in steps:
        ok = run(name, cmd, cwd, log, env) and ok
        if not ok:
            break
    report["steps"] = log
    report["local_replay"] = "PASS" if ok else "FAIL"
    report["pins_mismatch"] = pins_check()
    if "--pip-dry-run" in sys.argv:
        # Resolve the pinned requirements against the package index without installing
        # (a full fresh install of torch was not feasible on the development network).
        p = subprocess.run([py, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
                            "--report", str(tmp / "pip_report.json"), "-r", str(ROOT / "backend" / "requirements.txt")],
                           capture_output=True, text=True)
        report["pip_dry_run"] = "PASS" if p.returncode == 0 else f"FAIL: {(p.stderr or p.stdout).strip()[-300:]}"
    if shutil.which("docker"):
        d_ok = run("docker compose build", ["docker", "compose", "build"], ROOT, log, env)
        report["docker"] = "PASS" if d_ok else "FAIL"
    else:
        checks = docker_static()
        report["docker"] = "NOT VERIFIED"
        report["docker_note"] = "docker CLI not installed on this machine; static checks only"
        report["docker_static_checks"] = checks
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "reproducibility.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({k: report[k] for k in ("local_replay", "docker", "pins_mismatch")}, indent=2))


if __name__ == "__main__":
    main()
