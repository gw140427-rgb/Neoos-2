#!/usr/bin/env python3
"""Neoos Cloud VPS Queue Worker for Galaxy A16 Node.
Runs inside Podroid Alpine Linux. Connects to task queue without tunnels or static domains.
"""
import time
import subprocess
import json
import urllib.request
import urllib.error

TASK_TOPIC = "https://ntfy.sh/neoos-gw140427-vps-tasks"
STATUS_TOPIC = "https://ntfy.sh/neoos-gw140427-vps-status"

last_seen_time = int(time.time())

def send_status():
    res = subprocess.getoutput('docker ps --format "{{.Names}}"')
    vps_list = [x for x in res.split('\n') if x]
    payload = json.dumps({
        'node': 'Galaxy A16 (Real Podroid Docker)',
        'running_vps': len(vps_list),
        'list': vps_list,
        'time': int(time.time())
    }).encode('utf-8')
    try:
        req = urllib.request.Request(STATUS_TOPIC, data=payload, method='POST')
        with urllib.request.urlopen(req, timeout=5) as r:
            pass
    except Exception as e:
        print("[Status Sync Error]", e)

def process_tasks():
    global last_seen_time
    url = f"{TASK_TOPIC}/json?poll=1&since={last_seen_time}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode('utf-8')
            for line in raw.strip().split('\n'):
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get('event') == 'message':
                        last_seen_time = max(last_seen_time, ev.get('time', last_seen_time) + 1)
                        msg = ev.get('message', '')
                        print(f"[*] Received task: {msg}")
                        if 'create' in msg:
                            # Check 10-node limit
                            res = subprocess.getoutput('docker ps --format "{{.Names}}"')
                            vps_list = [x for x in res.split('\n') if x]
                            if len(vps_list) >= 10:
                                print("[!] Max capacity (10/10) reached!")
                                send_status()
                                continue
                            print("[*] Spawning real Docker container on Galaxy A16...")
                            out = subprocess.getoutput('docker run -d -m 64m alpine sleep 3600')
                            cid = out.strip()[:12]
                            print(f"[+] Real Docker Container Created: {cid}")
                            send_status()
                except Exception as ex:
                    print("[Task parse error]", ex)
    except Exception as e:
        pass

if __name__ == '__main__':
    print("==================================================")
    print("  Neoos VPS Queue Worker: Galaxy A16 Node Online  ")
    print("  No tunnels, no ngrok, no changing IP addresses!  ")
    print("==================================================")
    send_status()
    while True:
        process_tasks()
        time.sleep(1.5)
