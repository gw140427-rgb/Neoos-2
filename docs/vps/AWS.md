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
- `NEOOS_VPS_API_TOKEN`: random secret, at least 32 characters
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

All management endpoints require `Authorization: Bearer <token>`. Instance type and EBS size are allow-listed/bounded. The backend must be placed behind HTTPS; do not expose its HTTP port directly to the public internet.

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
