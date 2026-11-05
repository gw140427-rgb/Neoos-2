"""NeoOS rebuild MCP server with persistent SQLite task storage."""
from __future__ import annotations

import hmac
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from neoos_store import (
    VALID_STATUSES,
    add_task as store_add_task,
    get_database_path,
    list_tasks as store_list_tasks,
    read_journal as store_read_journal,
    task_count,
    update_task_status as store_update_task_status,
)

mcp = FastMCP(
    "neoos-rebuild",
    host=os.environ.get("HOST", "127.0.0.1"),
    port=int(os.environ.get("PORT", "8000")),
)


@mcp.tool()
def neoos_status() -> dict[str, Any]:
    """Return runtime and persistent storage status."""
    return {
        "project": "NeoOS Rebuild",
        "status": "starter",
        "database_backend": "sqlite",
        "database_path": str(get_database_path().resolve()),
        "task_count": task_count(),
        "worker_mode": "report-only; no command execution",
    }


@mcp.tool()
def list_tasks(status: str = "") -> list[dict[str, Any]]:
    """List tasks, optionally filtered by a valid status."""
    return store_list_tasks(status)


@mcp.tool()
def add_task(title: str, details: str = "") -> dict[str, Any]:
    """Add a task to the persistent queue; this does not execute the task."""
    return store_add_task(title, details)


@mcp.tool()
def update_task_status(task_id: str, status: str) -> dict[str, Any]:
    """Update a task status; allowed values are queued, in_progress, blocked, or done."""
    task = store_update_task_status(task_id, status)
    if task is None:
        raise ValueError(f"task not found: {task_id}")
    return task


@mcp.tool()
def read_journal(limit: int = 20) -> list[dict[str, Any]]:
    """Read recent journal entries. Limit is clamped to 1–100."""
    return store_read_journal(limit)


class BearerTokenMiddleware:
    """Require a shared bearer token for all HTTP MCP requests."""
    def __init__(self, app: Any, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            authorization = headers.get(b"authorization", b"").decode("latin-1")
            scheme, separator, supplied = authorization.partition(" ")
            if not separator or scheme.lower() != "bearer" or not hmac.compare_digest(supplied.strip(), self.token):
                body = b'{"error":"unauthorized"}'
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    transport = os.environ.get("NEOOS_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "streamable-http":
        token = os.environ.get("NEOOS_MCP_TOKEN", "").strip()
        if len(token) < 32:
            raise SystemExit("Set NEOOS_MCP_TOKEN to a secret of at least 32 characters for HTTP mode")
        import uvicorn

        app = BearerTokenMiddleware(mcp.streamable_http_app(), token)
        uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")))
    elif transport == "stdio":
        mcp.run(transport="stdio")
    else:
        raise SystemExit("NEOOS_MCP_TRANSPORT must be 'stdio' or 'streamable-http'")
