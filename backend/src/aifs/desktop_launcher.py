"""Desktop-owned loopback server; stdout contains only one ready JSON record."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import socket
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn


def configure_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(exist_ok=True)
    (data_dir / "basis_set_pool").mkdir(exist_ok=True)
    os.environ["AIFS_WORKFLOW_DB"] = str(data_dir / "aifs-workflow.sqlite3")
    os.environ["AIFS_EVIDENCE_DB"] = str(data_dir / "aifs-evidence.sqlite3")
    os.environ["AIFS_BASIS_SET_POOL"] = str(data_dir / "basis_set_pool")
    # Desktop base package uses FTS5; ambient model configuration must not
    # trigger unbundled downloads or import optional FAISS at startup.
    os.environ["AIFS_EMBEDDING_MODEL"] = ""
    from aifs.config import get_settings

    get_settings.cache_clear()


class DesktopServer(uvicorn.Server):
    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        if self.started and sockets:
            from aifs.api import SERVICE_VERSION

            port = sockets[0].getsockname()[1]
            print(
                json.dumps(
                    {
                        "event": "ready",
                        "service": "aifs-api",
                        "version": SERVICE_VERSION,
                        "baseUrl": f"http://127.0.0.1:{port}",
                    }
                ),
                flush=True,
            )


async def serve(data_dir: Path, parent_stdin: bool = False) -> None:
    configure_data(data_dir)
    # Import only after absolute paths are configured.
    from aifs.api import app

    handler = RotatingFileHandler(
        data_dir / "logs" / "backend.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    server = DesktopServer(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="info"))
    loggers = [
        logging.getLogger(),
        logging.getLogger("uvicorn.error"),
        logging.getLogger("uvicorn.access"),
    ]
    for logger in loggers:
        logger.addHandler(handler)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.set_inheritable(True)
    # A pipe EOF also stops the server if its owning Host disappears.
    if parent_stdin:
        import threading

        def watch_parent() -> None:
            sys.stdin.buffer.read()
            server.should_exit = True

        threading.Thread(target=watch_parent, daemon=True).start()
    try:
        await server.serve(sockets=[sock])
    finally:
        sock.close()
        for logger in loggers:
            logger.removeHandler(handler)
        handler.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--parent-stdin", action="store_true")
    args = parser.parse_args()
    asyncio.run(serve(args.data_dir.resolve(), args.parent_stdin))


if __name__ == "__main__":
    main()
