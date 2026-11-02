# NeoOS VPS status dashboard

The VPS dashboard currently provides **authenticated, read-only status** for Docker in Podroid. It does not create/delete containers or execute terminal commands.

## Start the API in Podroid

From the repository root, in the Podroid terminal:

```sh
export NEOOS_VPS_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export NEOOS_ALLOWED_ORIGINS="https://gw140427-rgb.github.io"
export NEOOS_NODE_NAME="Galaxy A16"
python3 vps_server.py
```

Use the exact HTTPS origin serving the dashboard in `NEOOS_ALLOWED_ORIGINS` (scheme + hostname only; no path). For a different host, replace the example origin. Keep the token private. Paste the same token into the dashboard; the page stores it only in the current browser tab session.

The API listens on port `8080` by default. `GET /api/status` requires `Authorization: Bearer <token>`. `/health` returns only a minimal service check. Browser origins must match the allowlist exactly. Docker is queried with a fixed argument list; user-supplied shell commands are never executed.

## Security notes

- Do not expose port `8080` directly to the public internet or configure router port forwarding for it.
- Use a trusted private network. For remote access, use a properly authenticated VPN or HTTPS reverse proxy.
- The old public `ntfy.sh` command worker has been disabled because anyone who knew its public topic could send container-create requests.
- The dashboard does not claim a server is online until it receives a valid authenticated response.

## Validation

```sh
python3 -m unittest discover -s tests -v
python -m py_compile vps_server.py neoos_vps_worker.py
```
