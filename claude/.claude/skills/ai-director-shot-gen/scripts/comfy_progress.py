"""Live progress of the remote ComfyUI queue, read from the server's own events (no guessing).

  python comfy_progress.py            # live, Ctrl+C to quit
  python comfy_progress.py --once     # wait for the next real progress event (max ~20 s) and print one snapshot

Jobs are queued without a client_id, so ComfyUI broadcasts every event to all websocket clients. This listens on
ws://<server>/ws (stdlib only) and shows: the running job, which node is executing (class name), that node's own
step counter (value/max from the sampler or any node using ComfyUI's ProgressBar), how many of the graph's nodes
have finished, and the queue. Times are measured, not estimated: elapsed since the job started and, for the
current node, a rate-based ETA from its own step counter.
"""
import argparse
import base64
import json
import os
import socket
import struct
import sys
import time
from urllib.parse import urlparse

import requests

BAR = 28


def bar(frac):
    frac = max(0.0, min(1.0, frac))
    n = int(round(frac * BAR))
    return "█" * n + "░" * (BAR - n)


def mmss(sec):
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class WS:
    """Minimal RFC 6455 client: text frames in, nothing out except pong/close."""

    def __init__(self, url):
        u = urlparse(url)
        self.s = socket.create_connection((u.hostname, u.port or 80), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {u.path}?{u.query} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.s.recv(1024)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError(head[:200])
        self.buf = head.split(b"\r\n\r\n", 1)[1]

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        while True:
            b1, b2 = self._read(2)
            op, ln = b1 & 0x0F, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(ln)
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if op == 1:
                return data.decode("utf-8", "replace")
            if op == 9:  # ping -> pong (client frames must be masked)
                m = os.urandom(4)
                self.s.sendall(bytes([0x8A, 0x80 | len(data)]) + m + bytes(c ^ m[i % 4] for i, c in enumerate(data)))
            if op == 8:
                raise ConnectionError("closed")
            # op 2 = binary (preview images): ignored


def job_name(graph):
    for n in graph.values():
        if n.get("class_type") == "SaveImage":
            return n["inputs"].get("filename_prefix", "?").split("/")[-1]
    return "?"


class State:
    def __init__(self, srv):
        self.srv = srv
        self.pid = None; self.graph = {}; self.name = "-"; self.t0 = None
        self.node = None; self.done = set(); self.val = 0; self.max = 0; self.step_t = []
        self.pending = []
        self.joined = False   # True when we attached to a job already running (start time unknown)
        self.log = ""; self.log_t = 0
        self.refresh_queue(first=True)

    def server_log(self):
        """Last progress line of the server log (for long nodes that send no step events, e.g. SeedVR2)."""
        if time.time() - self.log_t < 5:
            return self.log
        self.log_t = time.time()
        try:
            import subprocess
            cmd = (r"$f=(Get-ChildItem C:\ai\ComfyUI_windows_portable\ComfyUI\user\*.log | Sort LastWriteTime | "
                   r"Select -Last 1).FullName; Get-Content $f -Tail 40")
            out = subprocess.run(["ssh", "-o", "ConnectTimeout=5", "gpu-host", cmd], capture_output=True,
                                 timeout=15).stdout.decode("utf-8", "replace").splitlines()
            keys = ("Phase", "batch", "Batch", "step", "%|")
            hits = [l.split("] ", 2)[-1].strip() for l in out if any(k in l for k in keys)]
            self.log = hits[-1][:90] if hits else ""
        except Exception:
            pass
        return self.log

    def refresh_queue(self, first=False):
        q = requests.get(f"{self.srv}/queue", timeout=10).json()
        self.pending = [job_name(p[2]) for p in sorted(q["queue_pending"], key=lambda x: x[0])]
        if q["queue_running"]:
            r = q["queue_running"][0]
            if r[1] != self.pid:
                self.start(r[1], r[2]); self.joined = first
        elif self.pid and not q["queue_running"]:
            self.pid = None

    def start(self, pid, graph):
        self.pid, self.graph, self.name = pid, graph, job_name(graph)
        self.t0 = time.time(); self.node = None; self.done = set(); self.val = self.max = 0; self.step_t = []

    def on(self, msg):
        t, d = msg.get("type"), msg.get("data", {})
        if t == "status":
            self.refresh_queue()
        elif t == "execution_start":
            self.refresh_queue()
            if d.get("prompt_id") != self.pid:
                self.pid = d.get("prompt_id"); self.t0 = time.time(); self.done = set()
        elif t == "execution_cached":
            self.done.update(d.get("nodes", []))
        elif t == "executing":
            if self.node:
                self.done.add(self.node)
            self.node = d.get("node"); self.val = self.max = 0; self.step_t = []
            if self.node is None:  # job finished
                self.refresh_queue()
        elif t == "progress":
            self.node = d.get("node", self.node)
            self.val, self.max = d.get("value", 0), d.get("max", 0)
            self.step_t.append(time.time())

    def lines(self):
        if not self.pid:
            return ["[실행 중인 작업 없음]", "", "다음: " + (", ".join(self.pending) or "없음")]
        cls = self.graph.get(self.node or "", {}).get("class_type", "확인 중" if self.joined else "준비 중")
        total = len(self.graph) or 1
        el = time.time() - (self.t0 or time.time())
        since = "관측 후 " if self.joined else ""
        node_line = f"  노드 {cls}"
        if self.max:
            eta = ""
            if len(self.step_t) >= 2 and self.val:
                rate = (self.step_t[-1] - self.step_t[0]) / max(len(self.step_t) - 1, 1)
                eta = f"  이 노드 남은 ~{mmss(rate * (self.max - self.val))}"
            node_line += f"  {bar(self.val / self.max)} {self.val}/{self.max}{eta}"
        else:
            lg = self.server_log()
            node_line += f"  서버 로그: {lg}" if lg else "  (이 노드는 단계 정보를 보내지 않음)"
        return [f"[{self.name}]  그래프 {len(self.done)}/{total} 노드 완료  {bar(len(self.done) / total)}  경과 {since}{mmss(el)}",
                node_line,
                "다음: " + (", ".join(self.pending) or "없음")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    srv = a.server.rstrip("/")
    if sys.platform == "win32":
        os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    printed = 0
    while True:
        try:
            st = State(srv)
            ws = WS(srv.replace("http", "ws", 1) + "/ws?clientId=progress-" + os.urandom(4).hex())
            ws.s.settimeout(20 if a.once else 2)
            last = 0
            while True:
                try:
                    st.on(json.loads(ws.recv()))
                    got = True
                except socket.timeout:
                    got = False
                if a.once and (got and st.max or not got):
                    print("\n".join(st.lines()))
                    return
                if time.time() - last > 1:
                    lines = st.lines()
                    if printed:
                        sys.stdout.write(f"\x1b[{printed}F")
                    for ln in lines:
                        sys.stdout.write("\x1b[2K" + ln + "\n")
                    sys.stdout.flush(); printed = len(lines); last = time.time()
        except KeyboardInterrupt:
            return
        except Exception as e:
            if a.once:
                print(f"[서버 응답 없음: {type(e).__name__}: {e}]")
                return
            time.sleep(3)


if __name__ == "__main__":
    main()
