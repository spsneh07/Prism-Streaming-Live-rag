"""G1 (reproducibility) gate, shared by benchmark.py and report.py.

report.py recomputes G1 from the current results/reproducibility.json, so a later
reproduce.py run (e.g. once Docker is available) is reflected without re-running
the held-out benchmark.
"""

TARGET = "container launches with one command on a clean machine; replay completes unattended"


def g1_gate(repro):
    if repro is None:
        return {"gate": "G1", "name": "Reproducibility", "metric": "clean-copy replay + container launch",
                "measured": "not run", "target": TARGET, "status": "NOT RUN", "method": "scripts/reproduce.py"}
    local, docker = repro.get("local_replay"), repro.get("docker")
    if local == "PASS" and docker == "PASS":
        status = "PASS"
    elif local == "FAIL" or docker == "FAIL":
        status = "FAIL"
    else:
        status = "NOT VERIFIED"
    return {"gate": "G1", "name": "Reproducibility", "metric": "clean-copy replay (local) / container launch",
            "measured": f"local replay: {local}; docker: {docker}", "target": TARGET, "status": status,
            "method": "scripts/reproduce.py copies the repo without derived files into an empty directory and runs "
                      "ingest -> index -> calibration -> tests -> quick benchmark -> all demos -> backend smoke test; "
                      "then docker compose build, up, health/page check and pytest inside the container (static "
                      "Dockerfile checks only when the docker CLI is unavailable)"}
