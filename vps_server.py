#!/usr/bin/env python3
"""Neoos Cloud VPS Controller for Galaxy A16 Node (Podroid Docker backend)."""
import http.server
import subprocess
import json

class VPSHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        res = subprocess.getoutput('docker ps --format "{{.Names}}"')
        vps_list = [x for x in res.split('\n') if x]
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'node': 'Galaxy A16', 'running_vps': len(vps_list), 'list': vps_list}).encode())

    def do_POST(self):
        res = subprocess.getoutput('docker ps --format "{{.Names}}"')
        vps_list = [x for x in res.split('\n') if x]
        if len(vps_list) >= 10:
            self.send_response(429)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Node capacity full (10/10)', 'running_vps': len(vps_list)}).encode())
            return
        cnt = subprocess.getoutput('docker run -d -m 64m alpine sleep 3600')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'created', 'container_id': cnt[:12], 'tier': 'Trial'}).encode())

if __name__ == '__main__':
    print("Starting Neoos VPS Server on 0.0.0.0:8080...")
    http.server.HTTPServer(('0.0.0.0', 8080), VPSHandler).serve_forever()
