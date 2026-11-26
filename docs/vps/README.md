# NeoOS Podroid Docker backend

NeoOS Cloud is configured for the Docker Engine running inside Podroid. It creates
short-lived Linux **containers** on that phone; it does not create full virtual
machines, assign public IP addresses, or reserve a fixed-size virtual disk.

## 1. Podroid service

Run the API in the same Podroid environment that can execute docker ps.
The service listens on loopback port 8080 by default and refuses to start unless
NEOOS_API_TOKEN is set to a random secret at least 32 characters long.

```sh
export NEOOS_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export HOST=127.0.0.1
export PORT=8080
export NEOOS_NODE_NAME=Podroid
python3 podroid_vps_server.py
```

Keep the token private. Do not put it in a public HTML file, GitHub commit,
screenshot, or chat message. The API has a public, minimal GET /health
endpoint; all container data and every mutating endpoint require the bearer
token. An unset or short token makes protected routes fail closed with HTTP 503.

## 2. Console connection

There are two supported connection paths.

### Recommended: Vercel gateway

Configure these server-side Vercel project environment variables:

| Variable | Purpose |
| --- | --- |
| NEOOS_BACKEND_URL | HTTPS URL that securely tunnels/proxies to the Podroid API |
| NEOOS_API_TOKEN | The same backend bearer token configured in Podroid |
| NEOOS_CONSOLE_TOKEN | A separate random owner-console token, at least 32 characters |

The Cloud page sends X-NeoOS-Console-Token to the Vercel function. The function
checks that owner token, then adds the private Podroid bearer token before
forwarding the request. The browser never receives NEOOS_API_TOKEN.

NEOOS_BACKEND_URL must be reachable from Vercel over HTTPS. A private Podroid
address such as 10.x.x.x or 127.0.0.1 is not reachable from Vercel. Use a
proper authenticated HTTPS tunnel/reverse proxy; do not open the Podroid API
port directly to the public internet.

In the Cloud page, open the hidden developer settings, leave the custom API URL
empty, enter the NEOOS_CONSOLE_TOKEN, and save. This browser token is stored
only in the current tab's session storage.

### Direct HTTPS endpoint

Alternatively, enter the full HTTPS base URL of an authenticated reverse proxy
in the Cloud page and enter the Podroid NEOOS_API_TOKEN. The proxy must
forward the /api/instances paths to Podroid and allow the
https://neoos-2.vercel.app browser origin. Set
NEOOS_ALLOWED_ORIGINS to the exact origin if you use a different domain.

The direct path is not suitable for a plain HTTP public endpoint. Keep it behind
HTTPS and authentication.

## 3. Real Docker features

| Feature | API |
| --- | --- |
| List containers and live CPU/RAM | GET /api/instances |
| Create a guest | POST /api/instances with {"name":"worker-01","os":"alpine"} |
| Start / stop / restart | POST /api/instances/{id}/start, stop, reboot |
| Pause / resume | POST /api/instances/{id}/pause, unpause |
| Run a command | POST /api/instances/{id}/exec with {"cmd":"uname -a"} |
| Recent container logs | GET /api/instances/{id}/logs (last 100 lines) |
| Delete guest | DELETE /api/instances/{id} |

Supported templates:

- alpine — alpine:latest
- ubuntu — ubuntu:24.04
- debian — debian:bookworm-slim
- busybox — busybox:1.36
- node — node:22-alpine
- python — python:3.13-alpine
- nginx — nginx:alpine, started as a real Nginx foreground web server

Guests are capped by default at 256 MB RAM, 0.5 CPU and 64 PIDs. Docker
capabilities are dropped and no-new-privileges is enabled. Each guest receives
one host port from 8101–8199, bound to **127.0.0.1 only**; it is not a public
internet port. The Nginx template listens on container port 80.

The writable container layer survives stop/start and pause/resume, but it is
removed with the container. This version does not offer a fixed-size persistent
volume quota. The default TTL is 30 minutes and the reaper checks every 60
seconds. MAX_CONTAINERS defaults to 4 and can be changed in the Podroid
environment after checking phone resources.

## 4. Safety rules

- Only containers with the neoos.managed=guest label can be started, stopped,
  restarted, paused, resumed, sent commands, logged, or deleted.
- System/unmanaged containers, the box control-plane container, and names
  using the user-vps- protected prefix are denied by the backend itself.
- The browser's developer switch is only a user-interface gate. The real
  security boundary is the server-side owner token and the backend token.
- This is a **single-owner control panel**, not a public multi-user VPS service.
  It does not yet have user registration, per-user container ownership, or
  per-account quotas. Do not share the owner token or publish the terminal to
  strangers.
- Docker containers share the phone's host kernel. Dropped capabilities and
  resource limits are useful guardrails, not a guarantee equivalent to a
  hardware-isolated VM.
- Do not enable router port forwarding for ports 8080 or 8101–8199.

## 5. Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| NEOOS_API_TOKEN | required | Backend bearer secret (minimum 32 characters) |
| HOST | 127.0.0.1 | API listen address |
| PORT | 8080 | API listen port |
| NEOOS_NODE_NAME | Podroid | Node label shown in console |
| MAX_CONTAINERS | 4 | Maximum guest containers |
| NEOOS_TTL_SECONDS | 1800 | Guest lifetime |
| NEOOS_REAPER_INTERVAL | 60 | Expiry sweep interval |
| PROTECTED_CONTAINERS | box | Protected exact container names |
| PROTECTED_PREFIXES | user-vps- | Protected name prefixes |
| NEOOS_ALLOWED_ORIGINS | empty | Additional exact browser origins |

## 6. Validation

Run the repository tests and Python compile checks before restarting the service:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile podroid_vps_server.py vps_server.py neoos_vps_worker.py
```

The API code and Cloud page must be deployed together. Updating GitHub source
does not update an already running Podroid process; restart the Podroid API
only after reviewing the changes and preserving its existing environment.
