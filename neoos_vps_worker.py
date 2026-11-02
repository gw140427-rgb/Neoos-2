#!/usr/bin/env python3
"""Deprecated NeoOS worker: the unauthenticated public ntfy command queue is disabled."""


def main() -> int:
    print("NeoOS VPS worker is disabled.")
    print("The former public ntfy task topic accepted untrusted container-create messages.")
    print("No network requests or Docker commands were made.")
    print("Use vps_server.py for authenticated, read-only Podroid status instead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
