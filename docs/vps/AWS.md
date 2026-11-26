# NeoOS AWS EC2 VPS backend

This is an opt-in AWS backend alongside the existing Podroid read-only dashboard. It does not launch, stop, or terminate any AWS resources until you deploy it and send an authenticated request.

## Architecture

- Static dashboard: GitHub Pages / Vercel
- API: `aws_vps_server.py` (Python HTTP API)
- Compute provider: Amazon EC2 in `ap-northeast-2` by default
- Guest OS: Debian AMI supplied by the operator
- Credentials: use an attached IAM role. Never put AWS access keys in the browser, Git repository, or frontend environment variables.

## Required configuration

Set these environment variables on the API host:

- `AWS_REGION=ap-northeast-2`
- `NEOOS_VPS_API_TOKEN`: random secret, at least 32 characters (management endpoints answer `503 server_token_not_configured` until it is set)
- `NEOOS_ALLOWED_ORIGINS`: exact HTTPS origin of the dashboard
- `NEOOS_EC2_AMI_ID`: verified Debian AMI ID in the selected region
- `NEOOS_EC2_SUBNET_ID`: subnet in the selected VPC
- `NEOOS_EC2_SECURITY_GROUP_ID`: pre-created security group
- `NEOOS_EC2_KEY_NAME`: existing EC2 key pair name
- Optional: `NEOOS_EC2_INSTANCE_PROFILE`, `NEOOS_ALLOWED_INSTANCE_TYPES` (default `t3.micro`), `NEOOS_MAX_VOLUME_GB` (default 20)

The API deliberately does not create security groups or open SSH to the internet. Configure the security group separately and restrict SSH to a trusted source address or use Systems Manager Session Manager. Confirm the Debian AMI architecture matches the selected instance type.

## IAM permissions

Attach a narrowly scoped IAM role to the API host. It needs EC2 read access for instance discovery and permission to run, start, stop, reboot, and terminate only the intended NeoOS instances. Add `iam:PassRole` only if using `NEOOS_EC2_INSTANCE_PROFILE`, and scope it to that exact role. Do not use long-lived IAM user access keys.

## API

- `GET /health`: unauthenticated health check
- `GET /api/instances`: list only instances tagged `Project=NeoOS` and `ManagedBy=NeoOS`
- `POST /api/instances`: create one Debian EC2 instance
- `POST /api/instances/{instance-id}/start|stop|reboot`: lifecycle action
- `DELETE /api/instances/{instance-id}`: terminate a managed instance

All management endpoints require `Authorization: Bearer <token>`, including `GET /api/instances`; only `/health` is open. Instance type and EBS size are allow-listed/bounded. The backend must be placed behind HTTPS; do not expose its HTTP port directly to the public internet. `GET /api/instances` returns the public address only — the private VPC address is not exposed.

## Vercel / browser proxy

The dashboard never calls the backend directly. `api/instances.js` (and its `docs/api/instances.js` copy) is the only bridge, and it fails closed:

- `NEOOS_BACKEND_URL` (required): backend base URL, no trailing slash. Without it the proxy answers `503 backend_not_configured`.
- `NEOOS_API_TOKEN` (optional): sent to the backend as `Authorization: Bearer <token>`. Leave it empty only if the backend does not require a token.

The proxy allows exactly this surface and answers `404` for any other path and `405` for a method that path does not accept:

| Method & path | Forwarded as |
| --- | --- |
| `GET /api/instances` | status list |
| `POST /api/instances` | create |
| `POST /api/instances/{id}/start` \| `stop` \| `reboot` | lifecycle |
| `POST /api/instances/{id}/exec` | one-shot web terminal (`{"cmd": "..."}`) |
| `DELETE /api/instances/{id}` | delete |

Ids are limited to `[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}`, so a URL can never carry a
Docker flag. Which of these the backend actually honours is the backend's
decision: the AWS backend above still refuses every mutation with `405`,
while `podroid_vps_server.py` performs them inside the guest-container
guardrails described in `docs/vps/README.md`.

Keep the proxy's token equal to the backend's `NEOOS_VPS_API_TOKEN`, otherwise the proxy forwards no usable credential and the console falls back to its cached list.

## Rotating credentials that were already published

This repository no longer contains a default API token or a shared SSH password, but removing them from source revokes nothing by itself:

- Rotate every `NEOOS_VPS_API_TOKEN` value used before this change, then restart the backend; an already-running process keeps answering with the old token until it is restarted.
- The old token, the old shared SSH password and the old public address may still live in Git history and on the running instance. Review SSH password authentication on existing instances and use the key pair or Session Manager instead.
- `NEOOS_PROTECTED_INSTANCE_IDS` still ships a default control-plane instance id so the console cannot terminate it by mistake; override it for another deployment.

## Install and run

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export AWS_REGION=ap-northeast-2
export NEOOS_VPS_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export NEOOS_ALLOWED_ORIGINS="https://gw140427-rgb.github.io"
# Set the AMI, subnet, security-group and key-pair variables above.
python aws_vps_server.py
```

The current commit adds the backend only. It does not create AWS resources, incur EC2 charges, or change the existing Podroid dashboard. Before enabling instance creation, review AWS pricing and billing alerts with the account owner.
