"""Desktop must not report ready before it can open the workflow store."""

import asyncio

import pytest
import uvicorn

from aifs.desktop_launcher import DesktopServer, configure_data
from aifs.workflow_store import WorkflowError, WorkflowStore


def test_future_database_blocks_ready_event(tmp_path, capsys):
    configure_data(tmp_path)
    path = tmp_path / "aifs-workflow.sqlite3"
    store = WorkflowStore(path)
    store.connection.execute("PRAGMA user_version=99")
    store.close()
    server = DesktopServer(uvicorn.Config("aifs.api:app"))
    server.config.load()
    server.lifespan = server.config.lifespan_class(server.config)

    async def start():
        try:
            await server.startup(sockets=[])
        finally:
            if server.started:
                await server.shutdown(sockets=[])

    with pytest.raises(WorkflowError, match="newer"):
        asyncio.run(start())
    assert '"event": "ready"' not in capsys.readouterr().out
