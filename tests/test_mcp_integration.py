"""End-to-end MCP protocol test using an isolated temporary data directory."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_lifecycle_over_stdio_mcp(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            root = Path(__file__).resolve().parents[1]
            server = StdioServerParameters(
                command=sys.executable,
                args=[str(root / "neoos_mcp.py")],
                env=dict(os.environ, NEOOS_DATA_DIR=str(data_dir)),
            )

            async with stdio_client(server) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    created = await session.call_tool(
                        "add_task",
                        {"title": "Integration task", "details": "created over MCP"},
                    )
                    self.assertFalse(created.isError, str(created))
                    tasks_file = data_dir / "tasks.json"
                    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
                    self.assertEqual(len(tasks), 1)
                    task_id = tasks[0]["id"]
                    self.assertEqual(tasks[0]["title"], "Integration task")

                    updated = await session.call_tool(
                        "update_task_status",
                        {"task_id": task_id, "status": "done"},
                    )
                    self.assertFalse(updated.isError, str(updated))
                    tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
                    self.assertEqual(tasks[0]["status"], "done")

                    listed = await session.call_tool("list_tasks", {"status": "done"})
                    self.assertFalse(listed.isError, str(listed))
                    self.assertTrue((data_dir / "journal.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
