#!/usr/bin/env python3
"""Smoke the extracted native artifact: readiness, cards, restart and pipe EOF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(address, path, body=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        address + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        raw = response.read()
        return (
            json.loads(raw)
            if "json" in response.headers.get("Content-Type", "")
            else raw
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    runtime = json.loads((executable.parents[1] / "runtime.json").read_text())
    with tempfile.TemporaryDirectory(
        prefix="AIFS frozen path with spaces "
    ) as temporary:
        data = Path(temporary) / "saved data"
        processes = []
        stderr_path = Path(temporary) / "stderr.log"
        stderr = stderr_path.open("wb")

        def start():
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("AIFS_", "PYTHON"))
            }
            if os.name != "nt":
                env["PATH"] = "/usr/bin:/bin"
            process = subprocess.Popen(
                [str(executable), "--data-dir", str(data), "--parent-stdin"],
                cwd=temporary,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                env=env,
            )
            processes.append(process)
            # Windows selectors cannot wait on anonymous subprocess pipes.
            lines = queue.Queue()
            threading.Thread(
                target=lambda: lines.put(process.stdout.readline()), daemon=True
            ).start()
            try:
                raw = lines.get(timeout=20)
            except queue.Empty as error:
                raise AssertionError("Frozen backend timed out") from error
            if not raw:
                raise AssertionError(stderr_path.read_text())
            ready = json.loads(raw)
            assert ready["event"] == "ready" and ready["version"] == runtime["version"], ready
            address = ready["baseUrl"]
            assert address.startswith("http://127.0.0.1:")
            assert request(address, "/health")["status"] == "ok"
            return process, address

        try:
            first, address = start()
            task = {
                "task_id": "h2",
                "title": "H2 electronic energy",
                "purpose": "Obtain energy",
                "kind": "rest",
                "job_type": "energy",
                "system_name": "H2",
                "inputs": {
                    "position": "H 0 0 0\nH 0 0 0.74",
                    "position_source": "user",
                    "position_unit": "angstrom",
                    "charge": 0,
                    "charge_source": "user",
                    "spin": 1,
                    "spin_source": "user",
                },
                "decision": {
                    "xc": "PBE",
                    "source": "user",
                    "rationale": "User selected PBE",
                },
            }
            plan = {
                "question": "H2 single point energy",
                "goal": "other",
                "tasks": [task],
            }
            created = request(address, "/v1/plans", plan)
            plan_id = created["plan_id"]
            card = request(
                address, f"/v1/plans/{plan_id}/tasks/h2/cards", method="POST"
            )
            assert card["validation"]["valid"]
            assert card["request"]["position_unit"] == "angstrom"
            assert 'unit = "angstrom"' in card["content"]
            assert request(address, card["download_path"]).decode() == card["content"]
            assert request(
                address, "/v1/rest-inputs/validate", {"rest_input": card["content"]}
            )["valid"]
            revision = request(
                address,
                f"/v1/plans/{plan_id}",
                {
                    "expected_version": 1,
                    "change_reason": "Update question",
                    "plan": {**plan, "question": "Updated H2 request"},
                },
                "PUT",
            )
            assert revision["version"] == 2
            first.stdin.close()
            first.wait(timeout=10)
            assert first.returncode == 0
            second, reopened_address = start()
            assert request(reopened_address, f"/v1/plans/{plan_id}")["version"] == 2
            historical = request(
                reopened_address, f"/v1/plans/{plan_id}/cards/{card['card_id']}"
            )
            assert (
                historical["version"] == 1 and not historical["is_current_plan_version"]
            )
            assert historical["download_url"].startswith(reopened_address)
            with urllib.request.urlopen(
                historical["download_url"], timeout=10
            ) as downloaded:
                assert downloaded.read().decode() == card["content"]
            second.stdin.close()
            second.wait(timeout=10)
            assert second.returncode == 0
            report = {
                "native_backend": "passed",
                "aifs_version": runtime["version"],
                "platform": runtime["target"],
                "executable_sha256": hashlib.sha256(
                    executable.read_bytes()
                ).hexdigest(),
                "first_address": address,
                "reopened_address": reopened_address,
                "checks": [
                    "frozen-no-python-path",
                    "path-with-spaces",
                    "dynamic-loopback-port",
                    "health",
                    "plan-and-card",
                    "independent-validation",
                    "download-body",
                    "revision",
                    "restart-persistence",
                    "historical-card",
                    "fresh-download-url",
                    "parent-pipe-eof-cleanup",
                ],
                "desktop_ui": "not tested",
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            stderr.close()


if __name__ == "__main__":
    main()
