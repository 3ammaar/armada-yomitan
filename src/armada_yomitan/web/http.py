"""The web interface's HTTP handler."""

import http.server
import json
import queue
import re
import secrets
import threading
import urllib.parse

from armada_yomitan.anki.discovery import list_dir
from armada_yomitan.anki.install import anki_up_to_date
from armada_yomitan.assets import PAGE_HTML, render_texts
from armada_yomitan.yomitan.patch import KBD_PAGE_SCRIPT, YOMITAN_ID


def make_handler(ui):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, body=b"", ctype="text/plain"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _authorised(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            given = self.headers.get("X-Token") or query.get("t", [""])[0]
            return secrets.compare_digest(given, ui.token)

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if not self._authorised():
                return self._send(403, b"forbidden")
            if path == "/":
                page = render_texts(PAGE_HTML).replace("__EXT__", f"chrome-extension://{YOMITAN_ID}").replace("<!--ARMADA_YOMITAN_KBD-->", KBD_PAGE_SCRIPT)
                self._send(200, page.encode(), "text/html; charset=utf-8")
            elif path == "/events":
                self._events()
            elif path == "/fs":
                where = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("path", [""])[0]
                self._send(200, json.dumps(list_dir(where), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif path == "/anki_update_check":
                self._send(200, json.dumps({"up_to_date": anki_up_to_date()}).encode(), "application/json; charset=utf-8")
            elif re.fullmatch(r"/crop/\d+\.(png|jpg)", path):
                with ui._lock:
                    item = ui.crops.get(int(path[6:].split(".")[0]))
                self._send(200, item[0], item[1]) if item else self._send(404, b"gone")
            else:
                self._send(404, b"not found")

        def do_POST(self):
            if not self._authorised():
                return self._send(403, b"forbidden")
            url = urllib.parse.urlparse(self.path)
            action = {"/scan": ui.cmd_scan, "/stop": ui.cmd_stop, "/quit": ui.cmd_quit,
                      "/reinstall": ui.cmd_reinstall}.get(url.path)
            if url.path == "/zoom":
                try:
                    delta = max(-0.5, min(0.5, float(urllib.parse.parse_qs(url.query).get("d", ["0"])[0])))
                except ValueError:
                    return self._send(400, b"bad request")
                action = lambda: ui.cmd_zoom(delta)
            if url.path == "/draw":
                on = urllib.parse.parse_qs(url.query).get("on", ["0"])[0] == "1"
                action = lambda: ui.cmd_draw(on)
            if url.path == "/areas_clear":
                action = ui.cmd_areas_clear
            if url.path == "/draw_refresh":
                action = ui.cmd_draw_refresh
            if url.path == "/anki":
                action = ui.cmd_anki
            if url.path == "/anki_detect":
                action = ui.cmd_anki_detect
            if url.path == "/anki_install":
                action = ui.cmd_anki_install
            if url.path == "/anki_reinstall":
                action = ui.cmd_anki_reinstall
            if url.path == "/anki_cancel":
                action = ui.cmd_anki_cancel
            if url.path in ("/anki_use", "/anki_pick"):
                arg = urllib.parse.parse_qs(url.query).get("i" if url.path == "/anki_use" else "path", [""])[0]
                action = (lambda: ui.cmd_anki_use(arg)) if url.path == "/anki_use" else (lambda: ui.cmd_anki_pick(arg))
            if url.path == "/nodes":
                action = ui.cmd_nodes
            if url.path == "/node":
                nid = urllib.parse.parse_qs(url.query).get("id", [""])[0]
                action = lambda: ui.cmd_node(nid)
            if url.path == "/node_manual":
                nid = urllib.parse.parse_qs(url.query).get("id", [""])[0]
                action = lambda: ui.cmd_node_manual(nid)
            if url.path == "/sysdeps_check":
                action = lambda: ui.cmd_sysdeps_check(True)
            if url.path == "/sysdeps_install":
                action = ui.cmd_sysdeps_install
            if url.path == "/sysdeps_reboot":
                action = ui.cmd_sysdeps_reboot
            if url.path == "/kbdlog":
                note = urllib.parse.parse_qs(url.query).get("m", [""])[0]
                action = lambda: ui.cmd_kbdlog(note)
            if url.path == "/pref":
                query = urllib.parse.parse_qs(url.query)
                key, value = query.get("k", [""])[0], query.get("v", [""])[0]
                action = lambda: ui.cmd_pref(key, value)
            if action is None:
                return self._send(404, b"not found")
            threading.Thread(target=action, daemon=True).start()
            self._send(204)

        def _events(self):
            q = queue.Queue()
            with ui._lock:
                ui.clients.append(q)
            q.put({"type": "status", "text": ui.last_status})
            q.put({"type": "draw", "on": ui.drawing})
            q.put(ui._prefs_msg())
            q.put(ui.last_state)
            if ui.sysdeps["checked"]:
                q.put(ui._sysdeps_msg())
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while not ui.done.is_set():
                    try:
                        data = "data: " + json.dumps(q.get(timeout=15), ensure_ascii=False) + "\n\n"
                    except queue.Empty:
                        data = ": keep-alive\n\n"
                    self.wfile.write(data.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with ui._lock:
                    if q in ui.clients:
                        ui.clients.remove(q)

    return Handler
