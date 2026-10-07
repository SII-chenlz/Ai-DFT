#!/usr/bin/env python3
"""Build a native macOS arm64 or Windows x64 backend; no cross compilation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
from aifs import __version__ as VERSION  # noqa: E402


def main():
    machine = platform.machine().lower()
    if sys.platform == "darwin" and machine == "arm64":
        target = "darwin-arm64"
        executable = "aifs-backend/aifs-backend"
    elif sys.platform == "win32" and machine in {"amd64", "x86_64"} and sys.maxsize > 2**32:
        target = "win32-x64"
        executable = "aifs-backend/aifs-backend.exe"
    else:
        raise SystemExit("Native build requires macOS arm64 or Windows x64 Python")
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Native build requires Python 3.11")
    destination = ROOT / "build" / "desktop-runtimes" / target
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "aifs-backend",
        "--paths",
        str(ROOT / "backend" / "src"),
        "--distpath",
        str(destination),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build"),
        "--collect-submodules",
        "aifs",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.asyncio",
        "--hidden-import",
        "uvicorn.protocols.http.h11_impl",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--exclude-module",
        "faiss",
        "--exclude-module",
        "numpy",
        "--exclude-module",
        "torch",
        "--exclude-module",
        "sentence_transformers",
        str(ROOT / "packaging" / "desktop_entry.py"),
    ]
    subprocess.run(
        command,
        check=True,
        cwd=ROOT,
        env={
            **os.environ,
            "PYINSTALLER_CONFIG_DIR": str(ROOT / ".local" / "pyinstaller-cache"),
        },
    )
    files = []
    for path in sorted((destination / "aifs-backend").rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(destination).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    manifest = {
        "version": VERSION,
        "target": target,
        "executable": executable,
        "python": platform.python_version(),
        "files": files,
    }
    (destination / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Runtime built: {destination}")


if __name__ == "__main__":
    main()
