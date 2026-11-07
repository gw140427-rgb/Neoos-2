# NeoOS-2 on AWS EC2

Deployment notes for the SQLite-backed NeoOS-2 MCP service.

## AWS instance verified 2026-11-05

- Region: `ap-southeast-2` (Sydney)
- EC2 instance: `i-0c4a3985afb8d417b` (name: `neoos`)
- Instance type: `t3.micro`
- State at latest check: `running`
- Public IPv4 at latest check: assigned; do not expose the app port publicly
- Attached EBS volume: `vol-0b12f0b6e385fea15`, 8 GiB gp3
- EBS encryption: disabled
- Instance profile: `NeoOS-EC2-SSM-Role`
- Managed policy: `AmazonSSMManagedInstanceCore`
- SSM managed-node status: `Online`
- Security group SSH ingress is restricted to one IPv4 address; no app ingress rule is required for the loopback-only service.
- No S3 buckets or RDS instances were found in the regions accessible to the connected AWS role. AWS Organizations policies restricted inventory in other regions.

## Persistent data

Tasks and journal entries use Python's built-in SQLite driver. The EC2 service uses:

```sh
NEOOS_DB_PATH=/var/lib/neoos/neoos.sqlite3
```

This path is on the instance's persistent EBS root volume. SQLite WAL mode and a busy timeout are enabled. Existing `data/tasks.json` and `data/journal.jsonl` files are imported once if present; source files are not deleted.

The EBS volume is not encrypted. Do not store secrets or sensitive personal data in task descriptions. Review EBS encryption and backups with the AWS account owner before using the database for important data. Keep a tested backup; an EBS snapshot is a separate AWS resource and may incur charges.

## Service security

The MCP HTTP service binds only to `127.0.0.1:8000`. A random bearer token is stored in `/etc/neoos/neoos.env`, readable only by root and the service group. No security-group port was opened. Remote access requires a separately configured HTTPS reverse proxy or SSM port forwarding; do not expose port 8000 directly to the internet.

## Deployment layout

- Application: `/opt/Neoos-2`
- Service user: `neoos`
- Database: `/var/lib/neoos/neoos.sqlite3`
- Environment file: `/etc/neoos/neoos.env`
- systemd unit: `/etc/systemd/system/neoos-mcp.service`

The service worker is report-only and never runs queued tasks as shell commands. The existing `vps_server.py` is a separate authenticated, read-only Docker status API.

## Manual checks

```sh
sudo systemctl status neoos-mcp --no-pager
sudo journalctl -u neoos-mcp -n 80 --no-pager
sudo -u neoos env NEOOS_DB_PATH=/var/lib/neoos/neoos.sqlite3 /opt/Neoos-2/.venv/bin/python -m unittest discover -s /opt/Neoos-2/tests -v
```
