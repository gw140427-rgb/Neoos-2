# NeoOS Rebuild Operations Guide

This guide applies to the current NeoOS Rebuild starter in this repository. It is not a guide for restoring an older, deleted NeoOS implementation.

## Data location

The MCP server stores task state in:

- `tasks.json`: task records.
- `journal.jsonl`: append-only event records.

By default, these files live in the `data/` directory relative to the process working directory. Set `NEOOS_DATA_DIR` to use another directory. The worker and MCP server must use the same value to read the same data.

Do not store passwords, API keys, or private personal information in task titles, task details, or journal entries.

## Run checks

Use Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
# Activate the environment for your shell, then:
python -m pip install -r requirements.txt
python -m compileall -q neoos_mcp.py worker.py tests
python -m unittest discover -s tests -v
```

The CI workflow performs the same compile and test steps, then runs the report-only worker.

## Backup task data

1. Stop the MCP server and worker before making a filesystem copy, so no process is writing to the files.
2. Identify the actual data directory. If `NEOOS_DATA_DIR` is unset, resolve `data/` relative to the directory from which the server is launched.
3. Copy the whole directory to a separate backup location. For example:

```bash
cp -a data data-backup
```

Use a different destination name for each backup if you need to retain older snapshots. Keep backups private because task details and journal entries may contain user-provided text.

## Restore task data

1. Stop the MCP server and worker.
2. Make a separate copy of the current data directory before changing anything.
3. Confirm that the backup contains the expected `tasks.json` and `journal.jsonl` files.
4. Restore the backup into the configured data directory only after confirming the destination path. Do not merge unrelated task files from different snapshots.
5. Start the server and inspect `neoos_status`, `list_tasks`, and `read_journal` before continuing normal work.

The commands above are examples for a local checkout. They have not been run against a user's machine or any production data.

## Security notes

- The worker is report-only. It does not interpret task descriptions as shell commands.
- HTTP MCP mode requires `NEOOS_MCP_TOKEN` to be set to a secret of at least 32 characters. Never commit the token or paste it into task data.
- The HTTP middleware rejects missing, malformed, and incorrect bearer credentials. Keep HTTP mode behind a trusted network or authenticated reverse proxy; bearer authentication alone does not provide TLS.
- The GitHub Actions workflow uses read-only repository contents permission. It runs tests and the report-only worker; it does not deploy services or access deployment secrets.

## Troubleshooting

- **Task file missing:** verify the working directory and `NEOOS_DATA_DIR`. A missing task file is treated as an empty queue.
- **Task file is invalid JSON or not a JSON array:** the MCP server now raises a clear data error rather than silently replacing the file. Back up the file before attempting manual repair.
- **Journal contains a malformed line:** valid neighboring JSONL records remain readable; malformed lines are skipped.
- **Tests fail:** run the exact unittest command above and inspect the first failing assertion. Do not merge a change just because compilation succeeds.
- **Worker says report-only:** this is expected. The worker deliberately does not execute queued tasks.
