# NeoOS VPS backends

Two small Python services sit under the NeoOS console. Both talk to Docker on
the device with a fixed argument list (never a shell) and both are reached from
the browser only through `api/instances.js`.

| Service | What it does | Port |
| --- | --- | --- |
| `vps_server.py` | authenticated, read-only Docker status | `8080` |
| `podroid_vps_server.py` | guest container panel: list, create, start, stop, reboot, delete, exec | `8080` |

Run one of them at a time: they both default to port `8080`.

## Guest container panel (`podroid_vps_server.py`)

```sh
export NEOOS_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 podroid_vps_server.py
```

`GET /health` is open; every other route wants `Authorization: Bearer <token>`
when `NEOOS_API_TOKEN` is set. Leave the variable unset only on a private
network.

### Endpoints

| Method & path | Meaning |
| --- | --- |
| `GET /health` | `{"status": "ok", "provider": "podroid"}` |
| `GET /api/instances` | every container plus live CPU/RAM, published ports, TTL and `capacity` |
| `POST /api/instances` | `{"name", "os", "instance_type", "volume_gb"}` → `202` with the new instance |
| `POST /api/instances/{id}/start` \| `stop` \| `reboot` | lifecycle, `202` |
| `POST /api/instances/{id}/exec` | `{"cmd": "..."}` → `{"exit_code", "stdout", "stderr"}` |
| `DELETE /api/instances/{id}` | `202`, or `403` for a protected container |

`{id}` is a container name or a unique id prefix.

### What a guest gets

- `alpine` → `alpine:latest`, `ubuntu` → `ubuntu:24.04`, `debian` → `debian:bookworm-slim`
- `--cap-drop=ALL --security-opt=no-new-privileges`, `--memory=256m`,
  `--cpus=0.5`, `--pids-limit=64`
- one free host port from `8101`–`8199`, published as `-p <port>:80`
  (a service listening on port 80 inside the container is reachable at once)
- labels `neoos.managed=guest` and `neoos.expires_at=<epoch>`; `TTL` is 30
  minutes by default and a janitor thread removes expired guests every minute

### Guardrails

- `MAX_CONTAINERS` (default `4`) caps simultaneous guests. The next request gets
  `429 {"error": "capacity_full"}`. `GET /api/instances` reports
  `capacity: {"used", "max"}` and the console shows it as `사용 중 N / 4 슬롯`.
- Protected containers are never stopped, deleted or expired: `PROTECTED_CONTAINERS`
  (default `box`), anything named `user-vps-*` (`PROTECTED_PREFIXES`), and every
  container without the `neoos.managed=guest` label — including anything that
  already ran on the device before this service existed.
- Names must match `^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,30}$` and ids
  `^[a-zA-Z0-9_.-]{2,64}$`, so a request can never smuggle a Docker flag.
- `exec` runs `docker exec <container> sh -c <cmd>` with a 10 s timeout and an
  8192-character output cap. The container mounts nothing from the device, so a
  command's reach stops at the container. **Anyone holding the API token has a
  shell in every container**, so do not point a public console at it without
  real per-user authentication in front.

### Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` / `HOST` | `8080` / `0.0.0.0` | listen address |
| `NEOOS_API_TOKEN` | empty (open) | bearer token |
| `MAX_CONTAINERS` | `4` | guest slots |
| `NEOOS_TTL_SECONDS` | `1800` | guest lifetime |
| `NEOOS_REAPER_INTERVAL` | `60` | janitor period |
| `PROTECTED_CONTAINERS` | `box` | never stopped/deleted |
| `PROTECTED_PREFIXES` | `user-vps-` | never stopped/deleted |
| `NEOOS_ALLOWED_ORIGINS` | empty | extra browser origins (comma separated) |
| `NEOOS_NODE_NAME` | `Podroid` | shown as the instance region |

CORS answers only `https://neoos-2.vercel.app`, localhost/127.0.0.1 previews and
the extra origins above. `OPTIONS` answers `204`.

## Read-only status API (`vps_server.py`)

`GET /api/status` lists running Docker container names. It never creates,
stops or deletes anything.

```sh
export NEOOS_VPS_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export NEOOS_ALLOWED_ORIGINS="https://gw140427-rgb.github.io"
python3 vps_server.py
```

## Security notes

- Do not expose either port directly to the public internet or configure router
  port forwarding. Put an HTTPS reverse proxy with authentication in front, or
  use the Vercel gateway (`NEOOS_BACKEND_URL` + `NEOOS_API_TOKEN`).
- Keep the token private and rotate it if it ever appeared in a screenshot, a
  log or a commit.
- The old public `ntfy.sh` command worker stays disabled: anyone who knew its
  public topic could send container-create requests.

## Validation

```sh
python3 -m unittest discover -s tests -v
python -m py_compile vps_server.py podroid_vps_server.py neoos_vps_worker.py
```
